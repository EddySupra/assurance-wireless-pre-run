"""Tests for the "Choose your phone" screen.

The selector matters more than usual here. Both options are radios the site
gives the *same* id -- `id="deviceType"` on each -- so `label[for=]` cannot
tell them apart and the usual radio machinery has nothing unique to key on.
What distinguishes them is `value`, and what is actually on screen is the
painted `div.b-input` sitting immediately after each input.

    python -m pytest tests -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot.config import RunConfig  # noqa: E402
from aw_bot.steps import step_10_classify as step10  # noqa: E402

PHONE_HEADINGS = [
    "Choose your phone",
    "Bring Your Own Phone",
    "Order a Free, Basic Smartphone",
]


def test_the_phone_screen_is_recognised():
    assert step10._is_phone_screen(PHONE_HEADINGS) is True


def test_other_screens_are_not_mistaken_for_it():
    for headings in (
        ["Review your Assurance Wireless Account information"],
        ["California LifeLine Application"],
        ["Income and Demographic Information"],
        [],
    ):
        assert step10._is_phone_screen(headings) is False, headings


def test_the_free_phone_is_the_configured_choice():
    assert RunConfig().application.phone_option == "free"


def test_the_selector_targets_the_painted_control_by_value():
    """Not by id -- the site puts the same id on both options."""
    selector = step10._PHONE_SELECTOR.format(value="free")
    assert '[value="free"]' in selector
    assert "div.b-input" in selector
    assert "#deviceType" not in selector


def test_the_selector_distinguishes_the_two_options():
    free = step10._PHONE_SELECTOR.format(value="free")
    byod = step10._PHONE_SELECTOR.format(value="byod")
    assert free != byod


# -- refusing rather than guessing -------------------------------------------

class _Sb:
    def __init__(self, found=True, checked_after=True):
        self.found = found
        self.checked_after = checked_after
        self.reads = 0

    def execute_script(self, script, *args):
        self.reads += 1
        return {
            "offered": ["byod", "free"] if self.found else ["byod"],
            "found": self.found,
            # First read is the before-state, later reads the after-state.
            "checked": self.checked_after if self.reads > 1 else False,
        }


def test_a_missing_option_stops_the_lead():
    """Picking whichever radio happens to be there is not a substitute."""
    assert step10._choose_phone(_Sb(found=False), RunConfig(), Path(".")) is False


def test_a_selection_that_does_not_register_stops_the_lead(monkeypatch):
    """Continuing would leave the application with no device chosen."""
    monkeypatch.setattr(step10, "human_click", lambda *a, **k: None)
    monkeypatch.setattr(step10, "pause", lambda *a, **k: None)
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: None)

    assert step10._choose_phone(_Sb(checked_after=False), RunConfig(), Path(".")) is False


def test_a_successful_selection_continues(monkeypatch):
    advanced = []
    monkeypatch.setattr(step10, "human_click", lambda *a, **k: None)
    monkeypatch.setattr(step10, "pause", lambda *a, **k: None)
    monkeypatch.setattr(step10, "capture", lambda *a, **k: {})
    monkeypatch.setattr(step10, "advance_screen", lambda *a, **k: advanced.append(1))

    assert step10._choose_phone(_Sb(), RunConfig(), Path(".")) is True
    assert advanced, "it should press Continue after choosing"
