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


def test_every_choice_comes_from_the_allowed_set():
    picks = {_pick_os(("win", "mac")) for _ in range(200)}
    assert picks <= {"win", "mac"}


def test_a_single_option_is_always_chosen():
    assert _pick_os(("mac",)) == "mac"


def test_an_empty_setting_falls_back_to_windows():
    assert _pick_os(()) == "win"
    assert _pick_os(None) == "win"


def test_windows_dominates_the_mix():
    picks = [_pick_os(("win", "mac")) for _ in range(3000)]
    share = picks.count("win") / len(picks)
    assert 0.7 < share < 0.95, share


class _FakeGoLogin:
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
    assert "webRTC" not in gl.updated


def test_the_update_carries_the_profile_id():
    gl = _FakeGoLogin({"webRTC": {"mode": "real"}})
    _match_profile_to_proxy(gl, "profile-123", 1)
    assert gl.updated["id"] == "profile-123"


def test_an_unreadable_profile_is_survivable():
    class Broken:
        def setProfileId(self, profile_id):
            pass

        def getProfile(self, profile_id=None):
            raise RuntimeError("API down")

    _match_profile_to_proxy(Broken(), "abc", 1)


def test_a_failed_write_is_survivable():
    class HalfBroken(_FakeGoLogin):
        def update(self, options):
            raise RuntimeError("rejected")

    gl = HalfBroken({"webRTC": {"mode": "real"}})
    _match_profile_to_proxy(gl, "abc", 1)


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
    driver = _FakeDriver(["a", "b", "c"], current="b")
    _close_other_tabs(driver, 1)
    assert driver.window_handles == ["b"]


def test_the_attached_tab_is_the_one_kept():
    driver = _FakeDriver(["a", "b", "c"], current="a")
    _close_other_tabs(driver, 1)
    assert driver.window_handles == ["a"]
    assert driver.current == "a"


def test_a_single_tab_is_left_alone():
    driver = _FakeDriver(["a"], current="a")
    _close_other_tabs(driver, 1)
    assert driver.window_handles == ["a"]


def test_the_window_is_sized_to_the_profiles_own_screen():
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
    import aw_bot.gologin_backend as backend

    monkeypatch.setattr(backend.real_input, "display_size", lambda: (1536, 864))
    driver = _FakeDriver(["a"], screen={"w": 1920, "h": 1080, "fw": 1920, "fh": 1080})
    _size_window_to_screen(driver, RunConfig(), 1)

    width, height = driver.size
    assert width <= 1536
    assert height <= 864


def test_a_window_smaller_than_the_monitor_is_not_stretched(monkeypatch):
    import aw_bot.gologin_backend as backend

    monkeypatch.setattr(backend.real_input, "display_size", lambda: (2560, 1440))
    driver = _FakeDriver(["a"], screen={"w": 1366, "h": 728, "fw": 1366, "fh": 768})
    _size_window_to_screen(driver, RunConfig(), 1)
    assert driver.size == (1366, 728)


def test_an_unknown_display_leaves_the_browsers_answer_alone(monkeypatch):
    import aw_bot.gologin_backend as backend

    monkeypatch.setattr(backend.real_input, "display_size", lambda: None)
    driver = _FakeDriver(["a"], screen={"w": 1600, "h": 900, "fw": 1600, "fh": 900})
    _size_window_to_screen(driver, RunConfig(), 1)
    assert driver.size == (1600, 900)


def test_an_unreadable_screen_falls_back_to_the_configured_size():
    driver = _FakeDriver(["a"], screen=None)
    cfg = RunConfig()
    cfg.window_size = "1440,1000"
    _size_window_to_screen(driver, cfg, 1)
    assert driver.size == (1440, 1000)


def test_an_implausible_screen_is_not_trusted():
    driver = _FakeDriver(["a"], screen={"w": 0, "h": 0, "fw": 0, "fh": 0})
    cfg = RunConfig()
    cfg.window_size = "1440,1000"
    _size_window_to_screen(driver, cfg, 1)
    assert driver.size == (1440, 1000)


def test_headless_runs_are_left_alone():
    driver = _FakeDriver(["a"], screen={"w": 1920, "h": 1040})
    cfg = RunConfig()
    cfg.headless = True
    _size_window_to_screen(driver, cfg, 1)
    assert driver.size is None


def test_a_fresh_profile_and_proxy_per_lead_is_the_default():
    assert RunConfig().gologin.disposable_profiles is True


def test_the_busy_ceiling_is_one_minute():
    assert RunConfig().max_busy_wait == 60.0
