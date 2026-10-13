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

ENROLLMENT_FRAME = "#enrollment-frame"

CHALLENGE_IFRAME_HINTS = (
    "challenges.cloudflare.com",
    "turnstile",
)

CHALLENGE_TEXT_SIGNALS = (
    "checking your browser",
    "verify you are human",
    "just a moment",
    "needs to review the security of your connection",
)

CHALLENGE_SOURCE_SIGNALS = (
    "_cf_chl_opt",
)


NETWORK_REPUTATION_SIGNALS = (
    "botnet activity detected",
    "automated attack traffic",
    "unbotnet.me",
)


def network_reputation_block(sb) -> str:
    try:
        body = body_text(sb).lower()
        source = (sb.get_page_source() or "").lower()
    except Exception:
        return ""
    for signal in NETWORK_REPUTATION_SIGNALS:
        if signal in body or signal in source:
            return signal
    return ""

CONSENT_SELECTORS = (
    "#onetrust-accept-btn-handler",
    "#truste-consent-button",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "button#accept-cookies",
    'button[aria-label*="Accept" i]',
    'button[title*="Accept" i]',
)


def apply_flaresolverr_cookies(sb, cfg: RunConfig, url: str) -> bool:
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
    sb.wait_for_ready_state_complete(timeout=cfg.page_timeout)
    ensure_page_window(sb)
    handle_captcha(sb)
    check_not_blocked(sb)
    dismiss_consent(sb)

    warm_up(sb, cfg)


def ensure_page_window(sb) -> None:
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
    if not challenge_present(sb):
        LOG.debug("No challenge frame on page; skipping captcha handling")
        return

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


THROTTLE_SIGNALS = (
    "can not be processed at this time",
    "cannot be processed at this time",
    "unable to process your request",
    "try again later",
)


def is_throttle_message(message: str) -> bool:
    lowered = (message or "").lower()
    return any(signal in lowered for signal in THROTTLE_SIGNALS)


RETRYABLE_SIGNALS = (
    "communication delay",
    "please click dismiss and then click",
    "to re-try",
)

MAX_RETRY_PROMPTS = 3


def is_retryable_message(message: str) -> bool:
    lowered = (message or "").lower()
    return any(signal in lowered for signal in RETRYABLE_SIGNALS)


VENDOR_OUTAGE_SIGNALS = (
    "api is offline",
    "contact solix",
)


def is_vendor_outage(message: str) -> bool:
    lowered = (message or "").lower()
    return any(signal in lowered for signal in VENDOR_OUTAGE_SIGNALS)


PROGRESS_MODAL_HINTS = (
    "please wait",
    "validating",
    "loading",
    "processing",
    "one moment",
)


CONFIRM_MODAL_HINTS = ("please confirm",)


def is_confirm_modal(message: str) -> bool:
    return any(hint in (message or "").lower() for hint in CONFIRM_MODAL_HINTS)


def answer_confirm_modal(sb, message: str, cfg: RunConfig, step_label: str) -> bool:
    if not modal_present(sb):
        LOG.info("%s: the confirmation closed before it needed answering", step_label)
        return True

    lowered = (message or "").lower()

    if "child or dependent" in lowered:
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
    try:
        return bool(sb.execute_script(
            "return !!document.querySelector("
            "  'modal-container.show, modal-container[role=dialog], .modal.show');"
        ))
    except Exception:
        return False


def wait_for_modal_to_clear(sb, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not modal_present(sb):
            return True
        time.sleep(0.4)
    return not modal_present(sb)


def _click_modal_button(sb, text: str, cfg: RunConfig) -> bool:
    try:
        selector = sb.execute_script(_TAG_MODAL_BUTTON_JS, text)
    except Exception as exc:
        LOG.debug("Could not find the %r button: %s", text, exc)
        return False

    if not selector:
        return False

    try:
        bring_framed_element_into_view(sb, selector, cfg)
        human_click(sb, selector, cfg)
        return True
    except RealInputError:
        raise
    except Exception as exc:
        LOG.warning("Could not click the %r button for real: %s", text, exc)
        return False


def is_progress_modal(message: str) -> bool:
    lowered = (message or "").lower()
    return any(hint in lowered for hint in PROGRESS_MODAL_HINTS)


def modal_message(sb) -> str | None:
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
    try:
        return sb.execute_script(_FORM_VALIDITY_JS) or {}
    except Exception:
        return {}


def toast_message(sb) -> str | None:
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
    for selector in selectors:
        try:
            if sb.is_element_visible(selector):
                return selector
        except Exception:
            continue
    return None


_STORAGE_REPORTED = False


def _report_frame_storage(sb, step_label: str) -> None:
    global _STORAGE_REPORTED
    if _STORAGE_REPORTED:
        return
    _STORAGE_REPORTED = True
    try:
        environment.storage_report(sb, step_label)
    except Exception as exc:
        LOG.debug("%s: frame storage check failed: %s", step_label, exc)


def enter_enrollment_frame(sb, cfg: RunConfig, step_label: str) -> str:
    sb.switch_to_default_content()
    real_input.set_frame_origin(None)

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

    _report_frame_storage(sb, step_label)

    turnstile.install_now(sb, cfg)

    apply_flaresolverr_cookies(sb, cfg, frame_url)

    _look_before_touching(sb, cfg)

    return frame_url


def _align_frame_to_viewport(sb, cfg: RunConfig, step_label: str) -> None:
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
        if origin and origin.get("scrollBy"):
            smooth_scroll(sb, origin["scrollBy"], cfg)
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
        LOG.error("%s: bug in frame alignment -- %s", step_label, exc)
        real_input.set_frame_origin(None)
    except Exception as exc:
        LOG.debug("%s: could not align the enrollment frame: %s", step_label, exc)
        real_input.set_frame_origin(None)


def bring_framed_element_into_view(sb, selector: str, cfg: RunConfig | None = None) -> bool:
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
        if came_from_frame:
            try:
                sb.switch_to_frame(ENROLLMENT_FRAME)
            except Exception as exc:
                LOG.warning("Could not re-enter the enrollment frame after scrolling: %s", exc)
                return False

    return moved


def _look_before_touching(sb, cfg: RunConfig) -> None:
    if cfg.workers == 1 and not cfg.headless:
        real_input.focus_window(sb)

    if real_input.should_use(cfg):
        real_input.reading_pause(cfg)
        return

    rest(sb, cfg, "long")
    warm_up(sb, cfg)


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
                    document_loaded = True
                    deadline = time.time() + cfg.page_timeout
                    LOG.info("%s: frame loaded, waiting for the app to render", step_label)

                app = sb.execute_script(_APP_RENDERED_JS) or {}
                if app.get("controls") and not app.get("loading"):
                    return sb.execute_script("return window.location.href")
        except Exception:
            pass
        time.sleep(0.25)

    if document_loaded:
        raise PageMismatchError(
            f"{step_label}: the enrollment frame loaded but its application "
            f"never rendered any controls within {cfg.page_timeout}s. Usually a "
            f"slow connection; check the step's screenshot to be sure."
        )

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


ERROR_SELECTORS = (
    ".invalid-feedback",
    ".error-message",
    ".text-danger",
    "[class*='error']",
)


def screen_headings(sb) -> list[str]:
    try:
        return sb.execute_script(
            "return Array.from(document.querySelectorAll('h1,h2,h3,legend'))"
            ".map(e => e.innerText.trim()).filter(Boolean).slice(0, 10)"
        ) or []
    except Exception:
        return []


def validation_errors(sb) -> list[str]:
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
    return list(dict.fromkeys(messages))[:10]


REJECTION_SIGNALS = (
    ("invalid email address", BAD_EMAIL),
    ("email address is invalid", BAD_EMAIL),
    ("currently an assurance wireless customer", AW_TRANSFER),
    ("already an assurance wireless customer", AW_TRANSFER),
)


def rejection_verdict(message: str) -> str:
    lowered = (message or "").lower()
    return next((v for signal, v in REJECTION_SIGNALS if signal in lowered), "")


def frame_interruption(sb) -> str:
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


CONSENT_HEADINGS = (
    "do not sell my personal information",
    "manage consent preferences",
    "performance cookies",
    "privacy preference",
    "cookie",
)


def is_consent_screen(headings) -> bool:
    if not headings:
        return False
    lowered = [h.lower() for h in headings]
    return any(any(sig in h for sig in CONSENT_HEADINGS) for h in lowered)


BUSY_SELECTORS = (
    "button[disabled] .fa-spinner",
    "button[disabled] .fa-pulse",
    ".spinner-border",
    ".fa-spinner.fa-pulse",
)


def turnstile_state(sb) -> dict:
    return turnstile.state(sb)


def _wait_until_enabled(sb, selector: str, cfg: RunConfig, step_label: str) -> bool:
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
    status = turnstile.state(sb)

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

        code = status.get("errorCode")
        if code:
            LOG.error("%s: %s", step_label, turnstile.explain_error(code))
            if not retried and str(code).startswith("300"):
                retried = True
                turnstile.reset(sb, step_label, status)
                deadline = time.time() + cfg.turnstile_wait
                time.sleep(0.5)
                continue
            return False

        if status.get("expired") and not retried:
            retried = True
            LOG.info("%s: the Turnstile token expired before it was used", step_label)
            turnstile.reset(sb, step_label, status)

        if status.get("widgetShowing") and not asked:
            asked = True
            if not cfg.solve_challenges:
                LOG.error(
                    "%s: Cloudflare is asking for a human and nobody is watching. "
                    "Re-run with --solve-challenges (and a visible window) to "
                    "answer it yourself, or move the profiles to cleaner proxies "
                    "so it stops asking.", step_label,
                )
                return False

            deadline = time.time() + cfg.solve_challenge_wait
            LOG.warning(
                "%s: Cloudflare wants a human. Its checkbox is on screen in the "
                "browser window -- click it and the run picks up by itself. "
                "Waiting up to %.0fs.", step_label, cfg.solve_challenge_wait,
            )

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
    turnstile.reset(sb, step_label)


def _idle_signs_of_life(sb, cfg: RunConfig) -> None:
    if random.random() > 0.4:
        return
    idle_drift(sb, cfg)


def is_busy(sb) -> bool:
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
    allow_reclick: bool = False,
    first_look: float = 0.0,
) -> list[str]:
    selector = first_visible(sb, selectors)
    if selector is None:
        raise PageMismatchError(
            f"{step_label}: no visible Continue button. Tried: {', '.join(selectors)}"
        )

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

    wait_for_turnstile(sb, cfg, step_label)
    _wait_until_enabled(sb, selector, cfg, step_label)

    state = form_validity(sb)
    if state.get("formInvalid") or state.get("invalid"):
        LOG.warning(
            "%s: Angular considers the form invalid before submit. Offending "
            "controls: %s", step_label, state.get("invalid") or "(form-level)",
        )
    if state.get("radios"):
        LOG.info("%s: radio state at submit: %s", step_label, state["radios"])

    rest(sb, cfg, "long")

    before = screen_headings(sb)
    LOG.info("Clicking Continue via %s", selector)
    bring_framed_element_into_view(sb, selector, cfg)
    human_click(sb, selector, cfg)

    if settle > 0:
        quiet = min(first_look, settle) if first_look > 0 else settle
        LOG.info(
            "%s: hands off for %.0fs while the form works -- no driver "
            "traffic at all", step_label, quiet,
        )
        time.sleep(quiet)
        if quiet < settle:
            moved = screen_headings(sb)
            if moved and moved != before and not is_busy(sb):
                LOG.info("%s: next screen already up after %.0fs", step_label, quiet)
            else:
                time.sleep(settle - quiet)

    if _nothing_happened_yet(sb, before) and not _click_landed(sb, selector):
        LOG.warning(
            "%s: the click never reached Continue, so the app saw nothing. "
            "Re-aiming and clicking once more.", step_label,
        )
        try:
            bring_framed_element_into_view(sb, selector, cfg)
            human_click(sb, selector, cfg)
        except Exception as exc:
            LOG.warning("%s: could not re-aim at Continue: %s", step_label, exc)
        else:
            if settle > 0:
                LOG.info(
                    "%s: hands off for %.0fs after re-aiming", step_label, settle
                )
                time.sleep(settle)

    budget = timeout or cfg.page_timeout
    deadline = time.time() + budget
    hard_deadline = time.time() + max(budget, cfg.max_busy_wait)
    announced_busy = False

    poll = 2.0

    retries = 0

    while time.time() < deadline and time.time() < hard_deadline:
        modal = modal_message(sb)
        if modal:
            if is_progress_modal(modal):
                LOG.info("Waiting on the form: %s", modal)
                time.sleep(poll)
                continue
            if is_throttle_message(modal):
                raise ThrottledError(f"{step_label}: the host is refusing us -- {modal}")

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
                if answer_confirm_modal(sb, modal, cfg, step_label):
                    time.sleep(poll)
                    continue
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
                if verdict == AW_TRANSFER:
                    raise LeadRejectedError(
                        f"{step_label}: this applicant already has Assurance "
                        f"Wireless service -- {modal}", verdict,
                    )
                raise LeadRejectedError(
                    f"{step_label}: the form rejected this lead -- {modal}", verdict
                )

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

        if turnstile.state(sb).get("widgetShowing"):
            if not wait_for_turnstile(sb, cfg, step_label):
                raise BotBlockedError(
                    f"{step_label}: Cloudflare drew a 'Verify you are human' "
                    f"checkbox after Continue was pressed and nothing answered "
                    f"it. Re-run with --solve-challenges and a visible window "
                    f"to tick it by hand."
                )
            deadline = min(time.time() + budget, hard_deadline)
            time.sleep(poll)
            continue

        if is_busy(sb):
            status = turnstile.state(sb)

            code = status.get("errorCode")
            if code:
                raise BotBlockedError(
                    f"{step_label}: the form was still working when "
                    f"{turnstile.explain_error(code)}. The submission behind "
                    f"this screen cannot succeed without a token."
                )

            if not announced_busy:
                if not status.get("rendered") and not status.get("apiLoaded"):
                    if turnstile.ensure_api_loaded(sb, step_label):
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
                    LOG.info(
                        "%s: the form is busy and a Turnstile widget is still "
                        "deciding. Waiting up to %.0fs.",
                        step_label, cfg.max_busy_wait,
                    )
                else:
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
                LOG.info("Consent dialog opened over the form; dismissing it")
                dismiss_consent(sb)
                time.sleep(poll)
                continue
            LOG.info("Advanced to: %s", after)
            return after
        time.sleep(poll)

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

        raise ThrottledError(
            f"{step_label}: the form was still processing after "
            f"{cfg.max_busy_wait:.0f}s and never answered. The enrollment "
            f"host's lookup behind this screen is not responding."
        )

    _log_required_state(sb, step_label)

    _log_click_landed(sb, step_label, selector)

    if allow_reclick and not errors:
        moved = _press_continue_again(
            sb, cfg, step_label, selector, before, budget, settle
        )
        if moved:
            return moved

    raise PageMismatchError(
        f"{step_label}: clicked Continue but the screen never changed. "
        + (f"Form errors: {errors}" if errors else "No validation message was shown.")
        + (" A second Continue did not move it either, so the click is landing "
           "and the host is not answering." if allow_reclick else "")
    )


def _press_continue_again(
    sb, cfg: RunConfig, step_label: str, selector: str,
    before: list[str], budget: float, settle: float,
) -> list[str] | None:
    if not first_visible(sb, (selector,)):
        LOG.warning(
            "%s: Continue is no longer on the screen, so there is nothing to "
            "press again", step_label,
        )
        return None

    LOG.warning(
        "%s: the screen gave no reason for staying put -- pressing Continue "
        "once more to find out whether the first click reached it", step_label,
    )

    try:
        bring_framed_element_into_view(sb, selector, cfg)
        human_click(sb, selector, cfg)
    except Exception as exc:
        LOG.warning("%s: the second Continue could not be clicked: %s", step_label, exc)
        return None

    if settle > 0:
        LOG.info("%s: hands off for %.0fs after the second Continue", step_label, settle)
        time.sleep(settle)

    deadline = time.time() + budget
    while time.time() < deadline:
        modal = modal_message(sb)
        if modal and not is_progress_modal(modal):
            verdict = rejection_verdict(modal)
            if verdict:
                raise LeadRejectedError(
                    f"{step_label}: the form rejected this lead on a second "
                    f"Continue -- {modal}", verdict,
                )
            LOG.warning(
                "%s: the second Continue produced a message rather than a new "
                "screen -- %s", step_label, modal,
            )
            return None

        if is_busy(sb):
            deadline = min(time.time() + budget, deadline + 2.0)
            time.sleep(2.0)
            continue

        after = screen_headings(sb)
        if after and after != before:
            LOG.warning(
                "%s: the second Continue moved it. The first click was not "
                "reaching the button -- this is ours, not the host's.",
                step_label,
            )
            return after
        time.sleep(2.0)

    LOG.warning(
        "%s: the second Continue did nothing either, so the clicks are landing "
        "and the host is not answering", step_label,
    )
    return None


_FOCUS_AFTER_CLICK_JS = r"""
const want = document.querySelector(arguments[0]);
const active = document.activeElement;
const name = (n) => {
  if (!n) return null;
  const cls = (typeof n.className === 'string' && n.className.trim())
      ? '.' + n.className.trim().split(/\s+/).join('.') : '';
  return n.tagName.toLowerCase() + (n.id ? '#' + n.id : '') + cls;
};
return {
  found: !!want,
  focused: !!(want && active && (active === want || want.contains(active))),
  active: name(active),
  disabled: !!(want && want.disabled)
};
"""


def _click_landed(sb, selector: str) -> bool:
    try:
        state = sb.execute_script(_FOCUS_AFTER_CLICK_JS, selector) or {}
    except Exception:
        return True
    if not state.get("found"):
        return True
    return bool(state.get("focused"))


def _nothing_happened_yet(sb, before: list[str]) -> bool:
    try:
        if is_busy(sb):
            return False
        if modal_present(sb):
            return False
        after = screen_headings(sb)
        return not after or after == before
    except Exception:
        return False


def _log_click_landed(sb, step_label: str, selector: str) -> None:
    try:
        state = sb.execute_script(_FOCUS_AFTER_CLICK_JS, selector) or {}
    except Exception as exc:
        LOG.debug("%s: could not read what holds focus: %s", step_label, exc)
        return

    if not state.get("found"):
        LOG.warning("%s: the Continue button is no longer on the screen", step_label)
        return

    if state.get("focused"):
        LOG.warning(
            "%s: Continue still holds focus, so the click did reach it and the "
            "app simply never answered. This is the host, not the click.",
            step_label,
        )
    else:
        LOG.warning(
            "%s: Continue does not hold focus -- %s does. The click did not "
            "reach the button, so the app never saw it. This is ours.",
            step_label, state.get("active") or "nothing",
        )


_REQUIRED_STATE_JS = r"""
const out = {groups: {}, fields: [], invalid: []};

for (const el of document.querySelectorAll('input[type=radio], input[type=checkbox]')) {
  const name = el.getAttribute('name') || el.id || '(unnamed)';
  const g = out.groups[name] || (out.groups[name] = {options: 0, set: null, required: false});
  g.options += 1;
  if (el.required) g.required = true;
  if (el.checked) g.set = el.value || el.id || true;
}

for (const el of document.querySelectorAll('input:not([type=radio]):not([type=checkbox]), select, textarea')) {
  if (el.type === 'hidden' || !el.offsetParent) continue;
  const id = el.id || el.getAttribute('name');
  if (!id) continue;
  out.fields.push({
    field: id,
    required: !!el.required,
    filled: !!(el.value && String(el.value).trim()),
  });
  if (el.classList.contains('ng-invalid')) out.invalid.push(id);
}

for (const el of document.querySelectorAll('.ng-invalid[id]')) {
  if (out.invalid.indexOf(el.id) === -1) out.invalid.push(el.id);
}
return out;
"""


def _log_required_state(sb, step_label: str) -> None:
    try:
        state = sb.execute_script(_REQUIRED_STATE_JS) or {}
    except Exception as exc:
        LOG.debug("%s: could not read the screen's control state: %s", step_label, exc)
        return

    unset = [
        name for name, g in (state.get("groups") or {}).items()
        if g.get("required") and g.get("set") is None
    ]
    empty = [
        f["field"] for f in (state.get("fields") or [])
        if f.get("required") and not f.get("filled")
    ]

    LOG.warning(
        "%s: required controls at the stall -- %s; %s; %s", step_label,
        f"radio/checkbox groups with nothing selected: {unset}" if unset
        else "every required radio/checkbox group has a selection",
        f"empty required fields: {empty}" if empty
        else "every required field has a value",
        f"marked invalid by the app: {state.get('invalid')}"
        if state.get("invalid") else "nothing marked invalid by the app",
    )


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
    try:
        return sb.execute_script(
            _RADIO_STATE_JS, target.get("id"), target.get("index")
        ) or {}
    except Exception:
        return {}


def _radio_selector(radio: dict) -> str | None:
    rid = radio.get("id")
    return f'label[for="{rid}"]' if rid else None


def _select_radio(sb, target: dict, group: list[dict], cfg: RunConfig, label: str) -> dict:
    selector = _radio_selector(target)
    before = _radio_state(sb, target)

    if selector:
        try:
            bring_framed_element_into_view(sb, selector, cfg)
            try:
                sb.execute_script(
                    "const el = document.getElementById(arguments[0]);"
                    "if (el && el.checked) { el.checked = false; }",
                    target.get("id"),
                )
            except Exception as exc:
                LOG.debug("Could not clear %s before clicking: %s", selector, exc)

            human_click(sb, selector, cfg)
            pause(cfg, 0.3)

            state = _radio_state(sb, target)
            if state.get("ok") and state.get("ngModelSet"):
                return state

            if state.get("ok"):
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

    return sb.execute_script(
        _RADIO_PICK_JS, target["index"], target.get("id")
    ) or {}


def read_radios(sb) -> list[dict]:
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
    wanted = [
        r for r in radios
        if any(h in (r.get("name") or "").lower().replace(" ", "") for h in hints)
    ]

    if not wanted:
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

    if target.get("checked") and cfg.application.skip_preselected_radios:
        LOG.info(
            "%s already shows %s; leaving it as it is and moving on",
            label.capitalize(), answer,
        )
        return True

    result = _select_radio(sb, target, wanted, cfg, label)
    pause(cfg, 0.3)

    chosen = result.get("chosenLabel") or ""
    if not result.get("ok"):
        LOG.warning("Clicked %s = %s but the radio did not take", label, answer)
        return False

    if chosen and chosen.strip().lower() != answer.strip().lower():
        LOG.error(
            "Asked for %r on %s but the form now has %r selected",
            answer, label, chosen,
        )
        return False

    LOG.debug(
        "%s: %s, Angular state %s",
        label, chosen or answer, result.get("ngClasses") or "no ng-* classes",
    )

    LOG.info("Answered %s: %s", label, chosen or answer)
    return True
