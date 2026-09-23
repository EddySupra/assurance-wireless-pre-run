"""Tests for ticking the California LifeLine qualifying programme.

This one asserts something about a real person -- which government assistance
they are enrolled in, on their federal benefits application. So the behaviour
worth pinning is not just that it ticks the right box, but that it refuses
rather than improvises when it cannot: a programme it cannot find by name, or
a tick that does not register, has to stop the lead rather than let the form
be submitted claiming nothing or claiming the wrong thing.

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

QUALIFY_HEADINGS = [
    "California LifeLine Application",
    "How do you qualify for California LifeLine Service?",
]


def test_the_qualification_screen_is_recognised():
    assert step10._is_qualify_screen(QUALIFY_HEADINGS) is True


def test_recognition_ignores_case():
    assert step10._is_qualify_screen([h.upper() for h in QUALIFY_HEADINGS]) is True


def test_other_screens_are_not_mistaken_for_it():
    for headings in (
        ["Review your Assurance Wireless Account information"],
        ["Who is the Benefit Eligible Applicant?"],
        ["Income and Demographic Information"],
        [],
    ):
        assert step10._is_qualify_screen(headings) is False, headings


def test_the_configured_programme_is_calfresh():
    """Chosen deliberately, and constant because every lead qualifies this way."""
    assert "CalFresh" in RunConfig().application.qualifying_program


# -- refusing rather than guessing -------------------------------------------

class _Sb:
    """Answers the two scripts _choose_program runs."""

    def __init__(self, found, checked_after=True):
        self.found = found
        self.checked_after = checked_after
        self.clicked = []

    def execute_script(self, script, *args):
        if "programDocumentType" in script:
            return dict(self.found)
        if "box.checked" in script:
            return self.checked_after
        return {}


def test_an_unmatched_programme_stops_the_lead(monkeypatch):
    """The nearest option is not an acceptable substitute for the right one."""
    sb = _Sb({"options": ["Medicaid/Medi-Cal", "Supplemental Security Income (SSI)"]})
    assert step10._choose_program(sb, RunConfig(), _LEAD, Path(".")) is False


def test_a_tick_that_does_not_register_stops_the_lead(monkeypatch):
    """Otherwise the application goes in claiming no qualifying programme."""
    monkeypatch.setattr(step10, "human_click", lambda *a, **k: None)
    monkeypatch.setattr(step10, "pause", lambda *a, **k: None)
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: [])

    sb = _Sb(
        {
            "id": "abc",
            "selector": 'label[for="abc"]',
            "text": "CalFresh, Food Stamps or SNAP",
            "checked": False,
            "visible": True,
            "options": [],
        },
        checked_after=False,
    )
    assert step10._choose_program(sb, RunConfig(), _LEAD, Path(".")) is False


def test_a_successful_tick_continues(monkeypatch):
    advanced = []
    monkeypatch.setattr(step10, "human_click", lambda *a, **k: None)
    monkeypatch.setattr(step10, "pause", lambda *a, **k: None)
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: advanced.append(1))

    sb = _Sb(
        {
            "id": "abc",
            "selector": 'label[for="abc"]',
            "text": "CalFresh, Food Stamps or SNAP",
            "checked": False,
            "visible": True,
            "options": [],
        },
        checked_after=True,
    )
    assert step10._choose_program(sb, RunConfig(), _LEAD, Path(".")) is True
    assert advanced, "it should press Continue after ticking"


def test_an_already_ticked_programme_is_left_alone(monkeypatch):
    """Clicking a ticked box would clear it."""
    monkeypatch.setattr(step10, "pause", lambda *a, **k: None)
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: None)

    clicks = []
    monkeypatch.setattr(step10, "human_click", lambda *a, **k: clicks.append(1))

    sb = _Sb(
        {
            "id": "abc",
            "selector": 'label[for="abc"]',
            "text": "CalFresh, Food Stamps or SNAP",
            "checked": True,
            "visible": True,
            "options": [],
        },
        checked_after=True,
    )
    assert step10._choose_program(sb, RunConfig(), _LEAD, Path(".")) is True
    assert not clicks, "an already-ticked box must not be clicked again"
