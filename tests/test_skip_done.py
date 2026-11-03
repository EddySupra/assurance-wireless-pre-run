from aw_bot import sheets
from aw_bot.config import SheetConfig

HEADER = [
    "First Name", "Last Name", "Date of birth", "Last 4 SSN", "Street Address",
    "Apt", "City", "State", "ZIP Code", "Email", "PNUM", "Status",
]


def _row(first, status=""):
    return [first, "Doe", "01/02/1980", "1234", "1 Main St", "", "LA", "CA",
            "90001", f"{first.lower()}@x.com", "", status]


def _load(monkeypatch, rows, **kwargs):
    monkeypatch.setattr(sheets, "_fetch_values", lambda cfg: [HEADER] + rows)
    return sheets.load_leads(SheetConfig(), **kwargs)


def test_rows_with_a_status_are_skipped(monkeypatch):
    leads = _load(monkeypatch, [_row("Ann", "need documents"), _row("Bob"), _row("Cy", "rejected")])
    assert [lead.row_number for lead in leads] == [3]


def test_skip_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(sheets, "_fetch_values", lambda cfg: [HEADER, _row("Ann", "x"), _row("Bob")])
    cfg = SheetConfig()
    cfg.skip_done = False
    assert len(sheets.load_leads(cfg)) == 2


def test_a_single_requested_row_runs_even_with_a_status(monkeypatch):
    leads = _load(monkeypatch, [_row("Ann", "need documents")], only_row=2)
    assert [lead.row_number for lead in leads] == [2]
