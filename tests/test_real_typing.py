"""Tests for the check that decides whether real typing actually landed.

This check is a safety mechanism, not a formality: pyautogui types wherever the
operating system's focus happens to be, so "did the field take it?" is what
stands between a mistargeted click and an applicant's SSN going into whatever
window was in front. It has to stay strict about failure while not calling a
success a failure because it looked a moment too early.

    python -m pytest tests -q
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from selenium.common.exceptions import WebDriverException  # noqa: E402

from aw_bot.human import _field_holds  # noqa: E402


class _Field:
    """An input whose value appears after a given number of reads."""

    def __init__(self, value, *, ready_after=0, maxlength=None):
        self.value = value
        self.ready_after = ready_after
        self.maxlength = maxlength
        self.reads = 0

    def get_attribute(self, name):
        if name == "maxlength":
            return self.maxlength
        if name == "value":
            self.reads += 1
            return self.value if self.reads > self.ready_after else ""
        return None


def test_a_field_that_already_holds_the_value_passes():
    assert _field_holds(_Field("SAMANTHA"), "SAMANTHA") is True


def test_a_value_that_arrives_a_moment_later_still_passes():
    """The bug this fixes.

    Real keystrokes go through the OS input queue, so the browser may not have
    processed the last one when pyautogui returns. A four-character field
    loses that race more often than a long one -- there are fewer keystrokes
    of elapsed time behind the final character. `#ssn` fell back to synthetic
    input on every run because of it, while `#firstName` did not.
    """
    assert _field_holds(_Field("1234", ready_after=3), "1234") is True


def test_a_field_that_never_takes_the_value_fails():
    """The check that stops details being typed into the wrong window."""
    started = time.time()
    assert _field_holds(_Field(""), "1234", timeout=0.4) is False
    assert time.time() - started >= 0.3


def test_a_field_holding_something_else_fails():
    assert _field_holds(_Field("9999"), "1234", timeout=0.4) is False


def test_surrounding_whitespace_is_not_a_mismatch():
    assert _field_holds(_Field("  SAMANTHA  "), "SAMANTHA") is True


def test_a_maxlength_truncation_is_not_a_failure():
    """A field that caps its own length has taken as much as it accepts."""
    assert _field_holds(_Field("1234", maxlength="4"), "123456789") is True


def test_truncation_only_counts_when_it_matches_the_prefix():
    assert _field_holds(_Field("9999", maxlength="4"), "123456789", timeout=0.4) is False


def test_a_missing_or_odd_maxlength_is_ignored():
    assert _field_holds(_Field("1234", maxlength=""), "1234") is True
    assert _field_holds(_Field("1234", maxlength="abc"), "1234") is True
    assert _field_holds(_Field("1234", maxlength="0"), "123456", timeout=0.3) is False


def test_a_lost_element_fails_rather_than_waiting():
    class Gone:
        def get_attribute(self, name):
            raise WebDriverException("stale element")

    assert _field_holds(Gone(), "1234", timeout=2.0) is False


def test_a_numeric_value_is_compared_as_text():
    assert _field_holds(_Field("1234"), 1234) is True
