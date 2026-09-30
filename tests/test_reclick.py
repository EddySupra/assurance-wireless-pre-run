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


# -- the zero-risk discriminator ---------------------------------------------
#
# Chrome focuses a <button> as part of the default action of a real click. So
# at a stall, with nothing clicked since and the screen unchanged, whether the
# Continue button still holds focus says whether the click reached it -- and it
# says so without pressing anything a second time.

from aw_bot.page_utils import _FOCUS_AFTER_CLICK_JS, _log_click_landed  # noqa: E402


def test_the_focus_script_compares_against_the_element_we_aimed_at():
    assert "document.activeElement" in _FOCUS_AFTER_CLICK_JS
    assert "querySelector(arguments[0])" in _FOCUS_AFTER_CLICK_JS
    # A focused child of the button still counts as the button.
    assert "want.contains(active)" in _FOCUS_AFTER_CLICK_JS


class _Focus:
    def __init__(self, payload):
        self.payload = payload

    def execute_script(self, *a, **k):
        return self.payload


def test_focus_on_continue_is_reported_as_the_hosts_fault(caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        _log_click_landed(
            _Focus({"found": True, "focused": True, "active": "button.order-button"}),
            "Step 8", "button.order-button",
        )
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "the host, not the click" in joined


def test_focus_elsewhere_is_reported_as_ours(caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        _log_click_landed(
            _Focus({"found": True, "focused": False, "active": "body"}),
            "Step 8", "button.order-button",
        )
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "This is ours" in joined
    assert "body" in joined


class _Broken:
    def execute_script(self, *a, **k):
        raise RuntimeError("frame gone")


def test_a_failure_to_read_focus_is_not_fatal():
    """A report about a failure must not replace the real error."""
    _log_click_landed(_Broken(), "Step 8", "button.order-button")


# -- re-aiming when focus proves the click missed -----------------------------
#
# Evidence-gated, unlike the second press: focus says the app never saw the
# first click, so there is nothing to submit twice. Row 251 stalled at step 6
# with every control valid and `body#rootBody` holding focus -- the pointer
# event never arrived, and the run then waited out ninety seconds for a
# submission that was never made.

from aw_bot.page_utils import _click_landed, _nothing_happened_yet  # noqa: E402


class _Page:
    def __init__(self, payload):
        self.payload = payload

    def execute_script(self, *a, **k):
        return self.payload


def test_a_focused_button_counts_as_landed():
    assert _click_landed(_Page({"found": True, "focused": True}), "button") is True


def test_an_unfocused_button_counts_as_missed():
    assert _click_landed(_Page({"found": True, "focused": False}), "button") is False


def test_an_unreadable_page_is_not_treated_as_a_miss():
    """An unanswerable question is not evidence. Clicking again on no evidence
    is the thing this design exists to avoid."""
    assert _click_landed(_Broken(), "button") is True


def test_a_vanished_button_is_not_treated_as_a_miss():
    """It has gone because the screen moved on -- that is a landed click."""
    assert _click_landed(_Page({"found": False}), "button") is True


def test_nothing_happened_is_false_while_busy(monkeypatch):
    """A spinner means the click landed and the app is working."""
    monkeypatch.setattr(page_utils, "is_busy", lambda sb: True)
    assert _nothing_happened_yet(object(), BEFORE) is False


def test_nothing_happened_is_false_with_a_modal_open(monkeypatch):
    monkeypatch.setattr(page_utils, "is_busy", lambda sb: False)
    monkeypatch.setattr(page_utils, "modal_present", lambda sb: True)
    assert _nothing_happened_yet(object(), BEFORE) is False


def test_nothing_happened_is_false_once_the_headings_change(monkeypatch):
    monkeypatch.setattr(page_utils, "is_busy", lambda sb: False)
    monkeypatch.setattr(page_utils, "modal_present", lambda sb: False)
    monkeypatch.setattr(page_utils, "screen_headings", lambda sb: AFTER)
    assert _nothing_happened_yet(object(), BEFORE) is False


def test_nothing_happened_is_true_on_an_unchanged_idle_screen(monkeypatch):
    monkeypatch.setattr(page_utils, "is_busy", lambda sb: False)
    monkeypatch.setattr(page_utils, "modal_present", lambda sb: False)
    monkeypatch.setattr(page_utils, "screen_headings", lambda sb: BEFORE)
    assert _nothing_happened_yet(object(), BEFORE) is True


def test_an_unreadable_screen_blocks_the_re_aim(monkeypatch):
    """Both conditions must be positively true before anything is clicked."""
    def boom(sb):
        raise RuntimeError("frame gone")

    monkeypatch.setattr(page_utils, "is_busy", boom)
    assert _nothing_happened_yet(object(), BEFORE) is False


def test_the_focus_check_runs_after_the_silent_window_not_before():
    """Step 9 only started passing once nothing talked to the page while the
    backend decided. This check must not creep back into that gap."""
    source = Path("aw_bot/page_utils.py").read_text(encoding="utf-8")
    body = source.split("def advance_screen(")[1].split("\ndef ")[0]
    hands_off = body.index("hands off for %.0fs while the form works")
    check = body.index("_nothing_happened_yet(sb, before)")
    assert check > hands_off, "the focus check must come after the silent wait"
