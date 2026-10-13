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
    pass


def make_launcher(cfg: RunConfig, workers: int = 1, total_leads: int = 1):
    backend = (cfg.browser_backend or "gologin").lower()
    if backend not in BACKENDS:
        raise BrowserConfigError(
            f"Unknown browser_backend {backend!r}. Choose one of: {', '.join(BACKENDS)}"
        )
    _check_extensions(cfg, backend)
    if backend == "gologin":
        if cfg.gologin.disposable_profiles:
            return _DisposableGoLoginLauncher(cfg, workers, total_leads)
        return _GoLoginLauncher(cfg, workers)
    if backend == "browserless":
        return _BrowserlessLauncher(cfg, workers)
    return _SeleniumBaseLauncher(cfg)


def _check_extensions(cfg: RunConfig, backend: str) -> None:
    if not cfg.extension_dirs:
        return
    if backend in ("remote", "browserless"):
        LOG.warning(
            "Not loading the %d extension(s) from extensions/, EXTENSION_DIRS "
            "or --extension: the %s backend runs Chrome on another machine, "
            "which cannot load a folder from this one.",
            len(cfg.extension_dirs), backend,
        )
        return
    for folder in cfg.extension_dirs:
        if not (folder / "manifest.json").is_file():
            raise BrowserConfigError(
                f"Extension folder {folder} has no manifest.json. Point at the "
                f"unpacked extension -- the folder manifest.json sits in -- not "
                f"a .crx/.zip file or the folder above it."
            )
    LOG.info(
        "Loading %d extension(s) into every browser: %s",
        len(cfg.extension_dirs), ", ".join(str(f) for f in cfg.extension_dirs),
    )


class _BrowserlessLauncher:
    def __init__(self, cfg: RunConfig, workers: int = 1) -> None:
        from .browserless_backend import BrowserlessError, _token

        self.cfg = cfg
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
    def __init__(self, cfg: RunConfig) -> None:
        self.cfg = cfg

    def describe(self) -> str:
        return f"SeleniumBase ({self.cfg.browser_backend})"

    @contextmanager
    def session(self, worker_id: int = 1):
        from seleniumbase import SB

        from . import environment, stealth, turnstile

        with SB(**browser_kwargs(self.cfg, worker_id=worker_id)) as sb:
            stealth.apply(sb, self.cfg, self.cfg.browser_backend)
            turnstile.install(sb, self.cfg)
            environment.audit(sb, self.cfg, worker_id)
            yield sb


class _GoLoginLauncher:
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
    def __init__(self, cfg: RunConfig, workers: int = 1, total_leads: int = 1) -> None:
        from .gologin_backend import GoLoginError, count_profiles

        if not cfg.gologin.token:
            raise GoLoginError(
                "No GoLogin token. Copy .env.example to .env and set GOLOGIN_TOKEN "
                "(app.gologin.com -> Settings -> API), or pass --gologin-token."
            )
        self.cfg = cfg
        self.total_leads = max(1, total_leads)

        held, leftovers = count_profiles(cfg.gologin.token)
        if leftovers:
            LOG.warning(
                "This account holds %d profile(s), %d of them left over from "
                "earlier runs (named aw-*). Each lead needs a free slot. "
                "Clear them with:  python run.py --cleanup-profiles",
                held, leftovers,
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

    kwargs["uc"] = True
    if cfg.headless:
        kwargs["headless2"] = True

    if cfg.extension_dirs:
        kwargs["extension_dir"] = ",".join(str(f) for f in cfg.extension_dirs)

    if backend == "local-profile":
        if not cfg.profile_dir:
            raise BrowserConfigError(
                "browser_backend='local-profile' needs profile_dir set "
                "(or pass --profile-dir)."
            )
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

    LOG.warning(
        "Remote backend: UC-mode anti-bot-wall handling is unavailable over a "
        "grid. If step 1 fails, look at its screenshot before anything else."
    )
    LOG.info("Browsers will run on %s://%s:%s", scheme, parsed.hostname, port)

    return dict(protocol=scheme, servername=parsed.hostname, port=port)