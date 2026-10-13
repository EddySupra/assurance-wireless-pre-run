import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

START_URL = "https://www.assurancewireless.com/"

ALLOWED_HOST_SUFFIXES = ("assurancewireless.com", "solixinc.com")


def _extension_dirs() -> tuple[Path, ...]:
    from .extensions import discover

    dirs = list(discover(PROJECT_ROOT / "extensions"))
    for raw in (os.getenv("EXTENSION_DIRS") or "").split(","):
        raw = raw.strip().strip('"')
        if raw:
            path = Path(raw).expanduser()
            dirs.append(path if path.is_absolute() else PROJECT_ROOT / path)
    return tuple(dict.fromkeys(keyed_extension(d) for d in dirs))


def keyed_extension(folder: Path) -> Path:
    from .extensions import UNPACKED, with_capsolver_key

    key = (os.getenv("CAPSOLVER_API_KEY") or "").strip().strip('"')
    return with_capsolver_key(folder, key, PROJECT_ROOT / "extensions" / UNPACKED)


@dataclass
class SheetConfig:
    credentials_path: Path = field(default=PROJECT_ROOT / "credentials" / "service_account.json")

    spreadsheet_key: str = "14D6Uxl8MeRAL7lNy6IeSmeZNEeicRhqZR5Oecx6un_I"
    spreadsheet_url: str = ""

    worksheet_name: str = ""

    header_row: int = 1

    write_verdicts: bool = True
    verdict_column: str = "L"


@dataclass
class GoLoginConfig:
    token: str = field(default_factory=lambda: (os.getenv("GOLOGIN_TOKEN") or "").strip())
    profile_ids: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            p.strip() for p in (os.getenv("GOLOGIN_PROFILE_ID") or "").split(",") if p.strip()
        )
    )

    random_profile: bool = False

    chromedriver_path: str = field(default_factory=lambda: os.getenv("CHROMEDRIVER_PATH", ""))

    extra_args: tuple[str, ...] = ()

    disable_extensions: bool = False

    freshen_user_agent: bool = False

    disposable_profiles: bool = True

    proxy_type: str = "mobile"

    proxy_country: str = "US"

    profile_os: tuple[str, ...] = ("win", "mac")

    fresh_session: bool = True


@dataclass
class ApplicationConfig:
    account_pin: str = "470293"

    security_answers: tuple[str, str, str] = ("Brookfield", "Marigold", "Sandcastle")

    language: str = "English"
    contact_method: str = "Email"
    print_preference: str = "Standard Print"

    phone_option: str = "free"

    esign_consent: str = "Yes"

    esign_initials: str = "XX"

    wifi_911_acknowledged: str = "Yes"

    service_terms_agreed: bool = True

    household_lives_with_adult: str = "Yes"
    household_adult_has_lifeline: str = "Yes"
    household_shares_expenses: str = "No"

    qualifying_program: str = (
        "CalFresh, Food Stamps or Supplemental Nutrition Assistance Program (SNAP)"
    )

    eligible_applicant: str = "I am the Eligible Applicant"

    confirm_dependent_answer: str = "No"

    skip_preselected_radios: bool = True


@dataclass
class RunConfig:
    start_url: str = START_URL
    headless: bool = False

    reconnect_time: float = 5.0

    page_timeout: int = 45

    max_busy_wait: float = 60.0

    step10_first_look: float = 5.0

    turnstile_wait: float = 30.0

    solve_challenge_wait: float = 180.0

    solve_challenges: bool = False

    frame_direct: bool = False
    window_size: str = "1440,1000"

    save_artifacts: bool = True
    artifacts_root: Path = field(default=PROJECT_ROOT / "artifacts")

    keep_open: bool = False

    dry_run: bool = False

    human_like: bool = True

    real_input: bool = False

    allow_synthetic_fallback: bool = False

    verbose: bool = False

    type_delay: tuple[float, float] = (0.05, 0.16)
    action_pause: tuple[float, float] = (0.15, 0.45)
    mouse_steps: int = 9

    warm_up_seconds: tuple[float, float] = (0.6, 1.5)

    typo_chance: float = 0.015

    stealth: bool = True

    stealth_fingerprint: str = "auto"

    stealth_artifacts: str = "auto"

    capture_browser_logs: bool = False

    allow_third_party_storage: bool = False

    trace_turnstile: bool = False

    stop_after_progress: bool = False

    browserless_token: str = field(
        default_factory=lambda: (
            os.getenv("BROWSERLESS_TOKEN") or os.getenv("BROWSERLESS_API") or ""
        ).strip()
    )

    browserless_host: str = field(
        default_factory=lambda: (
            os.getenv("BROWSERLESS_HOST") or "production-sfo.browserless.io"
        ).strip()
    )

    browserless_stealth: bool = True

    browserless_live_view: bool = False

    browserless_live_open: bool = True

    browserless_live_quality: int = 70

    browserless_proxy: str = "residential"
    browserless_proxy_country: str = "us"

    browserless_timeout_ms: int = 900_000

    browser_backend: str = "gologin"
    grid_url: str = ""
    profile_dir: Path | None = None

    extension_dirs: tuple[Path, ...] = field(default_factory=_extension_dirs)

    gologin: GoLoginConfig = field(default_factory=GoLoginConfig)

    block_retries: int = 2

    workers: int = 1

    lead_delay: tuple[float, float] = (5.0, 10.0)

    sheet: SheetConfig = field(default_factory=SheetConfig)
    application: ApplicationConfig = field(default_factory=ApplicationConfig)
    use_flaresolverr: bool = False
    flaresolverr_endpoint: str = "http://localhost:8191/v1"