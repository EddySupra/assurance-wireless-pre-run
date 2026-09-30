"""What may be sped up, and what may not.

Step 9 only started passing when the run stopped talking to the page while the
backend decided: a hands-off window after the click with no driver traffic at
all, and a poll interval of seconds rather than a few per second. That fix is
invisible in the code -- it looks like nothing but a sleep and a constant --
which makes it exactly the sort of thing a later pass at "make it faster"
deletes without noticing.

So these are pinned. Everything else in the pacing is padding and may be tuned.

    python -m pytest tests -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot import human  # noqa: E402
from aw_bot.config import RunConfig  # noqa: E402
from aw_bot.steps import step_09_eligible_applicant as step9  # noqa: E402
from aw_bot.steps import step_10_classify as step10  # noqa: E402


# -- load-bearing: do not shorten ---------------------------------------------

def test_step_9_still_hands_the_browser_over_for_thirty_seconds():
    """The eligibility lookup is the one window where driver traffic was
    measurably the difference between passing and hanging."""
    assert step9.SETTLE_AFTER_CONTINUE >= 30.0


def test_step_10_keeps_its_settle_window():
    assert step10.SETTLE_AFTER_CONTINUE >= 15.0


def test_the_wait_loop_still_polls_in_seconds_not_fractions():
    """It used to run four execute_script calls every 0.25-0.5s -- eight CDP
    round trips a second into a page that was waiting on a server."""
    source = Path("aw_bot/page_utils.py").read_text(encoding="utf-8")
    body = source.split("def advance_screen(")[1].split("\ndef ")[0]
    assert "poll = 2.0" in body


def test_the_settle_is_a_bare_sleep_with_nothing_in_it():
    """Not a pause with idling in it. The point is no traffic at all, and an
    earlier version filled this wait with pointer drift."""
    source = Path("aw_bot/page_utils.py").read_text(encoding="utf-8")
    body = source.split("def advance_screen(")[1].split("\ndef ")[0]
    settle = body.index("hands off for %.0fs while the form works")
    after = body[settle:settle + 400]
    assert "time.sleep(settle)" in after
    assert "_idle_signs_of_life" not in after
    assert "execute_script" not in after


def test_a_lookup_the_form_is_working_through_is_still_waited_out():
    """Trimming page_timeout must not shorten a wait the form is genuinely
    busy with -- that is what max_busy_wait covers."""
    assert RunConfig().max_busy_wait >= 60.0


# -- padding: tuned, and still varied -----------------------------------------

def test_typing_speed_is_left_alone():
    """The one delay measured directly rather than inferred. 0.05-0.16s per
    character is already brisk touch-typing; faster is not a hand."""
    low, high = RunConfig().type_delay
    assert (low, high) == (0.05, 0.16)


def test_every_dwell_still_has_a_range():
    """A flat or fixed delay is the tell, not a short one. Trimming the top of
    each range must not collapse it to a constant."""
    for kind, (low, high) in human.DWELL.items():
        assert high > low, kind
        assert high >= low * 2, f"{kind} has almost no spread left"


def test_the_warm_up_is_shortened_but_not_removed():
    """A session whose first pointer event is the click on field one has
    nothing else to show the sensor."""
    low, high = RunConfig().warm_up_seconds
    assert low > 0 and high > low


def test_leads_are_still_spaced_apart():
    """Spacing a batch out is what keeps a long run from looking like a flood."""
    low, high = RunConfig().lead_delay
    assert low >= 5.0
    assert high > low


def test_the_pointer_path_still_has_enough_samples_to_be_a_curve():
    """Below about six it starts to read as straight segments, which is the
    shape a path classifier is built to pick out."""
    assert RunConfig().mouse_steps >= 6
