import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot.page_utils import advance_screen  # noqa: E402
from aw_bot.steps import step_09_eligible_applicant as step9  # noqa: E402


def test_advance_screen_accepts_a_settle_delay():
    assert "settle" in inspect.signature(advance_screen).parameters


def test_settling_is_off_unless_a_step_asks_for_it():
    assert inspect.signature(advance_screen).parameters["settle"].default == 0.0


def test_step_nine_waits_thirty_seconds():
    assert step9.SETTLE_AFTER_CONTINUE == 30.0


def test_step_nine_actually_passes_it_through():
    source = inspect.getsource(step9.choose_eligible_applicant)
    assert "settle=SETTLE_AFTER_CONTINUE" in source


def test_the_wait_is_shorter_than_the_step_timeout():
    assert step9.SETTLE_AFTER_CONTINUE < step9.ELIGIBILITY_TIMEOUT
