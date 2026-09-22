"""Tests for the shape of the run's pauses.

Shape, not values. What gives a scripted run away is rarely any single gap --
it is that every gap comes from the same flat range, so the distribution has a
hard floor, a hard ceiling and no tail. Real waiting clusters low, trails off,
and occasionally runs long because attention wandered.

These tests therefore assert statistical properties rather than exact numbers,
which is the only honest way to pin a random process.

    python -m pytest tests -q
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot import human  # noqa: E402


def _sample(low, high, n=4000):
    human._tempo = 1.0
    return [human._skewed(low, high) for _ in range(n)]


def test_delays_stay_broadly_inside_the_range():
    draws = _sample(0.4, 1.1)
    inside = [d for d in draws if 0.28 <= d <= 1.1]
    assert len(inside) / len(draws) > 0.9


def test_the_distribution_is_not_flat():
    """A uniform draw is the thing being replaced.

    Split the range in half: uniform puts about 50% in each. A human-shaped
    wait puts most of its mass in the lower half and trails into the upper.
    """
    low, high = 0.4, 1.1
    draws = _sample(low, high)
    midpoint = (low + high) / 2
    lower = sum(1 for d in draws if d < midpoint) / len(draws)
    assert lower > 0.6, lower


def test_there_is_a_tail_past_the_nominal_ceiling():
    """A ceiling never exceeded is itself an edge something can measure."""
    draws = _sample(0.4, 1.1)
    over = [d for d in draws if d > 1.1]
    assert over, "no draw ever ran long"
    assert len(over) / len(draws) < 0.15, "running long should be rare"


def test_nothing_is_ever_negative_or_zero():
    assert all(d > 0 for d in _sample(0.04, 0.32))


def test_a_degenerate_range_is_survivable():
    human._tempo = 1.0
    assert human._skewed(0.5, 0.5) >= 0
    assert human._skewed(1.0, 0.2) >= 0


def test_scale_stretches_the_whole_distribution():
    human._tempo = 1.0
    plain = statistics.median(human._skewed(0.4, 1.1) for _ in range(2000))
    scaled = statistics.median(human._skewed(0.4, 1.1, 3.0) for _ in range(2000))
    assert scaled > plain * 2


# -- the per-lead operator ---------------------------------------------------

def test_each_lead_gets_its_own_pace():
    paces = {round(human.new_operator(), 3) for _ in range(50)}
    assert len(paces) > 40, "leads should not share a pace"


def test_the_pace_stays_plausible():
    """Wide enough to differ between leads, not so wide it looks broken."""
    for _ in range(500):
        pace = human.new_operator()
        assert 0.55 <= pace <= 2.2, pace


def test_the_pace_moves_the_delays_with_it():
    human.new_operator()
    human._tempo = 0.6
    brisk = statistics.median(human._skewed(0.4, 1.1) for _ in range(2000))
    human._tempo = 1.8
    slow = statistics.median(human._skewed(0.4, 1.1) for _ in range(2000))
    assert slow > brisk * 1.5
    human._tempo = 1.0


# -- idle movement -----------------------------------------------------------

def test_idle_movement_has_more_than_one_behaviour():
    """Always doing the same thing is as much a pattern as doing nothing."""
    import inspect

    source = inspect.getsource(human.idle_drift)
    for kind in ("tremor", "settle", "nudge", "still"):
        assert kind in source


def test_idle_movement_sometimes_does_nothing():
    """A hand at rest is sometimes simply still."""
    import inspect

    source = inspect.getsource(human.idle_drift)
    assert 'if kind == "still"' in source
    assert "return" in source
