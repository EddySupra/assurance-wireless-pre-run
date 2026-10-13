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
    identity = {k: (v.copy() if isinstance(v, (dict, list)) else v)
                for k, v in COHERENT.items()}
    identity.update(overrides)
    return identity


def test_chrome_major_read_from_ua():
    assert _chrome_major(COHERENT["userAgent"]) == "151"


def test_chrome_major_of_a_non_chrome_ua_is_empty():
    assert _chrome_major("Mozilla/5.0 (X11; Linux x86_64) Firefox/126.0") == ""


def test_brand_major_ignores_the_grease_entry():
    assert _brand_major(COHERENT["uaData"]) == "151"


def test_platform_family_normalises_the_spellings():
    assert _platform_family("Windows NT 10.0; Win64") == "Windows"
    assert _platform_family("Win32") == "Windows"
    assert _platform_family("MacIntel") == "macOS"
    assert _platform_family("Linux x86_64") == "Linux"
    assert _platform_family("") == ""


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


def test_the_600_family_is_explained_not_just_printed():
    text = turnstile.explain_error("600010")
    assert "600010" in text
    assert "challenge" in text.lower()
    assert "storage" in text.lower()


def test_sitekey_errors_are_explained():
    assert "sitekey" in turnstile.explain_error("110").lower()


def test_an_unknown_code_still_returns_something_readable():
    assert "999999" in turnstile.explain_error("999999")


def test_no_code_means_no_message():
    assert turnstile.explain_error(None) == ""
    assert turnstile.explain_error("") == ""


def test_describe_puts_a_token_first():
    assert "token held" in turnstile.describe({"token": True, "tokenLength": 900})


def test_describe_names_the_error_when_there_is_one():
    summary = turnstile.describe({"rendered": True, "errorCode": "600010"})
    assert "600010" in summary


def test_describe_separates_a_loaded_api_from_a_rendered_widget():
    assert turnstile.describe({"apiLoaded": True, "rendered": False}) == (
        "API loaded, no widget rendered"
    )
    assert "rendered" in turnstile.describe(
        {"apiLoaded": True, "rendered": True, "sitekey": "0x4A"}
    )


def test_the_observer_does_not_hook_window_turnstile_by_default():
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
    from aw_bot.config import RunConfig

    source = turnstile._source(RunConfig())
    assert "__awTurnstile && window.__awTurnstile.installed" in source


def test_the_coep_block_is_explained_and_blamed_on_the_proxy():
    needles = dict(turnstile._ERROR_MEANINGS)
    meaning = needles["notsameoriginafterdefaultedtosameoriginbycoep"]
    assert "Cross-Origin-Resource-Policy" in meaning
    assert "proxy" in meaning


def test_the_duplicate_load_complaint_is_explained():
    needles = dict(turnstile._ERROR_MEANINGS)
    assert "twice" in needles["already has been loaded"]


def test_the_apps_typeerror_is_named_as_a_consequence():
    needles = dict(turnstile._ERROR_MEANINGS)
    assert "consequence" in needles["reading 'render'"]


def test_the_observer_collects_page_errors():
    from aw_bot.config import RunConfig

    source = turnstile._source(RunConfig())
    assert "__awPageErrors" in source
    assert "unhandledrejection" in source


def test_describe_of_an_unreadable_state_says_so():
    assert turnstile.describe({}) == "unreadable"


def test_describe_names_the_script_that_never_loaded():
    summary = turnstile.describe({
        "apiLoaded": False,
        "rendered": False,
        "observed": True,
        "diagnosis": {"hostPresent": True, "hostEmpty": True},
    })
    assert "never loaded" in summary


def test_a_screen_with_no_turnstile_is_not_reported_as_a_failure():
    summary = turnstile.describe({
        "apiLoaded": False,
        "rendered": False,
        "observed": True,
        "diagnosis": {"hostPresent": False},
    })
    assert summary == "not on this screen"
