import csv
import json
import queue
import random
import re
import sys
import threading
from pathlib import Path

from . import human, real_input, turnstile
from .artifacts import capture
from .browser import make_launcher
from .classify import (
    AW_TRANSFER,
    BAD_EMAIL,
    GOOD,
    NEED_DOCUMENTS,
    REJECTED,
    UNKNOWN,
)
from .config import RunConfig
from .errors import (
    AwBotError,
    BotBlockedError,
    LeadRejectedError,
    RealInputError,
    ThrottledError,
)
from .lead import Lead
from .sheets import write_verdict
from .logs import LOG, run_id, setup
from .page_utils import is_vendor_outage
from .steps.step_00_direct_frame import open_application_frame
from .steps.step_01_start_page import open_start_page
from .steps.step_02_apply_now import click_apply_now
from .steps.step_03_check_availability import check_availability
from .steps.step_04_open_application import open_application
from .steps.step_05_start_application import start_application
from .steps.step_06_personal_info import fill_personal_info
from .steps.step_07_service_address import fill_service_address
from .steps.step_08_contact_and_security import fill_contact_and_security
from .steps.step_09_eligible_applicant import choose_eligible_applicant
from .steps.step_10_classify import classify_lead


STEPS = (
    open_start_page,
    click_apply_now,
    check_availability,
    open_application,
    start_application,
    fill_personal_info,
    fill_service_address,
    fill_contact_and_security,
    choose_eligible_applicant,
    classify_lead,
)

STEPS_DIRECT = (open_application_frame,) + STEPS[4:]


def steps_for(cfg: RunConfig) -> tuple:
    return STEPS_DIRECT if cfg.frame_direct else STEPS


OUTCOMES = ("ok", "failed", "throttled", "not_attempted")


def run_batch(
    cfg: RunConfig, leads: list[Lead], on_lead_started=None
) -> dict[str, list]:
    rid = run_id()
    run_dir = cfg.artifacts_root / rid
    setup(run_dir, verbose=cfg.verbose)

    workers = max(1, min(cfg.workers, len(leads)))
    launcher = make_launcher(cfg, workers=workers, total_leads=len(leads))

    LOG.info("=" * 70)
    LOG.info(
        "Run %s  |  %d lead(s)  |  %d worker(s)  |  headless=%s  |  dry_run=%s",
        rid, len(leads), workers, cfg.headless, cfg.dry_run,
    )
    LOG.info("Browser: %s", launcher.describe())
    LOG.info("Artifacts: %s", run_dir)
    if workers > 1:
        LOG.info("Worker output interleaves in the console; per-lead evidence stays")
        LOG.info("separate under lead_<row>/, and results.csv is the summary.")
        if cfg.keep_open:
            LOG.warning("--keep-open is ignored with more than one worker")
    LOG.info("=" * 70)

    pending: queue.Queue = queue.Queue()
    for position, lead in enumerate(leads, start=1):
        pending.put((position, lead))

    state = _BatchState(total=len(leads), sheet_cfg=cfg.sheet)
    threads = [
        threading.Thread(
            target=_worker,
            args=(
                worker_id, cfg, launcher, run_dir, pending, state, workers,
                on_lead_started,
            ),
            name=f"lead-worker-{worker_id}",
            daemon=True,
        )
        for worker_id in range(1, workers + 1)
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    _drain_unstarted(pending, state)
    _write_results(run_dir, state.rows)

    LOG.info("=" * 70)
    LOG.info(
        "Done. %d ok, %d failed, %d throttled, %d not attempted.",
        *(len(state.results[name]) for name in OUTCOMES),
    )
    _log_verdicts(state.rows)
    for label in state.results["failed"]:
        LOG.error("FAILED: %s", label)
    if state.results["throttled"]:
        LOG.error("Batch stopped early: the enrollment host began refusing requests.")
        LOG.error(
            "Resume with --resume %s once it recovers -- that skips the leads "
            "that already completed. Do not use --start-row here: with "
            "%d worker(s) leads finish out of order, so a row after the "
            "throttled one may already be submitted.",
            run_dir / "results.csv",
            workers,
        )

    return state.results


class _BatchState:
    def __init__(self, total: int, sheet_cfg=None) -> None:
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.results: dict[str, list] = {name: [] for name in OUTCOMES}
        self.rows: list[dict] = []
        self.total = total
        self.sheet_cfg = sheet_cfg

    def record(self, lead: Lead, outcome: str, detail: str, verdict: str = "") -> None:
        with self.lock:
            self.results[outcome].append(lead.label)
            self.rows.append(
                {
                    "sheet_row": lead.row_number or "",
                    "name": f"{lead.first_name} {lead.last_name}",
                    "outcome": outcome,
                    "verdict": verdict,
                    "detail": detail,
                }
            )

        if verdict and self.sheet_cfg is not None:
            write_verdict(self.sheet_cfg, lead.row_number or 0, verdict)


def _worker(
    worker_id: int,
    cfg: RunConfig,
    launcher,
    run_dir: Path,
    pending: queue.Queue,
    state: _BatchState,
    workers: int,
    on_lead_started=None,
) -> None:
    handled = 0

    while not state.stop.is_set():
        try:
            position, lead = pending.get_nowait()
        except queue.Empty:
            return

        if handled:
            _space_out(cfg, state)
            if state.stop.is_set():
                state.record(lead, "not_attempted", "batch stopped before this lead")
                return

        if on_lead_started is not None:
            try:
                on_lead_started(lead)
            except Exception as exc:
                LOG.debug("Could not record the lead as started: %s", exc)

        handled += 1
        LOG.info("-" * 70)
        LOG.info("[w%d] Lead %d/%d -- %s", worker_id, position, state.total, lead.label)
        LOG.info("[w%d] Data: %s", worker_id, lead.for_log())

        lead_dir = run_dir / f"lead_{lead.row_number or position}"
        outcome, detail, verdict = _run_one(
            cfg, launcher, lead, lead_dir, worker_id=worker_id, allow_hold=(workers == 1)
        )
        state.record(lead, outcome, detail, verdict)

        if getattr(cfg, "stop_after_progress", False) and _made_progress(
            outcome, verdict, detail
        ):
            LOG.info(
                "[w%d] %s ended on something not yet accounted for (%s) -- "
                "stopping here so it can be looked at, rather than starting "
                "another lead. Its screenshots and page dumps are in %s.",
                worker_id, lead.label, verdict or outcome or "no verdict",
                run_dir / f"lead_{lead.row_number or position}",
            )
            state.stop.set()
            _drain_unstarted(pending, state)
            return

        if outcome == "throttled":
            LOG.error("[w%d] THROTTLED -- signalling every worker to stop.", worker_id)
            LOG.error("[w%d] %s", worker_id, detail)
            state.stop.set()
            return


def _run_one(
    cfg: RunConfig,
    launcher,
    lead: Lead,
    run_dir: Path,
    worker_id: int = 1,
    allow_hold: bool = True,
) -> tuple[str, str, str]:
    attempts = max(1, cfg.block_retries + 1)

    for attempt in range(1, attempts + 1):
        outcome, detail, verdict, blocked = _attempt_one(
            cfg, launcher, lead, run_dir, worker_id, allow_hold
        )
        if not blocked or attempt == attempts:
            if blocked:
                LOG.error(
                    "[w%d] %d browser(s) in a row failed to get anywhere for %s -- "
                    "giving up on this lead. The browsers are the problem here, "
                    "not the data.",
                    worker_id, attempts, lead.label,
                )
            return outcome, detail, verdict

        LOG.warning(
            "[w%d] Attempt %d/%d for %s failed on the browser, not the lead -- "
            "retrying on another one",
            worker_id, attempt, attempts, lead.label,
        )

    return outcome, detail, verdict


_BROWSER_GONE_SIGNALS = (
    "invalid session id",
    "session deleted",
    "browser has closed the connection",
    "not connected to devtools",
    "no such window",
    "target window already closed",
    "chrome not reachable",
    "disconnected",
    "actively refused",
    "connection refused",
    "max retries exceeded",
    "failed to establish a new connection",
    "connection aborted",
    "remote end closed connection",
    "timed out receiving message from renderer",
    "unable to receive message from renderer",
)


def _browser_died(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(signal in message for signal in _BROWSER_GONE_SIGNALS)


def _attempt_one(
    cfg: RunConfig,
    launcher,
    lead: Lead,
    run_dir: Path,
    worker_id: int,
    allow_hold: bool,
) -> tuple[str, str, str, bool]:
    verdict = ""

    real_input.reset_for_new_session()

    LOG.debug("[w%d] This lead is filled at %.2fx pace", worker_id, human.new_operator())

    try:
        with launcher.session(worker_id=worker_id) as sb:
            try:
                steps = steps_for(cfg)
                for index, step in enumerate(steps):
                    is_last = index == len(steps) - 1
                    result = step(sb, cfg, lead, run_dir, submit=not (cfg.dry_run and is_last))
                    verdict = (result or {}).get("verdict", verdict)
            except ThrottledError as exc:
                _capture_failure(sb, cfg, run_dir)
                _hold(cfg, sb, allow_hold)
                return "throttled", str(exc), verdict, False
            except LeadRejectedError as exc:
                LOG.warning("Lead rejected (%s): %s", exc.verdict, exc)
                _capture_failure(sb, cfg, run_dir)
                if (exc.verdict or "").strip().lower() == BAD_EMAIL:
                    LOG.info(
                        "Closing this browser and moving to the next lead."
                    )
                else:
                    _hold(cfg, sb, allow_hold)
                return "failed", str(exc), exc.verdict, False
            except RealInputError as exc:
                LOG.warning("Real input failed for %s: %s", lead.label, exc)
                _capture_failure(sb, cfg, run_dir)
                _hold(cfg, sb, allow_hold)
                return "failed", str(exc), verdict, True
            except BotBlockedError as exc:
                LOG.warning("Bot wall for %s: %s", lead.label, exc)
                _capture_failure(sb, cfg, run_dir)
                _hold(cfg, sb, allow_hold)
                return "failed", str(exc), verdict, True
            except AwBotError as exc:
                LOG.error("STEP FAILED for %s: %s", lead.label, exc)
                _capture_failure(sb, cfg, run_dir)
                _hold(cfg, sb, allow_hold)
                if is_vendor_outage(str(exc)):
                    LOG.warning(
                        "That is the enrollment host's own backend, not this "
                        "lead and not this automation -- trying another browser."
                    )
                    return "failed", str(exc), verdict, True
                return "failed", str(exc), verdict, _before_the_form(str(exc))
            except Exception as exc:
                gone = _browser_died(exc)
                if gone:
                    LOG.warning("Browser died mid-run for %s: %s", lead.label, exc)
                else:
                    LOG.exception("Unexpected error for %s: %s", lead.label, exc)
                _capture_failure(sb, cfg, run_dir)
                _hold(cfg, sb, allow_hold)
                return "failed", f"{type(exc).__name__}: {exc}", verdict, gone

            LOG.info("All implemented steps completed for %s", lead.label)
            _hold(cfg, sb, allow_hold)
            return "ok", "", verdict, False
    except AwBotError as exc:
        LOG.error("No browser for %s: %s", lead.label, exc)
        return "failed", f"browser did not start: {exc}", verdict, True
    except Exception as exc:
        LOG.exception("No browser for %s: %s", lead.label, exc)
        return "failed", f"browser did not start: {type(exc).__name__}: {exc}", verdict, True


def _log_verdicts(rows: list[dict]) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("verdict"):
            counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    if not counts:
        return
    LOG.info("Verdicts: %s", ", ".join(f"{n} {name}" for name, n in sorted(counts.items())))
    for row in rows:
        if row.get("verdict") == UNKNOWN:
            LOG.warning(
                "Row %s (%s) landed on a screen classify.py does not know yet.",
                row["sheet_row"], row["name"],
            )


def _space_out(cfg: RunConfig, state: _BatchState) -> None:
    low, high = cfg.lead_delay
    wait = random.uniform(low, high)
    LOG.info("Waiting %.0fs before the next lead", wait)
    state.stop.wait(wait)


_STEP_IN_DETAIL = re.compile(r"\bStep (\d+)\b", re.IGNORECASE)

_KNOWN_VERDICTS = frozenset({
    GOOD, NEED_DOCUMENTS, REJECTED, AW_TRANSFER, BAD_EMAIL,
})

_FORM_STEP = 6


def _before_the_form(detail: str) -> bool:
    match = _STEP_IN_DETAIL.search(detail or "")
    return bool(match) and int(match.group(1)) < _FORM_STEP


def _made_progress(outcome: str, verdict: str, detail: str) -> bool:
    named = (verdict or "").strip().lower()

    if named in _KNOWN_VERDICTS:
        return False
    if named == UNKNOWN:
        return True
    if named:
        return True

    if outcome == "ok":
        return False

    match = _STEP_IN_DETAIL.search(detail or "")
    if not match:
        return False
    return int(match.group(1)) >= _FORM_STEP


def _drain_unstarted(pending: queue.Queue, state: _BatchState) -> None:
    while True:
        try:
            _, lead = pending.get_nowait()
        except queue.Empty:
            return
        state.record(
            lead,
            "not_attempted",
            "batch stopped after throttling"
            if state.results["throttled"]
            else "batch stopped for a lead that needs looking at",
        )


def _capture_failure(sb, cfg: RunConfig, run_dir: Path) -> None:
    if not cfg.save_artifacts:
        return

    try:
        capture(sb, run_dir, "failure_frame", save=True)
    except Exception as exc:
        LOG.debug("Could not capture the frame at failure: %s", exc)

    _dump_turnstile(sb, run_dir)

    try:
        sb.switch_to_default_content()
    except Exception:
        pass
    capture(sb, run_dir, "failure", save=True)
    _dump_console(sb, run_dir)
    _dump_network(sb, run_dir)
    _dump_pending_requests(sb, run_dir)


def _dump_turnstile(sb, run_dir: Path) -> None:
    try:
        status = turnstile.state(sb)
    except Exception:
        return
    if not status or not status.get("observed"):
        return

    try:
        status["diagnosis"] = turnstile.diagnose(sb)
    except Exception:
        pass

    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "failure_turnstile.json").write_text(
            json.dumps(status, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        LOG.debug("Could not write the Turnstile dump: %s", exc)

    LOG.info("Turnstile at failure: %s", turnstile.describe(status))
    if status.get("errorCode"):
        LOG.warning("%s", turnstile.explain_error(status["errorCode"]))


def _dump_console(sb, run_dir: Path) -> None:
    try:
        entries = sb.console_logs()
    except Exception:
        return
    if not entries:
        return
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "failure_console.json").write_text(
            json.dumps(entries, indent=2), encoding="utf-8"
        )
        for entry in entries:
            if entry.get("level") in ("SEVERE", "ERROR"):
                LOG.warning("Console: %s", str(entry.get("message"))[:300])
    except Exception as exc:
        LOG.debug("Could not write the console dump: %s", exc)


def _dump_network(sb, run_dir: Path) -> None:
    try:
        summary = sb.network_summary()
    except Exception as exc:
        LOG.debug("Could not read the network log: %s", exc)
        return
    if not any(summary.values()):
        return

    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "failure_network.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        LOG.debug("Could not write the network dump: %s", exc)

    for response in summary.get("responses", []):
        url = str(response.get("url", ""))
        if "solixinc" not in url and "assurancewireless" not in url:
            continue
        status = response.get("status")
        if status and int(status) >= 400:
            LOG.warning(
                "Server answered %s %s for %s %s",
                status, response.get("statusText") or "", response.get("method") or "", url,
            )
    for failure in summary.get("failed", []):
        LOG.warning(
            "Request failed outright: %s %s -- %s",
            failure.get("method") or "", failure.get("url"), failure.get("error"),
        )


def _dump_pending_requests(sb, run_dir: Path) -> None:
    try:
        pending = sb.pending_requests()
    except Exception:
        return
    if not pending:
        return
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "failure_pending_requests.json").write_text(
            json.dumps(pending, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        LOG.debug("Could not write the pending-request dump: %s", exc)

    for request in pending[-6:]:
        LOG.warning("Never answered: %s %s", request.get("method"), request.get("url"))


def _write_results(run_dir: Path, rows: list[dict]) -> None:
    if not rows:
        return
    rows = sorted(rows, key=lambda r: (r["sheet_row"] == "", r["sheet_row"]))
    path = run_dir / "results.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["sheet_row", "name", "outcome", "verdict", "detail"]
        )
        writer.writeheader()
        writer.writerows(rows)
    LOG.info("Per-lead results: %s", path)


def _hold(cfg: RunConfig, sb, allow_hold: bool = True) -> None:
    if not cfg.keep_open or not allow_hold:
        return
    if sys.stdin and sys.stdin.isatty():
        LOG.info("Browser held open. Press Enter here to close it.")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
    else:
        LOG.info("keep_open set but no interactive terminal; holding 30s.")
        sb.sleep(30)
