"""Tests for the fingerprint-coherence checks and the Turnstile error reader.

Both of these exist to turn a silent failure into a named one, so the thing
worth pinning is that they name it correctly -- and, just as much, that they
stay quiet about a browser that is telling one consistent story. A check that
cries wolf on a healthy profile is worse than no check, because the next real
warning gets read as noise.

    python -m pytest tests -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot import turnstile  # noqa: E402
from aw_bot.environment import (  # noqa: E402
    _brand_major,
    _chrome_major,
    _platform_family,
    check,
)

# A plausible, internally consistent Windows profile: the shape the checks
# should have nothing to say about.
COHERENT = {
    "userAgent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.7922.173 Safari/537.36"
    ),
    "platform": "Win32",
    "language": "en-US",
    "languages": ["en-US", "en"],
    "timezone": "America/Los_Angeles",
    "cores": 8,
    "touch": 0,
    "webdriver": False,
    "cookieOk": True,
    "cdcKeys": 0,
    "chrome": True,
    "screen": {"w": 1920, "h": 1080},
    "window": {"innerW": 1440, "innerH": 900, "outerW": 1440, "outerH": 985},
    "uaData": {
        "mobile": False,
        "platform": "Windows",
        "brands": [
            {"brand": "Not=A?Brand", "version": "99"},
            {"brand": "Google Chrome", "version": "151"},
            {"brand": "Chromium", "version": "151"},
        ],
    },
}


def _with(**overrides):
    """COHERENT with a few fields replaced."""
    identity = {k: (v.copy() if isinstance(v, (dict, list)) else v)
                for k, v in COHERENT.items()}
    identity.update(overrides)
    return identity


# -- version parsing --------------------------------------------------------

def test_chrome_major_read_from_ua():
    assert _chrome_major(COHERENT["userAgent"]) == "151"


def test_chrome_major_of_a_non_chrome_ua_is_empty():
    assert _chrome_major("Mozilla/5.0 (X11; Linux x86_64) Firefox/126.0") == ""


def test_brand_major_ignores_the_grease_entry():
    """`Not=A?Brand;v=99` is deliberate nonsense and must not be read as a version.

    Chrome emits a junk "brand" on purpose so that parsers cannot assume the
    list's shape. Reading it as the browser version would make every healthy
    Chrome look like it was disagreeing with its own user agent.
    """
    assert _brand_major(COHERENT["uaData"]) == "151"


def test_platform_family_normalises_the_spellings():
    assert _platform_family("Windows NT 10.0; Win64") == "Windows"
    assert _platform_family("Win32") == "Windows"
    assert _platform_family("MacIntel") == "macOS"
    assert _platform_family("Linux x86_64") == "Linux"
    assert _platform_family("") == ""


# -- the coherence checks ---------------------------------------------------

def test_a_consistent_profile_raises_nothing():
    assert check(COHERENT) == []


def test_ua_and_client_hints_disagreeing_on_the_version_is_caught():
    identity = _with(uaData={
        "mobile": False,
        "platform": "Windows",
        "brands": [
            {"brand": "Not=A?Brand", "version": "99"},
            {"brand": "Google Chrome", "version": "118"},
        ],
    })
    problems = check(identity)
    assert any("151" in p and "118" in p for p in problems)


def test_platform_disagreeing_between_ua_and_navigator_is_caught():
    problems = check(_with(platform="MacIntel"))
    assert any("operating system does not agree" in p for p in problems)


def test_a_non_us_timezone_is_caught():
    problems = check(_with(timezone="Europe/Berlin"))
    assert any("timezone" in p and "United States" in p for p in problems)


def test_a_us_timezone_is_accepted():
    assert check(_with(timezone="America/New_York")) == []


def test_a_non_english_language_is_caught():
    problems = check(_with(language="de-DE", languages=["de-DE", "de"]))
    assert any("language" in p for p in problems)


def test_webdriver_flag_is_caught():
    problems = check(_with(webdriver=True))
    assert any("navigator.webdriver" in p for p in problems)


def test_chromedriver_globals_are_caught():
    problems = check(_with(cdcKeys=2))
    assert any("ChromeDriver global" in p for p in problems)


def test_a_window_bigger_than_its_screen_is_caught():
    problems = check(_with(window={"innerW": 2560, "innerH": 1400,
                                   "outerW": 2560, "outerH": 1440}))
    assert any("larger than the screen" in p for p in problems)


def test_zero_outer_dimensions_are_caught():
    problems = check(_with(window={"innerW": 1440, "innerH": 900,
                                   "outerW": 0, "outerH": 0}))
    assert any("zero outer dimensions" in p for p in problems)


def test_disabled_cookies_are_caught():
    problems = check(_with(cookieOk=False))
    assert any("cookies are disabled" in p.lower() for p in problems)


def test_an_empty_reading_is_reported_rather_than_passed():
    assert check({}) != []


# -- Turnstile error codes --------------------------------------------------

def test_the_600_family_is_explained_not_just_printed():
    """`600010` is the code behind this form's "(600)", so it must read clearly."""
    text = turnstile.explain_error("600010")
    assert "600010" in text
    assert "challenge" in text.lower()
    # The actionable causes have to survive into the message.
    assert "storage" in text.lower()


def test_sitekey_errors_are_explained():
    assert "sitekey" in turnstile.explain_error("110").lower()


def test_an_unknown_code_still_returns_something_readable():
    assert "999999" in turnstile.explain_error("999999")


def test_no_code_means_no_message():
    assert turnstile.explain_error(None) == ""
    assert turnstile.explain_error("") == ""


# -- the state summary ------------------------------------------------------

def test_describe_puts_a_token_first():
    assert "token held" in turnstile.describe({"token": True, "tokenLength": 900})


def test_describe_names_the_error_when_there_is_one():
    summary = turnstile.describe({"rendered": True, "errorCode": "600010"})
    assert "600010" in summary


def test_describe_separates_a_loaded_api_from_a_rendered_widget():
    """The distinction the old code could not make, and the bug it caused.

    `#ngx-turnstile` is the id of the loader <script>, so a page that had merely
    downloaded the API looked exactly like a page with a widget waiting on it.
    """
    assert turnstile.describe({"apiLoaded": True, "rendered": False}) == (
        "API loaded, no widget rendered"
    )
    assert "rendered" in turnstile.describe(
        {"apiLoaded": True, "rendered": True, "sitekey": "0x4A"}
    )


def test_the_observer_does_not_hook_window_turnstile_by_default():
    """Watching a property must not change whether it gets set.

    The observer used to install an accessor on `window.turnstile` to catch
    the moment of assignment. That is also exactly what a script hooking the
    API looks like, and Cloudflare's loader is hardened against being hooked:
    measured on this form, the script downloaded and ran and still never
    defined `window.turnstile`. The default now reads rather than intercepts.
    """
    from aw_bot.config import RunConfig

    source = turnstile._source(RunConfig())
    assert "__AW_TRACE__" not in source, "placeholder left unreplaced"
    assert "var TRACE = false;" in source


def test_tracing_can_be_asked_for_explicitly():
    from aw_bot.config import RunConfig

    cfg = RunConfig()
    cfg.trace_turnstile = True
    assert "var TRACE = true;" in turnstile._source(cfg)


def test_the_observer_is_idempotent():
    """It is installed per-document and again on entering the frame."""
    from aw_bot.config import RunConfig

    source = turnstile._source(RunConfig())
    assert "__awTurnstile && window.__awTurnstile.installed" in source


def test_the_coep_block_is_explained_and_blamed_on_the_proxy():
    """The message that finally named this failure.

    `NotSameOriginAfterDefaultedToSameOriginByCoep` means the response came
    back without a Cross-Origin-Resource-Policy header. Cloudflare sends that
    header, so its absence points at something rewriting responses in between
    -- which on this setup is the proxy exit, not anything in the browser.
    """
    needles = dict(turnstile._ERROR_MEANINGS)
    meaning = needles["notsameoriginafterdefaultedtosameoriginbycoep"]
    assert "Cross-Origin-Resource-Policy" in meaning
    assert "proxy" in meaning


def test_the_duplicate_load_complaint_is_explained():
    """Caused by re-requesting the script, which the run no longer does."""
    needles = dict(turnstile._ERROR_MEANINGS)
    assert "twice" in needles["already has been loaded"]


def test_the_apps_typeerror_is_named_as_a_consequence():
    """`reading 'render'` is downstream, not a separate fault to chase."""
    needles = dict(turnstile._ERROR_MEANINGS)
    assert "consequence" in needles["reading 'render'"]


def test_the_observer_collects_page_errors():
    """Without this the only copy of these messages is in somebody's DevTools."""
    from aw_bot.config import RunConfig

    source = turnstile._source(RunConfig())
    assert "__awPageErrors" in source
    assert "unhandledrejection" in source


def test_describe_of_an_unreadable_state_says_so():
    assert turnstile.describe({}) == "unreadable"


def test_describe_names_the_script_that_never_loaded():
    """The actual failure on this form, and the one nothing could see before.

    `<ngx-turnstile>` renders nothing until `window.turnstile` exists. When
    Cloudflare's script does not execute, the host element stays empty, no
    token can ever arrive, and the Continue button it gates spins forever.
    """
    summary = turnstile.describe({
        "apiLoaded": False,
        "rendered": False,
        "observed": True,
        "diagnosis": {"hostPresent": True, "hostEmpty": True},
    })
    assert "never loaded" in summary


def test_a_screen_with_no_turnstile_is_not_reported_as_a_failure():
    """The watcher installs on every page, so `observed` alone means nothing."""
    summary = turnstile.describe({
        "apiLoaded": False,
        "rendered": False,
        "observed": True,
        "diagnosis": {"hostPresent": False},
    })
    assert summary == "not on this screen"
