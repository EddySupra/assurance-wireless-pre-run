"""Where the browser runs.

One place that decides how each worker's browser is launched, so the runner
doesn't care which backend is in use.

    gologin        (default) a GoLogin (Orbita) profile: its own fingerprint,
                   proxy, cookies and local storage, started through the
                   GoLogin API and driven over its DevTools port
    local          a throwaway UC-mode Chrome on this machine
    local-profile  UC-mode Chrome reusing a profile directory, so cookies and
                   the ZIP-check session survive between runs
    remote         Chrome on another machine, over the standard WebDriver
                   protocol (Selenium Grid, or a selenium/standalone-chrome
                   container). Nothing runs locally but the script itself.

The three non-GoLogin backends run SeleniumBase and are kept as a fallback.
The `remote` one is the answer to "don't run browsers on my laptop": the
browsers live on a box you control, sized for however many workers you want.

Callers go through `make_launcher(cfg)` and then `launcher.session(worker_id)`,
which yields the same sb-shaped object either way -- SeleniumBase's own `sb` for
the SeleniumBase backends, and an SBShim wrapping the Orbita driver for GoLogin.
"""

from contextlib import contextmanager
from urllib.parse import urlparse

from aw_bot.flaresolverr import (
    solve_cloudflare_challenge,
    inject_cookies_into_driver,
)

from .config import RunConfig
from .errors import AwBotError
from .logs import LOG

SELENIUMBASE_BACKENDS = ("local", "local-profile", "remote")
BACKENDS = ("gologin", "browserless") + SELENIUMBASE_BACKENDS


class BrowserConfigError(AwBotError):
    """The browser backend is misconfigured."""


def make_launcher(cfg: RunConfig, workers: int = 1, total_leads: int = 1):
    """One launcher for the whole batch; call .session(worker_id) per lead."""
    backend = (cfg.browser_backend or "gologin").lower()
    if backend not in BACKENDS:
        raise BrowserConfigError(
            f"Unknown browser_backend {backend!r}. Choose one of: {', '.join(BACKENDS)}"
        )
    if backend == "gologin":
        if cfg.gologin.disposable_profiles:
            return _DisposableGoLoginLauncher(cfg, workers, total_leads)
        return _GoLoginLauncher(cfg, workers)
    if backend == "browserless":
        return _BrowserlessLauncher(cfg, workers)
    return _SeleniumBaseLauncher(cfg)


class _BrowserlessLauncher:
    """A hosted browser per lead, on Browserless's fleet and proxy pool.

    Nothing runs locally. Each lead gets a fresh session, so no cookies or
    storage carry between them -- the same isolation the disposable GoLogin
    profiles give, without managing profiles.
    """

    def __init__(self, cfg: RunConfig, workers: int = 1) -> None:
        from .browserless_backend import BrowserlessError, _token

        self.cfg = cfg
        # Fail here rather than per-lead: a missing token would otherwise
        # burn an applicant per worker discovering the same thing.
        try:
            _token(cfg)
        except BrowserlessError:
            raise

    def describe(self) -> str:
        from .browserless_backend import describe

        return describe(self.cfg)

    @contextmanager
    def session(self, worker_id: int = 1):
        from .browserless_backend import browserless_session

        with browserless_session(self.cfg, worker_id=worker_id) as sb:
            yield sb


class _SeleniumBaseLauncher:
    """UC-mode Chrome (or a grid), the way this project ran before GoLogin."""

    def __init__(self, cfg: RunConfig) -> None:
        self.cfg = cfg

    def describe(self) -> str:
        return f"SeleniumBase ({self.cfg.browser_backend})"

    @contextmanager
    def session(self, worker_id: int = 1):
        from seleniumbase import SB

        from . import environment, stealth, turnstile

        with SB(**browser_kwargs(self.cfg, worker_id=worker_id)) as sb:
            # Before the first navigation: the patches install on new
            # documents, so a page that is already open has had its look.
            stealth.apply(sb, self.cfg, self.cfg.browser_backend)
            turnstile.install(sb, self.cfg)
            environment.audit(sb, self.cfg, worker_id)
            yield sb


class _GoLoginLauncher:
    """A GoLogin profile per lead, leased from the account's pool."""

    def __init__(self, cfg: RunConfig, workers: int = 1) -> None:
        from .gologin_backend import GoLoginError, ProfilePool, resolve_profile_ids

        if not cfg.gologin.token:
            raise GoLoginError(
                "No GoLogin token. Copy .env.example to .env and set GOLOGIN_TOKEN "
                "(app.gologin.com -> Settings -> API), or pass --gologin-token."
            )
        self.cfg = cfg
        self.pool = ProfilePool(cfg.gologin.token, resolve_profile_ids(cfg))

        if workers > len(self.pool):
            raise GoLoginError(
                f"{workers} workers but only {len(self.pool)} GoLogin profile(s) "
                f"available. GoLogin will not run one profile in two browsers at "
                f"once, so add profiles or lower --workers."
            )

    def describe(self) -> str:
        return f"GoLogin ({len(self.pool)} profile(s) available)"

    @contextmanager
    def session(self, worker_id: int = 1):
        from .gologin_backend import gologin_session

        with self.pool.lease(release=not self.cfg.keep_open) as profile_id:
            with gologin_session(self.cfg, profile_id, worker_id=worker_id) as sb:
                yield sb


class _DisposableGoLoginLauncher:
    """A brand-new GoLogin profile, and a new proxy, for every lead.

    Nothing is reused between leads: each one gets its own generated
    fingerprint and its own proxy exit, and the profile is deleted when the
    lead finishes. That is the point -- a shared pool means a lead inherits
    whatever the previous ones left on that identity and that exit.
    """

    def __init__(self, cfg: RunConfig, workers: int = 1, total_leads: int = 1) -> None:
        from .gologin_backend import GoLoginError, count_profiles

        if not cfg.gologin.token:
            raise GoLoginError(
                "No GoLogin token. Copy .env.example to .env and set GOLOGIN_TOKEN "
                "(app.gologin.com -> Settings -> API), or pass --gologin-token."
            )
        self.cfg = cfg
        self.total_leads = max(1, total_leads)
        self.workers = max(1, workers)

        # Say now, not on the third lead. Creating a profile is the first
        # thing each lead does, so an account already at its allowance fails
        # every one of them in turn -- three browsers each, no browser ever
        # opened, and the reason buried in a 403 several screens up.
        #
        # How many slots the run needs at once is the worker count, not one.
        # Each worker holds its own profile for the length of its lead and
        # deletes it afterwards, so N workers means N live profiles for the
        # whole run -- and an account with room for one lead at a time will
        # fail the other four immediately.
        held, leftovers = count_profiles(cfg.gologin.token)
        if leftovers:
            LOG.warning(
                "This account holds %d profile(s), %d of them left over from "
                "earlier runs (named aw-*). Clear them with:  "
                "python run.py --cleanup-profiles",
                held, leftovers,
            )
        if self.workers > 1:
            LOG.info(
                "%d workers means %d profiles live at once, on top of the %d "
                "this account already holds. If GoLogin starts answering 403 "
                "'max profiles', that allowance is the ceiling on --workers.",
                self.workers, self.workers, held,
            )

    def describe(self) -> str:
        gl = self.cfg.gologin
        return (
            f"GoLogin (new profile per lead, "
            f"{gl.proxy_type or 'auto'} proxy in {gl.proxy_country})"
        )

    @contextmanager
    def session(self, worker_id: int = 1):
        from .gologin_backend import (
            create_disposable_profile,
            delete_profile,
            gologin_session,
        )

        profile_id, described = create_disposable_profile(self.cfg, worker_id)
        LOG.info("[w%d] This lead runs as %s", worker_id, described)
        try:
            with gologin_session(self.cfg, profile_id, worker_id=worker_id) as sb:
                yield sb
        finally:
            # --keep-open means somebody wants to look at the browser, and
            # deleting the profile out from under it would take it away. That
            # holds for a single lead and is a leak for a batch: every lead
            # would leave a profile behind, and a GoLogin account has a hard
            # cap on how many it may hold.
            #
            # Measured: a twenty-lead run left nine orphans and then died on
            # `403 You've reached max profiles number`, having never opened a
            # browser for leads three onward. So the profile is only kept when
            # there is exactly one lead to look at.
            if self.cfg.keep_open and self.total_leads <= 1:
                LOG.info(
                    "[w%d] Leaving profile %s in place (--keep-open); "
                    "delete it yourself when done", worker_id, profile_id,
                )
            else:
                if self.cfg.keep_open:
                    LOG.info(
                        "[w%d] Deleting profile %s despite --keep-open: this "
                        "is a %d-lead batch, and keeping one profile per lead "
                        "would fill the account's profile allowance.",
                        worker_id, profile_id, self.total_leads,
                    )
                delete_profile(self.cfg.gologin.token, profile_id, worker_id)


def browser_kwargs(cfg: RunConfig, worker_id: int = 1) -> dict:
    """SB() keyword arguments for one of the SeleniumBase backends."""
    backend = (cfg.browser_backend or "local").lower()
    if backend not in SELENIUMBASE_BACKENDS:
        raise BrowserConfigError(
            f"browser_kwargs is for the SeleniumBase backends "
            f"({', '.join(SELENIUMBASE_BACKENDS)}), not {backend!r}."
        )

    kwargs: dict = dict(browser="chrome", window_size=cfg.window_size)

    if backend == "remote":
        kwargs.update(_remote_kwargs(cfg))
        return kwargs

    # Local backends keep UC mode, which is what stops the carrier site
    # serving a bot wall.
    kwargs["uc"] = True
    if cfg.headless:
        # UC mode needs headless2, not plain headless.
        kwargs["headless2"] = True

    if backend == "local-profile":
        if not cfg.profile_dir:
            raise BrowserConfigError(
                "browser_backend='local-profile' needs profile_dir set "
                "(or pass --profile-dir)."
            )
        # A profile per worker: two Chromes cannot share one profile directory.
        profile = cfg.profile_dir / f"worker_{worker_id}"
        profile.mkdir(parents=True, exist_ok=True)
        kwargs["user_data_dir"] = str(profile)
        LOG.info("Worker %d reusing browser profile %s", worker_id, profile)

    return kwargs


def _remote_kwargs(cfg: RunConfig) -> dict:
    if not cfg.grid_url:
        raise BrowserConfigError(
            "browser_backend='remote' needs grid_url, e.g. "
            "http://10.0.0.5:4444 (pass --grid)."
        )

    parsed = urlparse(cfg.grid_url)
    if not parsed.hostname:
        raise BrowserConfigError(
            f"grid_url {cfg.grid_url!r} is not a URL. Expected something like "
            f"http://host:4444"
        )

    scheme = parsed.scheme or "http"
    port = parsed.port or (443 if scheme == "https" else 4444)

    # UC mode is deliberately NOT set here. It works by patching and driving a
    # chromedriver binary on this machine, which a remote grid never exposes,
    # so asking for it would fail or silently do nothing. That means a remote
    # run is a plain Chrome as far as the site is concerned, and this site does
    # fingerprint for automation -- expect the bot wall, and check the step 1
    # screenshot first if a remote run dies early.
    LOG.warning(
        "Remote backend: UC-mode anti-bot-wall handling is unavailable over a "
        "grid. If step 1 fails, look at its screenshot before anything else."
    )
    LOG.info("Browsers will run on %s://%s:%s", scheme, parsed.hostname, port)

    return dict(protocol=scheme, servername=parsed.hostname, port=port)