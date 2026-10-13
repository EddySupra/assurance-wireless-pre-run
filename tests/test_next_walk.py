import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run as run_module  # noqa: E402
from aw_bot.classify import (  # noqa: E402
    AW_TRANSFER,
    BAD_EMAIL,
    GOOD,
    NEED_DOCUMENTS,
    REJECTED,
    UNKNOWN,
)
from aw_bot.runner import _browser_died, _made_progress  # noqa: E402


def test_a_refused_chromedriver_connection_counts_as_a_dead_browser():
    exc = Exception(
        "HTTPConnectionPool(host='localhost', port=57212): Max retries exceeded "
        "with url: /session/abc/url (Caused by NewConnectionError('HTTPConnection"
        "(host=\\'localhost\\', port=57212): Failed to establish a new connection: "
        "[WinError 10061] No connection could be made because the target machine "
        "actively refused it'))"
    )
    assert _browser_died(exc) is True


def test_the_webdriver_phrasings_are_still_recognised():
    for message in (
        "invalid session id",
        "session deleted as the browser has closed the connection",
        "no such window: target window already closed",
        "chrome not reachable",
    ):
        assert _browser_died(Exception(message)) is True, message


def test_an_ordinary_step_failure_is_not_a_dead_browser():
    assert _browser_died(Exception("Step 6: the form rejected this lead")) is False


class _Lead:
    def __init__(self, row: int) -> None:
        self.row_number = row
        self.label = f"row {row}"


def _leads(*rows):
    return [_Lead(r) for r in rows]


def test_a_bad_email_is_not_progress():
    assert _made_progress("failed", BAD_EMAIL, "Step 6: invalid email address") is False


def test_the_verdict_match_ignores_case_and_padding():
    assert _made_progress("failed", " Bad Email ", "Step 6: ...") is False


def test_a_classified_verdict_lets_the_walk_carry_on():
    for verdict in (GOOD, NEED_DOCUMENTS, REJECTED, AW_TRANSFER):
        assert _made_progress("failed", verdict, "Step 10: ...") is False, verdict


def test_an_unknown_verdict_stops_the_walk():
    assert _made_progress("failed", UNKNOWN, "Step 10: ...") is True


def test_a_verdict_nobody_has_taught_this_about_stops_the_walk():
    assert _made_progress("failed", "some future bucket", "Step 10: ...") is True


def test_a_completed_lead_lets_the_walk_carry_on():
    assert _made_progress("ok", "", "") is False


def test_a_step_9_failure_is_progress_despite_having_no_verdict():
    detail = (
        "Step 9: the form gave up with -- Error: Unable to continue ... (600) "
        "-- and Cloudflare Turnstile error 600010"
    )
    assert _made_progress("failed", "", detail) is True


def test_a_dead_browser_is_not_progress():
    detail = (
        "MaxRetryError: HTTPConnectionPool(host='localhost', port=57212): Max "
        "retries exceeded with url: /session/abc/url (Caused by "
        "NewConnectionError('... actively refused it'))"
    )
    assert _made_progress("failed", "", detail) is False


def test_falling_over_before_the_form_is_not_progress():
    assert _made_progress("failed", "", "Step 4: the enrollment frame never loaded") is False
    assert _made_progress("failed", "", "Step 1: expected a host in ...") is False


def test_an_empty_detail_is_not_progress():
    assert _made_progress("failed", "", "") is False
    assert _made_progress("failed", None, None) is False


def test_one_lead_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(run_module, "CURSOR_PATH", tmp_path / "cursor")
    monkeypatch.setattr(run_module, "_read_cursor", lambda: 108)

    chosen = run_module._next_untested(_leads(107, 108, 109, 110, 111))
    assert [l.row_number for l in chosen] == [109]


def test_a_count_hands_out_that_many(tmp_path, monkeypatch):
    monkeypatch.setattr(run_module, "CURSOR_PATH", tmp_path / "cursor")
    monkeypatch.setattr(run_module, "_read_cursor", lambda: 108)

    chosen = run_module._next_untested(_leads(109, 110, 111, 112, 113), count=3)
    assert [l.row_number for l in chosen] == [109, 110, 111]


def test_leads_at_or_before_the_cursor_are_never_offered(tmp_path, monkeypatch):
    monkeypatch.setattr(run_module, "CURSOR_PATH", tmp_path / "cursor")
    monkeypatch.setattr(run_module, "_read_cursor", lambda: 110)

    chosen = run_module._next_untested(_leads(108, 109, 110, 111, 112), count=5)
    assert [l.row_number for l in chosen] == [111, 112]


def test_handing_leads_out_does_not_move_the_cursor(tmp_path, monkeypatch):
    cursor = tmp_path / "cursor"
    cursor.write_text("108", encoding="utf-8")
    monkeypatch.setattr(run_module, "CURSOR_PATH", cursor)
    monkeypatch.setattr(run_module, "_read_cursor", lambda: 108)

    run_module._next_untested(_leads(109, 110, 111, 112), count=3)
    assert cursor.read_text(encoding="utf-8").strip() == "108"


def test_the_cursor_advances_as_each_lead_starts(tmp_path, monkeypatch):
    cursor = tmp_path / "cursor"
    cursor.write_text("108", encoding="utf-8")
    monkeypatch.setattr(run_module, "CURSOR_PATH", cursor)
    monkeypatch.setattr(
        run_module, "_read_cursor",
        lambda: int(cursor.read_text(encoding="utf-8").strip() or 0),
    )

    run_module._record_cursor(_Lead(109))
    assert cursor.read_text(encoding="utf-8").strip() == "109"
    run_module._record_cursor(_Lead(110))
    assert cursor.read_text(encoding="utf-8").strip() == "110"


def test_the_cursor_never_moves_backwards(tmp_path, monkeypatch):
    cursor = tmp_path / "cursor"
    cursor.write_text("120", encoding="utf-8")
    monkeypatch.setattr(run_module, "CURSOR_PATH", cursor)
    monkeypatch.setattr(
        run_module, "_read_cursor",
        lambda: int(cursor.read_text(encoding="utf-8").strip() or 0),
    )

    run_module._record_cursor(_Lead(115))
    assert cursor.read_text(encoding="utf-8").strip() == "120"


def test_a_count_larger_than_the_sheet_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(run_module, "CURSOR_PATH", tmp_path / "cursor")
    monkeypatch.setattr(run_module, "_read_cursor", lambda: 108)

    chosen = run_module._next_untested(_leads(109, 110), count=50)
    assert [l.row_number for l in chosen] == [109, 110]


def test_a_count_of_zero_still_hands_out_one(tmp_path, monkeypatch):
    monkeypatch.setattr(run_module, "CURSOR_PATH", tmp_path / "cursor")
    monkeypatch.setattr(run_module, "_read_cursor", lambda: 108)

    chosen = run_module._next_untested(_leads(109, 110), count=0)
    assert [l.row_number for l in chosen] == [109]


def test_nothing_left_returns_empty_and_leaves_the_cursor_alone(tmp_path, monkeypatch):
    cursor = tmp_path / "cursor"
    cursor.write_text("200", encoding="utf-8")
    monkeypatch.setattr(run_module, "CURSOR_PATH", cursor)
    monkeypatch.setattr(run_module, "_read_cursor", lambda: 200)

    assert run_module._next_untested(_leads(109, 110), count=5) == []
    assert cursor.read_text(encoding="utf-8").strip() == "200"


def test_a_crash_on_the_first_lead_leaves_the_rest_available(tmp_path, monkeypatch):
    cursor = tmp_path / "cursor"
    cursor.write_text("131", encoding="utf-8")
    monkeypatch.setattr(run_module, "CURSOR_PATH", cursor)
    monkeypatch.setattr(
        run_module, "_read_cursor",
        lambda: int(cursor.read_text(encoding="utf-8").strip() or 0),
    )

    sheet = _leads(*range(132, 152))
    handed_out = run_module._next_untested(sheet, count=20)
    assert len(handed_out) == 20

    run_module._record_cursor(handed_out[0])

    assert [l.row_number for l in run_module._next_untested(sheet, count=3)] == [
        133, 134, 135
    ]
