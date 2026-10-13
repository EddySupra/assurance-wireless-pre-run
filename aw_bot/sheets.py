import csv
import threading
from pathlib import Path

import gspread

from .config import SheetConfig
from .errors import AwBotError, LeadDataError
from .lead import COLUMN_FALLBACK, FIELD_ALIASES, OPTIONAL, Lead, normalize_header
from .logs import LOG


class SheetError(AwBotError):
    pass


def load_leads(cfg: SheetConfig, only_row: int | None = None) -> list[Lead]:
    rows = _fetch_values(cfg)

    if len(rows) < cfg.header_row:
        raise SheetError(f"Sheet has {len(rows)} rows; no header row at {cfg.header_row}")

    headers = rows[cfg.header_row - 1]
    columns = _map_columns(headers)
    data_rows = rows[cfg.header_row :]

    leads: list[Lead] = []
    skipped = 0

    for offset, row in enumerate(data_rows):
        row_number = cfg.header_row + 1 + offset

        if only_row is not None and row_number != only_row:
            continue
        if not any(str(cell).strip() for cell in row):
            continue

        raw = {field: _cell(row, index) for field, index in columns.items()}

        if not any(str(raw.get(field) or "").strip() for field in columns if field not in OPTIONAL):
            continue

        try:
            leads.append(Lead.from_mapping(raw, row_number=row_number))
        except LeadDataError as exc:
            LOG.error("Skipping %s", exc)
            skipped += 1

    if only_row is not None and not leads:
        raise SheetError(f"Row {only_row} is empty, invalid, or past the end of the sheet")

    LOG.info("Loaded %d lead(s) from the sheet (%d skipped)", len(leads), skipped)
    return leads


def _fetch_values(cfg: SheetConfig) -> list[list[str]]:
    if not cfg.credentials_path.exists():
        raise SheetError(
            f"Service-account JSON not found at {cfg.credentials_path}. Download "
            f"the key from Google Cloud and share the sheet with that account's "
            f"client_email address."
        )
    if not (cfg.spreadsheet_key or cfg.spreadsheet_url):
        raise SheetError(
            "Set spreadsheet_key (or spreadsheet_url) in aw_bot/config.py, or "
            "pass --sheet-key on the command line."
        )

    try:
        client = gspread.service_account(filename=str(cfg.credentials_path))
        if cfg.spreadsheet_key:
            spreadsheet = client.open_by_key(cfg.spreadsheet_key)
        else:
            spreadsheet = client.open_by_url(cfg.spreadsheet_url)

        worksheet = (
            spreadsheet.worksheet(cfg.worksheet_name)
            if cfg.worksheet_name
            else spreadsheet.sheet1
        )
        LOG.info("Reading '%s' / '%s'", spreadsheet.title, worksheet.title)
        return worksheet.get_all_values()

    except gspread.exceptions.SpreadsheetNotFound as exc:
        raise SheetError(
            "Spreadsheet not found. Most often this means the sheet was never "
            "shared with the service account's client_email."
        ) from exc
    except gspread.exceptions.WorksheetNotFound as exc:
        raise SheetError(f"No worksheet named {cfg.worksheet_name!r} in that spreadsheet") from exc
    except gspread.exceptions.APIError as exc:
        raise SheetError(f"Google Sheets API rejected the request: {exc}") from exc


def _map_columns(headers: list[str]) -> dict[str, int]:
    seen = {normalize_header(h): i for i, h in enumerate(headers) if str(h).strip()}
    columns: dict[str, int] = {}

    for field, aliases in FIELD_ALIASES.items():
        index = next((seen[a] for a in aliases if a in seen), None)

        if index is None:
            index = _letter_index(COLUMN_FALLBACK[field])
            if field not in OPTIONAL:
                LOG.warning(
                    "No header matched %r; falling back to column %s",
                    field,
                    COLUMN_FALLBACK[field],
                )
        columns[field] = index

    return columns


_write_lock = threading.Lock()
_write_sheet = None


def _verdict_worksheet(cfg: SheetConfig):
    global _write_sheet
    if _write_sheet is not None:
        return _write_sheet

    client = gspread.service_account(filename=str(cfg.credentials_path))
    spreadsheet = (
        client.open_by_key(cfg.spreadsheet_key) if cfg.spreadsheet_key
        else client.open_by_url(cfg.spreadsheet_url)
    )
    _write_sheet = (
        spreadsheet.worksheet(cfg.worksheet_name) if cfg.worksheet_name
        else spreadsheet.sheet1
    )
    return _write_sheet


def reset_write_cache() -> None:
    global _write_sheet
    with _write_lock:
        _write_sheet = None


def write_verdict(cfg: SheetConfig, row_number: int, verdict: str) -> bool:
    if not cfg.write_verdicts:
        return False
    if not row_number or not (verdict or "").strip():
        return False

    cell = f"{cfg.verdict_column.upper()}{int(row_number)}"
    try:
        with _write_lock:
            worksheet = _verdict_worksheet(cfg)
            worksheet.update_acell(cell, verdict)
    except gspread.exceptions.APIError as exc:
        LOG.warning(
            "Could not write %r to %s: %s. The verdict is still in results.csv.",
            verdict, cell, exc,
        )
        return False
    except Exception as exc:
        LOG.warning(
            "Could not write %r to %s (%s: %s). The verdict is still in "
            "results.csv.", verdict, cell, type(exc).__name__, exc,
        )
        return False

    LOG.info("Wrote %r to %s", verdict, cell)
    return True


def _letter_index(letter: str) -> int:
    return ord(letter.upper()) - ord("A")


def _cell(row: list[str], index: int) -> str:
    return row[index] if 0 <= index < len(row) else ""


def completed_rows(results_csv: Path) -> set[int]:
    if not results_csv.exists():
        raise SheetError(f"No results file at {results_csv}")

    done: set[int] = set()
    with results_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("outcome") == "ok" and str(row.get("sheet_row") or "").strip():
                done.add(int(row["sheet_row"]))

    LOG.info("Resume: skipping %d lead(s) already completed in %s", len(done), results_csv)
    return done
