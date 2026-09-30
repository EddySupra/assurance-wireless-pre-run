"""Tests for the browser-level click with a real press duration.

The gap this fills is narrow and specific. Typing without --real-input already
goes through chromedriver to CDP Input.dispatchKeyEvent, so it is trusted and
already paced. Clicking is trusted too -- except that ActionChains refuses
inside the enrollment frame (it addresses the top-level viewport, and that
frame is taller than the window, so a press aimed in there can land nowhere at
all). In-frame clicks therefore fell through to sb.click(), whose press
duration is zero on every click in the run.

What matters most here is the refusal behaviour: every path that cannot
complete a click must leave the ordinary click still correct, and must never
leave the page holding a mouse button down.

    python -m pytest tests -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot import cdp_input, real_input  # noqa: E402
from aw_bot.config import RunConfig  # noqa: E402


class _Driver:
    def __init__(self, fail_on=None):
        self.events = []
        self.fail_on = fail_on

    def execute_cdp_cmd(self, cmd, params):
        if self.fail_on and params.get("type") == self.fail_on:
            raise RuntimeError("socket died")
        self.events.append((params.get("type"), params.get("x"), params.get("y")))


class _Sb:
    def __init__(self, driver=None):
        self.driver = driver if driver is not None else _Driver()


class _NoCdp:
    """A driver from a backend that cannot dispatch CDP."""
    driver = object()


def _aimed(monkeypatch, point=(400.0, 300.0)):
    origin = {"x": 0, "y": 0, "w": 1900, "h": 1000, "fx": 0.0, "fy": 0.0}
    monkeypatch.setattr(
        real_input, "aim_point", lambda sb, el: (point[0], point[1], origin)
    )


def _fast(monkeypatch):
    monkeypatch.setattr(cdp_input.time, "sleep", lambda s: None)


# -- what a successful click looks like ---------------------------------------

def test_a_click_presses_holds_and_releases(monkeypatch):
    _aimed(monkeypatch)
    _fast(monkeypatch)
    sb = _Sb()

    assert cdp_input.click(sb, object(), RunConfig()) is True

    kinds = [kind for kind, _, _ in sb.driver.events]
    assert kinds.count("mousePressed") == 1
    assert kinds.count("mouseReleased") == 1
    assert kinds.index("mousePressed") < kinds.index("mouseReleased")


def test_the_pointer_approaches_before_it_presses(monkeypatch):
    """A click with no preceding movement is as distinctive as one with no
    dwell -- and the frame is where ActionChains could not draw the approach."""
    _aimed(monkeypatch)
    _fast(monkeypatch)
    sb = _Sb()

    cdp_input.click(sb, object(), RunConfig())
    kinds = [kind for kind, _, _ in sb.driver.events]
    assert kinds.count("mouseMoved") >= 4
    assert kinds.index("mouseMoved") < kinds.index("mousePressed")


def test_the_press_lands_exactly_on_the_aimed_point(monkeypatch):
    """The approach may jitter; the click itself must not."""
    _aimed(monkeypatch, point=(512.0, 384.0))
    _fast(monkeypatch)
    sb = _Sb()

    cdp_input.click(sb, object(), RunConfig())
    pressed = [(x, y) for kind, x, y in sb.driver.events if kind == "mousePressed"]
    assert pressed == [(512.0, 384.0)]


def test_the_path_ends_on_the_target_not_near_it(monkeypatch):
    points = cdp_input._path_to(300.0, 200.0, RunConfig())
    assert points[-1] == (300.0, 200.0)
    assert len(points) >= 4
    # And it is a curve, not a straight line: the midpoint is off the chord.
    mid = points[len(points) // 2]
    chord_y = points[0][1] + (200.0 - points[0][1]) * 0.5
    assert abs(mid[1] - chord_y) > 0.5 or abs(mid[0] - (points[0][0] + (300.0 - points[0][0]) * 0.5)) > 0.5


# -- refusing, without leaving the page mid-press -----------------------------

def test_a_driver_without_cdp_falls_back(monkeypatch):
    """Not every backend can dispatch CDP; the ordinary click still works."""
    assert cdp_input.available(_NoCdp()) is False
    assert cdp_input.click(_NoCdp(), object(), RunConfig()) is False


def test_an_unaimable_element_is_refused(monkeypatch):
    """aim_point's reasons are real -- off screen, too thin, something drawn
    over it -- and none of them get better by clicking anyway."""
    monkeypatch.setattr(real_input, "aim_point", lambda sb, el: None)
    sb = _Sb()

    assert cdp_input.click(sb, object(), RunConfig()) is False
    assert not sb.driver.events


def test_a_failure_mid_press_still_releases_the_button(monkeypatch):
    """A press with no release leaves the page holding the button down, and
    the caller is about to click again."""
    _aimed(monkeypatch)
    _fast(monkeypatch)
    sb = _Sb(_Driver(fail_on="mouseReleased"))

    assert cdp_input.click(sb, object(), RunConfig()) is False
    # It tried to release, failed, and reported failure rather than claiming
    # a click it did not finish.
    assert any(kind == "mousePressed" for kind, _, _ in sb.driver.events)


def test_a_failure_before_the_press_reports_failure(monkeypatch):
    _aimed(monkeypatch)
    _fast(monkeypatch)
    sb = _Sb(_Driver(fail_on="mouseMoved"))

    assert cdp_input.click(sb, object(), RunConfig()) is False


# -- how it is wired in ------------------------------------------------------

def test_it_is_off_by_default():
    """It was on for one parallel run and a Cloudflare Turnstile checkbox
    appeared at step 9 -- the step whose whole history is about the browser
    doing things a hand-run session does not. Unexplained, so the default is
    the configuration that was working, and this stays behind a flag."""
    assert RunConfig().cdp_input is False


def test_action_chains_is_still_tried_first():
    """It is the longest-proven path; CDP covers the case it refuses."""
    source = Path("aw_bot/human.py").read_text(encoding="utf-8")
    body = source.split("def human_click(")[1].split("\ndef ")[0]
    assert body.index("_pressed_click(sb, selector, cfg)") < body.index("cdp_input.click")


def test_the_cdp_click_is_opt_in():
    source = Path("run.py").read_text(encoding="utf-8")
    assert "--cdp-input" in source
    assert "cfg.cdp_input = True" in source
    # And nothing turns it on without being asked.
    assert "cdp_input: bool = False" in Path("aw_bot/config.py").read_text(encoding="utf-8")
