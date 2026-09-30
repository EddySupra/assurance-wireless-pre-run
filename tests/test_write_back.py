"""Tests for writing each lead's verdict back to the sheet.

Column L, beside the lead it belongs to, so the classification lives where
whoever works the leads will look for it rather than only in the run's
results.csv.

Two things matter more than the write itself: that a lead which was never
classified leaves the cell alone -- a browser dying is not a decision about an
applicant -- and that a sheet which cannot be written never takes down a run,
because the verdicts of every lead still to come depend on it carrying on.

    python -m pytest tests -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gspread  # noqa: E402

from aw_bot import runner, sheets  # noqa: E402
from aw_bot.config import RunConfig, SheetConfig  # noqa: E402
from aw_bot.lead import Lead  # noqa: E402


class _Sheet:
    """Records the cells written to it."""

    def __init__(self, fail=None):
        self.written = []
        self.fail = fail

    def update_acell(self, cell, value):
        if self.fail:
            raise self.fail
        self.written.append((cell, value))


def _lead(row=207):
    return Lead(
        row_number=row, first_name="RICARDO", last_name="LOPEZ", dob="1980-01-01",
        ssn_last4="1234", street="1 Main St", city="Lynwood", state="CA",
        zip_code="90262", phone="5555555555", email="x@example.com",
    )


def _patch(monkeypatch, sheet):
    monkeypatch.setattr(sheets, "_verdict_worksheet", lambda cfg: sheet)
    sheets.reset_write_cache()


# -- where it goes -----------------------------------------------------------

def test_the_verdict_goes_in_column_l_beside_its_row(monkeypatch):
    sheet = _Sheet()
    _patch(monkeypatch, sheet)

    assert sheets.write_verdict(SheetConfig(), 207, "need documents") is True
    assert sheet.written == [("L207", "need documents")]


def test_the_column_is_configurable(monkeypatch):
    """So moving it is a config change, not a code change."""
    sheet = _Sheet()
    _patch(monkeypatch, sheet)

    cfg = SheetConfig()
    cfg.verdict_column = "n"
    sheets.write_verdict(cfg, 42, "good")
    assert sheet.written == [("N42", "good")]


def test_column_l_is_the_default():
    assert SheetConfig().verdict_column == "L"
    assert SheetConfig().write_verdicts is True


# -- what is deliberately not written ----------------------------------------

def test_a_lead_with_no_verdict_leaves_the_cell_alone(monkeypatch):
    """A browser dying is not a decision about an applicant, and writing
    anything for it would dress a run problem up as a classification."""
    sheet = _Sheet()
    _patch(monkeypatch, sheet)

    assert sheets.write_verdict(SheetConfig(), 207, "") is False
    assert sheets.write_verdict(SheetConfig(), 207, "   ") is False
    assert not sheet.written


def test_a_lead_with_no_row_number_is_not_written(monkeypatch):
    """Nowhere to put it, and guessing a row would overwrite someone else."""
    sheet = _Sheet()
    _patch(monkeypatch, sheet)

    assert sheets.write_verdict(SheetConfig(), 0, "good") is False
    assert not sheet.written


def test_the_write_back_can_be_switched_off(monkeypatch):
    sheet = _Sheet()
    _patch(monkeypatch, sheet)

    cfg = SheetConfig()
    cfg.write_verdicts = False
    assert sheets.write_verdict(cfg, 207, "good") is False
    assert not sheet.written


# -- a sheet that cannot be written must not stop the run --------------------

def test_an_api_error_is_a_warning_not_a_failure(monkeypatch):
    """The verdict is already in results.csv and the log. Every lead still to
    come depends on the run carrying on."""
    response = type(
        "R", (),
        {"json": lambda self: {"error": {"code": 429, "message": "quota exceeded",
                                         "status": "RESOURCE_EXHAUSTED"}},
         "text": "quota exceeded", "status_code": 429},
    )()
    _patch(monkeypatch, _Sheet(fail=gspread.exceptions.APIError(response)))
    assert sheets.write_verdict(SheetConfig(), 207, "good") is False


def test_any_other_failure_is_also_survivable(monkeypatch):
    _patch(monkeypatch, _Sheet(fail=RuntimeError("network gone")))
    assert sheets.write_verdict(SheetConfig(), 207, "good") is False


# -- the runner calls it once per classified lead ----------------------------

def test_recording_a_verdict_writes_it(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "write_verdict", lambda cfg, row, verdict: calls.append((row, verdict)))

    state = runner._BatchState(total=1, sheet_cfg=SheetConfig())
    state.record(_lead(207), "ok", "", "need documents")

    assert calls == [(207, "need documents")]


def test_recording_a_failure_writes_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "write_verdict", lambda cfg, row, verdict: calls.append((row, verdict)))

    state = runner._BatchState(total=1, sheet_cfg=SheetConfig())
    state.record(_lead(208), "failed", "Step 2: URL never reached /apply-now", "")

    assert not calls
    # But it is still recorded locally, so the row is not silently forgotten.
    assert state.rows[0]["sheet_row"] == 208


def test_no_sheet_config_means_no_write(monkeypatch):
    """What the rest of the suite relies on to stay offline."""
    calls = []
    monkeypatch.setattr(runner, "write_verdict", lambda *a: calls.append(a))

    state = runner._BatchState(total=1)
    state.record(_lead(209), "ok", "", "good")
    assert not calls


def test_the_write_happens_outside_the_batch_lock():
    """A network call under the lock would stop every other worker recording
    while one of them talks to Google."""
    source = Path("aw_bot/runner.py").read_text(encoding="utf-8")
    body = source.split("def record(")[1].split("\ndef ")[0]
    lock_block_end = body.index("        # Put the verdict back")
    assert "with self.lock:" in body[:lock_block_end]
    # The call sits at method indentation, not inside the `with`.
    assert "\n        if verdict and self.sheet_cfg is not None:" in body
