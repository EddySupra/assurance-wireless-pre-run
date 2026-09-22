"""Run-wide settings. Tweak here rather than in the step modules."""

import os
from dataclasses import dataclass, field
from pathlib import Path



PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Secrets (the GoLogin token above all) live in .env, which is not committed.
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:  # python-dotenv missing: real environment variables still work
    pass

# Step 1 target: the public start page of the Assurance Wireless site.
START_URL = "https://www.assurancewireless.com/"

# Hosts that count as "still in the right flow", matched by domain suffix so
# subdomains are covered. solixinc.com is there because the application form
# itself is served from vmuappcloud.solixinc.com inside an iframe -- Solix
# administers Lifeline eligibility.
ALLOWED_HOST_SUFFIXES = ("assurancewireless.com", "solixinc.com")


@dataclass
class SheetConfig:
    """Where the leads live. Fill in spreadsheet_key once and forget it."""

    # Service-account JSON downloaded from Google Cloud. The sheet must be
    # shared with the client_email inside that file.
    credentials_path: Path = field(default=PROJECT_ROOT / "credentials" / "service_account.json")

    # From the sheet URL: /spreadsheets/d/<THIS PART>/edit
    spreadsheet_key: str = "14D6Uxl8MeRAL7lNy6IeSmeZNEeicRhqZR5Oecx6un_I"
    spreadsheet_url: str = ""

    # Blank means the first tab.
    worksheet_name: str = ""

    # 1-based row holding the column titles; data starts on the next row.
    header_row: int = 1


@dataclass
class GoLoginConfig:
    """The GoLogin account and profiles the browsers run as.

    The token is read from .env (GOLOGIN_TOKEN) rather than written here, so it
    never lands in the repo. GOLOGIN_PROFILE_ID may hold one id or several,
    comma-separated -- with more than one worker you need at least one profile
    per worker, since GoLogin will not run a profile in two browsers at once.
    """

    token: str = field(default_factory=lambda: (os.getenv("GOLOGIN_TOKEN") or "").strip())
    profile_ids: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            p.strip() for p in (os.getenv("GOLOGIN_PROFILE_ID") or "").split(",") if p.strip()
        )
    )

    # Ignore profile_ids and draw from every profile on the account instead.
    random_profile: bool = False

    # Leave blank to match a chromedriver to Orbita's Chrome major automatically.
    chromedriver_path: str = field(default_factory=lambda: os.getenv("CHROMEDRIVER_PATH", ""))

    # Extra Chromium flags for Orbita, e.g. ("--start-maximized",).
    extra_args: tuple[str, ...] = ()

    # Start Orbita with its extensions switched off.
    #
    # GoLogin ships an extension called "Ad Blocker" in these profiles, and its
    # rules match `/akam/` -- the endpoint Akamai Bot Manager posts its sensor
    # telemetry to. Blocking it does not hide the automation, it advertises it:
    # Akamai sees a client that never reports, scores it as a bot, and answers
    # "Access Denied". That is the bot wall this run kept hitting, and it is
    # why the same flow works by hand in an ordinary browser.
    #
    # Measured: with extensions on, the sensor request fails with
    # ERR_BLOCKED_BY_CLIENT; with them off it returns 200. The proxy is
    # unaffected either way -- the exit IP is identical -- because GoLogin
    # applies it in the browser rather than through an extension.
    disable_extensions: bool = True

    # Build a brand-new profile for every lead instead of reusing the pool.
    #
    # Reusing eight saved profiles means eight identities and, more to the
    # point, one proxy provider's exit pool shared between them -- so a lead
    # inherits whatever reputation the previous ones left on that exit. A
    # fresh profile per lead gets its own fingerprint (GoLogin generates a
    # coherent one: OS, UA, screen, GPU, fonts and timezone all agreeing) and
    # its own proxy, and is deleted afterwards so nothing carries forward.
    #
    # On by default. It costs a profile slot and proxy traffic per lead, and
    # that is the cheaper side of the trade: the pooled alternative means one
    # refused exit poisons every lead that follows it, and a profile the site
    # has already seen carries whatever it decided last time. Measured on this
    # project, leads on reused profiles hit "Access Denied" and blank
    # enrollment frames in runs of several at a time.
    #
    # Use --gologin-profile with a pool (and no --new-profile-per-lead) to go
    # back to reusing saved profiles.
    disposable_profiles: bool = True

    # Which GoLogin proxy to attach to a disposable profile. Blank asks
    # GoLogin for whichever type the account still has traffic for; otherwise
    # "mobile", "resident" or "dataCenter". Mobile and residential are the
    # ones worth using here -- datacentre exits are the easiest to flag.
    proxy_type: str = "mobile"

    # Two-letter country for that proxy. The application is for a US benefit
    # programme, so a non-US exit is a contradiction before the form is even
    # filled in.
    proxy_country: str = "US"

    # Operating systems to draw from when generating profiles. Variety here is
    # the point: a run of leads that are all the same Windows build is a
    # pattern, and GoLogin keeps each one internally consistent.
    profile_os: tuple[str, ...] = ("win", "mac")

    # Start every run from the profile as it was saved, and throw away what the
    # run did rather than saving it back.
    #
    # GoLogin's default is the opposite: stop() uploads the browser's state to
    # the profile, so cookies survive into the next run. That is the right
    # behaviour for an account you are staying signed in to, and the wrong one
    # here -- once a site plants a block cookie, every later run on that
    # profile inherits it and gets refused before it starts. Leave this on
    # unless a flow actually needs the session to carry over.
    fresh_session: bool = True


@dataclass
class ApplicationConfig:
    """Answers the wizard demands that the sheet does not carry.

    These are the same for every lead. That is deliberate: this is a pre-run
    whose job is to find out which bucket a lead falls into, and it stops at
    the decision screen rather than completing an enrollment. If that ever
    changes -- if these applications are actually finished and handed to
    customers -- the PIN and answers have to become per-lead and recorded,
    because a customer cannot use an account whose PIN nobody wrote down.
    """

    # 6-15 digits. The form rejects personal information and easy sequences,
    # so this is deliberately not a birthday, a run of digits or a repeat.
    account_pin: str = "470293"

    # One per security question. Same rules: nothing personal, nothing guessable.
    security_answers: tuple[str, str, str] = ("Brookfield", "Marigold", "Sandcastle")

    # Contact preferences. Email is the contact method because every sheet row
    # has an email while the phone column is optional.
    language: str = "English"
    contact_method: str = "Email"
    print_preference: str = "Standard Print"

    # "Who is the Benefit Eligible Applicant?" -- the sheet holds one adult per
    # row, with that person's own DOB and SSN, so the applicant is always the
    # person applying rather than a child or dependent.
    eligible_applicant: str = "I am the Eligible Applicant"

    # How to answer the "Please Confirm" dialog that appears when the form
    # believes the applicant is qualifying through a child or dependent:
    #
    #   "You have indicated that you wish to qualify through a child or
    #    dependent in your household. If this is correct press YES. If you
    #    are applying for yourself, press NO"
    #
    # "No" is the answer that matches the data: every row is an adult applying
    # with their own DOB and SSN, so pressing Yes asserts a qualification
    # route that is not true of the applicant.
    #
    # Set to "Yes" only to walk through the screens *after* this one while
    # mapping the flow. It is a deliberate setting rather than a hardcoded
    # click because the two answers make materially different claims on a
    # federal benefits application, and that choice should be visible.
    #
    # Worth knowing: seeing this dialog at all usually means the applicant
    # radio did not end up where it was meant to. The fix is upstream, in
    # getting that selection to register -- not in the answer given here.
    confirm_dependent_answer: str = "No"

    # Leave a radio alone when it already holds the answer we want.
    #
    # The wizard renders several screens with the right option pre-selected
    # (temporary address No, mailing-same-as-home Yes, print preference
    # Standard, eligible applicant "I am"). Clicking those is an interaction
    # no applicant would perform -- they would read the screen and press
    # Continue.
    #
    # The old behaviour clicked anyway, to force Angular to register the
    # value. Measured on the eligible-applicant screen, that did make the
    # control read ng-dirty/ng-touched and still produced "(600)", by three
    # different routes. So the click was not buying what it was supposed to.
    #
    # Set False to go back to clicking pre-selected radios.
    skip_preselected_radios: bool = True


@dataclass
class RunConfig:
    start_url: str = START_URL
    headless: bool = False

    # UC mode reconnect window, in seconds. This is the stretch where the
    # driver detaches so the page's bot checks see a clean browser. Bump it
    # if the site starts serving challenge pages.
    reconnect_time: float = 5.0

    # Generous because GoLogin profiles go out through a residential proxy:
    # measured start-page loads run ~40s to interactive on these profiles.
    page_timeout: int = 90

    # How long to keep waiting while the form is visibly busy -- the submit
    # button disabled with a spinner in it.
    #
    # One minute. This was 900s on the theory that the eligibility lookup
    # behind the benefit-applicant screen legitimately runs for minutes, and
    # the runs since do not support it: every lead that sat on that spinner
    # past a minute went on to fail anyway, one of them after ten and a half
    # minutes of waiting, and none of them ever came back with an answer. A
    # spinner that has not resolved inside a minute is not a slow lookup, it
    # is a request that is not going to be answered -- so the extra fourteen
    # minutes bought nothing except a much slower way to reach the same
    # verdict.
    #
    # Raise it with --max-busy-wait if a lead is ever seen to recover late;
    # that would be evidence worth having, and it is one flag away.
    max_busy_wait: float = 60.0

    # How long to wait for Cloudflare Turnstile to hand the form a token. The
    # enrollment app disables Continue until it does, so this is the ceiling on
    # "the button is spinning".
    #
    # Short on purpose. Measured over several runs, this widget either issues a
    # token within a few seconds or never issues one at all -- a refusal looks
    # exactly like a long wait, so waiting longer only costs minutes per lead
    # and tells you nothing you did not know at 30s.
    #
    # The one case that genuinely needs longer is a *visible* challenge with
    # --solve-challenges on, where a person has to walk over and click it.
    # That case extends itself (see solve_challenge_wait); this ceiling is for
    # the silent case.
    turnstile_wait: float = 30.0

    # The longer ceiling, used only once Cloudflare has actually drawn its
    # checkbox and --solve-challenges says somebody is there to click it.
    solve_challenge_wait: float = 180.0

    # Hold the run when Cloudflare renders a challenge, so the person watching
    # can answer it and the run carries on. Off by default: an unattended batch
    # should report the challenge and move on rather than wait for nobody.
    solve_challenges: bool = False

    # Skip the four public pages and open the enrollment app directly. A
    # development shortcut for the later screens; it bypasses the session the
    # public pages establish, so confirm findings with a full run.
    frame_direct: bool = False
    window_size: str = "1440,1000"

    # Save a screenshot + a page inventory after each step.
    save_artifacts: bool = True
    artifacts_root: Path = field(default=PROJECT_ROOT / "artifacts")

    # Leave the browser open at the end of the run so you can inspect state.
    keep_open: bool = False

    # Run the whole flow but stop short of committing the LAST implemented
    # step: its fields get filled and screenshotted, and its submit button is
    # not clicked. Earlier steps still submit, since their submissions are how
    # you reach the later pages at all.
    dry_run: bool = False

    # Type character by character, pause between actions, and walk the mouse
    # to each element before clicking it. Slower, but an agent can follow the
    # run and step in, and instant form fills are a bot-detection signal.
    human_like: bool = True

    # Drive the machine's real mouse and keyboard instead of injecting events
    # into the page (--real-input). Akamai's sensor reports pointer paths, key
    # timings and whether events are trusted, and injected input carries none
    # of that. Off by default because it takes over the desktop: it needs a
    # visible window, a single worker, and the machine to itself while it runs.
    real_input: bool = False

    # Let a failed real-input action finish with injected events instead of
    # failing the lead. Off: a silent degradation is the one failure mode
    # worth refusing, because the run reports success while the page receives
    # exactly the untrusted events --real-input was turned on to avoid.
    allow_synthetic_fallback: bool = False

    # Log the debug detail -- notably every real-input decision, which is the
    # only way to see why it fell back to synthetic input.
    verbose: bool = False

    type_delay: tuple[float, float] = (0.05, 0.16)     # seconds per character
    action_pause: tuple[float, float] = (0.4, 1.1)     # between actions
    mouse_steps: int = 12                              # points sampled per pointer move

    # Move the mouse around each page before touching its fields. The sensor
    # scores the first seconds of a page, and a session whose first pointer
    # event is the click on field one has nothing to score but that. Range in
    # seconds; (0, 0) turns it off.
    warm_up_seconds: tuple[float, float] = (2.5, 5.0)

    # How often a typed letter comes out as its keyboard neighbour and gets
    # backspaced. Real form-filling has corrections in it. Low on purpose:
    # every correction is a chance for the form's own validation to see a
    # half-typed value, and only letters are ever affected -- never the digits
    # of an SSN, a date or a ZIP.
    typo_chance: float = 0.015

    # Scrub the traces that say "this browser is being driven" -- the
    # webdriver flag, ChromeDriver's globals, a document that reports itself
    # hidden and unfocused because the window is in the background. Costs
    # nothing and applies on every backend. See aw_bot/stealth.py.
    stealth: bool = True

    # Whether to also impose a device identity (GPU, cores, timezone, UA,
    # canvas noise).
    #
    #   auto  on for the SeleniumBase backends, off for GoLogin (default)
    #   on    always -- for comparing the two
    #   off   never
    #
    # "auto" is not a hedge. A GoLogin profile already carries a complete
    # fingerprint whose parts were chosen to agree with each other and with
    # its proxy; a second identity layered over the top replaces some of those
    # parts and not others, and the leftover disagreement is more visible than
    # the ordinary fingerprint it replaced.
    stealth_fingerprint: str = "auto"

    # Whether to scrub automation artefacts (webdriver flag, ChromeDriver
    # globals, plugin list). Same three settings, same default reasoning as
    # above: "auto" applies them on the SeleniumBase backends and skips them
    # on GoLogin.
    #
    # Skipping is not laziness. An Orbita profile is a normally launched
    # browser reached over its DevTools port, so it reports webdriver=false,
    # no $cdc_ globals and a real plugin list on its own -- measured. Patching
    # it anyway replaced `false` with `undefined` (which is the wrong answer)
    # and turned document.hasFocus and permissions.query into own properties
    # that a page can spot. The patches were the only thing left to detect.
    stealth_artifacts: str = "auto"

    # Ask Chrome for its console and network logs.
    #
    # Off by default, and that is a detection decision rather than a
    # performance one. Serving these logs makes ChromeDriver enable the CDP
    # Runtime and Network domains for the session, and a page can detect that
    # with a one-line trick (a getter on `.stack` passed to console.log fires
    # only when something is listening on Runtime). It is one of the few
    # things that distinguishes a driven browser from a used one after the
    # fingerprint has been cleaned up.
    #
    # Turn it on with --capture-logs when diagnosing something that needs the
    # network exchange, and expect the run to be scored worse while it is on.
    capture_browser_logs: bool = False

    # Keep third-party storage working for the nested Turnstile frame.
    #
    # The challenge on the eligible-applicant screen runs three frames deep --
    # Cloudflare's inside the Solix app's inside assurancewireless.com -- and
    # a challenge that cannot read or write storage in its own frame cannot
    # complete. It then fails with a `600***` code, and this form reports every
    # failure it has as "(600)", so the two are indistinguishable on screen.
    #
    # Off by default because it changes how the browser behaves and most
    # profiles do not need it. The frame storage check that runs on entering
    # the enrollment frame says whether this one does: turn this on if it
    # warns that cookies or storage cannot be written in there.
    allow_third_party_storage: bool = False

    # Hook Cloudflare's Turnstile API to record the sitekey it renders with
    # and the error code it fails with.
    #
    # Off by default, and that is a correctness decision rather than a
    # cautious one. Tracing installs an accessor on `window.turnstile` so the
    # moment of assignment can be caught -- which is also precisely what a
    # script hooking the API looks like, and Cloudflare's loader is hardened
    # against being hooked. Measured on this form: with the accessor in place
    # the script downloaded and ran (`onload` fired, the host was reachable)
    # and still never defined `window.turnstile`, which is a loader declining
    # to initialise rather than a network failure.
    #
    # Without it the run still sees everything that matters -- whether the API
    # arrived, whether a widget rendered, whether a token exists -- by reading
    # rather than intercepting. Turn it on to diagnose, not to succeed.
    trace_turnstile: bool = False

    # Stop the batch at the first lead that gets past the email check.
    #
    # Set by `--next N`. The site validates the email address at the
    # personal-info screen and throws the lead out when it does not deliver,
    # and this sheet has a lot of addresses that do not -- ten leads have died
    # that way without ever reaching the form's later screens. Handing the run
    # several leads lets it walk past those by itself.
    #
    # It stops at the first one that survives, because past that point every
    # further lead is a real application submitted for no additional
    # information. The count is a ceiling on attempts, not a target.
    stop_after_progress: bool = False

    # --- Browserless (browser_backend="browserless") ------------------------
    #
    # A hosted browser fleet with its own stealth handling and proxy pool. It
    # is a peer of the GoLogin backend rather than a replacement for it: both
    # supply a browser somebody else maintains, on a network that is not this
    # office's. Worth having because every lever inside our own browser has
    # been measured and levelled, and what is left to vary is the fleet and
    # the exit IP.
    #
    # Read from .env so it never lands in the repo.
    # BROWSERLESS_API is accepted as an alias: it is the name people reach for
    # first, and a token that is present under the "wrong" name looks
    # identical to no token at all.
    browserless_token: str = field(
        default_factory=lambda: (
            os.getenv("BROWSERLESS_TOKEN") or os.getenv("BROWSERLESS_API") or ""
        ).strip()
    )

    # Shared-cloud default. A dedicated plan has its own host, and a
    # dedicated token against this one is refused -- which reads as a bad
    # token when the token is fine.
    browserless_host: str = field(
        default_factory=lambda: (
            os.getenv("BROWSERLESS_HOST") or "production-sfo.browserless.io"
        ).strip()
    )

    # Browserless's own anti-detection. On by default: it is the reason to
    # use the service rather than a plain remote Chrome.
    browserless_stealth: bool = True

    # Ask Browserless for a URL that streams the hosted session, so a person
    # can watch it -- and click into it, since the live view takes real input.
    # Off by default: it is for watching a run, not for running a batch.
    browserless_live_view: bool = False

    # Whether to open that URL in this machine's browser, or just log it.
    browserless_live_open: bool = True

    # Stream quality, 1-100. Browserless's own default is 70.
    browserless_live_quality: int = 70

    # "residential" to use their proxy pool, blank for none. Plan-gated, so
    # check it is available on the account before relying on it.
    browserless_proxy: str = "residential"
    browserless_proxy_country: str = "us"

    # How long Browserless keeps a session before reclaiming it. The
    # eligibility lookup on step 9 alone runs for minutes, so the default of
    # a few tens of seconds would cut a working run off mid-submit.
    #
    # This is what the flow *wants*, not what it necessarily gets: the value
    # is plan-capped, and asking for more than the plan allows is refused at
    # the handshake with a bare HTTP 400. The shared cloud caps it at 120s
    # (measured), so the backend clamps to that and warns about the
    # shortfall -- see PLAN_TIMEOUT_CAP_MS in browserless_backend.py. Raising
    # it here only helps on a deployment whose cap is higher.
    browserless_timeout_ms: int = 900_000

    # Where the browser runs. "gologin" (the default) launches a GoLogin
    # (Orbita) profile, which brings its own fingerprint, proxy and cookies.
    # The SeleniumBase backends are still here as a fallback: "local"
    # (throwaway UC Chrome), "local-profile" (UC Chrome reusing profile_dir),
    # "remote" (Chrome on the machine at grid_url).
    browser_backend: str = "gologin"
    grid_url: str = ""                      # e.g. http://10.0.0.5:4444
    profile_dir: Path | None = None         # for browser_backend="local-profile"

    gologin: GoLoginConfig = field(default_factory=GoLoginConfig)

    # Extra attempts, on a different browser, when the site serves a bot wall
    # or the profile will not launch. Blocks here are per-profile and
    # short-lived -- the proxy pool is shared, so one profile is refused while
    # the next goes straight through. This does not retry anything else: every
    # other failure means retrying would just resubmit the applicant.
    block_retries: int = 2

    # How many leads to process at once, each in its own browser. Every
    # worker paces itself with lead_delay, so N workers means N leads in
    # flight -- raise lead_delay alongside this to keep the same overall rate.
    workers: int = 1

    # Idle between leads. Spacing a batch out is what keeps a long run from
    # looking like a flood; it is not there to defeat the host's limits, it is
    # there to stay under them.
    lead_delay: tuple[float, float] = (15.0, 40.0)

    sheet: SheetConfig = field(default_factory=SheetConfig)
    application: ApplicationConfig = field(default_factory=ApplicationConfig)
    use_flaresolverr: bool = False
    flaresolverr_endpoint: str = "http://localhost:8191/v1"