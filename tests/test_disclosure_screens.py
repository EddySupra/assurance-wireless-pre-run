import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot.config import RunConfig  # noqa: E402
from aw_bot.steps import step_10_classify as step10  # noqa: E402


class _Lead:
    first_name = "LINDA"
    last_name = "JOHNSON"


_LEAD = _Lead()

HOUSEHOLD_BODY = (
    "1. Do you live with another adult? Adults are 18 years old or older or "
    "are emancipated minors. 2. Does the adult who lives with you receive a "
    "California LifeLine discount? 3. Do you share income and living expenses "
    "with the adult who lives with you? Certification"
)

ESIGN_BODY = (
    "Assurance Wireless E-Signature Consent You must agree to the Assurance "
    "Wireless E-Signature Consent policy to use electronic signatures in "
    "order to submit your application online."
)


def test_the_household_screen_is_recognised():
    assert step10._is_household_screen(HOUSEHOLD_BODY) is True


def test_the_esignature_screen_is_recognised():
    assert step10._is_esign_screen(ESIGN_BODY) is True


def test_they_are_not_confused_with_each_other():
    assert step10._is_esign_screen(HOUSEHOLD_BODY) is False
    assert step10._is_household_screen(ESIGN_BODY) is False


def test_an_unrelated_screen_is_neither():
    body = "Income and Demographic Information Please Help"
    assert step10._is_household_screen(body) is False
    assert step10._is_esign_screen(body) is False
    assert step10._is_household_screen("") is False
    assert step10._is_esign_screen(None) is False


def test_the_household_answers_are_yes_yes_no():
    app = RunConfig().application
    assert app.household_lives_with_adult == "Yes"
    assert app.household_adult_has_lifeline == "Yes"
    assert app.household_shares_expenses == "No"


def test_the_esignature_consent_is_agreed():
    assert RunConfig().application.esign_consent == "Yes"


def test_the_signature_comes_from_the_applicants_own_name():
    initials, full = step10._signature_values(_LEAD)
    assert initials == "LJ"
    assert full == "LINDA JOHNSON"


def test_the_initials_are_uppercased_and_two_letters():
    class _Lower:
        first_name = "linda"
        last_name = "johnson"

    initials, _ = step10._signature_values(_Lower())
    assert initials == "LJ"
    assert len(initials) == 2


def test_surrounding_whitespace_is_trimmed():
    class _Padded:
        first_name = "  LINDA "
        last_name = " JOHNSON  "

    initials, full = step10._signature_values(_Padded())
    assert initials == "LJ"
    assert full == "LINDA JOHNSON"


def test_a_missing_name_yields_nothing_to_sign_with():
    class _Nameless:
        first_name = ""
        last_name = ""

    initials, full = step10._signature_values(_Nameless())
    assert initials == ""
    assert full == ""


def test_the_signature_fields_use_the_sites_real_ids():
    assert step10.ESIGN_INITIALS_FIELD == "#esigintl"
    assert step10.ESIGN_NAME_FIELD == "#esigname"


def test_each_question_has_its_own_setting():
    fields = [field for _, field in step10.HOUSEHOLD_QUESTIONS]
    assert len(fields) == 3
    assert len(set(fields)) == 3

    app = RunConfig().application
    for field in fields:
        assert hasattr(app, field), field


def test_the_questions_are_matched_by_their_own_wording():
    hints = [hint for hint, _ in step10.HOUSEHOLD_QUESTIONS]
    body = HOUSEHOLD_BODY.lower()
    for hint in hints:
        assert hint in body, hint


def test_every_question_excludes_the_other_two():
    hints = [hint for hint, _ in step10.HOUSEHOLD_QUESTIONS]
    body = HOUSEHOLD_BODY.lower()
    for hint in hints:
        others = [h for h in hints if h != hint]
        assert body.count(hint) == 1, hint
        for other in others:
            assert other != hint


class _Screen:
    def __init__(self, blocks, holds_after=True):
        self.blocks = blocks
        self.holds_after = holds_after
        self.clicked = []
        self.checked = {}

    def execute_script(self, script, *args):
        if "arguments[1] || []" in script:
            hint = args[0]
            if hint not in self.blocks:
                return {"found": False, "reason": "no block holds that question"}
            radios = [dict(r) for r in self.blocks[hint]]
            for r in radios:
                if r.get("id") in self.checked:
                    r["checked"] = self.checked[r["id"]]
            return {"found": True, "text": hint, "radios": radios}
        if "el.checked" in script:
            return self.holds_after
        if "checkbox" in script:
            return [] if "out.push" in script else True
        return True


def _yes_no(prefix):
    return [
        {"id": f"{prefix}Y", "value": "Y", "label": "Yes", "checked": False,
         "selector": f'input[id="{prefix}Y"] + div.b-input'},
        {"id": f"{prefix}N", "value": "N", "label": "No", "checked": False,
         "selector": f'input[id="{prefix}N"] + div.b-input'},
    ]


def _three_questions():
    return {hint: _yes_no(f"q{i}") for i, (hint, _) in enumerate(step10.HOUSEHOLD_QUESTIONS)}


def test_each_question_is_answered_from_its_own_block(monkeypatch):
    clicks = []
    monkeypatch.setattr(step10, "human_click", lambda sb, sel, cfg: clicks.append(sel))
    monkeypatch.setattr(step10, "pause", lambda *a, **k: None)
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: None)

    sb = _Screen(_three_questions())
    assert step10._answer_household(sb, RunConfig(), _LEAD, Path(".")) is True

    assert clicks == [
        'input[id="q0Y"] + div.b-input',
        'input[id="q1Y"] + div.b-input',
        'input[id="q2N"] + div.b-input',
    ]


def test_an_already_correct_answer_is_left_alone(monkeypatch):
    clicks = []
    monkeypatch.setattr(step10, "human_click", lambda sb, sel, cfg: clicks.append(sel))
    monkeypatch.setattr(step10, "pause", lambda *a, **k: None)
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: None)

    blocks = _three_questions()
    for radio in blocks[step10.HOUSEHOLD_QUESTIONS[0][0]]:
        if radio["label"] == "Yes":
            radio["checked"] = True

    sb = _Screen(blocks)
    assert step10._answer_household(sb, RunConfig(), _LEAD, Path(".")) is True
    assert 'input[id="q0Y"] + div.b-input' not in clicks
    assert len(clicks) == 2


def test_a_question_that_cannot_be_found_stops_the_lead(monkeypatch):
    monkeypatch.setattr(step10, "human_click", lambda *a, **k: None)
    monkeypatch.setattr(step10, "pause", lambda *a, **k: None)
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})
    blocks = _three_questions()
    del blocks[step10.HOUSEHOLD_QUESTIONS[1][0]]
    assert step10._answer_household(_Screen(blocks), RunConfig(), _LEAD, Path(".")) is False


def test_a_block_covering_two_questions_stops_the_lead(monkeypatch):
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})

    class _Merged(_Screen):
        def execute_script(self, script, *args):
            if "arguments[1] || []" in script:
                return {"found": False, "reason": "block also covers: " + args[1][0]}
            return super().execute_script(script, *args)

    assert step10._answer_household(_Merged({}), RunConfig(), _LEAD, Path(".")) is False


def test_a_missing_option_stops_the_lead(monkeypatch):
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})
    blocks = _three_questions()
    blocks[step10.HOUSEHOLD_QUESTIONS[0][0]] = [
        {"id": "x", "value": "M", "label": "Maybe", "checked": False,
         "selector": 'input[id="x"] + div.b-input'},
    ]
    assert step10._answer_household(_Screen(blocks), RunConfig(), _LEAD, Path(".")) is False


def test_an_answer_that_does_not_stick_stops_the_lead(monkeypatch):
    monkeypatch.setattr(step10, "human_click", lambda *a, **k: None)
    monkeypatch.setattr(step10, "pause", lambda *a, **k: None)
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: None)

    sb = _Screen(_three_questions(), holds_after=False)
    assert step10._answer_household(sb, RunConfig(), _LEAD, Path(".")) is False


def test_the_certification_text_is_read_from_the_row_not_the_label():
    js = step10._TICK_CERTIFICATIONS_JS
    assert "aria-labelledby" in js
    assert "closest('[aria-labelledby]')" in js
    assert "label[for=" in js


def test_the_sweep_stays_scoped_to_the_form():
    assert "form input[type=checkbox]" in step10._TICK_CERTIFICATIONS_JS
    assert "form input[type=checkbox]" in step10._ALL_TICKED_JS


def test_disabled_boxes_are_left_out_of_both_scripts():
    assert "!b.disabled" in step10._TICK_CERTIFICATIONS_JS
    assert "!b.disabled" in step10._ALL_TICKED_JS
