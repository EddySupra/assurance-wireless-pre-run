"""Reads leads from the Google Sheet via a gspread service account.

Uses get_all_values() rather than get_all_records() on purpose: column F has
no header, and get_all_records raises on blank/duplicate header cells.
"""

import csv
from pathlib import Path

import gspread

from .config import SheetConfig
from .errors import AwBotError, LeadDataError
from .lead import COLUMN_FALLBACK, FIELD_ALIASES, OPTIONAL, Lead, normalize_header
from .logs import LOG


class SheetError(AwBotError):
    """Could not open or read the sheet."""


def load_leads(cfg: SheetConfig, only_row: int | None = None) -> list[Lead]:
    """Return every valid lead in the sheet, or just one if only_row is given.

    Rows that fail validation are logged and skipped so one bad row doesn't
    stop the batch.
    """
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
            continue  # blank spacer row

        raw = {field: _cell(row, index) for field, index in columns.items()}

        # A row carrying nothing in any field we read is not a malformed
        # lead, it is not a lead at all -- so it is skipped the same way a
        # wholly blank row is, rather than counted and shouted about.
        #
        # The check above only catches rows where every single cell is empty,
        # and this sheet has tens of thousands of trailing rows that hold
        # something harmless outside the mapped columns: a leftover formula,
        # a stray space, a checkbox. Each of those produced an ERROR line
        # reading "missing required field(s)" followed by every field name,
        # which buried the real data problems (two truncated emails, a
        # handful of genuinely incomplete rows) under ~50_000 lines of noise
        # and left a --next run grinding for minutes before it opened a
        # browser. Measured on this sheet.
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
    """Field name -> column index, by header text, falling back to position."""
    seen = {normalize_header(h): i for i, h in enumerate(headers) if str(h).strip()}
    columns: dict[str, int] = {}

    for field, aliases in FIELD_ALIASES.items():
        index = next((seen[a] for a in aliases if a in seen), None)

        if index is None:
            index = _letter_index(COLUMN_FALLBACK[field])
            # Column F legitimately has no header, so only make noise about
            # the fields we actually expect to be labeled.
            if field not in OPTIONAL:
                LOG.warning(
                    "No header matched %r; falling back to column %s",
                    field,
                    COLUMN_FALLBACK[field],
                )
        columns[field] = index

    return columns


def _letter_index(letter: str) -> int:
    return ord(letter.upper()) - ord("A")


def _cell(row: list[str], index: int) -> str:
    return row[index] if 0 <= index < len(row) else ""


def completed_rows(results_csv: Path) -> set[int]:
    """Sheet rows a previous run finished, read from its results.csv.

    Resuming by row number alone is unsafe once workers > 1: leads finish out
    of order, so rows after the throttled one may already be submitted.
    Skipping the rows recorded as "ok" is what prevents a duplicate
    application. Rows that failed are NOT skipped -- they never went through,
    so they are fair game on a retry.
    """
    if not results_csv.exists():
        raise SheetError(f"No results file at {results_csv}")

    done: set[int] = set()
    with results_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("outcome") == "ok" and str(row.get("sheet_row") or "").strip():
                done.add(int(row["sheet_row"]))

    LOG.info("Resume: skipping %d lead(s) already completed in %s", len(done), results_csv)
    return done
