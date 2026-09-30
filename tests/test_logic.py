"""Tests for the parts that decide things, which are the parts worth pinning.

Nothing here opens a browser or touches the site. These cover the pure logic
the run leans on: how a lead gets bucketed, which failures are worth another
browser, and how the SeleniumBase-shaped selectors are translated -- each of
which cost a real run to discover the first time.

    python -m pytest tests -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot.classify import (  # noqa: E402
    BAD_EMAIL,
    GOOD,
    NEED_DOCUMENTS,
    REJECTED,
    UNKNOWN,
    classify_screen,
    is_terminal,
)
from aw_bot.errors import BotBlockedError  # noqa: E402
from aw_bot.page_utils import (  # noqa: E402
    challenge_present,
    check_not_blocked,
    frame_interruption,
    is_busy,
    is_consent_screen,
    is_confirm_modal,
    network_reputation_block,
    rejection_verdict,
    turnstile_state,
)
from aw_bot import real_input  # noqa: E402
from aw_bot.config import RunConfig  # noqa: E402
from aw_bot.runner import _browser_died  # noqa: E402
from aw_bot.steps.step_00_direct_frame import encode_email  # noqa: E402
from aw_bot.sb_shim import _by, _text  # noqa: E402


# --------------------------------------------------------------------------
# classify: which bucket a screen puts the lead in
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "heading, expected",
    [
        ("Income and Demographic Information", GOOD),
        ("ALMOST DONE! Upload Your Qualifying and Identity Proof Documents", NEED_DOCUMENTS),
        ("Consent to Transfer LifeLine Benefit", REJECTED),
    ],
)
def test_known_screens_are_classified(heading, expected):
    verdict, why = classify_screen([heading], "")
    assert verdict == expected
    assert why  # the reason is what makes an artifact readable later


def test_unseen_screen_is_unknown_not_guessed():
    verdict, why = classify_screen(["Service/Home/e911 Registered Address"], "body text")
    assert verdict == UNKNOWN
    assert "Service/Home/e911" in why


def test_no_headings_at_all_is_unknown():
    assert classify_screen([], "")[0] == UNKNOWN


def test_body_text_classifies_when_the_heading_does_not():
    verdict, _ = classify_screen(
        ["Almost there"], "you currently receive a california lifeline benefit with another "
        "service provider"
    )
    assert verdict == REJECTED


def test_document_request_wins_over_a_passing_mention_of_income():
    """Order matters: a doc-upload screen can mention income in passing, and
    calling that lead a sale would be the expensive mistake."""
    verdict, _ = classify_screen(
        ["ALMOST DONE! Upload Your Qualifying and Identity Proof Documents"],
        "income and demographic information will be requested later",
    )
    assert verdict == NEED_DOCUMENTS


def test_matching_ignores_case():
    assert classify_screen(["INCOME AND DEMOGRAPHIC INFORMATION"], "")[0] == GOOD


def test_terminal_verdicts():
    assert is_terminal(GOOD) and is_terminal(REJECTED) and is_terminal(NEED_DOCUMENTS)
    assert not is_terminal(UNKNOWN)


# --------------------------------------------------------------------------
# rejections the form makes before any decision screen
# --------------------------------------------------------------------------


def test_invalid_email_modal_becomes_a_verdict():
    message = "Important: Sorry, that's an invalid email address. Be sure it's correct."
    assert rejection_verdict(message) == BAD_EMAIL


def test_unrecognised_rejection_has_no_verdict():
    """An unfamiliar rejection must stay a failure rather than be mislabelled."""
    assert rejection_verdict("Please correct the highlighted fields") == ""
    assert rejection_verdict("") == ""


# --------------------------------------------------------------------------
# which failures deserve another browser
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "invalid session id: session deleted as the browser has closed the connection",
        "no such window: target window already closed",
        "disconnected: not connected to DevTools",
        "chrome not reachable",
    ],
)
def test_browser_gone_is_retryable(message):
    assert _browser_died(Exception(message))


@pytest.mark.parametrize(
    "message",
    [
        "Step 6: typed first name into #firstName but the field holds 'X'",
        "Element '#continue' did not become visible within 30s",
        "the form rejected this lead -- invalid email address",
    ],
)
def test_real_failures_are_not_retried(message):
    """Retrying these would resubmit the applicant, which is what makes the
    enrollment host start refusing."""
    assert not _browser_died(Exception(message))


# --------------------------------------------------------------------------
# selector translation: SeleniumBase's dialect -> plain Selenium
# --------------------------------------------------------------------------


def test_plain_css_is_left_alone():
    assert _by("#firstName") == ("css selector", "#firstName")
    assert _by("button.btn-outline") == ("css selector", "button.btn-outline")


def test_xpath_is_recognised():
    assert _by("//div[@id]")[0] == "xpath"


def test_contains_becomes_xpath():
    how, what = _by('button:contains("Start Application")')
    assert how == "xpath"
    assert what == '//button[contains(normalize-space(.), "Start Application")]'


def test_contains_keeps_a_class_qualifier():
    """`button.order-button:contains("Continue")` must not match the Back
    button, so the class has to survive the translation."""
    how, what = _by('button.order-button:contains("Continue")')
    assert how == "xpath"
    assert "order-button" in what and "Continue" in what


def test_contains_keeps_an_id_qualifier():
    _, what = _by('a#go:contains("Next")')
    assert '@id="go"' in what


def test_single_quoted_contains_works():
    _, what = _by("button:contains('Continue')")
    assert "Continue" in what


# --------------------------------------------------------------------------
# a closing window can answer with bytes
# --------------------------------------------------------------------------


def test_bytes_from_a_dying_window_become_text():
    assert _text(b"https://example.com/x") == "https://example.com/x"


def test_text_passthrough_and_none():
    assert _text("already a string") == "already a string"
    assert _text(None) == ""


# --------------------------------------------------------------------------
# things put in front of the form inside the frame
# --------------------------------------------------------------------------


class _FakeSb:
    """Just enough of the sb surface for frame_interruption."""

    def __init__(self, title="", body="", iframe_srcs=()):
        self._title, self._body, self._srcs = title, body, list(iframe_srcs)

    def get_title(self):
        return self._title

    def get_text(self, _selector):
        return self._body

    def execute_script(self, script, *args):
        return self._srcs if "iframe" in script else None


def test_akamai_block_inside_the_frame_is_named():
    sb = _FakeSb(title="Access Denied", body="You don't have permission to access")
    assert "block page" in frame_interruption(sb)


def test_turnstile_iframe_inside_the_frame_is_named():
    sb = _FakeSb(body="one moment", iframe_srcs=["https://challenges.cloudflare.com/x"])
    assert "challenge" in frame_interruption(sb)


def test_human_verification_wording_is_named():
    """"Verify you are human" is Cloudflare's wording, so it is now reported
    as the challenge it is rather than as a generic prompt."""
    assert "challenge" in frame_interruption(_FakeSb(body="please verify you are human"))


def test_an_ordinary_screen_is_not_an_interruption():
    sb = _FakeSb(title="Assurance Wireless Enrollment", body="Who is the Benefit Eligible Applicant?")
    assert frame_interruption(sb) == ""


# --------------------------------------------------------------------------
# real OS-level input: when it is allowed to take over the machine
# --------------------------------------------------------------------------


@pytest.mark.skipif(not real_input.AVAILABLE, reason="pyautogui not installed")
def test_real_input_is_used_when_asked_for():
    assert real_input.should_use(RunConfig(real_input=True))


def test_real_input_is_off_unless_asked_for():
    assert not real_input.should_use(RunConfig())


def test_real_input_refuses_headless():
    """There is no window to aim the cursor at."""
    assert not real_input.should_use(RunConfig(real_input=True, headless=True))


def test_real_input_refuses_parallel_workers():
    """One machine, one cursor: parallel workers would fight over it."""
    assert not real_input.should_use(RunConfig(real_input=True, workers=3))


# --------------------------------------------------------------------------
# the consent dialog is not a wizard screen
# --------------------------------------------------------------------------


def test_onetrust_panel_is_recognised_as_consent():
    """Seen live: this opened over the eligibility screen and was taken for
    the next step of the application."""
    assert is_consent_screen(
        ["Do Not Sell My Personal Information", "Manage Consent Preferences",
         "Performance Cookies"]
    )


def test_wizard_screens_are_not_consent():
    assert not is_consent_screen(["Who is the Benefit Eligible Applicant?"])
    assert not is_consent_screen(["Income and Demographic Information"])
    assert not is_consent_screen([])


# --------------------------------------------------------------------------
# "still working" is not "stuck"
# --------------------------------------------------------------------------


class _VisibilitySb:
    """Reports the given selectors as visible, everything else as not."""

    def __init__(self, visible=()):
        self.visible = set(visible)

    def is_element_visible(self, selector):
        return selector in self.visible


def test_spinner_on_a_disabled_button_is_busy():
    """What the eligibility screen actually shows while its lookup runs:
    <button disabled><span class="fa fa-spinner fa-pulse"></span>Continue"""
    assert is_busy(_VisibilitySb({"button[disabled] .fa-spinner"}))


def test_bootstrap_spinner_is_busy():
    assert is_busy(_VisibilitySb({".spinner-border"}))


def test_a_settled_screen_is_not_busy():
    assert not is_busy(_VisibilitySb())


def test_visibility_errors_do_not_count_as_busy():
    class Broken:
        def is_element_visible(self, selector):
            raise RuntimeError("frame swapped")

    assert not is_busy(Broken())


# --------------------------------------------------------------------------
# Cloudflare interstitials, including the one served as the page itself
# --------------------------------------------------------------------------


class _PageSb:
    """A page with a title, body text and source."""

    def __init__(self, title="", body="", source="", iframe_srcs=()):
        self._title, self._body = title, body
        self._source, self._srcs = source, list(iframe_srcs)

    def get_title(self):
        return self._title

    def get_text(self, _selector):
        return self._body

    def get_page_source(self):
        return self._source

    def execute_script(self, script, *args):
        return self._srcs if "iframe" in script else None


def test_challenge_page_is_caught_by_its_title():
    """The real one is titled "Checking your Browser...", which matched none
    of the block signals -- it was visible on screen while the code saw
    nothing."""
    assert challenge_present(_PageSb(title="Checking your Browser…"))


def test_challenge_page_is_caught_by_its_source():
    assert challenge_present(_PageSb(source="window._cf_chl_opt = {...}"))


def test_visible_turnstile_iframe_is_a_challenge():
    assert challenge_present(_PageSb(iframe_srcs=["https://challenges.cloudflare.com/x"]))


def test_embedded_invisible_turnstile_is_not_a_challenge():
    """The enrollment form carries a Turnstile widget on every screen. Counting
    its mere presence as a challenge made a refused token report as "something
    is in front of the form" on a screen where nothing was."""
    sb = _PageSb(title="Assurance Wireless Enrollment", body="Who is the Benefit Eligible Applicant?")
    sb._srcs = []  # the filter drops invisible frames before we see them
    assert not challenge_present(sb)


def test_ordinary_page_is_not_a_challenge():
    assert not challenge_present(
        _PageSb(title="Assurance Wireless", body="Apply now", source="<html>")
    )


def test_botnet_wording_is_a_network_verdict():
    sb = _PageSb(body="Botnet activity detected. Automated attack traffic ...")
    assert network_reputation_block(sb)


def test_network_block_says_the_network_is_the_problem():
    """The remedy differs from every other block: no fingerprint or pacing
    change clears an IP-reputation verdict, so the message must say so."""
    sb = _PageSb(body="botnet activity detected", source="unbotnet.me")
    with pytest.raises(BotBlockedError) as caught:
        check_not_blocked(sb)
    assert "network" in str(caught.value).lower()


def test_clean_page_is_not_blocked():
    check_not_blocked(_PageSb(title="Assurance Wireless", body="Apply now today"))


# --------------------------------------------------------------------------
# Turnstile is what the Continue button is actually waiting for
# --------------------------------------------------------------------------


class _ScriptSb:
    """Returns a canned result for execute_script."""

    def __init__(self, result):
        self.result = result

    def execute_script(self, script, *args):
        return self.result


def test_a_rendered_widget_without_a_token_is_the_gate():
    """The form cannot submit until the widget it rendered issues a token.

    Note `rendered`, not `present`. The distinction is the bug this replaced:
    the old reading treated the loader <script id="ngx-turnstile"> as a widget,
    so every screen from step 9's Continue onwards looked like it was waiting
    on a challenge that had never been asked for.
    """
    state = turnstile_state(_ScriptSb(
        {"rendered": True, "token": False, "widgetShowing": False}
    ))
    assert state["rendered"] and not state["token"]


def test_a_loaded_api_is_not_a_rendered_widget():
    """Downloading Turnstile's API says nothing about a challenge being up."""
    state = turnstile_state(_ScriptSb(
        {"apiLoaded": True, "rendered": False, "token": False}
    ))
    assert state["apiLoaded"] and not state["rendered"]


def test_a_visible_widget_means_interaction_was_demanded():
    state = turnstile_state(_ScriptSb(
        {"rendered": True, "token": False, "widgetShowing": True}
    ))
    assert state["widgetShowing"]


def test_turnstile_with_a_token_is_satisfied():
    state = turnstile_state(_ScriptSb(
        {"rendered": True, "token": True, "widgetShowing": False}
    ))
    assert state["token"]


def test_an_error_code_survives_into_the_state():
    """The code is the whole point: `600***` is what "(600)" on screen means."""
    state = turnstile_state(_ScriptSb(
        {"rendered": True, "token": False, "errorCode": "600010"}
    ))
    assert state["errorCode"] == "600010"


def test_missing_turnstile_reads_as_absent():
    class Broken:
        def execute_script(self, script, *args):
            raise RuntimeError("frame gone")

    assert turnstile_state(Broken()) == {}


# --------------------------------------------------------------------------
# the enrollment app's own URL encoding
# --------------------------------------------------------------------------


def test_email_encoding_matches_the_site():
    """Checked against a URL the site itself produced: @ becomes |, reversed,
    then base64."""
    assert encode_email("dmimbo@gmail.com") == "bW9jLmxpYW1nfG9ibWltZA=="


def test_email_encoding_is_case_and_space_insensitive():
    assert encode_email("  DMIMBO@Gmail.com ") == encode_email("dmimbo@gmail.com")


# --------------------------------------------------------------------------
# a confirmation is a question, not a refusal
# --------------------------------------------------------------------------


CONFIRM_TEXT = (
    "Please Confirm: You have indicated that you wish to qualify through a "
    "child or dependent in your household."
)


def test_the_applicant_confirmation_is_recognised():
    """Seen live on row 64: the run had got through the screen and then
    reported this as "the form rejected the data"."""
    assert is_confirm_modal(CONFIRM_TEXT)


def test_a_real_rejection_is_not_a_confirmation():
    assert not is_confirm_modal(
        "Important: Sorry, that's an invalid email address. Be sure it's correct."
    )
    assert not is_confirm_modal("Important: The application can not be processed at this time.")
    assert not is_confirm_modal("")



# -- the second way the wizard asks for proof --------------------------------

from aw_bot.classify import (  # noqa: E402
    NEED_DOCUMENTS as _ND, SCREENS as _SCREENS, TERMINAL as _TERMINAL,
    classify_screen as _classify,
)

WORKSHEET_HEADINGS = ["California Household Worksheet"]
WORKSHEET_BODY = (
    "california household worksheet please read and acknowledge the "
    "following: lifeline is a government program that provides discounted "
    "phone service to qualified households. only one discount per household "
    "is allowed."
)


def test_the_household_worksheet_is_need_documents():
    """Reached when the applicant says they live with another adult who has
    their own LifeLine benefit -- more than one household at the address,
    which needs a worksheet to evidence it. Its breadcrumb reads
    "... | Disclosures | Submit Proof", so it is the same answer as the
    upload screen: approval is blocked on paperwork the agent lacks.
    """
    verdict, why = _classify(WORKSHEET_HEADINGS, WORKSHEET_BODY)
    assert verdict == _ND
    assert "Worksheet" in why


def test_it_is_recognised_from_the_body_alone():
    verdict, _ = _classify([], WORKSHEET_BODY)
    assert verdict == _ND


def test_the_upload_screen_still_classifies():
    """The two share a verdict, and the older one must not be shadowed."""
    verdict, why = _classify(
        ["ALMOST DONE! Upload Your Qualifying and Identity Proof Documents"], ""
    )
    assert verdict == _ND
    assert "Upload" in why


def test_every_screen_declared_for_a_terminal_verdict_is_reachable():
    """classify_screen used to build {verdict: screen}, keeping only the last
    screen declared for each. Adding a second way to reach a bucket would
    have silently disabled the first, and no test would have failed.
    """
    for verdict in _TERMINAL:
        for screen in _SCREENS:
            if screen.verdict != verdict:
                continue
            for signal in screen.headings:
                got, _ = _classify([signal], "")
                assert got == verdict, (screen.label, signal, got)
            for signal in screen.body:
                got, _ = _classify([], signal)
                assert got == verdict, (screen.label, signal, got)


def test_more_than_one_screen_shares_the_need_documents_verdict():
    """Otherwise the regression above could not recur, and the test above
    would be passing vacuously."""
    sharing = [s for s in _SCREENS if s.verdict == _ND]
    assert len(sharing) >= 2, [s.label for s in sharing]


# -- a wedged renderer is a dead browser -------------------------------------

from aw_bot.runner import _browser_died as _died  # noqa: E402


def test_a_renderer_timeout_is_worth_another_browser():
    """Row 256 hit this on driver.get() for the start page -- nothing entered,
    no form yet -- and the lead was thrown away instead of retried.

    Selenium reports it as a plain TimeoutException, so none of the
    session/connection signals matched it.
    """
    exc = Exception(
        "Message: timeout: Timed out receiving message from renderer: -0.003\n"
        "  (Session info: chrome=151.0.7922.173)"
    )
    assert _died(exc) is True


def test_the_other_renderer_wording_matches_too():
    assert _died(Exception("unable to receive message from renderer")) is True


def test_a_page_timeout_is_still_not_a_dead_browser():
    """An ordinary wait timing out says something about the page, not the
    browser, and retrying it on a new profile would repeat the same wait."""
    for message in (
        "Step 2: URL never reached any of ['/apply-now'] within 90s",
        "Step 10: clicked Continue but the screen never changed",
        "Message: timeout: Timed out waiting for element to be visible",
    ):
        assert _died(Exception(message)) is False, message
