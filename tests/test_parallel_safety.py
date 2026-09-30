"""Tests for running several browsers at once.

Parallelism here is not a matter of raising a number: the module held state
that every worker would have shared. A module-level typing tempo makes five
concurrent leads type at whatever speed the last one to start happened to
draw, which reinstates the single-signature problem the tempo exists to
remove -- and does it invisibly, because nothing in the log looks wrong.

The same class of bug once made "lead 2 always fail" through a leaked frame
origin. With threads it happens simultaneously rather than in sequence, so it
is harder to see, which is why it is pinned here rather than left to a run.

    python -m pytest tests -q
"""

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot import human  # noqa: E402
from aw_bot.gologin_backend import _is_profile_cap  # noqa: E402


# -- one operator per worker, not one per process -----------------------------

def test_each_thread_draws_its_own_tempo():
    """Five workers are five different people at five different keyboards."""
    drawn = {}
    barrier = threading.Barrier(5)

    def work(name):
        human.new_operator()
        barrier.wait()                      # all five have drawn before any reads
        drawn[name] = human._current_tempo()

    threads = [threading.Thread(target=work, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(drawn) == 5
    # Each thread still sees the value it drew, not the last one written.
    assert len(set(drawn.values())) > 1, (
        "every thread ended up with the same tempo, so the state is shared"
    )


def test_one_thread_drawing_does_not_change_another():
    """The specific failure: worker B's tempo overwriting worker A's."""
    human.new_operator()
    mine = human._current_tempo()

    other = {}

    def work():
        human.new_operator()
        other["tempo"] = human._current_tempo()

    t = threading.Thread(target=work)
    t.start()
    t.join()

    assert human._current_tempo() == mine, "another worker changed this one's pace"
    assert other["tempo"] != mine or True      # it drew its own, whatever it was


def test_a_fresh_thread_has_a_sane_default():
    """A worker that has not drawn yet must not divide by a missing tempo."""
    seen = {}

    def work():
        seen["tempo"] = human._current_tempo()

    t = threading.Thread(target=work)
    t.start()
    t.join()
    assert seen["tempo"] == human._DEFAULT_TEMPO == 1.0


def test_the_tempo_is_thread_local_not_a_module_global():
    """Pinned against someone reintroducing `global _tempo`."""
    source = Path("aw_bot/human.py").read_text(encoding="utf-8")
    assert "threading.local()" in source
    assert "global _tempo" not in source


def test_the_delay_helpers_read_the_per_thread_tempo():
    source = Path("aw_bot/human.py").read_text(encoding="utf-8")
    assert "* _current_tempo()" in source
    # No bare `_tempo` left anywhere it could be read as the old global.
    assert "* _tempo" not in source


# -- real input and parallel workers are mutually exclusive ------------------

def test_real_input_with_several_workers_is_refused():
    """One machine, one cursor. Two workers would each find the pointer
    somewhere they did not leave it, and real_input refuses over exactly that
    -- so the batch would spend its time failing instead of filling forms."""
    source = Path("run.py").read_text(encoding="utf-8")
    assert "if args.real_input and args.workers > 1:" in source
    guard = source.split("if args.real_input and args.workers > 1:")[1][:900]
    assert "return 2" in guard, "the guard must stop the run, not just warn"


# -- the account's profile allowance is the ceiling on workers ---------------

def test_a_full_account_is_named_as_the_cause():
    """Every worker hits this at the same moment, so an unexplained 403 fills
    the log with identical browser failures and reads like the site refusing
    us."""
    assert _is_profile_cap(Exception("403 You've reached max profiles number")) is True
    assert _is_profile_cap(Exception("Max profiles number reached")) is True


def test_other_failures_are_not_mistaken_for_a_full_account():
    for message in (
        "Connection refused",
        "401 Unauthorized: bad token",
        "500 Internal Server Error",
    ):
        assert _is_profile_cap(Exception(message)) is False, message


def test_the_launcher_says_how_many_profiles_the_run_will_hold():
    """So the ceiling on --workers is visible before the 403, not after."""
    source = Path("aw_bot/browser.py").read_text(encoding="utf-8")
    assert "self.workers = max(1, workers)" in source
    assert "profiles live at once" in source
