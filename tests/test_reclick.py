"""Tests for the one permitted second press of Continue.

Row 245 sat on the account review screen for 106 seconds after a click that
real-input had confirmed on target, with every required control valid, no
modal, no spinner, no Turnstile error and no validation message. Two things
produce that and they want opposite answers: the host's backend never
answered, or the click never reached the button's handler. The second is not
hypothetical here -- a real click on the service-terms box, confirmed on
target by elementFromPoint, left the input `ng-pristine`.

advance_screen clicked once and only watched, so it could never tell the two
apart. These tests pin the second press, and pin that it stays off everywhere
it is not explicitly wanted.

    python -m pytest tests -q
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot import page_utils  # noqa: E402
from aw_bot.classify import REJECTED  # noqa: E402
from aw_bot.config import RunConfig  # noqa: E402
from aw_bot.errors import LeadRejectedError  # noqa: E402

BEFORE = ["Review your Assurance Wireless Account information"]
AFTER = ["How do you qualify for California LifeLine Service?"]


# -- it is off unless asked for ----------------------------------------------

def test_a_second_press_is_off_by_default():
    """Every screen that answers a question keeps its single click."""
    import inspect

    sig = inspect.signature(page_utils.advance_screen)
    assert sig.parameters["allow_reclick"].default is False


def test_only_the_pass_through_screen_turns_it_on():
    """A second Continue is only harmless where it starts a lookup rather
    than committing something, so it is granted per-caller, not globally."""
    source = Path("aw_bot/steps/step_10_classify.py").read_text(encoding="utf-8")
    assert source.count("allow_reclick=True") == 1

    # And it is the acknowledge-and-continue call, not one of the handlers
    # that answer a question: the nearest preceding log line is the
    # pass-through one.
    before_flag = source.split("allow_reclick=True")[0]
    last_log = before_flag.rfind("LOG.info(")
    assert "continuing past it" in before_flag[last_log:]


# -- the two outcomes it exists to tell apart --------------------------------

def _quiet(monkeypatch, headings_sequence, busy=False, modal=None):
    """Stub everything _press_continue_again touches."""
    seq = list(headings_sequence)
    monkeypatch.setattr(page_utils, "first_visible", lambda sb, sels: sels[0])
    monkeypatch.setattr(page_utils, "bring_framed_element_into_view", lambda *a, **k: True)
    monkeypatch.setattr(page_utils, "human_click", lambda *a, **k: None)
    monkeypatch.setattr(page_utils, "modal_message", lambda sb: modal)
    monkeypatch.setattr(page_utils, "is_progress_modal", lambda m: False)
    monkeypatch.setattr(page_utils, "is_busy", lambda sb: busy)
    monkeypatch.setattr(page_utils, "screen_headings", lambda sb: seq.pop(0) if seq else BEFORE)
    monkeypatch.setattr(page_utils.time, "sleep", lambda s: None)


def test_a_second_press_that_moves_the_screen_returns_the_new_headings(monkeypatch):
    """This is the outcome that says the fault was ours, not the host's."""
    _quiet(monkeypatch, [AFTER])
    got = page_utils._press_continue_again(
        object(), RunConfig(), "Step 10", "button.order-button", BEFORE, 10.0, 0.0
    )
    assert got == AFTER


def test_a_second_press_that_changes_nothing_returns_none(monkeypatch):
    """And this is the outcome that says the host is not answering."""
    _quiet(monkeypatch, [])
    got = page_utils._press_continue_again(
        object(), RunConfig(), "Step 10", "button.order-button", BEFORE, 0.5, 0.0
    )
    assert got is None


def test_it_says_which_of_the_two_it_decided(monkeypatch, caplog):
    """The next occurrence should not have to be diagnosed from scratch."""
    import logging

    _quiet(monkeypatch, [AFTER])
    with caplog.at_level(logging.WARNING):
        page_utils._press_continue_again(
            object(), RunConfig(), "Step 10", "button.order-button", BEFORE, 10.0, 0.0
        )
    assert any("this is ours, not the host's" in r.getMessage() for r in caplog.records)


# -- a rejection arriving late is still a classification ---------------------

def test_a_rejection_on_the_second_press_is_classified_not_failed(monkeypatch):
    """The form answering the question this run asks is a verdict, whenever
    it arrives -- reporting it as a stuck screen would lose the lead."""
    _quiet(
        monkeypatch, [],
        modal="You currently receive a California LifeLine benefit with another service provider",
    )
    monkeypatch.setattr(page_utils, "rejection_verdict", lambda m: REJECTED)

    with pytest.raises(LeadRejectedError) as caught:
        page_utils._press_continue_again(
            object(), RunConfig(), "Step 10", "button.order-button", BEFORE, 10.0, 0.0
        )
    assert caught.value.verdict == REJECTED


def test_a_message_that_is_not_a_verdict_stops_without_raising(monkeypatch):
    _quiet(monkeypatch, [], modal="Something the run has never seen")
    monkeypatch.setattr(page_utils, "rejection_verdict", lambda m: None)

    got = page_utils._press_continue_again(
        object(), RunConfig(), "Step 10", "button.order-button", BEFORE, 10.0, 0.0
    )
    assert got is None


def test_a_vanished_button_is_not_clicked_again(monkeypatch):
    """Nothing to press, and pressing whatever replaced it would be worse."""
    monkeypatch.setattr(page_utils, "first_visible", lambda sb, sels: None)
    clicks = []
    monkeypatch.setattr(page_utils, "human_click", lambda *a, **k: clicks.append(1))

    got = page_utils._press_continue_again(
        object(), RunConfig(), "Step 10", "button.order-button", BEFORE, 10.0, 0.0
    )
    assert got is None
    assert not clicks


def test_only_one_extra_press_is_made(monkeypatch):
    """Not a loop -- a screen ignoring two clicks is saying something else."""
    _quiet(monkeypatch, [])
    clicks = []
    monkeypatch.setattr(page_utils, "human_click", lambda *a, **k: clicks.append(1))

    page_utils._press_continue_again(
        object(), RunConfig(), "Step 10", "button.order-button", BEFORE, 0.5, 0.0
    )
    assert len(clicks) == 1
