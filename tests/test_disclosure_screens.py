"""Tests for the screens between the qualifying programme and the verdict.

Two of them, and both make statements rather than ask preferences: an
electronic signature consent, and a one-per-household certification whose own
text mentions prosecution. The answers are constants taken from the reference
recordings, and they are only defensible because this run stops at the screen
that states the verdict and never completes the submission.

So what these pin is the wiring -- that each question is answered from its own
setting, that the values match the recordings, and that a question which
cannot be matched stops the lead instead of being guessed at.

    python -m pytest tests -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot.config import RunConfig  # noqa: E402
from aw_bot.steps import step_10_classify as step10  # noqa: E402


class _Lead:
    """Just the name fields the signature screen reads."""

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


# -- recognising the screens -------------------------------------------------

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


# -- the answers match the recordings ----------------------------------------

def test_the_household_answers_are_yes_yes_no():
    """Exactly what the reference recording selects, in order.

    Read together they say the applicant shares an address with another
    LifeLine recipient but a separate household -- the combination the form's
    own notes describe as still qualifying.
    """
    app = RunConfig().application
    assert app.household_lives_with_adult == "Yes"
    assert app.household_adult_has_lifeline == "Yes"
    assert app.household_shares_expenses == "No"


def test_the_esignature_consent_is_agreed():
    assert RunConfig().application.esign_consent == "Yes"


# -- what the consent is signed with -----------------------------------------

def test_the_signature_comes_from_the_applicants_own_name():
    """Not a constant.

    The initials box takes two letters and the name box takes the applicant's
    name as the site already holds it, so anything else is simply wrong. The
    reference recording types "XX" into the initials, which is a placeholder
    rather than a rule.
    """
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
    """The handler refuses on this rather than signing a blank."""
    class _Nameless:
        first_name = ""
        last_name = ""

    initials, full = step10._signature_values(_Nameless())
    assert initials == ""
    assert full == ""


def test_the_signature_fields_use_the_sites_real_ids():
    """Guessed selectors missed both and the screen silently refused to move."""
    assert step10.ESIGN_INITIALS_FIELD == "#esigintl"
    assert step10.ESIGN_NAME_FIELD == "#esigname"


def test_each_question_has_its_own_setting():
    """Three separate fields, so they cannot drift into agreeing silently.

    A shared default would answer all three the same way, and the third
    answer is deliberately the opposite of the first two.
    """
    fields = [field for _, field in step10.HOUSEHOLD_QUESTIONS]
    assert len(fields) == 3
    assert len(set(fields)) == 3

    app = RunConfig().application
    for field in fields:
        assert hasattr(app, field), field


def test_the_questions_are_matched_by_their_own_wording():
    """Position is not enough -- a reordered form would answer the wrong one."""
    hints = [hint for hint, _ in step10.HOUSEHOLD_QUESTIONS]
    body = HOUSEHOLD_BODY.lower()
    for hint in hints:
        assert hint in body, hint


# -- each question is found by its own wording -------------------------------

def test_every_question_excludes_the_other_two():
    """What the locator uses to reject a block covering more than one question.

    All three questions are Yes/No, so a block that spans two of them offers
    an option matching the answer either way and the wrong row gets clicked
    with nothing to show for it.
    """
    hints = [hint for hint, _ in step10.HOUSEHOLD_QUESTIONS]
    body = HOUSEHOLD_BODY.lower()
    for hint in hints:
        others = [h for h in hints if h != hint]
        # Each hint appears once in the screen text, and in one question only.
        assert body.count(hint) == 1, hint
        for other in others:
            assert other != hint


class _Screen:
    """A household screen with three separate Yes/No questions.

    `blocks` maps a question hint to the radios its own block contains.
    """

    def __init__(self, blocks, holds_after=True):
        self.blocks = blocks
        self.holds_after = holds_after
        self.clicked = []
        self.checked = {}

    def execute_script(self, script, *args):
        if "arguments[1] || []" in script:          # the question locator
            hint = args[0]
            if hint not in self.blocks:
                return {"found": False, "reason": "no block holds that question"}
            radios = [dict(r) for r in self.blocks[hint]]
            for r in radios:
                if r.get("id") in self.checked:
                    r["checked"] = self.checked[r["id"]]
            return {"found": True, "text": hint, "radios": radios}
        if "el.checked" in script:                  # reading one back
            return self.holds_after
        if "checkbox" in script:                    # certifications
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
    """The bug this replaced answered question one three times.

    Matching on the answer's label alone picks the first "Yes" on the screen,
    which is already ticked by the time question two is asked -- so two and
    three were silently left blank.
    """
    clicks = []
    monkeypatch.setattr(step10, "human_click", lambda sb, sel, cfg: clicks.append(sel))
    monkeypatch.setattr(step10, "pause", lambda *a, **k: None)
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: None)

    sb = _Screen(_three_questions())
    assert step10._answer_household(sb, RunConfig(), _LEAD, Path(".")) is True

    # Yes, Yes, No -- one click each, and each in a different question's block.
    assert clicks == [
        'input[id="q0Y"] + div.b-input',
        'input[id="q1Y"] + div.b-input',
        'input[id="q2N"] + div.b-input',
    ]


def test_an_already_correct_answer_is_left_alone(monkeypatch):
    """Clicking a radio that already holds the wanted answer is not what a
    person does, and this site notices interactions a person would not make."""
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


# -- refusing rather than guessing -------------------------------------------

def test_a_question_that_cannot_be_found_stops_the_lead(monkeypatch):
    """Answering by position would certify something nobody checked."""
    monkeypatch.setattr(step10, "human_click", lambda *a, **k: None)
    monkeypatch.setattr(step10, "pause", lambda *a, **k: None)
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})
    blocks = _three_questions()
    del blocks[step10.HOUSEHOLD_QUESTIONS[1][0]]
    assert step10._answer_household(_Screen(blocks), RunConfig(), _LEAD, Path(".")) is False


def test_a_block_covering_two_questions_stops_the_lead(monkeypatch):
    """The locator returns nothing rather than pick from a merged block."""
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})

    class _Merged(_Screen):
        def execute_script(self, script, *args):
            if "arguments[1] || []" in script:
                return {"found": False, "reason": "block also covers: " + args[1][0]}
            return super().execute_script(script, *args)

    assert step10._answer_household(_Merged({}), RunConfig(), _LEAD, Path(".")) is False


def test_a_missing_option_stops_the_lead(monkeypatch):
    """A question offering something other than the configured answer."""
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})
    blocks = _three_questions()
    blocks[step10.HOUSEHOLD_QUESTIONS[0][0]] = [
        {"id": "x", "value": "M", "label": "Maybe", "checked": False,
         "selector": 'input[id="x"] + div.b-input'},
    ]
    assert step10._answer_household(_Screen(blocks), RunConfig(), _LEAD, Path(".")) is False


def test_an_answer_that_does_not_stick_stops_the_lead(monkeypatch):
    """A painted radio that swallows the click leaves the certification
    saying the opposite of what was intended, or nothing at all."""
    monkeypatch.setattr(step10, "human_click", lambda *a, **k: None)
    monkeypatch.setattr(step10, "pause", lambda *a, **k: None)
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: None)

    sb = _Screen(_three_questions(), holds_after=False)
    assert step10._answer_household(sb, RunConfig(), _LEAD, Path(".")) is False


# -- the log has to say what was certified -----------------------------------

def test_the_certification_text_is_read_from_the_row_not_the_label():
    """These boxes carry a label with no text in it:

        <div aria-labelledby="cert2lbl" role="radiogroup" class="row">
          <div><div id="cert2lbl">I understand that violating the
               one-per-household benefit rule ... and potentially,
               prosecution by the United States government.</div></div>
          <div><label for="crt2" class="b-contain"><span></span>
               <input id="crt2"><div class="b-input"></div></label></div>
        </div>

    so label[for=] logged every one of them as an empty string. The run's log
    is the record of what was agreed to on somebody's benefits application,
    and one of these mentions prosecution, so "certifying -- " on its own is
    not good enough.
    """
    js = step10._TICK_CERTIFICATIONS_JS
    assert "aria-labelledby" in js
    assert "closest('[aria-labelledby]')" in js
    # The label is still tried first; the row is the fallback.
    assert "label[for=" in js


def test_the_sweep_stays_scoped_to_the_form():
    """The nav hamburger is a bare checkbox outside the form on every page."""
    assert "form input[type=checkbox]" in step10._TICK_CERTIFICATIONS_JS
    assert "form input[type=checkbox]" in step10._ALL_TICKED_JS


def test_disabled_boxes_are_left_out_of_both_scripts():
    """The first certification is disabled until the questions above it are
    answered, so a sweep that ignored `disabled` would demand a box the form
    has not enabled yet."""
    assert "!b.disabled" in step10._TICK_CERTIFICATIONS_JS
    assert "!b.disabled" in step10._ALL_TICKED_JS
