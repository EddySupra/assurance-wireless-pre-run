"""Tests for the "Attestations" screen.

The screen between the e-signature consent and the verdict. It carries two
required controls built differently from each other: a Bootstrap button-group
toggle for the Wi-Fi 911 acknowledgement, where the label is the button, and
the site's usual painted checkbox for the service terms.

Both are statements rather than preferences, and both are only defensible as
constants for the reason the rest of this module is: the run stops at the
screen that states the verdict and never completes the submission.

    python -m pytest tests -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot.config import RunConfig  # noqa: E402
from aw_bot.steps import step_10_classify as step10  # noqa: E402


class _Lead:
    first_name = "RICARDO"
    last_name = "LOPEZ"


_LEAD = _Lead()

HEADINGS = [
    "Attestations",
    "LIMITATIONS WITH WIFI CALLING SERVICE",
    "ASSURANCE WIRELESS SERVICE TERMS",
]


def test_the_screen_is_recognised():
    assert step10._is_attestations_screen(HEADINGS) is True


def test_recognition_ignores_case():
    assert step10._is_attestations_screen([h.lower() for h in HEADINGS]) is True


def test_other_screens_are_not_mistaken_for_it():
    for headings in (
        ["Choose your phone"],
        ["California LifeLine Application"],
        ["Income and Demographic Information"],
        ["Review your Assurance Wireless Account information"],
        [],
    ):
        assert step10._is_attestations_screen(headings) is False, headings


# -- the selectors match the live DOM ----------------------------------------

def test_the_911_answer_clicks_the_toggle_label():
    """Here the label *is* the button, so its centre is the right target.

    That is the opposite of the programme and certification rows, whose
    labels are paragraphs -- a click at the centre of one of those lands on
    the sentence rather than the control, which is why they aim at the
    painted div instead.
    """
    assert step10._E911_LABEL.format(answer="yes") == 'label[for="e911yes"]'
    assert step10._E911_LABEL.format(answer="no") == 'label[for="e911no"]'


def test_the_service_terms_box_aims_at_the_painted_control():
    assert step10._SIGNATURE_CHECKBOX == 'input[id="sigCheck"] + div.b-input'
    assert "div.b-input" in step10._SIGNATURE_CHECKBOX


def test_the_configured_answers():
    app = RunConfig().application
    assert app.wifi_911_acknowledged == "Yes"
    assert app.service_terms_agreed is True


# -- the nav hamburger is not a certification --------------------------------

def test_the_certification_sweep_is_scoped_to_the_form():
    """This app keeps its mobile nav menu in a bare checkbox outside the form:

        <application><input id="menu-switch" type="checkbox"> ...

    on every page. An unscoped sweep ticks it, opens the nav drawer over the
    form, and then insists it stay ticked -- so the lead stops on a screen it
    had already filled in correctly.
    """
    assert "form input[type=checkbox]" in step10._TICK_CERTIFICATIONS_JS
    assert "form input[type=checkbox]" in step10._ALL_TICKED_JS


# -- refusing rather than guessing -------------------------------------------

class _Sb:
    def __init__(self, before, after=None):
        self.before = before
        self.after = after if after is not None else dict(before)
        self.reads = 0
        self.clicked = []

    def execute_script(self, script, *args):
        self.reads += 1
        return self.before if self.reads == 1 else self.after


_READY = {
    "hasE911": True, "e911Yes": False, "e911No": False,
    "hasSignature": True, "signature": False,
}
_DONE = {
    "hasE911": True, "e911Yes": True, "e911No": False,
    "hasSignature": True, "signature": True,
}


def _quiet(monkeypatch, clicks):
    monkeypatch.setattr(step10, "human_click", lambda sb, sel, cfg: clicks.append(sel))
    monkeypatch.setattr(step10, "pause", lambda *a, **k: None)
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})


def test_both_controls_are_answered_then_continued(monkeypatch):
    clicks, advanced = [], []
    _quiet(monkeypatch, clicks)
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: advanced.append(1))

    sb = _Sb(_READY, _DONE)
    assert step10._answer_attestations(sb, RunConfig(), _LEAD, Path(".")) is True
    assert clicks == ['label[for="e911yes"]', 'input[id="sigCheck"] + div.b-input']
    assert advanced


def test_a_screen_missing_its_controls_stops_the_lead(monkeypatch):
    """A layout change should stop the lead, not click at where it used to be."""
    _quiet(monkeypatch, [])
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: None)

    missing = dict(_READY, hasSignature=False)
    assert step10._answer_attestations(_Sb(missing), RunConfig(), _LEAD, Path(".")) is False


def test_a_click_that_does_not_register_stops_the_lead(monkeypatch):
    """Continuing would leave a required acknowledgement unmade."""
    clicks = []
    _quiet(monkeypatch, clicks)
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: None)

    stuck = dict(_READY, e911Yes=True, signature=False)
    assert step10._answer_attestations(_Sb(_READY, stuck), RunConfig(), _LEAD, Path(".")) is False


def test_already_answered_controls_are_left_alone(monkeypatch):
    """Clicking a ticked box clears it, and clicking a chosen toggle is an
    interaction a person would not produce."""
    clicks = []
    _quiet(monkeypatch, clicks)
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: None)

    assert step10._answer_attestations(_Sb(_DONE), RunConfig(), _LEAD, Path(".")) is True
    assert clicks == []


def test_an_unusable_911_setting_stops_the_lead(monkeypatch):
    _quiet(monkeypatch, [])
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: None)

    cfg = RunConfig()
    cfg.application.wifi_911_acknowledged = "Maybe"
    assert step10._answer_attestations(_Sb(_READY), cfg, _LEAD, Path(".")) is False
