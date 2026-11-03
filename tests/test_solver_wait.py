from aw_bot import page_utils


class FakeSB:
    def __init__(self, busy_for):
        self.busy_for = busy_for
        self.calls = 0

    def execute_script(self, script):
        if "window.self" in script:
            return False
        self.calls += 1
        return self.calls <= self.busy_for


def test_no_wait_when_the_solver_is_idle():
    assert page_utils.wait_for_captcha_solver(FakeSB(0), "Step 9") is True


def test_waits_until_the_solver_finishes(monkeypatch):
    monkeypatch.setattr(page_utils.time, "sleep", lambda s: None)
    sb = FakeSB(3)
    assert page_utils.wait_for_captcha_solver(sb, "Step 9", timeout=30) is True
    assert sb.calls == 4


def test_gives_up_after_the_timeout(monkeypatch):
    monkeypatch.setattr(page_utils.time, "sleep", lambda s: None)
    clock = iter(range(0, 1000, 5))
    monkeypatch.setattr(page_utils.time, "time", lambda: next(clock))
    assert page_utils.wait_for_captcha_solver(FakeSB(10**6), "Step 9", timeout=10) is False


def test_timezone_comparison_flags_a_mismatch(caplog):
    import logging
    from aw_bot import environment

    environment.EXPECTED_BY_WORKER[7] = {"ip": "1.2.3.4", "city": "Los Angeles", "region": "California", "timezone": "America/Los_Angeles"}
    with caplog.at_level(logging.INFO):
        environment._compare_with_proxy(None, {"timezone": "America/New_York"}, 7, False)
    assert any("Timezone mismatch" in r.message for r in caplog.records)

    environment.EXPECTED_BY_WORKER[8] = {"ip": "1.2.3.4", "city": "Los Angeles", "region": "California", "timezone": "America/Los_Angeles"}
    caplog.clear()
    with caplog.at_level(logging.INFO):
        environment._compare_with_proxy(None, {"timezone": "America/Los_Angeles"}, 8, False)
    assert any("Timezone matches" in r.message for r in caplog.records)
