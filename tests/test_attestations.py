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


def test_the_911_answer_clicks_the_toggle_label():
    assert step10._E911_LABEL.format(answer="yes") == 'label[for="e911yes"]'
    assert step10._E911_LABEL.format(answer="no") == 'label[for="e911no"]'


def test_the_service_terms_box_has_two_honest_targets():
    targets = step10._SIGNATURE_CHECKBOX
    assert isinstance(targets, tuple)
    assert targets[0] == 'label[for="sigCheck"]'
    assert targets[1] == 'input[id="sigCheck"] + div.b-input'
    assert len(set(targets)) == len(targets)


def test_the_configured_answers():
    app = RunConfig().application
    assert app.wifi_911_acknowledged == "Yes"
    assert app.service_terms_agreed is True


def test_the_certification_sweep_is_scoped_to_the_form():
    assert "form input[type=checkbox]" in step10._TICK_CERTIFICATIONS_JS
    assert "form input[type=checkbox]" in step10._ALL_TICKED_JS


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
    assert clicks == ['label[for="e911yes"]', 'label[for="sigCheck"]'], (
        "one click per control, and the first target for each"
    )
    assert advanced


def test_a_screen_missing_its_controls_stops_the_lead(monkeypatch):
    _quiet(monkeypatch, [])
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: None)

    missing = dict(_READY, hasSignature=False)
    assert step10._answer_attestations(_Sb(missing), RunConfig(), _LEAD, Path(".")) is False


def test_a_click_that_does_not_register_stops_the_lead(monkeypatch):
    clicks = []
    _quiet(monkeypatch, clicks)
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: None)

    stuck = dict(_READY, e911Yes=True, signature=False)
    assert step10._answer_attestations(_Sb(_READY, stuck), RunConfig(), _LEAD, Path(".")) is False


def test_already_answered_controls_are_left_alone(monkeypatch):
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


class _Slow:
    def __init__(self, delay):
        self.delay = delay
        self.reads = 0
        self.clicks = 0

    def execute_script(self, script, *args):
        self.reads += 1
        if self.reads == 1:
            return dict(_READY)
        set_now = self.reads > self.delay
        return dict(_READY, e911Yes=set_now, signature=set_now)


def test_a_control_that_lags_is_waited_for(monkeypatch):
    sb = _Slow(delay=4)
    clicks = []
    _quiet(monkeypatch, clicks)
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: None)

    assert step10._answer_attestations(sb, RunConfig(), _LEAD, Path(".")) is True
    assert len(clicks) == 2, "one click per control, not a retry"


def test_a_control_that_never_sets_tries_each_target_then_stops(monkeypatch):
    clicks = []
    _quiet(monkeypatch, clicks)
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: None)

    sb = _Sb(_READY, dict(_READY))
    assert step10._answer_attestations(sb, RunConfig(), _LEAD, Path(".")) is False

    assert clicks == [step10._E911_LABEL.format(answer="yes")], clicks


def test_the_service_terms_box_falls_back_to_the_other_target(monkeypatch):
    clicks = []
    _quiet(monkeypatch, clicks)
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: None)

    class _PaintedOnly:
        def __init__(self):
            self.reads = 0
            self.signed = False

        def execute_script(self, script, *args):
            self.reads += 1
            if self.reads == 1:
                return dict(_READY)
            return dict(_READY, e911Yes=True, signature=self.signed)

    sb = _PaintedOnly()

    def _click(_sb, selector, _cfg):
        clicks.append(selector)
        if selector == 'input[id="sigCheck"] + div.b-input':
            sb.signed = True

    monkeypatch.setattr(step10, "human_click", _click)

    assert step10._answer_attestations(sb, RunConfig(), _LEAD, Path(".")) is True
    assert clicks.index('label[for="sigCheck"]') < clicks.index(
        'input[id="sigCheck"] + div.b-input'
    )


def test_the_wait_is_counted_in_polls_not_wall_clock():
    assert isinstance(step10._SETTLE_POLLS, int)
    assert step10._SETTLE_POLLS >= 2


def test_a_failure_reports_what_the_click_would_have_hit():
    js = step10._HIT_TEST_JS
    assert "elementFromPoint" in js
    assert "getBoundingClientRect" in js
    assert "innerHeight" in js
