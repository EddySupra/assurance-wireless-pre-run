"""Entry point.

    python run.py --list-profiles         # GoLogin profiles on the account
    python run.py --test-lead --dry-run   # fake lead, fills fields, submits nothing
    python run.py --test-lead             # fake lead, submits for real
    python run.py --row 2                 # one sheet row
    python run.py                         # every lead in the sheet

Browsers run as GoLogin (Orbita) profiles by default, so set GOLOGIN_TOKEN and
GOLOGIN_PROFILE_ID in .env first (see .env.example). --backend switches back to
the old SeleniumBase UC-mode Chrome.
"""

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

from aw_bot.browser import BACKENDS
from aw_bot.config import START_URL, RunConfig
from aw_bot.errors import AwBotError
from aw_bot.gologin_backend import cleanup_disposable_profiles, list_profiles
from aw_bot.logs import setup
from aw_bot.netcheck import check_network
from aw_bot.lead import sample_lead
from aw_bot.runner import run_batch
from aw_bot.sheets import completed_rows, load_leads

# FlareSolverr integration
from aw_bot.flaresolverr import (
    solve_cloudflare_challenge,
    inject_cookies_into_driver,
    get_cookie_cache,
)


# Where --next remembers how far down the sheet testing has got. One line,
# holding the last row number handed out.
CURSOR_PATH = Path(__file__).resolve().parent / ".test_cursor"


def _read_cursor() -> int:
    try:
        return int(CURSOR_PATH.read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return 0


def _record_cursor(lead) -> None:
    """Mark a lead as used, the moment it is about to get a browser.

    Only ever moves forward. With several workers the leads finish out of
    order, and a cursor that could move backwards would re-offer an applicant
    the host has already seen -- which is what makes it start refusing.
    """
    row = lead.row_number or 0
    if row <= _read_cursor():
        return
    try:
        CURSOR_PATH.write_text(str(row), encoding="utf-8")
    except OSError as exc:
        print(f"--next: could not record the cursor: {exc}", file=sys.stderr)


def _next_untested(leads: list, count: int = 1) -> list:
    """The next `count` leads after the last one --next handed out.

    Walking the sheet rather than re-running one row matters beyond tidiness:
    the enrollment host starts refusing an applicant who is submitted
    repeatedly, so a fresh lead per test is also what keeps the flow working.

    A count above one is for the case that kept stopping these test runs
    dead: the site validates the email address at the personal-info screen
    and throws the lead out when it does not deliver, and this sheet is full
    of addresses that do not. Handing out several leads lets the run walk
    past those by itself instead of needing --next typed again for each one.

    The cursor advances to the last lead handed out, not the last one that
    worked, so a rejected applicant is never offered again on the next run.
    """
    cursor = _read_cursor()
    remaining = [l for l in leads if (l.row_number or 0) > cursor]

    if not remaining:
        print(
            f"--next: no lead past row {cursor}. Delete {CURSOR_PATH.name} to "
            f"start again from the top.",
            file=sys.stderr,
        )
        return []

    chosen = remaining[: max(1, count)]

    # The cursor is NOT written here. It advances one lead at a time, as each
    # one actually starts (see _record_cursor). Recording the whole batch up
    # front looks equivalent and is not: a batch that stops early -- a crashed
    # browser, a throttle, the first lead getting through -- would mark every
    # lead it never reached as used, and `--next` would skip them for good.
    # Measured: one dead chromedriver cost nineteen untried leads that way.

    if len(chosen) == 1:
        print(
            f"--next: testing row {chosen[0].row_number} ({chosen[0].label})",
            file=sys.stderr,
        )
    else:
        print(
            f"--next: up to {len(chosen)} lead(s), rows "
            f"{chosen[0].row_number}-{chosen[-1].row_number}, stopping at the "
            f"first one that gets past the email check.",
            file=sys.stderr,
        )
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser(description="Assurance Wireless application automation")

    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--test-lead", action="store_true", help="use the built-in fake lead, skip the sheet"
    )
    source.add_argument("--row", type=int, help="run only this sheet row number")
    source.add_argument(
        "--next",
        nargs="?",
        type=int,
        const=1,
        metavar="N",
        help="run the next lead this machine has not tested yet, and remember "
             "it (see .test_cursor), so no applicant is submitted twice -- "
             "which is what the enrollment host starts refusing. Give it a "
             "count (--next 5) to keep walking when a lead is thrown out "
             "before it reaches the form: the sheet has a lot of dead email "
             "addresses, and the site rejects those at the personal-info "
             "screen. It stops as soon as one lead gets past that screen, so "
             "a count is a ceiling on attempts rather than a promise to "
             "submit that many applications.",
    )
    source.add_argument(
        "--start-row",
        type=int,
        help="run from this sheet row onward (single-worker runs; see --resume)",
    )
    source.add_argument(
        "--resume",
        metavar="RESULTS_CSV",
        help="resume a stopped batch, skipping leads that already completed "
             "(path to a previous run's results.csv). Safer than --start-row, "
             "which can re-submit leads that finished out of order.",
    )

    parser.add_argument("--sheet-key", help="spreadsheet key, overriding config.py")
    parser.add_argument("--worksheet", help="worksheet/tab name, overriding config.py")
    parser.add_argument(
        "--dry-run", action="store_true", help="fill fields but never click submit"
    )
    gologin = parser.add_argument_group(
        "GoLogin",
        "Which GoLogin profile the browser runs as. Values fall back to .env "
        "(GOLOGIN_TOKEN, GOLOGIN_PROFILE_ID).",
    )
    gologin.add_argument(
        "--gologin-profile",
        metavar="ID[,ID...]",
        help="profile(s) to run, overriding GOLOGIN_PROFILE_ID. With several "
             "workers you need at least one profile per worker.",
    )
    gologin.add_argument(
        "--random-profile",
        action="store_true",
        help="draw profiles from every one on the account, ignoring GOLOGIN_PROFILE_ID",
    )
    gologin.add_argument(
        "--new-profile-per-lead",
        action="store_true",
        default=None,
        help="build a fresh GoLogin profile, with its own generated "
             "fingerprint and its own proxy, for every lead -- then delete it. "
             "Nothing carries over between leads: no shared identity and no "
             "shared proxy exit. This is the default; the flag is kept so it "
             "can be asked for explicitly.",
    )
    gologin.add_argument(
        "--cleanup-profiles",
        action="store_true",
        help="delete the aw-* profiles left over from earlier runs and exit. "
             "A GoLogin account caps how many profiles it holds, and once that "
             "is reached every lead fails at the first step with a 403 without "
             "ever opening a browser. Only touches names this project "
             "generated; profiles made by hand are left alone.",
    )
    gologin.add_argument(
        "--keep-extensions",
        action="store_true",
        help="start Orbita with its extensions enabled, the way GoLogin runs a "
             "profile by hand. The run disables them by default because the "
             "bundled ad blocker blocks Akamai's /akam/ sensor, which reads as "
             "a bot -- but it also means the automated browser launches "
             "differently from a manual one. Use it to test whether that "
             "difference matters.",
    )
    gologin.add_argument(
        "--keep-session",
        action="store_true",
        help="let the profile keep its cookies and local storage instead of "
             "starting clean. The run clears them by default so a block cookie "
             "cannot carry between leads -- the cost is that every automated "
             "visit looks like a first-time visitor, where a hand-run profile "
             "arrives with history.",
    )
    gologin.add_argument(
        "--reuse-profiles",
        action="store_true",
        help="reuse the saved profiles in GOLOGIN_PROFILE_ID instead of "
             "building a fresh one per lead. Cheaper on proxy traffic, and "
             "the reason it is not the default: one refused exit then poisons "
             "every lead after it, and a profile the site has already judged "
             "carries that judgement into the next application.",
    )
    gologin.add_argument(
        "--proxy-type",
        choices=("mobile", "resident", "dataCenter", "auto"),
        help="which GoLogin proxy to attach with --new-profile-per-lead "
             "(default mobile). 'auto' takes whichever type the account still "
             "has traffic for.",
    )
    gologin.add_argument(
        "--proxy-country",
        metavar="CC",
        help="two-letter country for that proxy (default US)",
    )
    gologin.add_argument("--gologin-token", help="API token, overriding GOLOGIN_TOKEN in .env")
    gologin.add_argument(
        "--chromedriver",
        metavar="PATH",
        help="use this chromedriver instead of matching one to Orbita's Chrome version",
    )
    gologin.add_argument(
        "--check-network",
        action="store_true",
        help="open the start page once on each profile and report whether the "
             "site serves it, blocks it, or flags the network. No lead data is "
             "used. Run this after changing proxies.",
    )
    gologin.add_argument(
        "--list-profiles",
        action="store_true",
        help="print the profiles on the account and exit (needs only a token)",
    )

    # FlareSolverr argument group
    flaresolverr = parser.add_argument_group(
        "FlareSolverr",
        "Automatic Cloudflare challenge solving. Requires FlareSolverr running "
        "on localhost:8191. Start with: docker run -d -p 8191:8191 "
        "flaresolverr/flaresolverr:latest",
    )
    flaresolverr.add_argument(
        "--use-flaresolverr",
        action="store_true",
        help="automatically solve Cloudflare challenges before browser starts; "
             "caches cookies to disk to reuse on subsequent runs (much faster)",
    )
    flaresolverr.add_argument(
        "--flaresolverr-endpoint",
        default="http://localhost:8191/v1",
        help="FlareSolverr API endpoint (default localhost:8191)",
    )
    flaresolverr.add_argument(
        "--clear-cache",
        action="store_true",
        help="delete all cached Cloudflare solution cookies; forces fresh "
             "challenge solve on next run",
    )

    parser.add_argument(
        "--backend",
        choices=BACKENDS,
        help="where the browser runs (default: gologin). 'browserless' runs it "
             "on Browserless's hosted fleet with their stealth and proxies "
             "(needs BROWSERLESS_TOKEN). The rest are the old SeleniumBase "
             "UC-mode paths.",
    )
    parser.add_argument(
        "--browserless-token",
        metavar="TOKEN",
        help="Browserless API token, overriding BROWSERLESS_TOKEN in .env",
    )
    parser.add_argument(
        "--browserless-host",
        metavar="HOST",
        help="Browserless host (default production-sfo.browserless.io). A "
             "dedicated plan has its own -- a dedicated token against the "
             "shared cloud is refused, which looks like a bad token.",
    )
    parser.add_argument(
        "--browserless-live",
        action="store_true",
        help="open a live view of the hosted browser so you can watch the run "
             "(and click into it -- the view takes real input). Browserless "
             "only; the browser is headless in a data centre, so this is the "
             "only way to see it.",
    )
    parser.add_argument(
        "--browserless-proxy",
        choices=("residential", "none"),
        help="use Browserless's residential proxy pool (default residential). "
             "Plan-gated, so check it is on the account first.",
    )
    parser.add_argument(
        "--grid",
        metavar="URL",
        help="run the browsers on another machine instead of this one, e.g. "
             "http://10.0.0.5:4444 (a Selenium Grid or selenium/standalone-chrome)",
    )
    parser.add_argument(
        "--profile-dir",
        metavar="PATH",
        help="reuse browser profiles under PATH so sessions persist between runs",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="how many leads to process at once, each in its own browser (default 1)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="disable human-paced typing/mouse movement (fills fields instantly)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="log the debug detail too"
    )
    parser.add_argument(
        "--frame-direct",
        action="store_true",
        help="skip steps 1-4 and open the enrollment app straight from its own "
             "URL. Much faster when working on the later screens; it bypasses "
             "the session the public pages set up, so confirm with a full run.",
    )
    parser.add_argument(
        "--solve-challenges",
        action="store_true",
        help="when Cloudflare shows its checkbox, hold the run so you can click "
             "it in the browser window; the run resumes by itself. Without this "
             "a challenge is reported and the lead moves on.",
    )
    parser.add_argument(
        "--real-input",
        action="store_true",
        help="drive the machine's actual mouse and keyboard instead of "
             "injecting events, so the site's sensor sees trusted input. "
             "Takes over the desktop while it runs: needs a visible window and "
             "a single worker, and you cannot use the machine meanwhile.",
    )
    parser.add_argument(
        "--no-cdp-input",
        action="store_true",
        help="do not give in-frame clicks a real press duration through CDP. "
             "On by default; this is for comparing against the old behaviour, "
             "where a click inside the enrollment frame had a dwell time of "
             "zero because ActionChains refuses in there.",
    )
    parser.add_argument(
        "--allow-synthetic-fallback",
        action="store_true",
        help="with --real-input, let an action that could not be done with the "
             "real mouse and keyboard finish with injected events instead of "
             "failing the lead. Off by default: a silent fall back reports "
             "success while the page receives the untrusted events that "
             "--real-input exists to avoid.",
    )
    parser.add_argument(
        "--no-stealth",
        action="store_true",
        help="skip the anti-detection patches entirely (aw_bot/stealth.py). "
             "For seeing what the site does with an unpatched browser.",
    )
    parser.add_argument(
        "--fingerprint",
        choices=("auto", "on", "off"),
        help="whether to impose a device identity (GPU, cores, timezone, UA) "
             "on top of the automation-artefact scrubbing. Default 'auto': on "
             "for the SeleniumBase backends, off for GoLogin, whose profiles "
             "already carry a consistent fingerprint that a second one would "
             "only contradict.",
    )
    parser.add_argument(
        "--confirm-dependent",
        choices=("yes", "no"),
        help="how to answer the 'Please Confirm' dialog about qualifying "
             "through a child or dependent. Default no, which is what the "
             "sheet's data says (adults applying for themselves). 'yes' is "
             "for mapping the screens past it and asserts a qualification "
             "route the lead data does not support.",
    )
    parser.add_argument(
        "--capture-logs",
        action="store_true",
        help="collect Chrome's console and network logs for diagnosis. This "
             "enables the CDP Runtime and Network domains, which anti-bot "
             "scoring can detect -- so it makes the run easier to spot. Off "
             "by default for that reason.",
    )
    parser.add_argument(
        "--max-busy-wait",
        type=float,
        metavar="SECONDS",
        help="how long to keep waiting while the form shows a spinner "
             "(default 60). Every lead that sat past a minute went on to fail "
             "anyway, so the old 900s ceiling only made the same verdict "
             "slower to reach. Raise it if a lead is ever seen to recover late.",
    )
    parser.add_argument(
        "--trace-turnstile",
        action="store_true",
        help="hook Cloudflare's Turnstile API to record its sitekey and error "
             "codes. Diagnostic only: the hook is an accessor on "
             "window.turnstile, which is what intercepting the API looks like, "
             "and Cloudflare's loader can respond by never initialising at all.",
    )
    parser.add_argument(
        "--allow-third-party-storage",
        action="store_true",
        help="let the nested Cloudflare Turnstile frame use cookies and "
             "storage. Try this when the run warns that the enrollment frame "
             "cannot write them: a challenge without storage fails with a "
             "600-series code, which this form shows as its own '(600)'.",
    )
    parser.add_argument("--url", default=START_URL, help="override the start URL")
    parser.add_argument("--headless", action="store_true", help="run without a visible window")
    parser.add_argument(
        "--keep-open", action="store_true", help="leave the browser open when a run ends"
    )
    parser.add_argument(
        "--no-artifacts", action="store_true", help="skip screenshots/HTML/element dumps"
    )
    args = parser.parse_args()

    # Handle --clear-cache flag early
    if args.clear_cache:
        cache = get_cookie_cache()
        cache.clear()
        print("Cleared all cached FlareSolverr cookies", file=sys.stderr)
        return 0

    cfg = RunConfig(
        start_url=args.url,
        headless=args.headless,
        keep_open=args.keep_open,
        dry_run=args.dry_run,
        save_artifacts=not args.no_artifacts,
        human_like=not args.fast,
        real_input=args.real_input,
        allow_synthetic_fallback=args.allow_synthetic_fallback,
        solve_challenges=args.solve_challenges,
        frame_direct=args.frame_direct,
        stealth=not args.no_stealth,
        verbose=args.verbose,
        workers=args.workers,
    )
    # Real input and parallel workers cannot both be had.
    #
    # --real-input drives the machine's own mouse and keyboard, and the machine
    # has one cursor. Two workers would take turns yanking it across the screen
    # and each would find the pointer somewhere it did not leave it -- which
    # real_input notices and refuses over, so the run would spend its time
    # failing on "the pointer was taken by somebody else mid-click" rather than
    # filling in forms. Refused up front, because the alternative is a batch
    # that looks like it is working and is not.
    if args.no_cdp_input:
        cfg.cdp_input = False

    if args.real_input and args.workers > 1:
        print(
            "--real-input drives this machine's actual mouse and keyboard, so it",
            f"cannot run {args.workers} browsers at once -- there is one cursor and",
            "they would fight over it.",
            "",
            "Either:",
            "  --real-input      one lead at a time, strongest input",
            f"  --workers {args.workers}       parallel, browser-level input -- still",
            "                    isTrusted, still paced and curved (see human.py)",
            sep=chr(10),
            file=sys.stderr,
        )
        return 2

    if args.gologin_token:
        cfg.gologin.token = args.gologin_token.strip()
    if args.gologin_profile:
        cfg.gologin.profile_ids = tuple(
            p.strip() for p in args.gologin_profile.split(",") if p.strip()
        )
    cfg.gologin.random_profile = args.random_profile
    # Both default on; these turn them off so a run can be made to match how
    # GoLogin launches a profile by hand, which is the comparison that matters
    # when the same profile succeeds manually and fails automated.
    if args.keep_extensions:
        cfg.gologin.disable_extensions = False
    if args.keep_session:
        cfg.gologin.fresh_session = False
    # Only when actually asked for, either way round. Assigning the flag
    # unconditionally is how the config default stopped meaning anything:
    # `store_true` hands back False when the flag is absent, so a default of
    # True was overwritten with False on every run that did not pass it, and
    # fresh profiles silently never happened.
    if args.reuse_profiles:
        cfg.gologin.disposable_profiles = False
    elif args.new_profile_per_lead:
        cfg.gologin.disposable_profiles = True
    if args.proxy_type:
        # "auto" is spelled as an empty string internally: that is what the
        # GoLogin call treats as "pick whatever there is traffic for".
        cfg.gologin.proxy_type = "" if args.proxy_type == "auto" else args.proxy_type
    if args.proxy_country:
        cfg.gologin.proxy_country = args.proxy_country.strip().upper()
    if args.chromedriver:
        cfg.gologin.chromedriver_path = args.chromedriver

    if args.fingerprint:
        cfg.stealth_fingerprint = args.fingerprint
    if args.confirm_dependent:
        cfg.application.confirm_dependent_answer = args.confirm_dependent.title()
    if args.backend:
        cfg.browser_backend = args.backend
    if args.grid:
        cfg.browser_backend = "remote"
        cfg.grid_url = args.grid
    elif args.profile_dir:
        cfg.browser_backend = "local-profile"
        cfg.profile_dir = Path(args.profile_dir)
    if args.sheet_key:
        cfg.sheet.spreadsheet_key = args.sheet_key
    if args.worksheet:
        cfg.sheet.worksheet_name = args.worksheet

    # Configure FlareSolverr
    cfg.capture_browser_logs = args.capture_logs
    cfg.allow_third_party_storage = args.allow_third_party_storage
    cfg.trace_turnstile = args.trace_turnstile
    if args.max_busy_wait:
        cfg.max_busy_wait = args.max_busy_wait
    if args.browserless_token:
        cfg.browserless_token = args.browserless_token.strip()
    if args.browserless_host:
        cfg.browserless_host = args.browserless_host.strip()
    cfg.browserless_live_view = args.browserless_live
    if args.browserless_proxy:
        cfg.browserless_proxy = "" if args.browserless_proxy == "none" else args.browserless_proxy
    cfg.use_flaresolverr = args.use_flaresolverr
    cfg.flaresolverr_endpoint = args.flaresolverr_endpoint
    
    if args.use_flaresolverr:
        print("FlareSolverr enabled: will auto-solve Cloudflare challenges", file=sys.stderr)
        # Disable manual challenge solving if FlareSolverr is on
        if cfg.solve_challenges:
            print("--solve-challenges disabled (FlareSolverr handles challenges automatically)", file=sys.stderr)
            cfg.solve_challenges = False

    if args.check_network:
        if not cfg.gologin.token:
            print(
                "No GoLogin token. Set GOLOGIN_TOKEN in .env or pass --gologin-token.",
                file=sys.stderr,
            )
            return 2
        return check_network(cfg)

    if args.list_profiles:
        if not cfg.gologin.token:
            print(
                "No GoLogin token. Set GOLOGIN_TOKEN in .env or pass --gologin-token.",
                file=sys.stderr,
            )
            return 2
        return list_profiles(cfg.gologin.token)

    if args.cleanup_profiles:
        if not cfg.gologin.token:
            print(
                "No GoLogin token. Set GOLOGIN_TOKEN in .env or pass --gologin-token.",
                file=sys.stderr,
            )
            return 2
        setup(cfg.artifacts_root / "cleanup", verbose=cfg.verbose)
        cleanup_disposable_profiles(cfg.gologin.token)
        return 0

    try:
        if args.test_lead:
            leads = [sample_lead()]
        else:
            leads = load_leads(cfg.sheet, only_row=args.row)
            if args.next:
                leads = _next_untested(leads, args.next)
                # Several leads here means "keep going until one gets
                # somewhere", not "submit this many applications". The batch
                # stops at the first lead that survives the email check.
                cfg.stop_after_progress = args.next > 1
            if args.start_row:
                leads = [l for l in leads if (l.row_number or 0) >= args.start_row]
            if args.resume:
                done = completed_rows(Path(args.resume))
                leads = [l for l in leads if (l.row_number or 0) not in done]
    except AwBotError as exc:
        print(f"Could not load leads: {exc}", file=sys.stderr)
        return 2

    if not leads:
        print("No leads to run.", file=sys.stderr)
        return 2

    try:
        results = run_batch(
            cfg, leads, on_lead_started=_record_cursor if args.next else None
        )
    except AwBotError as exc:
        print(f"Could not start the browser: {exc}", file=sys.stderr)
        return 2
    unfinished = results["failed"] + results["throttled"] + results["not_attempted"]
    return 0 if not unfinished else 1


if __name__ == "__main__":
    sys.exit(main())