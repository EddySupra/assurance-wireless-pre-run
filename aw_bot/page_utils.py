"""Page handling shared by every step: settling a fresh page, clearing
interstitials, and verifying we are where we expect to be.

Every step calls `settle()` right after it navigates, so all of them get the
same bot-wall, DevTools, and consent-banner handling.
"""

import random
import time
from urllib.parse import urlparse

from selenium.webdriver.common.action_chains import ActionChains

from . import environment, real_input, turnstile
from .config import ALLOWED_HOST_SUFFIXES, RunConfig
from .classify import AW_TRANSFER, BAD_EMAIL
from .errors import (
    BotBlockedError,
    LeadRejectedError,
    PageMismatchError,
    RealInputError,
    ThrottledError,
)
from .human import human_click, idle_drift, pause, rest, smooth_scroll, warm_up
from .logs import LOG

# Phrases that mean a WAF/bot-detection layer answered instead of the site.
BLOCK_SIGNALS = (
    "access denied",
    "pardon our interruption",
    "request unsuccessful",
    "you have been blocked",
    "unusual traffic",
    "incapsula",
    "reference #",
    "attention required",
)

# The application form itself lives in this cross-origin iframe.
ENROLLMENT_FRAME = "#enrollment-frame"

# Iframe sources that mean a bot-check interstitial is in the way.
CHALLENGE_IFRAME_HINTS = (
    "challenges.cloudflare.com",
    "turnstile",
)

# Wording and markers on a Cloudflare interstitial served as the page itself,
# where there is no third-party iframe to spot it by. The challenge page's own
# title is "Checking your Browser...", which matches none of the block signals
# above -- it was found by hand, on screen, while the code saw nothing.
CHALLENGE_TEXT_SIGNALS = (
    "checking your browser",
    "verify you are human",
    "just a moment",
    "needs to review the security of your connection",
)

# Markers in the page source of a Cloudflare challenge document.
CHALLENGE_SOURCE_SIGNALS = (
    # Cloudflare's interstitial bootstrap object. This one is specific to a
    # challenge *page* -- the document Cloudflare serves instead of the site.
    "_cf_chl_opt",
)

# Deliberately NOT a challenge signal: "/cdn-cgi/challenge-platform".
#
# That path is how an ordinary embedded Turnstile widget loads, so it is in
# the source of every enrollment screen once the widget renders, challenge or
# no challenge. Matching on it made challenge_present() true for the whole
# wizard, which made frame_interruption() report "a bot-check challenge is in
# front of the form" on screens where nothing was in front of anything.
#
# That is the same mistake the visible-iframe check below already guards
# against, and it is worth naming because of what it cost: a step 9 that
# simply had not finished its eligibility lookup was reported as a Cloudflare
# bot wall, and the real cause went unexamined for a long time. A challenge
# that is actually challenging the user is visible, or it is a challenge page.

# Cloudflare says this when it has judged the *network*, not the browser:
# "Botnet activity detected. Automated attack traffic has been detected from
# your network." No fingerprint or input behaviour changes that verdict -- it
# is the exit IP's reputation, so the answer is different proxies.
NETWORK_REPUTATION_SIGNALS = (
    "botnet activity detected",
    "automated attack traffic",
    "unbotnet.me",
)


def network_reputation_block(sb) -> str:
    """Cloudflare's "your network is the problem" wording, if it is on screen."""
    try:
        body = body_text(sb).lower()
        source = (sb.get_page_source() or "").lower()
    except Exception:
        return ""
    for signal in NETWORK_REPUTATION_SIGNALS:
        if signal in body or signal in source:
            return signal
    return ""

# Consent/cookie banners overlay the page and swallow the next click, so clear
# one if it's there. Ordered most to least likely.
CONSENT_SELECTORS = (
    "#onetrust-accept-btn-handler",
    "#truste-consent-button",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "button#accept-cookies",
    'button[aria-label*="Accept" i]',
    'button[title*="Accept" i]',
)


def apply_flaresolverr_cookies(sb, cfg: RunConfig, url: str) -> bool:
    """Ask FlareSolverr for a Cloudflare clearance cookie and install it.

    Off unless --use-flaresolverr. Returns whether cookies were injected.

    Two limits worth knowing before relying on this, because neither is
    obvious from the flag's name:

      * FlareSolverr clears the "Checking your browser" *interstitial* and
        hands back `cf_clearance`. It does not produce a
        `cf-turnstile-response` token, which is what the embedded widget on
        the eligibility screen wants -- those are different mechanisms, and a
        clearance cookie does not satisfy a widget.
      * It solves in its own browser on this machine's connection, so the
        cookie is issued against a different IP than the GoLogin proxy the
        run goes out on. Cloudflare binds clearance to the client it issued
        it to, so a cookie earned on one address is not automatically good on
        another.

    It is still worth having for the interstitial case, and it is cheap to
    try. It is not a route past the Turnstile widget.
    """
    if not getattr(cfg, "use_flaresolverr", False):
        return False

    try:
        from .flaresolverr import inject_cookies_into_driver, solve_cloudflare_challenge
    except Exception as exc:
        LOG.warning("FlareSolverr requested but unavailable: %s", exc)
        return False

    try:
        domain = urlparse(url).hostname or ""
    except Exception:
        return False
    if not domain:
        return False

    try:
        cookies = solve_cloudflare_challenge(url)
    except Exception as exc:
        LOG.warning("FlareSolverr could not solve %s: %s", domain, exc)
        return False

    if not cookies:
        LOG.info("FlareSolverr returned no cookies for %s", domain)
        return False

    try:
        # Cookies can only be set for the origin currently loaded.
        inject_cookies_into_driver(sb.driver, cookies, domain)
    except Exception as exc:
        LOG.warning("Could not install FlareSolverr cookies for %s: %s", domain, exc)
        return False

    LOG.info(
        "Installed %d FlareSolverr cookie(s) for %s: %s",
        len(cookies), domain, ", ".join(sorted(cookies)),
    )
    return True


def settle(sb, cfg: RunConfig) -> None:
    """Wait for a freshly loaded page and clear anything covering it."""
    sb.wait_for_ready_state_complete(timeout=cfg.page_timeout)
    ensure_page_window(sb)
    handle_captcha(sb)
    check_not_blocked(sb)
    dismiss_consent(sb)

    # Give the page a few seconds of mouse movement before the step starts
    # filling it in. This runs per page rather than once per run because the
    # sensor scores each page load, and every screen in this wizard is one.
    # It is the largest single cost of --human-like (a few seconds a screen);
    # --fast skips it along with everything else here.
    warm_up(sb, cfg)


def ensure_page_window(sb) -> None:
    """UC mode intermittently leaves the driver attached to a DevTools window
    after the reconnect. Every later call would then read that window instead
    of the site, so point the driver back at the real page.
    """
    if not (sb.get_current_url() or "").startswith("devtools://"):
        return

    LOG.warning("Driver was attached to a DevTools window; switching back to the page")
    for index, handle in enumerate(sb.driver.window_handles):
        sb.driver.switch_to.window(handle)
        url = sb.get_current_url() or ""
        if not url.startswith("devtools://"):
            LOG.info("Switched to window %d (%s)", index, url)
            return

    raise PageMismatchError(
        "Only DevTools windows are open -- the browser launch did not load the site."
    )


def handle_captcha(sb) -> None:
    """Click through a Cloudflare/Turnstile interstitial, if there is one.

    Only runs when a challenge is actually on the page: uc_gui_click_captcha
    fires a real mouse click at a computed screen position, so calling it
    blindly can click whatever happens to be under that spot.
    """
    if not challenge_present(sb):
        LOG.debug("No challenge frame on page; skipping captcha handling")
        return

    # Nothing here can answer a challenge: uc_gui_click_captcha belongs to UC
    # mode, and the shim raises rather than pretending. Say what is on screen
    # and let the flow carry on -- a challenge that clears itself will, and one
    # that does not is caught where it actually blocks something.
    LOG.warning(
        "A bot-check challenge is on screen. Nothing here answers it "
        "automatically; use --solve-challenges with a visible window to clear "
        "it by hand, or run the profile on a proxy that is not being challenged."
    )
    try:
        sb.wait_for_ready_state_complete(timeout=30)
    except Exception:
        pass


def challenge_present(sb) -> bool:
    title = (sb.get_title() or "").lower()
    if any(signal in title for signal in CHALLENGE_TEXT_SIGNALS):
        return True

    try:
        body = body_text(sb).lower()[:3000]
        if any(signal in body for signal in CHALLENGE_TEXT_SIGNALS):
            return True
        source = (sb.get_page_source() or "")[:20000].lower()
        if any(signal in source for signal in CHALLENGE_SOURCE_SIGNALS):
            return True
    except Exception:
        pass

    try:
        srcs = sb.execute_script(
            "return Array.from(document.querySelectorAll('iframe'))"
            ".filter(f => f.offsetParent || f.getClientRects().length)"
            ".map(f => f.src || '')"
        ) or []
    except Exception:
        return False
    # Only a *visible* challenge frame counts. The enrollment form embeds
    # Turnstile on every screen, so presence alone is true the whole way
    # through the wizard -- treating that as an interruption made a refused
    # token report as "something is in front of the form" on a screen where
    # nothing was. The same reasoning keeps an invisible reCAPTCHA out of it.
    return any(hint in (src or "").lower() for src in srcs for hint in CHALLENGE_IFRAME_HINTS)


def check_not_blocked(sb) -> None:
    title = (sb.get_title() or "").lower()
    body = body_text(sb).lower()[:3000]

    reputation = network_reputation_block(sb)
    if reputation:
        raise BotBlockedError(
            f"Cloudflare is refusing this network, not this browser (matched "
            f"{reputation!r}): \"Botnet activity detected. Automated attack "
            f"traffic has been detected from your network.\" That is the exit "
            f"IP's reputation, so no fingerprint, pacing or input change will "
            f"clear it -- the profiles need proxies on a cleaner range."
        )

    hit = next((s for s in BLOCK_SIGNALS if s in title or s in body), None)
    if hit:
        raise BotBlockedError(
            f"Bot-protection page detected (matched {hit!r}). "
            f"Title: {sb.get_title()!r}. Try a longer reconnect_time, a fresh "
            f"browser profile, or a different network."
        )


def dismiss_consent(sb) -> None:
    for selector in CONSENT_SELECTORS:
        try:
            if sb.is_element_visible(selector):
                sb.click(selector, timeout=5)
                LOG.info("Dismissed consent banner via %s", selector)
                sb.sleep(0.5)
                return
        except Exception:
            continue
    LOG.debug("No consent banner found")


# Text the enrollment host returns when it has had enough of us.
THROTTLE_SIGNALS = (
    "can not be processed at this time",
    "cannot be processed at this time",
    "unable to process your request",
    "try again later",
)


def is_throttle_message(message: str) -> bool:
    lowered = (message or "").lower()
    return any(signal in lowered for signal in THROTTLE_SIGNALS)


# The app asking to be tried again, in as many words:
#
#   "A communication delay has occurred please click dismiss and then click
#    'Next' to re-try. If the delay persists you may see this message, repeat
#    the process."
#
# Not a verdict and not a refusal -- an instruction. Reading it as "the form
# rejected the data" threw away a lead the site had explicitly invited us to
# resubmit, which is the one kind of failure that costs nothing to get right.
RETRYABLE_SIGNALS = (
    "communication delay",
    "please click dismiss and then click",
    "to re-try",
)

# How many times to take the site up on it. Bounded because "repeat the
# process" is not an invitation to submit an application indefinitely.
MAX_RETRY_PROMPTS = 3


def is_retryable_message(message: str) -> bool:
    """Is the app asking us to dismiss this and try the same submit again?"""
    lowered = (message or "").lower()
    return any(signal in lowered for signal in RETRYABLE_SIGNALS)


# Modals the app uses as progress spinners rather than errors. Treating one
# of these as a rejection aborts a submission that was still in flight.
PROGRESS_MODAL_HINTS = (
    "please wait",
    "validating",
    "loading",
    "processing",
    "one moment",
)


# Modals that ask a question rather than report a failure. The wizard uses one
# to double-check the benefit applicant: "You have indicated that you wish to
# qualify through a child or dependent ... If this is correct press YES. If you
# are applying for yourself, press NO". Treating that as a rejection stopped
# the run at the exact moment it had got through the screen.
CONFIRM_MODAL_HINTS = ("please confirm",)


def is_confirm_modal(message: str) -> bool:
    return any(hint in (message or "").lower() for hint in CONFIRM_MODAL_HINTS)


def answer_confirm_modal(sb, message: str, cfg: RunConfig, step_label: str) -> bool:
    """Answer a confirmation dialog the way this run's configuration implies.

    Only answers questions it actually recognises. An unfamiliar confirmation
    is left alone and reported, because clicking Yes or No at random on a form
    that is submitting an application is worse than stopping.
    """
    # The dialog may have closed between being read and being answered --
    # either it timed out on its own or a previous pass already dealt with
    # it. Nothing to answer is not a failure.
    if not modal_present(sb):
        LOG.info("%s: the confirmation closed before it needed answering", step_label)
        return True

    lowered = (message or "").lower()

    if "child or dependent" in lowered:
        # Yes confirms qualifying through a child or dependent; No means
        # "applying for myself". Which one to send is a configured decision
        # (see ApplicationConfig.confirm_dependent_answer) rather than
        # something inferred here, because the two answers claim different
        # things about the applicant.
        wanted = (cfg.application.confirm_dependent_answer or "No").strip().title()

        if wanted == "Yes":
            LOG.warning(
                "%s: answering the dependent confirmation with YES. That asserts "
                "this applicant qualifies through a child or dependent, which the "
                "sheet does not say -- it is set that way in "
                "ApplicationConfig.confirm_dependent_answer.", step_label,
            )

        if _click_modal_button(sb, wanted, cfg):
            LOG.info(
                "%s: answered the confirmation with %s (applicant is %r)",
                step_label, wanted, cfg.application.eligible_applicant,
            )
            # Let it close before the caller looks again, or the next pass
            # finds the same dialog mid-dismissal and tries to answer it
            # twice.
            if not wait_for_modal_to_clear(sb):
                LOG.warning(
                    "%s: the confirmation was answered but is still on screen",
                    step_label,
                )
            return True
        LOG.warning("%s: could not find a %r button on the confirmation", step_label, wanted)
        return False

    LOG.warning(
        "%s: an unfamiliar confirmation is on screen and this will not guess an "
        "answer to it -- %s", step_label, message,
    )
    return False


# Tag the wanted modal button with an id so a *real* click can be aimed at it.
#
# Script is used only to label the element, never to activate it. The click
# itself goes through the same trusted path as every other click in the run:
# a scripted `button.click()` arrives with isTrusted false, and firing one on
# a confirmation dialog -- at the end of a form, on the screen the anti-bot
# layer is watching hardest -- is exactly the tell we have been removing
# everywhere else. Same method for clicking as the rest of the flow.
_TAG_MODAL_BUTTON_JS = r"""
const wanted = arguments[0].trim().toLowerCase();
const modal = document.querySelector(
  'modal-container.show, modal-container[role=dialog], .modal.show, .modal-content');
if (!modal) return null;
const button = Array.from(modal.querySelectorAll('button')).find(
  b => (b.innerText || '').trim().toLowerCase() === wanted);
if (!button) return null;
const id = 'aw-modal-btn';
button.id = id;
return '#' + id;
"""


def modal_present(sb) -> bool:
    """Is any dialog still on screen?"""
    try:
        return bool(sb.execute_script(
            "return !!document.querySelector("
            "  'modal-container.show, modal-container[role=dialog], .modal.show');"
        ))
    except Exception:
        return False


def wait_for_modal_to_clear(sb, timeout: float = 15.0) -> bool:
    """Wait for an answered dialog to actually close.

    Answering one is not instant: the app runs its handler, the dialog
    animates out, and for a moment it is still in the DOM. A loop that comes
    straight back round sees it, tries to answer it a second time, and finds
    the button it tagged has gone stale -- which then gets reported as a
    confirmation nobody could answer, on a lead where the answer had in fact
    already gone through. Measured exactly that: "answered the confirmation
    with No" at 07:31:56, "stale element reference" seven seconds later, and
    the step failed on a dialog it had already dealt with.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not modal_present(sb):
            return True
        time.sleep(0.4)
    return not modal_present(sb)


def _click_modal_button(sb, text: str, cfg: RunConfig) -> bool:
    """Click the modal button whose label is exactly `text`, for real.

    The dialog this exists for looks like:

        <div class="modal-footer">
          <button class="btn btn-danger float-start">No</button>
          <button class="btn btn-success float-end">Yes</button>
        </div>
    """
    try:
        selector = sb.execute_script(_TAG_MODAL_BUTTON_JS, text)
    except Exception as exc:
        LOG.debug("Could not find the %r button: %s", text, exc)
        return False

    if not selector:
        return False

    try:
        # Same treatment as any other control inside the enrollment frame:
        # put it where a native click can land, then click it properly.
        bring_framed_element_into_view(sb, selector, cfg)
        human_click(sb, selector, cfg)
        return True
    except RealInputError:
        # See the radio path: a refusal to use synthetic input has to reach
        # the runner, not be turned into "could not click that button".
        raise
    except Exception as exc:
        LOG.warning("Could not click the %r button for real: %s", text, exc)
        return False


def is_progress_modal(message: str) -> bool:
    lowered = (message or "").lower()
    return any(hint in lowered for hint in PROGRESS_MODAL_HINTS)


def modal_message(sb) -> str | None:
    """Title + body of the open Bootstrap modal, or None if there isn't one.

    The enrollment app reports its validation failures through these rather
    than inline field errors, so any step that submits has to check here or it
    will report 'nothing happened' while the reason sits on screen.
    """
    try:
        parts = sb.execute_script(
            "const m = document.querySelector('modal-container.show, modal-container[role=dialog]');"
            "if (!m) return null;"
            "const t = m.querySelector('.modal-title');"
            "const b = m.querySelector('.modal-body');"
            "return [t ? t.innerText.trim() : '', b ? b.innerText.trim() : ''];"
        )
    except Exception:
        return None

    if not parts:
        # No Bootstrap modal -- but this app has a second way of telling you
        # something went wrong, and it is not a modal at all.
        return toast_message(sb)

    title, body = parts
    return f"{title}: {body}".strip(": ").strip() or None


_FORM_VALIDITY_JS = r"""
const forms = Array.from(document.querySelectorAll('form'));
const invalid = Array.from(document.querySelectorAll(
  'input.ng-invalid, select.ng-invalid, textarea.ng-invalid'
)).map(el => ({
  id: el.id || null,
  name: el.getAttribute('name') || null,
  type: el.getAttribute('type') || el.tagName.toLowerCase(),
  cls: (el.className || '').split(/\s+/).filter(c => c.indexOf('ng-') === 0).join(' ')
}));
const untouched = Array.from(document.querySelectorAll('input[type=radio]')).map(el => ({
  id: el.id || null,
  checked: el.checked,
  cls: (el.className || '').split(/\s+/).filter(c => c.indexOf('ng-') === 0).join(' ')
}));
return {
  formInvalid: forms.some(f => (f.className || '').indexOf('ng-invalid') !== -1),
  invalid: invalid.slice(0, 8),
  radios: untouched.slice(0, 6)
};
"""


def form_validity(sb) -> dict:
    """What Angular thinks of the form, as opposed to how it looks.

    A control can be visibly filled while the model behind it is empty -- the
    DOM and ngModel are different things, and it is the model that gets
    submitted. When they disagree, this app answers the submit with a bare
    "Unable to continue ... (600)", which says nothing about which field was
    at fault.

    Logged before Continue is pressed so the mismatch is visible at the moment
    it matters, rather than reconstructed afterwards from an opaque error.
    """
    try:
        return sb.execute_script(_FORM_VALIDITY_JS) or {}
    except Exception:
        return {}


def toast_message(sb) -> str | None:
    """An ngx-toastr notification, which is the app's *other* error channel.

    The enrollment app raises backend failures as a toast, not a modal:

        <div class="ngx-toastr toast-error">
          <div class="toast-title">Error</div>
          <div class="toast-message">Unable to continue. ... (600)</div>
        </div>

    Nothing here looked for those, so a step that hit one saw no modal, no
    validation text and no screen change, and reported "clicked Continue but
    the screen never changed" -- while the reason was on screen the whole
    time, in the one place the code never checked. The (600) failures were
    invisible for exactly that reason.

    Toasts also auto-dismiss, so this is checked on every pass of the wait
    loop rather than once at the end, or it would be gone before anyone asked.
    """
    try:
        parts = sb.execute_script(
            "const t = document.querySelector("
            "  '.ngx-toastr.toast-error, .ngx-toastr.toast-warning, .toast-error');"
            "if (!t) return null;"
            "const title = t.querySelector('.toast-title');"
            "const body = t.querySelector('.toast-message');"
            "return [title ? title.innerText.trim() : '',"
            "        body ? body.innerText.trim() : t.innerText.trim()];"
        )
    except Exception:
        return None

    if not parts:
        return None

    title, body = parts
    return f"{title}: {body}".strip(": ").strip() or None


def dismiss_modal(sb) -> bool:
    """Close an open modal so the page underneath is usable again.

    Refuses to touch a dialog that is asking a question. The footer selector
    below matches the *first* button in the footer, which on this app's
    "Please Confirm" dialog is "No" -- so using this to clear a confirmation
    silently answers it, and answers it the same way every time regardless of
    what the run intended. Those go to answer_confirm_modal instead.
    """
    message = modal_message(sb)
    if message and is_confirm_modal(message):
        LOG.warning(
            "Not dismissing a confirmation dialog -- it is asking something, "
            "and clicking its first button would answer it by accident: %s",
            message[:160],
        )
        return False

    for selector in (
        "modal-container .modal-footer button",
        "modal-container button.btn-close",
    ):
        try:
            if sb.is_element_visible(selector):
                sb.click(selector, timeout=5)
                sb.sleep(0.5)
                LOG.info("Dismissed modal via %s", selector)
                return True
        except Exception:
            continue
    return False


def first_visible(sb, selectors) -> str | None:
    """First selector in `selectors` that's actually on screen, or None."""
    for selector in selectors:
        try:
            if sb.is_element_visible(selector):
                return selector
        except Exception:
            continue
    return None


# Set once a run reports on the frame's storage, because the answer cannot
# change between steps and the warning is worth reading once rather than nine
# times.
_STORAGE_REPORTED = False


def _report_frame_storage(sb, step_label: str) -> None:
    """Check third-party storage in the enrollment frame, once per run."""
    global _STORAGE_REPORTED
    if _STORAGE_REPORTED:
        return
    _STORAGE_REPORTED = True
    try:
        environment.storage_report(sb, step_label)
    except Exception as exc:
        LOG.debug("%s: frame storage check failed: %s", step_label, exc)


def enter_enrollment_frame(sb, cfg: RunConfig, step_label: str) -> str:
    """Switch into the application iframe and return its URL.

    Always re-entered from the top document: navigating inside the frame
    invalidates any earlier frame reference, so steps can't assume they are
    still in it. The frame is cross-origin (vmuappcloud.solixinc.com), which
    WebDriver handles, but it does mean nothing inside is reachable until we
    switch.
    """
    sb.switch_to_default_content()
    # Back in the top document, so any frame offset on record is stale. It is
    # set again below if we switch into the frame.
    real_input.set_frame_origin(None)

    # In direct-frame mode the application is the top document, so there is no
    # iframe to switch into and the steps can work where they already are.
    if "solixinc.com" in (sb.get_current_url() or ""):
        frame_url = _wait_frame_ready(sb, cfg, step_label)
        LOG.info("%s: the application is the page itself (%s)", step_label, frame_url)
        _look_before_touching(sb, cfg)
        return frame_url

    try:
        sb.wait_for_element_present(ENROLLMENT_FRAME, timeout=cfg.page_timeout)
    except Exception as exc:
        raise PageMismatchError(
            f"{step_label}: no {ENROLLMENT_FRAME} iframe on {sb.get_current_url()}. "
            f"The application only renders after the ZIP check has been submitted."
        ) from exc

    _align_frame_to_viewport(sb, cfg, step_label)

    sb.switch_to_frame(ENROLLMENT_FRAME)
    frame_url = _wait_frame_ready(sb, cfg, step_label)
    LOG.info("%s: inside the enrollment frame (%s)", step_label, frame_url)

    # Turnstile runs in here, not out there, and so do its prerequisites.
    # Checked once per run: the answer is a property of the browser and the
    # frame, not of the screen, and repeating it on every step would be noise.
    _report_frame_storage(sb, step_label)

    # The observer installs on new documents, and this frame is a document the
    # session did not navigate itself. Running it directly is idempotent.
    turnstile.install_now(sb, cfg)

    # Inside the frame the origin is the Solix app, which is the thing behind
    # Cloudflare -- so this is the only place a clearance cookie for it can
    # be set.
    apply_flaresolverr_cookies(sb, cfg, frame_url)

    _look_before_touching(sb, cfg)

    return frame_url


def _align_frame_to_viewport(sb, cfg: RunConfig, step_label: str) -> None:
    """Scroll the outer page so the enrollment frame starts at the top of it.

    Pointer coordinates are always relative to the *top-level* viewport, even
    for an element found inside a frame -- so whether ActionChains can reach a
    field depends on where the outer page happens to be scrolled, which
    nothing inside the frame can see or change.

    This frame is taller than the window, so it never gets a scrollbar of its
    own and `scrollIntoView` inside it does nothing at all. The result was
    that every pointer move on every enrollment screen was refused with "move
    target out of bounds", silently, and the run filled eight screens without
    the mouse moving once -- on exactly the screens Turnstile is scoring.

    Doing this here is what makes it safe: at this point we are still in the
    top document, so it is an ordinary scroll with no frame switching.
    """
    try:
        origin = sb.execute_script(
            """
            const f = document.querySelector(arguments[0]);
            if (!f) return null;
            // 'start' puts the frame's top edge at the top of the window, so
            // the screens inside it render where the pointer can reach.
            // Position read here; the actual scrolling is done in steps by
            // the caller, because scrollIntoView moves the page in one frame
            // and nothing physical scrolls like that.
            const want = f.getBoundingClientRect().top - 8;
            const r = f.getBoundingClientRect();
            return {
              scrollBy: want,
              x:  window.screenX + (window.outerWidth - window.innerWidth) / 2,
              y:  window.screenY + (window.outerHeight - window.innerHeight),
              w:  window.innerWidth,
              h:  window.innerHeight,
              fx: r.left,
              fy: r.top
            };
            """,
            ENROLLMENT_FRAME,
        )
        # Measured here and nowhere else: this is the last moment the driver
        # is in the top document, and these numbers are unobtainable from
        # inside a cross-origin frame. real_input needs them to aim at the
        # screen; without them every real click on these screens misses.
        if origin and origin.get("scrollBy"):
            smooth_scroll(sb, origin["scrollBy"], cfg)
            # Re-read after moving: the offsets above were measured before.
            origin = sb.execute_script(
                "const f = document.querySelector(arguments[0]);"
                "if (!f) return null;"
                "const r = f.getBoundingClientRect();"
                "return {x: window.screenX + (window.outerWidth - window.innerWidth) / 2,"
                "        y: window.screenY + (window.outerHeight - window.innerHeight),"
                "        w: window.innerWidth, h: window.innerHeight,"
                "        fx: r.left, fy: r.top};",
                ENROLLMENT_FRAME,
            )
        real_input.set_frame_origin(origin)
    except (NameError, AttributeError, TypeError) as exc:
        # A bug in this function, not a page that would not cooperate. The
        # broad handler below used to swallow these at debug level, which is
        # how a plain NameError here silently disabled frame alignment for a
        # whole run and surfaced only as "#firstName did not become visible".
        LOG.error("%s: bug in frame alignment -- %s", step_label, exc)
        real_input.set_frame_origin(None)
    except Exception as exc:
        # Best-effort: a step that cannot scroll still runs, it just falls
        # back to clicking without the pointer path.
        LOG.debug("%s: could not align the enrollment frame: %s", step_label, exc)
        real_input.set_frame_origin(None)


def bring_framed_element_into_view(sb, selector: str, cfg: RunConfig | None = None) -> bool:
    """Scroll the outer page so a field inside the enrollment frame is reachable.

    Why this is needed at all: the enrollment iframe is rendered as tall as
    its content, so it never has a scrollbar and its own viewport already
    contains every field. `scrollIntoView` inside it is therefore a no-op, and
    because it is a no-op it never propagates to the parent either -- so the
    outer page stays wherever it was and fields below the fold sit outside the
    top-level viewport, which is the only coordinate space pointer events
    have. That is the whole reason the mouse never moved on these screens.

    The frame is cross-origin, so `window.parent.scrollTo` is not available
    from inside it. Stepping out to the top document, scrolling, and stepping
    back is the only way -- and it invalidates any element handle taken
    before the switch, which is why callers pass a selector and re-find
    afterwards rather than handing in an element.

    Returns whether the outer page was actually moved.
    """
    try:
        inner_top = sb.execute_script(
            "const el = document.querySelector(arguments[0]);"
            "if (!el) return null;"
            "const r = el.getBoundingClientRect();"
            "return r.top + r.height / 2;",
            selector,
        )
    except Exception:
        return False
    if inner_top is None:
        return False

    moved = False
    came_from_frame = False
    try:
        sb.switch_to_default_content()

        # Is there a frame to come back to?
        #
        # In direct-frame mode the application IS the top document, so there
        # is no enrollment iframe -- and there is no outer page to scroll
        # either, since the field is already in the only document there is.
        # Without this check the work below finds no frame and does nothing,
        # and then the `finally` tries to switch into that frame anyway and
        # blocks for the full page timeout: 90 seconds, measured, waiting for
        # an element that cannot appear, once per scrolled field.
        #
        # Tested by presence rather than by URL on purpose. `enter_enrollment_frame`
        # can tell the modes apart by URL because it looks right after
        # returning to the top document; here the caller is usually still
        # inside the frame, and WebDriver reports the *frame's* URL as the
        # current one -- which is solixinc.com in both modes, so the URL
        # cannot distinguish them at this point.
        came_from_frame = bool(sb.find_elements(ENROLLMENT_FRAME))
        if not came_from_frame:
            return False

        result = sb.execute_script(
            """
            const f = document.querySelector(arguments[0]);
            if (!f) return null;
            const target = f.getBoundingClientRect().top + arguments[1];
            // Put the field near the middle of the window, where a pointer
            // move to it is always in bounds.
            const delta = target - (window.innerHeight / 2);
            const moved = Math.abs(delta) >= 8;
            // Reported, not performed: the caller scrolls it in steps.
            window.__awScrollWanted = moved ? delta : 0;
            // Re-read after scrolling: the frame has just moved, and a stale
            // offset would send every real click to where it used to be.
            const r = f.getBoundingClientRect();
            return {
              moved: moved,
              origin: {
                x:  window.screenX + (window.outerWidth - window.innerWidth) / 2,
                y:  window.screenY + (window.outerHeight - window.innerHeight),
                w:  window.innerWidth,
                h:  window.innerHeight,
                fx: r.left,
                fy: r.top
              }
            };
            """,
            ENROLLMENT_FRAME,
            inner_top,
        )
        if result:
            moved = bool(result.get("moved"))
            wanted = 0
            try:
                wanted = sb.execute_script("return window.__awScrollWanted || 0;") or 0
            except Exception:
                wanted = 0
            if wanted:
                if cfg is not None:
                    smooth_scroll(sb, wanted, cfg)
                else:
                    sb.execute_script("window.scrollBy(0, arguments[0]);", wanted)
            origin = result.get("origin")
            if wanted:
                # The frame moved with the page, so the offsets in `result`
                # are stale; a stale origin sends every real click to where
                # the field used to be.
                try:
                    origin = sb.execute_script(
                        "const f = document.querySelector(arguments[0]);"
                        "if (!f) return null;"
                        "const r = f.getBoundingClientRect();"
                        "return {x: window.screenX + (window.outerWidth - window.innerWidth) / 2,"
                        "        y: window.screenY + (window.outerHeight - window.innerHeight),"
                        "        w: window.innerWidth, h: window.innerHeight,"
                        "        fx: r.left, fy: r.top};",
                        ENROLLMENT_FRAME,
                    )
                except Exception:
                    pass
            real_input.set_frame_origin(origin)
    except Exception as exc:
        LOG.debug("Could not scroll the outer page for %s: %s", selector, exc)
    finally:
        # Getting back inside is not optional: every caller is mid-step and
        # expects to still be in the frame. A failure here would turn a
        # cosmetic scroll into a broken step, so it is retried loudly.
        #
        # Only when we actually left one, though -- see above.
        if came_from_frame:
            try:
                sb.switch_to_frame(ENROLLMENT_FRAME)
            except Exception as exc:
                LOG.warning("Could not re-enter the enrollment frame after scrolling: %s", exc)
                return False

    return moved


def _look_before_touching(sb, cfg: RunConfig) -> None:
    """Spend a moment on a freshly rendered enrollment screen before filling it.

    This is the frame equivalent of what settle() does for the public pages,
    and it matters more here than there. Every screen from step 5 on lives in
    this frame, none of them call settle(), and the frame is where Cloudflare
    Turnstile sits scoring the session -- so until now the run arrived at the
    screen Turnstile watches with no pointer activity behind it at all, picked
    a radio, and hit Continue inside a tenth of a second. Turnstile runs here
    in `interaction-only` mode, which means it is scoring exactly that: what
    the session did before it was asked for a token.

    Costs a few seconds per screen and only when human_like is on.
    """
    # Bring the window genuinely to the front before filling anything.
    #
    # document.hasFocus() reads false whenever the window is behind something
    # else, and a form being filled in a window nobody is looking at is a
    # real signal, not a false one. The stealth layer used to answer it by
    # overriding hasFocus to return true -- which turned out to be the more
    # detectable of the two problems, because the override is visible on
    # `document` where natively there is no own property at all.
    #
    # So: no lie, just put the window in front so the honest answer is true.
    # This activates a window without taking the mouse or keyboard, so it is
    # safe outside --real-input. Skipped with several workers, which would
    # otherwise fight each other for the foreground.
    if cfg.workers == 1 and not cfg.headless:
        real_input.focus_window(sb)

    if real_input.should_use(cfg):
        real_input.reading_pause(cfg)
        return

    # Read the screen, then move over it, the way a person would. The reading
    # beat carries its own pointer drift, so the screen is never touched by a
    # session that has been motionless since it rendered.
    rest(sb, cfg, "long")
    warm_up(sb, cfg)


# The frame is an Angular app: the document finishes loading long before the
# app has drawn anything, and in between it renders an "Loading..." placeholder
# over a static security notice. That notice alone is enough text to look
# "loaded", so readyState plus a body-length check says ready while the screen
# is still empty -- on a slow connection a step then hunts for buttons that
# have not been rendered yet. Waiting for real controls is the honest signal.
#
# Counting *visible* controls matters: the frame ships a hidden `menu-switch`
# checkbox and a display:none decoy text input on every screen, so a plain
# element count is never zero and the check would pass against a blank screen.
_APP_RENDERED_JS = """
const visible = el => !!(el.offsetParent || el.getClientRects().length);
const controls = Array.from(document.querySelectorAll(
    'button, a.btn, select, textarea, input:not([type=hidden]):not([type=checkbox])'
)).filter(visible);
return {
  controls: controls.length,
  loading: /loading\\.\\.\\./i.test(document.body.innerText || '')
};
"""


def _wait_frame_ready(sb, cfg: RunConfig, step_label: str) -> str:
    deadline = time.time() + cfg.page_timeout
    document_loaded = False

    while time.time() < deadline:
        try:
            state = sb.execute_script("return document.readyState")
            if state == "complete" and len(body_text(sb)) > 50:
                if not document_loaded:
                    # The app gets its own budget from here. A frame that took
                    # most of the first window to arrive would otherwise have
                    # no time left to render, and a slow proxy would look
                    # exactly like a refusal.
                    document_loaded = True
                    deadline = time.time() + cfg.page_timeout
                    LOG.info("%s: frame loaded, waiting for the app to render", step_label)

                app = sb.execute_script(_APP_RENDERED_JS) or {}
                if app.get("controls") and not app.get("loading"):
                    return sb.execute_script("return window.location.href")
        except Exception:
            pass  # frame still swapping documents
        time.sleep(0.25)

    if document_loaded:
        # The frame served a real document; it is the Angular app inside that
        # never finished painting. That is one slow lead, not a host that has
        # stopped answering -- raising ThrottledError here would stop the whole
        # batch over a slow proxy.
        raise PageMismatchError(
            f"{step_label}: the enrollment frame loaded but its application "
            f"never rendered any controls within {cfg.page_timeout}s. Usually a "
            f"slow connection; check the step's screenshot to be sure."
        )

    # A frame that loads to nothing at all is how the host refuses.
    raise ThrottledError(
        f"{step_label}: the enrollment frame never loaded within "
        f"{cfg.page_timeout}s (blank or broken frame). The enrollment host is "
        f"refusing to serve the form. Most often that follows repeated "
        f"submissions of the same applicant. Give it time rather than retrying."
    )


def body_text(sb) -> str:
    try:
        return sb.get_text("body") or ""
    except Exception:
        return ""


def normalize_path(url: str) -> str:
    return urlparse(url).path.rstrip("/").lower() or "/"


def accepted_paths(expected: str | tuple[str, ...]) -> set[str]:
    paths = (expected,) if isinstance(expected, str) else tuple(expected)
    return {p.rstrip("/").lower() or "/" for p in paths}


def wait_for_path(sb, expected: str | tuple[str, ...], timeout: int, step_label: str) -> str:
    """Poll until the URL path is one of `expected`; return the one we got.

    Waiting on the URL rather than a load event, since these clicks can be
    handled client-side and can redirect before settling.
    """
    allowed = accepted_paths(expected)
    deadline = time.time() + timeout

    while time.time() < deadline:
        path = normalize_path(sb.get_current_url())
        if path in allowed:
            return path
        time.sleep(0.25)

    raise PageMismatchError(
        f"{step_label}: URL never reached any of {sorted(allowed)} within "
        f"{timeout}s (still on {sb.get_current_url()})"
    )


def verify_on_site(
    sb,
    step_label: str,
    expected_path: str | tuple[str, ...] | None = None,
    min_body_chars: int = 200,
) -> None:
    """Confirm we're still on an Assurance Wireless host, on one of the
    expected paths, with a page that actually rendered.

    `expected_path` takes a tuple because the site redirects some routes
    (/apply-now being the first one we hit).

    `min_body_chars` guards against a WAF returning the right URL with an
    empty shell. Set it to 0 for pages whose content is all inside an iframe,
    since the top document is legitimately near-empty there.
    """
    url = sb.get_current_url()
    host = (urlparse(url).hostname or "").lower()

    if not any(host == s or host.endswith("." + s) for s in ALLOWED_HOST_SUFFIXES):
        raise PageMismatchError(
            f"{step_label}: expected a host in {ALLOWED_HOST_SUFFIXES} but the "
            f"browser is on {host!r} (full URL: {url})"
        )

    if expected_path is not None:
        allowed = accepted_paths(expected_path)
        path = normalize_path(url)
        if path not in allowed:
            raise PageMismatchError(
                f"{step_label}: expected path in {sorted(allowed)} but landed "
                f"on {path!r} (full URL: {url})"
            )

    if min_body_chars:
        length = len(body_text(sb))
        if length < min_body_chars:
            raise PageMismatchError(
                f"{step_label}: URL is correct but the page looks empty "
                f"({length} chars of text). Likely a challenge or a failed render."
            )


# Angular renders validation messages into these.
ERROR_SELECTORS = (
    ".invalid-feedback",
    ".error-message",
    ".text-danger",
    "[class*='error']",
)


def screen_headings(sb) -> list[str]:
    """The headings that identify which wizard screen is showing."""
    try:
        return sb.execute_script(
            "return Array.from(document.querySelectorAll('h1,h2,h3,legend'))"
            ".map(e => e.innerText.trim()).filter(Boolean).slice(0, 10)"
        ) or []
    except Exception:
        return []


def validation_errors(sb) -> list[str]:
    """Whatever the form is complaining about, in its own words."""
    messages: list[str] = []
    for selector in ERROR_SELECTORS:
        try:
            found = sb.execute_script(
                "return Array.from(document.querySelectorAll(arguments[0]))"
                ".filter(e => e.offsetParent !== null)"
                ".map(e => e.innerText.trim()).filter(Boolean);",
                selector,
            ) or []
            messages.extend(found)
        except Exception:
            continue
    # Dedupe while keeping order.
    return list(dict.fromkeys(messages))[:10]


# Modal wording that means "this lead's data is wrong", mapped to the bucket
# it puts them in. These are rejections of the applicant, not of the run, so
# they are worth a verdict rather than a failure.
REJECTION_SIGNALS = (
    ("invalid email address", BAD_EMAIL),
    ("email address is invalid", BAD_EMAIL),
    # Announced as an "Important" modal after the eligible-applicant screen:
    # "Our records show that you are currently an Assurance Wireless
    # customer." The applicant is already on this carrier, so the application
    # stops here -- but it is a routing answer for the agent rather than a
    # refusal of the data, which is why it gets its own bucket rather than
    # being filed with the rejections.
    ("currently an assurance wireless customer", AW_TRANSFER),
    ("already an assurance wireless customer", AW_TRANSFER),
)


def rejection_verdict(message: str) -> str:
    """The bucket this rejection message puts the lead in, or "" if unknown."""
    lowered = (message or "").lower()
    return next((v for signal, v in REJECTION_SIGNALS if signal in lowered), "")


def frame_interruption(sb) -> str:
    """A challenge or block page sitting on top of the current document.

    Mirrors what settle() checks on the outer page, for the steps that run
    inside the frame and never get to call it.
    """
    try:
        title = (sb.get_title() or "").lower()
        body = body_text(sb).lower()[:3000]
    except Exception:
        return ""

    hit = next((s for s in BLOCK_SIGNALS if s in title or s in body), None)
    if hit:
        return f"a block page (matched {hit!r})"

    if challenge_present(sb):
        return "a bot-check challenge (Cloudflare/Turnstile)"

    for hint in ("verify you are human", "are you a robot", "security check"):
        if hint in body:
            return f"a human-verification prompt (matched {hint!r})"

    return ""


# Headings that belong to the cookie/consent dialog rather than to the wizard.
# OneTrust can open over the form at any moment -- it did so mid-run on the
# eligibility screen -- and because `advance_screen` judges progress by the
# headings changing, its panel reads as "we advanced" and the run then
# classifies a cookie dialog as an application screen.
CONSENT_HEADINGS = (
    "do not sell my personal information",
    "manage consent preferences",
    "performance cookies",
    "privacy preference",
    "cookie",
)


def is_consent_screen(headings) -> bool:
    """Are these headings the consent dialog rather than a wizard screen?"""
    if not headings:
        return False
    lowered = [h.lower() for h in headings]
    return any(any(sig in h for sig in CONSENT_HEADINGS) for h in lowered)


# The app marks work in progress by disabling the submit button and spinning an
# icon inside it. Waiting on a clock instead of on this is what made the
# eligibility step look broken: its lookup runs for minutes, and every fixed
# timeout expired while the form was still legitimately working.
BUSY_SELECTORS = (
    "button[disabled] .fa-spinner",
    "button[disabled] .fa-pulse",
    ".spinner-border",
    ".fa-spinner.fa-pulse",
)


# Cloudflare Turnstile lives in aw_bot/turnstile.py, which watches the widget's
# own callbacks instead of trying to read its state out of the DOM. The short
# version of why: this app renders Turnstile explicitly and invisibly, so there
# is no container and no `cf-turnstile-response` input to look at, and the id
# the old selector matched (`#ngx-turnstile`) belongs to the loader script tag
# rather than to any widget. See that module's docstring.


def turnstile_state(sb) -> dict:
    """What Cloudflare's widget on this screen is doing, if it is there."""
    return turnstile.state(sb)


def _wait_until_enabled(sb, selector: str, cfg: RunConfig, step_label: str) -> bool:
    """Wait for the submit button to stop being disabled.

    Turnstile is the usual reason it is disabled, but the app also disables it
    while validating a field, and clicking through either is a no-op.
    """
    deadline = time.time() + cfg.page_timeout
    while time.time() < deadline:
        try:
            disabled = sb.execute_script(
                "const el = document.querySelector(arguments[0]);"
                "return el ? (el.disabled === true) : null;",
                selector,
            )
        except Exception:
            return False
        if disabled is None or not disabled:
            return True
        time.sleep(0.5)

    LOG.warning("%s: %s is still disabled; clicking it anyway", step_label, selector)
    return False


def wait_for_turnstile(sb, cfg: RunConfig, step_label: str) -> bool:
    """Wait for Turnstile to hand the form a token, asking for help if it wants one.

    Four outcomes now, where the old version could only see three -- and the
    one it could not see is the one that was actually happening.

      * nothing has been rendered -- there is no challenge on this screen, so
        there is nothing to wait for. The API script merely being loaded is
        not a widget; treating it as one is what made this function burn its
        budget on screens that were never challenged in the first place.
      * a token arrives -- Cloudflare was satisfied, carry on
      * a visible challenge is drawn -- the control doing its job, so the run
        stops and asks the person at the keyboard, then resumes on the token
      * Turnstile reports an error code -- it did not refuse silently, it said
        why, and passing that on is worth far more than another two minutes of
        waiting for something that has already failed

    Returns whether the form ended up with a token.
    """
    status = turnstile.state(sb)

    # No widget means no wait. The app renders Turnstile only on the screen
    # that needs it, so every other Continue should pass straight through.
    if not status.get("rendered"):
        if status.get("apiLoaded"):
            LOG.debug(
                "%s: the Turnstile API is loaded but no widget has been "
                "rendered; nothing to wait for", step_label,
            )
        return True

    if status.get("token"):
        LOG.debug("%s: Turnstile already holds a token", step_label)
        return True

    if status.get("errorCode"):
        LOG.error("%s: %s", step_label, turnstile.explain_error(status["errorCode"]))
        return False

    LOG.info(
        "%s: a Turnstile widget was rendered (sitekey %s); waiting for a token",
        step_label, status.get("sitekey") or "?",
    )

    # Put the browser window in front before waiting on the widget.
    #
    # The page's own scripts can be told the document is focused, but Turnstile
    # runs in a cross-origin iframe of Cloudflare's own, and the signals it
    # weighs are not only the ones a page can read. A window that is genuinely
    # behind the terminal is a window nobody is looking at, and this widget is
    # in `interaction-only` mode, which means it is deciding whether a person
    # is there at all.
    #
    # This only activates a window: it does not take the mouse or keyboard,
    # so it is safe outside --real-input. Skipped with several workers, where
    # they would fight each other for the foreground.
    if cfg.workers == 1 and not cfg.headless:
        if real_input.focus_window(sb):
            LOG.debug("%s: brought the browser to the front for Turnstile", step_label)

    started = time.time()
    deadline = started + cfg.turnstile_wait
    asked = False
    retried = False

    while time.time() < deadline:
        status = turnstile.state(sb)
        if status.get("token"):
            LOG.info("%s: Turnstile issued a token; the form can continue", step_label)
            return True

        # Turnstile named its own failure. Nothing is gained by waiting out the
        # rest of the clock, and the code is the single most useful thing this
        # run can report -- it is the difference between "blocked, somehow" and
        # a specific cause somebody can go and fix.
        code = status.get("errorCode")
        if code:
            LOG.error("%s: %s", step_label, turnstile.explain_error(code))
            # The 300 family is Cloudflare's own transient error, and the one
            # case its documentation says to retry. Everything else is a
            # verdict, and asking again just gets the same answer slower.
            if not retried and str(code).startswith("300"):
                retried = True
                turnstile.reset(sb, step_label, status)
                deadline = time.time() + cfg.turnstile_wait
                time.sleep(0.5)
                continue
            return False

        # A token that arrived and went stale before the form used it. That is
        # the one situation a reset genuinely repairs.
        if status.get("expired") and not retried:
            retried = True
            LOG.info("%s: the Turnstile token expired before it was used", step_label)
            turnstile.reset(sb, step_label, status)

        if status.get("widgetShowing") and not asked:
            asked = True
            # Say so the moment the checkbox appears rather than after a long
            # silent wait. Once it is visible the outcome is decided: either a
            # person clicks it now, or this lead is not going through, and
            # sitting on it for minutes tells nobody anything.
            if not cfg.solve_challenges:
                LOG.error(
                    "%s: Cloudflare is asking for a human and nobody is watching. "
                    "Re-run with --solve-challenges (and a visible window) to "
                    "answer it yourself, or move the profiles to cleaner proxies "
                    "so it stops asking.", step_label,
                )
                return False

            # A person has to walk over and click, which is the one case worth
            # waiting minutes for -- so the short ceiling is lifted here and
            # only here.
            deadline = time.time() + cfg.solve_challenge_wait
            LOG.warning(
                "%s: Cloudflare wants a human. Its checkbox is on screen in the "
                "browser window -- click it and the run picks up by itself. "
                "Waiting up to %.0fs.", step_label, cfg.solve_challenge_wait,
            )

        # Do not hold perfectly still while the widget decides.
        #
        # This wait is the one stretch of the run that Turnstile is actually
        # watching. The widget is mounted only once Continue is pressed, so
        # everything the warm-up and the form-filling produced is already
        # behind it -- and from here the old code slept in a tight loop,
        # touching nothing, for up to three minutes. An `interaction-only`
        # widget exists to decide whether a person is present, and a viewport
        # with no pointer events in it at all for the whole scoring window is
        # the strongest possible answer of "no".
        #
        # Small and occasional on purpose: this is a person waiting on a
        # spinner, not a person using the page. Never clicks -- a stray click
        # here would hit whatever the app drew under the pointer.
        _idle_signs_of_life(sb, cfg)
        time.sleep(random.uniform(0.6, 1.4))

    status = turnstile.state(sb)
    if asked:
        LOG.error("%s: the Turnstile challenge was not cleared in time", step_label)
    else:
        LOG.warning(
            "%s: the widget was rendered but issued neither a token nor an "
            "error within %.0fs (%s).",
            step_label, cfg.turnstile_wait, turnstile.describe(status),
        )
    return False


def _retry_turnstile(sb, step_label: str) -> None:
    """Ask the Turnstile widget to have another go. Best-effort.

    Kept as a name for the existing call sites; the guards that stop a reset
    from throwing away a token that has already arrived live in the turnstile
    module, because that is the mistake worth making impossible rather than
    remembering not to make.
    """
    turnstile.reset(sb, step_label)


def _idle_signs_of_life(sb, cfg: RunConfig) -> None:
    """A little pointer drift, the way a hand rests on a mouse while waiting.

    Thinned on purpose: a twitch on every pass of a half-second poll loop is
    a metronome, and a metronome is a pattern. Roughly two in five.
    """
    if random.random() > 0.4:
        return
    idle_drift(sb, cfg)


def is_busy(sb) -> bool:
    """Is the form still working on the last thing it was asked to do?"""
    for selector in BUSY_SELECTORS:
        try:
            if sb.is_element_visible(selector):
                return True
        except Exception:
            continue
    return False


def advance_screen(
    sb,
    cfg: RunConfig,
    step_label: str,
    selectors,
    timeout: int | None = None,
    settle: float = 0.0,
) -> list[str]:
    """Click Continue and confirm the wizard actually moved on.

    The wizard is a single-page app, so "did it advance" is judged by the
    headings changing rather than by a navigation. If they do not change, the
    form almost certainly rejected something -- surface its own validation text
    rather than a bare timeout.

    Returns the new screen's headings.
    """
    selector = first_visible(sb, selectors)
    if selector is None:
        raise PageMismatchError(
            f"{step_label}: no visible Continue button. Tried: {', '.join(selectors)}"
        )

    # A modal already open would swallow the click -- but *how* it is cleared
    # matters. dismiss_modal() clicks the first button in the footer, and on
    # this app's confirmation dialog that is "No":
    #
    #   <div class="modal-footer">
    #     <button class="btn btn-danger float-start">No</button>
    #     <button class="btn btn-success float-end">Yes</button>
    #
    # So a dialog asking a real question was being answered by whichever
    # button happened to come first in the DOM, before the code that decides
    # the answer ever ran. Route questions to the answerer; only dismiss
    # things that are not asking anything.
    open_modal = modal_message(sb)
    if open_modal:
        if is_confirm_modal(open_modal):
            LOG.info("%s: a confirmation is open before submit -- answering it", step_label)
            if not answer_confirm_modal(sb, open_modal, cfg, step_label):
                raise PageMismatchError(
                    f"{step_label}: a confirmation is waiting for an answer that "
                    f"this run does not recognise -- {open_modal}"
                )
        else:
            dismiss_modal(sb)

    # Turnstile has to hand over its token *before* the click, not after. The
    # app disables Continue until the token lands, and a click on a disabled
    # button is silently nothing -- the run then waits out the clock on a form
    # that was never actually submitted. Waiting first is also what a person
    # does: they answer the challenge, then press the button.
    wait_for_turnstile(sb, cfg, step_label)
    _wait_until_enabled(sb, selector, cfg, step_label)

    # Say what the model looks like before submitting, so a "(600)" afterwards
    # can be attributed instead of guessed at.
    state = form_validity(sb)
    if state.get("formInvalid") or state.get("invalid"):
        LOG.warning(
            "%s: Angular considers the form invalid before submit. Offending "
            "controls: %s", step_label, state.get("invalid") or "(form-level)",
        )
    if state.get("radios"):
        LOG.info("%s: radio state at submit: %s", step_label, state["radios"])

    # Read the screen before submitting it.
    #
    # Everything above this point happens in a couple of seconds, and a form
    # that is filled and submitted inside that window is not one a person
    # filled in. The gap between the last field and the submit is the single
    # most obvious timing signal a page can measure, and it costs a few
    # seconds to not have it. Longer than the between-field pauses on
    # purpose: this is the beat where somebody checks what they entered.
    # `rest` rather than `dwell`: the pointer drifts during the wait instead of
    # the viewport going dead for several seconds immediately before a submit,
    # which is the most conspicuous moment in the whole screen to go still.
    rest(sb, cfg, "long")

    before = screen_headings(sb)
    LOG.info("Clicking Continue via %s", selector)
    # Same reason as the radio: a native click needs the button inside the
    # top-level viewport, and nothing inside this frame can put it there.
    # Without this the click is refused and falls back to a scripted one,
    # which arrives untrusted on the screen that is being scored.
    bring_framed_element_into_view(sb, selector, cfg)
    human_click(sb, selector, cfg)

    # Sit with the screen before starting to judge it.
    #
    # The loop below works out what the form is doing by looking at it, and in
    # the moment after a click there is nothing to see yet: no spinner, no
    # modal, no new headings. Waiting first means the first look lands on a
    # screen that has actually reacted.
    if settle > 0:
        # Hands off the browser completely while the form works.
        #
        # Not a pause with idling in it -- nothing at all. No execute_script,
        # no ActionChains, no driver traffic of any kind.
        #
        # The reason is the one measurement that separates this from every
        # other theory: the same profile, the same proxy and the same machine
        # complete this lookup by hand, and fail under automation. So the
        # difference is not the identity, it is what the driver does -- and
        # what it does here is several hundred `Runtime.evaluate` round trips
        # into the page (four checks, twice a second, for as long as the
        # spinner turns) plus WebDriver-dispatched pointer events, during
        # exactly the window the backend is deciding. A hand-run session
        # produces none of that.
        #
        # Earlier versions filled this wait with pointer drift on the theory
        # that stillness looks robotic. That reasoning applies while a person
        # is *using* a page; it does not apply to a browser nobody is touching
        # while it waits for a server, which is genuinely still.
        LOG.info(
            "%s: hands off for %.0fs while the form works -- no driver "
            "traffic at all", step_label, settle,
        )
        time.sleep(settle)

    budget = timeout or cfg.page_timeout
    deadline = time.time() + budget
    # An absolute stop, so "still spinning" cannot wait forever.
    hard_deadline = time.time() + max(budget, cfg.max_busy_wait)
    announced_busy = False

    # How often to look at the screen while it works.
    #
    # This used to be every 0.25-0.5s, and each pass ran four separate
    # `execute_script` calls -- the modal text, the Turnstile state, the busy
    # spinner, the headings. Eight CDP round trips a second into the page, for
    # as long as the spinner turned. Over a ninety-second lookup that is
    # several hundred evaluations arriving while the backend decides, and a
    # hand-run browser produces none of them.
    #
    # A form that takes tens of seconds to answer does not need watching twice
    # a second. Looking every couple of seconds costs nothing in responsiveness
    # and cuts the driver's footprint during the critical window by an order of
    # magnitude.
    poll = 2.0

    # How many times the app has asked to be re-tried on this screen.
    retries = 0

    while time.time() < deadline and time.time() < hard_deadline:
        # The app reports rejections through a modal, so check for one before
        # concluding that nothing happened.
        modal = modal_message(sb)
        if modal:
            # "Validating email address. Please wait..." is a spinner, not a
            # verdict -- the real answer comes after it closes.
            if is_progress_modal(modal):
                LOG.info("Waiting on the form: %s", modal)
                time.sleep(poll)
                continue
            if is_throttle_message(modal):
                raise ThrottledError(f"{step_label}: the host is refusing us -- {modal}")

            # The app asking to be tried again. Do what it says: dismiss the
            # dialog, press the same button, and give the screen its budget
            # back. Treating this as a rejection threw the lead away on the
            # one failure the site had told us how to recover from.
            if is_retryable_message(modal):
                if retries >= MAX_RETRY_PROMPTS:
                    raise ThrottledError(
                        f"{step_label}: the host asked us to retry "
                        f"{retries} times and never got further -- {modal}"
                    )
                retries += 1
                LOG.info(
                    "%s: the form reported a communication delay and asked to "
                    "be re-tried (%d of %d) -- %s",
                    step_label, retries, MAX_RETRY_PROMPTS, modal,
                )
                _click_modal_button(sb, "Dismiss", cfg) or dismiss_modal(sb)
                rest(sb, cfg, "medium")
                bring_framed_element_into_view(sb, selector, cfg)
                human_click(sb, selector, cfg)
                if settle > 0:
                    LOG.info(
                        "%s: hands off for %.0fs after the retry", step_label, settle
                    )
                    time.sleep(settle)
                deadline = min(time.time() + budget, hard_deadline)
                continue

            if is_confirm_modal(modal):
                # A question, not a refusal. Answering it is how the screen
                # gets past -- the run used to stop here having succeeded.
                if answer_confirm_modal(sb, modal, cfg, step_label):
                    time.sleep(poll)
                    continue
                # The answer did not go in. If the dialog has gone anyway,
                # something else closed it and the screen is free to move on;
                # only a dialog still sitting there is a real dead end.
                if not modal_present(sb):
                    LOG.info(
                        "%s: the confirmation closed on its own; carrying on",
                        step_label,
                    )
                    time.sleep(poll)
                    continue
                raise PageMismatchError(
                    f"{step_label}: a confirmation is waiting for an answer that "
                    f"this run does not recognise -- {modal}"
                )
            verdict = rejection_verdict(modal)
            if verdict:
                # "Rejected" is the wrong word for some of these. An applicant
                # who already has Assurance Wireless service has not had their
                # data refused -- the form has answered the question the run
                # was asking, and the answer routes them somewhere else.
                if verdict == AW_TRANSFER:
                    raise LeadRejectedError(
                        f"{step_label}: this applicant already has Assurance "
                        f"Wireless service -- {modal}", verdict,
                    )
                raise LeadRejectedError(
                    f"{step_label}: the form rejected this lead -- {modal}", verdict
                )

            # Before calling this "the form rejected the data", ask Turnstile
            # whether it failed first.
            #
            # This app reports its own failure as a bare `(600)`, and the
            # `600***` family is exactly what Cloudflare Turnstile returns when
            # the challenge cannot be completed in this browser. When the
            # widget has an error code at the moment the form gives up, that
            # code is the reason -- and reporting it as a data rejection sends
            # whoever reads the log off to check the applicant's details, which
            # is the one place the problem is not.
            status = turnstile.state(sb)
            if status.get("errorCode"):
                raise BotBlockedError(
                    f"{step_label}: the form gave up with -- {modal} -- and "
                    f"{turnstile.explain_error(status['errorCode'])}"
                )
            if status.get("rendered") and not status.get("token"):
                raise BotBlockedError(
                    f"{step_label}: the form gave up with -- {modal} -- having "
                    f"rendered a Cloudflare Turnstile widget that never issued "
                    f"a token, so the submission carried no proof of a human."
                )
            raise PageMismatchError(f"{step_label}: the form rejected the data -- {modal}")

        # A challenge nobody has answered, whatever the button is doing.
        #
        # Turnstile here is `interaction-only`, and on this screen it does not
        # gate the button up front -- Continue is enabled, the click goes
        # through, and only *then* does Cloudflare escalate and draw a "Verify
        # you are human" checkbox. Nothing ticks it, so the form sits there.
        # That is the real reason step 9 never came back, and it is visible
        # only in the screenshot: every other signal looks like a slow lookup.
        #
        # Checked before the busy test, not inside it: the spinner stops once
        # the app gives up waiting, and a check that only ran while the button
        # was spinning would miss the checkbox that is still on screen.
        # Checked on every pass, because the widget appears partway through.
        if turnstile.state(sb).get("widgetShowing"):
            if not wait_for_turnstile(sb, cfg, step_label):
                raise BotBlockedError(
                    f"{step_label}: Cloudflare drew a 'Verify you are human' "
                    f"checkbox after Continue was pressed and nothing answered "
                    f"it. Re-run with --solve-challenges and a visible window "
                    f"to tick it by hand."
                )
            # Answered: give the form its budget back to finish the job.
            deadline = min(time.time() + budget, hard_deadline)
            time.sleep(poll)
            continue

        # Work in progress is not a stalled screen: keep the clock rolling for
        # as long as the form is visibly busy, up to the hard deadline.
        if is_busy(sb):
            status = turnstile.state(sb)

            # Turnstile failing while the spinner is still turning ends the
            # wait there and then. The app will keep spinning until its own
            # timeout -- measured at ten minutes on this screen -- and then
            # show "(600)", so without this the run spends those ten minutes
            # waiting for an answer that was already decided.
            code = status.get("errorCode")
            if code:
                raise BotBlockedError(
                    f"{step_label}: the form was still working when "
                    f"{turnstile.explain_error(code)}. The submission behind "
                    f"this screen cannot succeed without a token."
                )

            if not announced_busy:
                # A spinner with no widget behind it is the failure this form
                # dies of: `<ngx-turnstile>` sits empty because Cloudflare's
                # script never executed, so no token can ever arrive and the
                # button it gates spins until something gives up. Try to get
                # the script loaded rather than waiting out a clock for an
                # event that cannot happen.
                if not status.get("rendered") and not status.get("apiLoaded"):
                    if turnstile.ensure_api_loaded(sb, step_label):
                        # The app's own component can render now. Give the
                        # screen its budget back to finish the job.
                        deadline = min(time.time() + budget, hard_deadline)
                        announced_busy = True
                        time.sleep(poll)
                        continue
                    raise BotBlockedError(
                        f"{step_label}: Cloudflare's Turnstile script will not "
                        f"load in this browser, so the form's widget was never "
                        f"created and its Continue button stays disabled. The "
                        f"spinner is waiting for a token that cannot arrive."
                    )

                if status.get("rendered") and not status.get("token"):
                    # A widget really is up and has not answered yet. Worth
                    # saying, and worth waiting for -- but no longer worth
                    # nudging: a reset here is what used to discard a token
                    # that had just arrived through the callback.
                    LOG.info(
                        "%s: the form is busy and a Turnstile widget is still "
                        "deciding. Waiting up to %.0fs.",
                        step_label, cfg.max_busy_wait,
                    )
                else:
                    # `is_busy` matches a spinner on a disabled button, and on
                    # this screen that is what the app shows while it runs the
                    # eligibility lookup -- which takes minutes, by design. With
                    # no widget rendered there is no bot wall to blame, and a
                    # spinner is the app working until it stops being one.
                    LOG.info(
                        "%s: the form is working on it (spinner on the button); "
                        "waiting up to %.0fs more", step_label, cfg.max_busy_wait,
                    )
                announced_busy = True
            deadline = min(time.time() + budget, hard_deadline)
            time.sleep(poll)
            continue

        after = screen_headings(sb)
        if after and after != before:
            if is_consent_screen(after):
                # Not progress: the banner opened over the form. Clear it and
                # keep waiting for the screen underneath to actually change.
                LOG.info("Consent dialog opened over the form; dismissing it")
                dismiss_consent(sb)
                time.sleep(poll)
                continue
            LOG.info("Advanced to: %s", after)
            return after
        time.sleep(poll)

    # Nothing moved, and the form is no longer working on it. *Now* an
    # unresolved Turnstile is worth reporting: the widget is on the screen,
    # it has issued no token, nothing is spinning any more, and the button it
    # gates is still disabled. Judged here rather than in the busy loop above,
    # because up there a missing token is indistinguishable from a lookup that
    # simply has not finished.
    if not is_busy(sb):
        status = turnstile.state(sb)
        if status.get("errorCode"):
            raise BotBlockedError(
                f"{step_label}: the form went idle and "
                f"{turnstile.explain_error(status['errorCode'])}"
            )
        if status.get("rendered") and not status.get("token"):
            raise BotBlockedError(
                f"{step_label}: the form went idle with Continue still disabled "
                f"and Cloudflare Turnstile holding no token, so it could not be "
                f"submitted."
            )

    # Before calling that a stuck form, check whether something was put in
    # front of it: steps from 5 on work inside the enrollment frame and never
    # call settle(), so an interstitial or a block page served in here is
    # invisible to every check the early steps rely on. Left unlooked for, it
    # presents exactly as "the screen never changed".
    interruption = frame_interruption(sb)
    if interruption:
        raise PageMismatchError(
            f"{step_label}: the screen never changed because something is in "
            f"front of it -- {interruption}"
        )

    errors = validation_errors(sb)

    if announced_busy and is_busy(sb):
        status = turnstile.state(sb)
        if status.get("errorCode"):
            raise BotBlockedError(
                f"{step_label}: after {cfg.max_busy_wait:.0f}s, "
                f"{turnstile.explain_error(status['errorCode'])}"
            )
        if status.get("rendered") and not status.get("token"):
            raise BotBlockedError(
                f"{step_label}: Cloudflare Turnstile never issued a token after "
                f"{cfg.max_busy_wait:.0f}s, so Continue stayed disabled. "
                + (
                    "Its challenge was on screen waiting to be solved -- run "
                    "with --keep-open and clear it by hand to confirm."
                    if status.get("widgetShowing")
                    else "It was refused silently, which is what Cloudflare does "
                         "to an IP it has already judged."
                )
            )

        # Still spinning with no Turnstile involved: the backend behind this
        # screen never answered. That is the host's problem, not the page's.
        raise ThrottledError(
            f"{step_label}: the form was still processing after "
            f"{cfg.max_busy_wait:.0f}s and never answered. The enrollment "
            f"host's lookup behind this screen is not responding."
        )

    raise PageMismatchError(
        f"{step_label}: clicked Continue but the screen never changed. "
        + (f"Form errors: {errors}" if errors else "No validation message was shown.")
    )


# Every radio on the screen, visible or not, with the text of its label. The
# enrollment app hides the inputs themselves and paints the labels, so these
# never appear in the element inventory and a click on the input lands on
# whatever is drawn over it -- the label is what has to be clicked.
_RADIO_JS = r"""
const labelFor = (el) => {
  let text = '';
  if (el.id) {
    const lab = document.querySelector('label[for="' + el.id + '"]');
    if (lab) text = lab.innerText || '';
  }
  if (!text && el.closest('label')) text = el.closest('label').innerText || '';
  return text.replace(/\s+/g, ' ').trim().slice(0, 120);
};
return Array.from(document.querySelectorAll('input[type=radio]')).map((el, i) => ({
  index: i,
  id: el.id || null,
  name: el.getAttribute('name') || null,
  value: el.value,
  checked: el.checked,
  label: labelFor(el)
}));
"""


# Select a radio and report what the group actually ends up holding.
#
# Two things this gets right that the previous version did not:
#
#   * It finds the input by id first, falling back to the positional index.
#     The index comes from a *separate* querySelectorAll in read_radios, and
#     this is an Angular screen that re-renders between the two calls -- so
#     the index can point at a different radio by the time it is used. On the
#     eligible-applicant screen that meant asking for "I am the Eligible
#     Applicant" and selecting "My Child or Dependent" instead, which the
#     server then answered with a confirm-you-meant-a-dependent modal.
#
#   * It reports the label of whatever is genuinely checked afterwards. The
#     old script forced `el.checked = true` and then returned `el.checked`,
#     so it answered "yes, selected" every single time, including when it had
#     just selected the wrong thing.
_RADIO_PICK_JS = r"""
const wantIndex = arguments[0];
const wantId = arguments[1];
const all = () => Array.from(document.querySelectorAll('input[type=radio]'));

const el = (wantId && document.getElementById(wantId)) || all()[wantIndex];
if (!el) return {ok: false};

const labelOf = (r) => {
  let t = '';
  if (r.id) {
    const lab = document.querySelector('label[for="' + r.id + '"]');
    if (lab) t = lab.innerText || '';
  }
  if (!t && r.closest('label')) t = r.closest('label').innerText || '';
  return t.replace(/\s+/g, ' ').trim();
};

// Never drive this by assigning `checked`. These radios carry no value
// attribute -- Angular binds them through RadioControlValueAccessor, which
// reads the group on a `change` event. Clearing `checked` first leaves a
// moment where nothing in the group is selected, and a `change` seen during
// it writes the wrong option into the model: the app then asked to confirm
// qualifying "through a child or dependent" on a run that had chosen "I am
// the Eligible Applicant".
//
// So: click it if it is not selected, and if it already is, just tell Angular
// to re-read the group. Either way the DOM never passes through a state the
// form could misread.
const lab = el.id ? document.querySelector('label[for="' + el.id + '"]') : null;
if (!el.checked) {
  (lab || el).click();
}
el.dispatchEvent(new Event('change', {bubbles: true}));

const group = el.getAttribute('name');
const chosen = all().filter(r => r.getAttribute('name') === group && r.checked);

// Angular's own view of the field. A radio the *user* changed reads
// ng-valid ng-dirty ng-touched; one that only looks checked in the DOM does
// not, and the server is then sent nothing -- which is what the app answers
// with "Unable to continue ... (600)". Reporting it lets the caller tell a
// real selection from a cosmetic one instead of guessing after the fact.
const ng = (el.className || '').split(/\s+/).filter(c => c.indexOf('ng-') === 0);

return {
  ok: el.checked,
  id: el.id || null,
  chosenLabel: chosen.length ? labelOf(chosen[0]) : '',
  chosenCount: chosen.length,
  ngClasses: ng,
  ngModelSet: ng.indexOf('ng-dirty') !== -1 || ng.indexOf('ng-touched') !== -1
};
"""


_RADIO_STATE_JS = r"""
const id = arguments[0];
const all = Array.from(document.querySelectorAll('input[type=radio]'));
const el = id ? document.getElementById(id) : all[arguments[1]];
if (!el) return null;
const labelOf = (r) => {
  let t = '';
  if (r.id) { const l = document.querySelector('label[for="' + r.id + '"]'); if (l) t = l.innerText || ''; }
  if (!t && r.closest('label')) t = r.closest('label').innerText || '';
  return t.replace(/\s+/g, ' ').trim();
};
const group = el.getAttribute('name');
const chosen = all.filter(r => r.getAttribute('name') === group && r.checked);
const ng = (el.className || '').split(/\s+/).filter(c => c.indexOf('ng-') === 0);
return {
  ok: el.checked,
  id: el.id || null,
  chosenLabel: chosen.length ? labelOf(chosen[0]) : '',
  chosenCount: chosen.length,
  ngClasses: ng,
  ngModelSet: ng.indexOf('ng-dirty') !== -1 || ng.indexOf('ng-touched') !== -1
};
"""


def _radio_state(sb, target: dict) -> dict:
    """Read-only view of one radio and its group. Touches nothing."""
    try:
        return sb.execute_script(
            _RADIO_STATE_JS, target.get("id"), target.get("index")
        ) or {}
    except Exception:
        return {}


def _radio_selector(radio: dict) -> str | None:
    """What to aim a real click at -- the label, which is what a person hits."""
    rid = radio.get("id")
    return f'label[for="{rid}"]' if rid else None


def _select_radio(sb, target: dict, group: list[dict], cfg: RunConfig, label: str) -> dict:
    """Choose a radio with real, trusted clicks wherever possible.

    Why this matters more than it looks: a JS `.click()` and a hand-built
    `new Event('change')` both arrive with `isTrusted: false`, and that is the
    single clearest "not a person" signal a page can read. Measured in this
    project's own browser: JS click -> isTrusted False, WebDriver click ->
    isTrusted True. The old code used the JS path on the eligible-applicant
    screen -- which is exactly the screen where Cloudflare escalates to a
    visible checkbox for this run and never does for a human on the same
    profile.

    The awkward part is that the site renders this radio pre-selected while
    Angular's model behind it is empty, and clicking an already-checked radio
    fires `click` but never `change`, so the model stays empty and the submit
    comes back "(600)". The old fix was to force the state in JS. This does it
    with real clicks instead: click the *other* option first, then the one we
    want, so the browser itself produces a genuine change event. Two trusted
    clicks beat one untrusted one.
    """
    selector = _radio_selector(target)
    before = _radio_state(sb, target)

    if selector:
        try:
            # Put the label where a real click can actually land.
            #
            # A native click needs the element inside the *top-level*
            # viewport, and `scrollIntoView` inside this frame does nothing --
            # the frame is taller than the window, so it has no scrollbar of
            # its own and the outer page never moves. The click is then
            # refused as out of view, we fall back to a scripted one, and the
            # untrusted event lands on the single screen where it costs most.
            # Scrolling the outer page first is what makes the trusted click
            # possible at all.
            bring_framed_element_into_view(sb, selector, cfg)
            # Make the click a real state change, without ever selecting the
            # wrong option.
            #
            # Clicking a label whose radio is already checked fires `click`
            # but never `change`, and Angular's radio binding listens for
            # `change` -- so the model keeps whatever it had (nothing), the
            # submit goes up empty and the server answers "(600)". Measured:
            # a run where the radio ended ng-pristine got (600) in fourteen
            # seconds and the site never even asked its confirmation
            # question; a run where it ended ng-dirty ng-touched got through
            # to that question.
            #
            # So the property is cleared first and then a *real* click does
            # the selecting. The script only writes `checked = false` -- it
            # dispatches nothing, fabricates no events -- and the change
            # event that follows is the browser's own, from a trusted click
            # on the option we actually want. That is what the earlier
            # version got right and the "one clean click" rewrite lost.
            try:
                sb.execute_script(
                    "const el = document.getElementById(arguments[0]);"
                    "if (el && el.checked) { el.checked = false; }",
                    target.get("id"),
                )
            except Exception as exc:
                LOG.debug("Could not clear %s before clicking: %s", selector, exc)

            # Deliberately NOT bouncing through the other option first.
            #
            # An earlier version did, on the theory that a pre-selected radio
            # leaves Angular's model empty and only a real state change fixes
            # it. Measured, that backfired on this screen: clicking "My Child
            # or Dependent" makes the site open its "Please Confirm" dialog
            # immediately, the dialog then covers the page, the follow-up
            # click on the right option is refused as intercepted, and the
            # run falls back to a scripted click -- an untrusted event on the
            # one screen where that costs most. It also leaves a confirmation
            # on screen claiming a qualification route the applicant does not
            # have.
            #
            # The premise was wrong too: ng-dirty and ng-touched mean "a user
            # has interacted with this control", not "the model holds a
            # value". A field the app rendered pre-selected is pristine by
            # definition, so their absence says nothing about the model.
            #
            # One click, on the option we actually want.
            human_click(sb, selector, cfg)
            pause(cfg, 0.3)

            state = _radio_state(sb, target)
            if state.get("ok") and state.get("ngModelSet"):
                return state

            if state.get("ok"):
                # Checked, but Angular still shows it pristine -- the change
                # event did not land, and this screen answers that with a
                # "(600)" rather than a validation message. Worth one more
                # real click before settling for the scripted path.
                LOG.info(
                    "%s is checked but Angular still reads %s; clicking it once "
                    "more so the change registers",
                    label.capitalize(), state.get("ngClasses"),
                )
                try:
                    sb.execute_script(
                        "const el = document.getElementById(arguments[0]);"
                        "if (el && el.checked) { el.checked = false; }",
                        target.get("id"),
                    )
                    human_click(sb, selector, cfg)
                    pause(cfg, 0.3)
                    state = _radio_state(sb, target)
                    if state.get("ok") and state.get("ngModelSet"):
                        return state
                except RealInputError:
                    # --real-input refusing to degrade is a decision, not a
                    # mishap; swallowing it here would put the run back on the
                    # synthetic path it was told never to use.
                    raise
                except Exception as exc:
                    LOG.debug("Second real click on %s failed: %s", selector, exc)

            LOG.warning(
                "A real click on %s did not check it; falling back to scripted "
                "selection (which the site can tell apart from a person)", selector,
            )
        except Exception as exc:
            LOG.warning(
                "Could not click %s for real (%s); falling back to scripted "
                "selection", selector, exc,
            )

    # Last resort. Untrusted, and the site can see that -- but a form filled
    # imperfectly beats a form not filled at all.
    return sb.execute_script(
        _RADIO_PICK_JS, target["index"], target.get("id")
    ) or {}


def read_radios(sb) -> list[dict]:
    """Every radio on the screen, with its group name and label text."""
    try:
        radios = sb.execute_script(_RADIO_JS) or []
    except Exception as exc:
        LOG.warning("Could not read the screen's radio buttons: %s", exc)
        return []
    LOG.info(
        "Radio groups on screen: %s",
        sorted({r.get("name") for r in radios if r.get("name")}),
    )
    return radios


def answer_radio(sb, radios: list[dict], label: str, hints, answer: str, cfg: RunConfig) -> bool:
    """Pick `answer` in the radio group whose name matches one of `hints`.

    Returns whether the option ended up selected. A group that cannot be found
    is a warning rather than a failure: the form may already default it, and
    the screenshot shows what actually happened.
    """
    wanted = [
        r for r in radios
        if any(h in (r.get("name") or "").lower().replace(" ", "") for h in hints)
    ]

    if not wanted:
        # Group names are not always words. "Who is the Benefit Eligible
        # Applicant?" is `flagBQP`, which no sensible hint would match, so fall
        # back to the labels -- what the answer says is the reliable part.
        wanted = [
            r for r in radios
            if answer.strip().lower() == (r.get("label") or "").strip().lower()
        ]
        if wanted:
            LOG.info(
                "No radio group named like %r; matched %r on its label instead",
                label, answer,
            )

    if not wanted:
        LOG.warning(
            "No radio group found for %r (hints %s, answer %r). Leaving it at "
            "whatever the form defaults to. Groups on screen: %s",
            label, list(hints), answer,
            sorted({r.get("name") for r in radios if r.get("name")}),
        )
        return False

    target = next(
        (r for r in wanted
         if answer.lower() == (r.get("label") or "").strip().lower()
         or answer.lower() == (r.get("value") or "").strip().lower()),
        None,
    )
    if target is None:
        target = next(
            (r for r in wanted if answer.lower() in (r.get("label") or "").lower()),
            None,
        )
    if target is None:
        LOG.warning(
            "Radio group %r has no %r option; saw %s",
            label, answer, [(r.get("value"), r.get("label")) for r in wanted],
        )
        return False

    # A radio that already holds the wanted answer is left alone.
    #
    # This reverses an older rule that said to click it anyway, on the theory
    # that a pre-selected radio leaves Angular's model unset and the server
    # is sent nothing -- the documented cause of "Unable to continue ...
    # (600)". Every way of acting on that theory has now been tried on this
    # screen and every one still ended in (600):
    #
    #   forced scripted click        -> ng-dirty                  -> (600)
    #   one real click               -> ng-pristine               -> (600)
    #   clear then real click        -> ng-dirty ng-touched       -> (600)
    #
    # Leaving it untouched is the one case never tested, and it is also what
    # a person does: nobody clicks a radio that is already on the answer they
    # want, so any click here is an interaction a real applicant would not
    # have produced. If the value is right, the only thing left to do is
    # press Continue.
    if target.get("checked") and cfg.application.skip_preselected_radios:
        LOG.info(
            "%s already shows %s; leaving it as it is and moving on",
            label.capitalize(), answer,
        )
        return True

    # Select it, then confirm against the form rather than against our intent.
    result = _select_radio(sb, target, wanted, cfg, label)
    pause(cfg, 0.3)

    # What the group actually holds now, which is not the same question as
    # "did our click run". The form is the authority here, not our intent.
    chosen = result.get("chosenLabel") or ""
    if not result.get("ok"):
        LOG.warning("Clicked %s = %s but the radio did not take", label, answer)
        return False

    if chosen and chosen.strip().lower() != answer.strip().lower():
        # The wrong option ended up selected. Worth failing on rather than
        # carrying on: this screen decides who the benefit is being claimed
        # for, and the application means something different if it is wrong.
        LOG.error(
            "Asked for %r on %s but the form now has %r selected",
            answer, label, chosen,
        )
        return False

    # Say whether Angular actually registered the change, not just whether the
    # DOM looks right. These two disagreeing is the documented cause of the
    # app's "(600)" failure, and it is cheap to notice here rather than infer
    # it from a server error several minutes later.
    # Note the interaction state, but do not read anything into it.
    #
    # ng-pristine/ng-untouched mean "no user has interacted with this
    # control", not "the model is empty" -- a value the app rendered itself
    # is pristine by definition and perfectly valid. An earlier version of
    # this warned that a pristine control meant Angular had not registered
    # the value and was heading for a "(600)", and acted on that by clicking
    # the wrong option to force a change event. That was wrong on both
    # counts and caused a confirmation dialog that blocked the real click.
    # ng-valid is the part that actually speaks to validity.
    LOG.debug(
        "%s: %s, Angular state %s",
        label, chosen or answer, result.get("ngClasses") or "no ng-* classes",
    )

    LOG.info("Answered %s: %s", label, chosen or answer)
    return True
