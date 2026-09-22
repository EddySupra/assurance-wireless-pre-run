"""Tests for the per-lead profile: its OS mix and its agreement with the proxy.

A generated fingerprint only helps if it is unremarkable, and "unremarkable"
is a property of the distribution rather than of any one profile. It also only
helps if nothing underneath it contradicts the exit it goes out through --
WebRTC in particular, which answers with the machine's own address unless it
is told not to and makes every other precaution beside the point.

    python -m pytest tests -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot.config import RunConfig  # noqa: E402
from aw_bot.gologin_backend import (  # noqa: E402
    _close_other_tabs,
    _match_profile_to_proxy,
    _pick_os,
    _size_window_to_screen,
)


# -- the OS mix --------------------------------------------------------------

def test_every_choice_comes_from_the_allowed_set():
    picks = {_pick_os(("win", "mac")) for _ in range(200)}
    assert picks <= {"win", "mac"}


def test_a_single_option_is_always_chosen():
    assert _pick_os(("mac",)) == "mac"


def test_an_empty_setting_falls_back_to_windows():
    assert _pick_os(()) == "win"
    assert _pick_os(None) == "win"


def test_windows_dominates_the_mix():
    """An even split would make every other applicant a Mac user.

    That is roughly three times the real share, and a run of leads that is
    half macOS is itself a pattern -- the opposite of what a generated
    fingerprint is for.
    """
    picks = [_pick_os(("win", "mac")) for _ in range(3000)]
    share = picks.count("win") / len(picks)
    assert 0.7 < share < 0.95, share


# -- agreement with the proxy ------------------------------------------------

class _FakeGoLogin:
    """Enough of the SDK to see what would have been written."""

    def __init__(self, profile):
        self.profile = profile
        self.updated = None

    def setProfileId(self, profile_id):
        pass

    def getProfile(self, profile_id=None):
        return self.profile

    def update(self, options):
        self.updated = options
        return options


def test_webrtc_in_real_mode_is_corrected():
    """The one that matters: `real` answers STUN with the true address.

    A page reads the home IP straight past the proxy, so the site sees a
    residential exit in California and a WebRTC candidate from wherever this
    machine actually is.
    """
    gl = _FakeGoLogin({"webRTC": {"mode": "real", "fillBasedOnIp": False}})
    _match_profile_to_proxy(gl, "abc", 1)

    assert gl.updated is not None
    assert gl.updated["webRTC"]["mode"] == "alerted"
    assert gl.updated["webRTC"]["fillBasedOnIp"] is True


def test_a_masked_webrtc_that_ignores_the_exit_is_corrected():
    gl = _FakeGoLogin({"webRTC": {"mode": "alerted", "fillBasedOnIp": False}})
    _match_profile_to_proxy(gl, "abc", 1)
    assert gl.updated["webRTC"]["fillBasedOnIp"] is True


def test_a_profile_that_already_agrees_is_left_alone():
    """The generated fingerprint is coherent; writing over it is the risk."""
    gl = _FakeGoLogin({
        "webRTC": {"mode": "alerted", "fillBasedOnIp": True},
        "timezone": {"fillBasedOnIp": True},
    })
    _match_profile_to_proxy(gl, "abc", 1)
    assert gl.updated is None


def test_a_pinned_timezone_is_pointed_back_at_the_exit():
    gl = _FakeGoLogin({
        "webRTC": {"mode": "alerted", "fillBasedOnIp": True},
        "timezone": {"fillBasedOnIp": False},
    })
    _match_profile_to_proxy(gl, "abc", 1)
    assert gl.updated["timezone"]["fillBasedOnIp"] is True
    # WebRTC was already right, so it is not rewritten.
    assert "webRTC" not in gl.updated


def test_the_update_carries_the_profile_id():
    gl = _FakeGoLogin({"webRTC": {"mode": "real"}})
    _match_profile_to_proxy(gl, "profile-123", 1)
    assert gl.updated["id"] == "profile-123"


def test_an_unreadable_profile_is_survivable():
    """Best-effort: a lead is not worth failing over a tuning call."""

    class Broken:
        def setProfileId(self, profile_id):
            pass

        def getProfile(self, profile_id=None):
            raise RuntimeError("API down")

    _match_profile_to_proxy(Broken(), "abc", 1)  # must not raise


def test_a_failed_write_is_survivable():
    class HalfBroken(_FakeGoLogin):
        def update(self, options):
            raise RuntimeError("rejected")

    gl = HalfBroken({"webRTC": {"mode": "real"}})
    _match_profile_to_proxy(gl, "abc", 1)  # must not raise


# -- one tab, and a window with real dimensions ------------------------------

class _FakeSwitch:
    def __init__(self, driver):
        self.driver = driver

    def window(self, handle):
        if handle not in self.driver.handles:
            raise RuntimeError("no such window")
        self.driver.current = handle


class _FakeDriver:
    def __init__(self, handles, current=None, screen=None):
        self.handles = list(handles)
        self.current = current or (handles[0] if handles else None)
        self.screen = screen
        self.switch_to = _FakeSwitch(self)
        self.size = None
        self.position = None

    @property
    def window_handles(self):
        return list(self.handles)

    @property
    def current_window_handle(self):
        if self.current is None:
            raise RuntimeError("no window")
        return self.current

    def close(self):
        self.handles.remove(self.current)
        self.current = None

    def execute_script(self, script, *args):
        if self.screen is None:
            raise RuntimeError("cannot read screen")
        return self.screen

    def set_window_size(self, w, h):
        self.size = (w, h)

    def set_window_position(self, x, y):
        self.position = (x, y)


def test_the_extra_tabs_are_closed():
    """Orbita opens its own start page beside ours on every run."""
    driver = _FakeDriver(["a", "b", "c"], current="b")
    _close_other_tabs(driver, 1)
    assert driver.window_handles == ["b"]


def test_the_attached_tab_is_the_one_kept():
    """Closing the tab the driver is on leaves every later command homeless."""
    driver = _FakeDriver(["a", "b", "c"], current="a")
    _close_other_tabs(driver, 1)
    assert driver.window_handles == ["a"]
    assert driver.current == "a"


def test_a_single_tab_is_left_alone():
    driver = _FakeDriver(["a"], current="a")
    _close_other_tabs(driver, 1)
    assert driver.window_handles == ["a"]


def test_the_window_is_sized_to_the_profiles_own_screen():
    """Not to a constant.

    Every generated fingerprint carries its own screen, so a fixed 1440x1000
    is larger than the monitor on a profile reporting 1366x768 -- a window
    bigger than its screen, which is a sharper contradiction than the zero
    dimensions it was meant to fix.
    """
    driver = _FakeDriver(["a"], screen={"w": 1366, "h": 728, "fw": 1366, "fh": 768})
    _size_window_to_screen(driver, RunConfig(), 1)
    assert driver.size == (1366, 728)
    assert driver.position == (0, 0)


def test_the_window_never_exceeds_the_screen_it_claims():
    driver = _FakeDriver(["a"], screen={"w": 1280, "h": 700, "fw": 1280, "fh": 800})
    _size_window_to_screen(driver, RunConfig(), 1)
    width, height = driver.size
    assert width <= 1280 and height <= 800


def test_the_window_is_clamped_to_the_real_monitor(monkeypatch):
    """The regression that broke --real-input.

    A GoLogin profile's screen belongs to its fingerprint, not to this
    machine. Sizing the window to a fingerprinted 1920x1080 on a smaller
    physical display puts the lower half of the form below the bottom of the
    screen -- which the synthetic path never notices, because it addresses the
    page, and which kills real input, because the real mouse can only reach
    pixels that exist.
    """
    import aw_bot.gologin_backend as backend

    monkeypatch.setattr(backend.real_input, "display_size", lambda: (1536, 864))
    driver = _FakeDriver(["a"], screen={"w": 1920, "h": 1080, "fw": 1920, "fh": 1080})
    _size_window_to_screen(driver, RunConfig(), 1)

    width, height = driver.size
    assert width <= 1536
    assert height <= 864


def test_a_window_smaller_than_the_monitor_is_not_stretched(monkeypatch):
    """Clamping only ever shrinks; it must not invent a bigger window."""
    import aw_bot.gologin_backend as backend

    monkeypatch.setattr(backend.real_input, "display_size", lambda: (2560, 1440))
    driver = _FakeDriver(["a"], screen={"w": 1366, "h": 728, "fw": 1366, "fh": 768})
    _size_window_to_screen(driver, RunConfig(), 1)
    assert driver.size == (1366, 728)


def test_an_unknown_display_leaves_the_browsers_answer_alone(monkeypatch):
    """pyautogui missing is not a reason to refuse to size the window."""
    import aw_bot.gologin_backend as backend

    monkeypatch.setattr(backend.real_input, "display_size", lambda: None)
    driver = _FakeDriver(["a"], screen={"w": 1600, "h": 900, "fw": 1600, "fh": 900})
    _size_window_to_screen(driver, RunConfig(), 1)
    assert driver.size == (1600, 900)


def test_an_unreadable_screen_falls_back_to_the_configured_size():
    """A real window beats a zero-sized one even if the size is a guess."""
    driver = _FakeDriver(["a"], screen=None)
    cfg = RunConfig()
    cfg.window_size = "1440,1000"
    _size_window_to_screen(driver, cfg, 1)
    assert driver.size == (1440, 1000)


def test_an_implausible_screen_is_not_trusted():
    """A 0x0 or tiny screen reading would produce the very window we avoid."""
    driver = _FakeDriver(["a"], screen={"w": 0, "h": 0, "fw": 0, "fh": 0})
    cfg = RunConfig()
    cfg.window_size = "1440,1000"
    _size_window_to_screen(driver, cfg, 1)
    assert driver.size == (1440, 1000)


def test_headless_runs_are_left_alone():
    """They are launched with --window-size and have no window to place."""
    driver = _FakeDriver(["a"], screen={"w": 1920, "h": 1040})
    cfg = RunConfig()
    cfg.headless = True
    _size_window_to_screen(driver, cfg, 1)
    assert driver.size is None


# -- the defaults the user asked for ----------------------------------------

def test_a_fresh_profile_and_proxy_per_lead_is_the_default():
    assert RunConfig().gologin.disposable_profiles is True


def test_the_busy_ceiling_is_one_minute():
    """Every lead that sat past a minute failed anyway; one waited 10.5."""
    assert RunConfig().max_busy_wait == 60.0
