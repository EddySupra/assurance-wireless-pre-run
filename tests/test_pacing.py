import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot import human, page_utils  # noqa: E402
from aw_bot.config import RunConfig  # noqa: E402
from aw_bot.steps import step_09_eligible_applicant as step9  # noqa: E402
from aw_bot.steps import step_10_classify as step10  # noqa: E402


def test_step_9_still_hands_the_browser_over_for_thirty_seconds():
    assert step9.SETTLE_AFTER_CONTINUE >= 30.0


def test_step_10_keeps_its_settle_window():
    assert step10.SETTLE_AFTER_CONTINUE >= 15.0


def test_the_wait_loop_still_polls_in_seconds_not_fractions():
    source = Path("aw_bot/page_utils.py").read_text(encoding="utf-8")
    body = source.split("def advance_screen(")[1].split("\ndef ")[0]
    assert "poll = 2.0" in body


def test_the_settle_is_a_bare_sleep_with_nothing_in_it():
    source = Path("aw_bot/page_utils.py").read_text(encoding="utf-8")
    body = source.split("def advance_screen(")[1].split("\ndef ")[0]
    settle = body.index("hands off for %.0fs while the form works")
    after = body[settle:settle + 400]
    assert "time.sleep(quiet)" in after
    assert "_idle_signs_of_life" not in after
    assert "execute_script" not in after


def test_step_9_sits_out_its_whole_window():
    source = Path("aw_bot/steps/step_09_eligible_applicant.py").read_text(encoding="utf-8")
    assert "first_look" not in source


def test_step_10_looks_once_inside_its_window():
    look = RunConfig().step10_first_look
    assert 0 < look < step10.SETTLE_AFTER_CONTINUE


BEFORE = ["Attestations"]
AFTER = ["California Household Worksheet"]


def _advance(monkeypatch, headings, busy=False, first_look=5.0):
    seq = [BEFORE] + list(headings)
    busy_seq = [busy]
    sleeps = []
    monkeypatch.setattr(page_utils, "first_visible", lambda sb, sels: sels[0])
    monkeypatch.setattr(page_utils, "modal_message", lambda sb: None)
    monkeypatch.setattr(page_utils, "wait_for_turnstile", lambda *a, **k: None)
    monkeypatch.setattr(page_utils, "_wait_until_enabled", lambda *a, **k: None)
    monkeypatch.setattr(page_utils, "form_validity", lambda sb: {})
    monkeypatch.setattr(page_utils, "rest", lambda *a, **k: None)
    monkeypatch.setattr(page_utils, "bring_framed_element_into_view", lambda *a, **k: True)
    monkeypatch.setattr(page_utils, "human_click", lambda *a, **k: None)
    monkeypatch.setattr(page_utils, "_nothing_happened_yet", lambda sb, before: False)
    monkeypatch.setattr(page_utils, "is_busy", lambda sb: busy_seq.pop(0) if busy_seq else False)
    monkeypatch.setattr(page_utils, "screen_headings", lambda sb: seq.pop(0) if seq else AFTER)
    monkeypatch.setattr(page_utils.time, "sleep", sleeps.append)
    page_utils.advance_screen(
        object(), RunConfig(), "Step 10", ("button.order-button",),
        settle=15.0, first_look=first_look,
    )
    return sleeps


def test_a_screen_already_up_skips_the_rest_of_the_window(monkeypatch):
    assert _advance(monkeypatch, [AFTER]) == [5.0]


def test_a_screen_not_up_yet_gets_the_whole_window_untouched(monkeypatch):
    assert _advance(monkeypatch, [BEFORE, AFTER])[:2] == [5.0, 10.0]


def test_a_new_screen_still_spinning_gets_the_whole_window(monkeypatch):
    assert _advance(monkeypatch, [AFTER], busy=True)[:2] == [5.0, 10.0]


def test_no_first_look_is_the_old_single_window(monkeypatch):
    assert _advance(monkeypatch, [AFTER], first_look=0.0) == [15.0]


def test_a_lookup_the_form_is_working_through_is_still_waited_out():
    assert RunConfig().max_busy_wait >= 60.0


def test_typing_speed_is_left_alone():
    low, high = RunConfig().type_delay
    assert (low, high) == (0.05, 0.16)


def test_every_dwell_still_has_a_range():
    for kind, (low, high) in human.DWELL.items():
        assert high > low, kind
        assert high >= low * 2, f"{kind} has almost no spread left"


def test_the_warm_up_is_shortened_but_not_removed():
    low, high = RunConfig().warm_up_seconds
    assert low > 0 and high > low


def test_leads_are_still_spaced_apart():
    low, high = RunConfig().lead_delay
    assert low >= 5.0
    assert high > low


def test_the_pointer_path_still_has_enough_samples_to_be_a_curve():
    assert RunConfig().mouse_steps >= 6
