"""Drives leads through the application, one step per page.

Each lead gets its own browser session, so a half-finished application can't
bleed into the next one. With cfg.workers > 1 several leads run concurrently,
each in its own browser; browser.make_launcher decides what that browser is
(by default a GoLogin profile, leased so no two workers share one).
"""

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


# The flow, in order. Every step takes (sb, cfg, lead, run_dir, submit=...),
# so adding a page means appending it here and nothing else.
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

# The same flow with the four public pages replaced by opening the wizard
# directly. A development shortcut for working on the later screens without
# paying two minutes of navigation for every attempt.
STEPS_DIRECT = (open_application_frame,) + STEPS[4:]


def steps_for(cfg: RunConfig) -> tuple:
    return STEPS_DIRECT if cfg.frame_direct else STEPS


OUTCOMES = ("ok", "failed", "throttled", "not_attempted")


def run_batch(
    cfg: RunConfig, leads: list[Lead], on_lead_started=None
) -> dict[str, list]:
    """Run every lead. Returns {outcome: [lead labels]}.

    `on_lead_started(lead)` fires as each lead is about to get a browser. It
    exists for the `--next` cursor: a lead must be marked as used the moment
    it might submit an application, and must *not* be marked if the batch
    never reached it. Recording the whole batch up front gets that wrong in
    the expensive direction -- one crashed browser stopped a twenty-lead run
    after its first lead, and the other nineteen were never offered again.
    """
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

    state = _BatchState(total=len(leads))
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
    """Shared, lock-guarded bookkeeping across workers."""

    def __init__(self, total: int) -> None:
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.results: dict[str, list] = {name: [] for name in OUTCOMES}
        self.rows: list[dict] = []
        self.total = total

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

        # Each worker paces its own leads, so N workers means N leads in
        # flight. Raise lead_delay alongside workers to keep the overall rate.
        if handled:
            _space_out(cfg, state)
            if state.stop.is_set():
                state.record(lead, "not_attempted", "batch stopped before this lead")
                return

        # Before the browser opens, not after it closes: from here on this
        # lead may reach the site, and an applicant the host has already seen
        # must never be offered again.
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

        # The lead got past the gate we were walking leads to get past, so
        # stop rather than submit another application for nothing. See
        # RunConfig.stop_after_progress: this is only on for `--next N`.
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
            # Stop everyone. Pushing on against a host that has stopped
            # answering burns leads and can leave half-entered applications.
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
    """Run one lead, retrying on a different browser when the browser is at fault.

    Two failures say nothing about the lead and everything about the browser it
    was given: a bot wall, which is a property of the profile's IP and
    fingerprint rather than the data, and Orbita dying mid-run. Both are worth
    another profile.

    Everything else is left alone deliberately. A rejected field or a changed
    page will fail identically on the next browser, and retrying it would
    resubmit the applicant -- which is what makes the enrollment host start
    refusing in the first place.

    Returns (outcome, detail, verdict).
    """
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

    return outcome, detail, verdict  # unreachable; keeps the type checker happy


# Selenium's way of saying the browser is no longer there. Orbita does die
# mid-run now and then -- a crash, or GoLogin pulling it -- and the message is
# the only thing distinguishing that from a genuine automation error.
_BROWSER_GONE_SIGNALS = (
    "invalid session id",
    "session deleted",
    "browser has closed the connection",
    "not connected to devtools",
    "no such window",
    "target window already closed",
    "chrome not reachable",
    "disconnected",
    # chromedriver's own process exiting, which is the bluntest form of "the
    # browser went away" and the one this list used to miss. Selenium talks to
    # it over HTTP on localhost, so when it dies the failure surfaces from
    # urllib3 as a refused connection rather than as any WebDriver error --
    # and none of the signals above appear anywhere in that message. Measured:
    # a lead was thrown away rather than retried because of exactly this.
    "actively refused",
    "connection refused",
    "max retries exceeded",
    "failed to establish a new connection",
    "connection aborted",
    "remote end closed connection",
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
    """One pass in one browser. Returns (outcome, detail, verdict, was_blocked)."""
    verdict = ""

    # The outer try covers opening and closing the browser itself, which the
    # step handlers below never see: a GoLogin profile that will not launch or
    # an unreachable API would otherwise kill the worker thread and drop this
    # lead from the results entirely instead of reporting it as failed.
    # Nothing measured against the last browser may carry into this one: it
    # is a different window, in a different place, with no frame open yet.
    real_input.reset_for_new_session()

    # A different person, near enough, fills in each lead.
    LOG.debug("[w%d] This lead is filled at %.2fx pace", worker_id, human.new_operator())

    try:
        with launcher.session(worker_id=worker_id) as sb:
            try:
                steps = steps_for(cfg)
                for index, step in enumerate(steps):
                    # dry_run holds back only the final step: the earlier
                    # submissions are what get you to the later pages at all.
                    is_last = index == len(steps) - 1
                    result = step(sb, cfg, lead, run_dir, submit=not (cfg.dry_run and is_last))
                    verdict = (result or {}).get("verdict", verdict)
            except ThrottledError as exc:
                _capture_failure(sb, cfg, run_dir)
                _hold(cfg, sb, allow_hold)
                return "throttled", str(exc), verdict, False
            except LeadRejectedError as exc:
                # The site looked at the lead and said no. Not a run failure,
                # and not worth another browser -- it would say the same.
                LOG.warning("Lead rejected (%s): %s", exc.verdict, exc)
                _capture_failure(sb, cfg, run_dir)
                # A dead email address is a fact about the sheet, not something
                # to stand and look at: the screenshot is already saved, the
                # next lead needs a clean browser, and --keep-open would
                # otherwise park the run on a window nobody wants to inspect.
                # Every other rejection still holds, because those are verdicts
                # about an applicant and worth seeing.
                if (exc.verdict or "").strip().lower() == BAD_EMAIL:
                    LOG.info(
                        "Closing this browser and moving to the next lead."
                    )
                else:
                    _hold(cfg, sb, allow_hold)
                return "failed", str(exc), exc.verdict, False
            except RealInputError as exc:
                # Worth another browser, and not the lead's fault: the causes
                # are the window losing focus or a field moving out of the
                # pointer's reach, both properties of this browser rather than
                # of this applicant.
                LOG.warning("Real input failed for %s: %s", lead.label, exc)
                _capture_failure(sb, cfg, run_dir)
                _hold(cfg, sb, allow_hold)
                return "failed", str(exc), verdict, True
            except BotBlockedError as exc:
                # Worth another browser: see _run_one.
                LOG.warning("Bot wall for %s: %s", lead.label, exc)
                _capture_failure(sb, cfg, run_dir)
                _hold(cfg, sb, allow_hold)
                return "failed", str(exc), verdict, True
            except AwBotError as exc:
                LOG.error("STEP FAILED for %s: %s", lead.label, exc)
                _capture_failure(sb, cfg, run_dir)
                _hold(cfg, sb, allow_hold)
                # A failure on the public pages is worth another browser.
                #
                # Steps 1-5 are navigation: opening the site, pressing Apply
                # Now, the ZIP check. Nothing there has looked at the
                # applicant yet, so "Step 2: URL never reached /apply-now"
                # says something went wrong with this session, not with this
                # lead -- and another browser is exactly the right answer.
                # Measured: a lead was thrown away on that error while the
                # very next browser walked the same pages without trouble.
                #
                # So is the host announcing that its own backend is down. That
                # one reads like a data rejection because it arrives the same
                # way, but the identity lookup never ran, so nothing was
                # recorded and another browser costs nothing.
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
                    # The browser process went away underneath us. Nothing was
                    # wrong with the lead, so another browser deserves a go.
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
        # A profile that will not launch is also worth trying another one.
        return "failed", f"browser did not start: {exc}", verdict, True
    except Exception as exc:
        LOG.exception("No browser for %s: %s", lead.label, exc)
        return "failed", f"browser did not start: {type(exc).__name__}: {exc}", verdict, True


def _log_verdicts(rows: list[dict]) -> None:
    """Summarise what the wizard decided, which is the point of the run."""
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
    # Waiting on the stop event rather than sleeping means a throttle found by
    # another worker cuts this pause short instead of stalling the shutdown.
    state.stop.wait(wait)


_STEP_IN_DETAIL = re.compile(r"\bStep (\d+)\b", re.IGNORECASE)

# Outcomes the classifier already accounts for. A lead that reaches one of
# these is finished and filed; there is nothing for a person to add, so the
# walk carries on to the next lead.
_KNOWN_VERDICTS = frozenset({
    GOOD, NEED_DOCUMENTS, REJECTED, AW_TRANSFER, BAD_EMAIL,
})

# Step 6 is the first screen that puts the applicant in front of the form. A
# lead that got there was actually tried; one that fell over earlier was not.
_FORM_STEP = 6


def _before_the_form(detail: str) -> bool:
    """Did this fail on the public pages, before the applicant was entered?

    Those steps are navigation, so a failure there is a property of the
    session rather than of the lead, and deserves a fresh browser. A failure
    from step 6 on has the applicant's data in front of it and repeating it
    would just re-submit them.

    A failure naming no step at all is left alone: `_browser_died` already
    covers the ones worth retrying, and guessing here would retry genuine
    faults three times over.
    """
    match = _STEP_IN_DETAIL.search(detail or "")
    return bool(match) and int(match.group(1)) < _FORM_STEP


def _made_progress(outcome: str, verdict: str, detail: str) -> bool:
    """Did this lead turn up something a person still needs to look at?

    This decides whether `--next N` stops walking. The rule is "stop only for
    something we cannot already account for", which sorts every outcome into
    one of two piles.

    Keep walking -- nothing new here:

      * thrown out on the email address. The form never saw the applicant, so
        nothing about the run was tested.
      * the run breaking: a dead chromedriver, a profile that would not start.
        Same reason, and worth the next lead rather than a stop.
      * a verdict the classifier already knows: good, need documents,
        rejected, aw transfer. The lead reached an answer and was filed
        correctly. Stopping on these would end the batch on its first real
        success, which is the opposite of useful.

    Stop -- this needs eyes:

      * an `unknown` verdict: the wizard stopped on a screen nothing here
        recognises, which is exactly the case that has to be read and added.
      * a failure that got as far as the form and produced no verdict at all,
        such as a step 9 that never resolved.

    The detail matters as much as the verdict, because a crashed browser and a
    step 9 failure both leave the verdict empty. An earlier version read that
    emptiness as "got somewhere" and let one dead browser stop a twenty-lead
    batch after its first lead; what separates them is whether the failure
    names a step the run had actually reached.
    """
    named = (verdict or "").strip().lower()

    # A classified outcome is a finished lead, whether or not it was a sale.
    if named in _KNOWN_VERDICTS:
        return False
    if named == UNKNOWN:
        return True
    if named:
        # A verdict nobody has taught this function about yet: treat it the
        # way it treats `unknown`, since that is what it is.
        return True

    if outcome == "ok":
        return False

    # No verdict at all: decide on how far the run got before it failed.
    match = _STEP_IN_DETAIL.search(detail or "")
    if not match:
        # Not even a step number -- this is the plumbing failing rather than
        # the site answering.
        return False
    return int(match.group(1)) >= _FORM_STEP


def _drain_unstarted(pending: queue.Queue, state: _BatchState) -> None:
    while True:
        try:
            _, lead = pending.get_nowait()
        except queue.Empty:
            return
        # Why the batch stopped, rather than assuming. It ends for two quite
        # different reasons -- the host refusing us, or a lead reaching an
        # outcome nothing recognises -- and reporting the first for both sent
        # somebody looking for a throttle that had not happened.
        state.record(
            lead,
            "not_attempted",
            "batch stopped after throttling"
            if state.results["throttled"]
            else "batch stopped for a lead that needs looking at",
        )


def _capture_failure(sb, cfg: RunConfig, run_dir: Path) -> None:
    """Dump the failure, from inside the frame first and then the whole page.

    Order matters and used to be wrong. Every step from 5 on works inside the
    enrollment iframe, and switching out before capturing threw away the only
    screen that could explain the failure -- leaving a dump of the outer shell,
    which says "your form is loading" no matter what went wrong. The frame goes
    first, while we are still in it, and the top document follows for the cases
    where the trouble is outside the frame (a bot wall, a consent overlay).
    """
    if not cfg.save_artifacts:
        return

    # Only meaningful if a step had actually switched into the frame; at the
    # top document this just captures the same thing twice, which is cheap.
    try:
        capture(sb, run_dir, "failure_frame", save=True)
    except Exception as exc:
        LOG.debug("Could not capture the frame at failure: %s", exc)

    # While still inside the frame: Turnstile lives in here, and its record is
    # the one piece of evidence that can tell a refused challenge apart from a
    # rejected applicant. Both present as "(600)" on screen.
    _dump_turnstile(sb, run_dir)

    try:
        sb.switch_to_default_content()
    except Exception:
        pass
    capture(sb, run_dir, "failure", save=True)
    _dump_console(sb, run_dir)
    # Before _dump_pending_requests: reading the performance log empties it,
    # and this one needs the answered requests the other throws away.
    _dump_network(sb, run_dir)
    _dump_pending_requests(sb, run_dir)


def _dump_turnstile(sb, run_dir: Path) -> None:
    """Write out what Cloudflare's widget did, including why it failed.

    The enrollment app shows `Unable to continue ... (600)` for everything, and
    Turnstile's own failures are numbered `600***`. Until this was recorded
    there was no way to tell from a dump whether the challenge had failed, and
    several runs were spent looking at the applicant's data instead.
    """
    try:
        status = turnstile.state(sb)
    except Exception:
        return
    if not status or not status.get("observed"):
        return

    # Why there is no widget, not just that there is none. An empty
    # `<ngx-turnstile>` and a script that never executed look identical in the
    # state alone, and only one of them is a network problem.
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
    """Save the browser console next to the failure dumps."""
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
    """Save what the app asked for and what the server answered.

    The enrollment app reports failures as a bare code -- "Unable to continue
    ... (600)" -- with nothing in the console. The response that carried that
    code is the only place the reason can be, so the whole exchange is written
    out and the app's own calls are surfaced in the log.
    """
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

    # The app's own endpoints, not the analytics noise around them.
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
    """Name whatever the page was still waiting on when it gave up."""
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
    """One row per lead, so a stopped batch can be picked up where it left off."""
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
    """Keep the window up so a human can look at where it stopped.

    Single-worker runs only: prompting on stdin while several browsers are
    running would block the whole batch on one window.
    """
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
