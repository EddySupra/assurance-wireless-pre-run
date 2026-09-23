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
    app = RunConfig().application
    assert app.esign_consent == "Yes"
    assert app.esign_initials == "XX"


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


# -- refusing rather than guessing -------------------------------------------

class _Sb:
    """No radios on the page at all."""

    def execute_script(self, script, *args):
        return [] if "checkbox" in script else True


def test_a_household_screen_with_no_questions_stops_the_lead(monkeypatch):
    monkeypatch.setattr(step10, "read_radios", lambda sb: [])
    assert step10._answer_household(_Sb(), RunConfig(), Path(".")) is False


def test_an_unanswerable_question_stops_the_lead(monkeypatch):
    """A certification about someone's living arrangements is not guessable."""
    monkeypatch.setattr(step10, "read_radios", lambda sb: [{"label": "Maybe"}])
    monkeypatch.setattr(step10, "answer_radio", lambda *a, **k: False)
    assert step10._answer_household(_Sb(), RunConfig(), Path(".")) is False
