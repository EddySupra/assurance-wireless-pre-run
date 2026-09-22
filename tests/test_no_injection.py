"""The browser must not be modified on an ordinary run.

A GoLogin profile's value is that it is an unmodified browser: the stealth
layer's artefact patches are deliberately off for it, because measured side by
side the patches were the only thing left to detect. Anything this project
injects therefore has nothing masking it.

Diagnostics added during debugging quietly broke that. The Turnstile observer
ran in every document, wrapped `console.error`, left a `setInterval` going and
fetched Cloudflare's own script from the page; the storage check wrote a
cookie and two storage keys into the enrollment frame. All useful while
diagnosing, all visible to anything looking, and all of it running by default.

These tests pin the default: nothing is installed unless --trace-turnstile
asks for it.

    python -m pytest tests -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot import turnstile  # noqa: E402
from aw_bot.config import RunConfig  # noqa: E402


class _Driver:
    def __init__(self):
        self.cdp_calls = []
        self.scripts = []

    def execute_cdp_cmd(self, cmd, params):
        self.cdp_calls.append((cmd, params))

    def execute_script(self, script, *args):
        self.scripts.append(script)
        return {}


class _Sb:
    def __init__(self):
        self.driver = _Driver()
        self.scripts = []

    def execute_script(self, script, *args):
        self.scripts.append(script)
        return {}


def test_nothing_is_injected_on_a_default_run():
    sb = _Sb()
    assert turnstile.install(sb, RunConfig()) is False
    assert sb.driver.cdp_calls == []


def test_nothing_is_injected_into_an_open_document_either():
    sb = _Sb()
    assert turnstile.install_now(sb, RunConfig()) is False
    assert sb.scripts == []


def test_a_missing_config_is_treated_as_no_tracing():
    """Defaulting to "inject" on an unknown caller is how this crept back."""
    sb = _Sb()
    assert turnstile.install(sb) is False
    assert turnstile.install_now(sb) is False
    assert sb.driver.cdp_calls == []


def test_tracing_installs_when_it_is_asked_for():
    cfg = RunConfig()
    cfg.trace_turnstile = True
    sb = _Sb()
    assert turnstile.install(sb, cfg) is True
    assert len(sb.driver.cdp_calls) == 1
    cmd, params = sb.driver.cdp_calls[0]
    assert cmd == "Page.addScriptToEvaluateOnNewDocument"
    assert "__awTurnstile" in params["source"]


def test_reading_the_state_needs_no_observer():
    """The default path has to work without anything having been installed.

    `state()` reads the DOM and the Turnstile API's own `getResponse`, so the
    observer is an extra rather than a prerequisite -- which is what makes
    turning it off by default possible at all.
    """
    assert "window.__awTurnstile || null" in turnstile.STATE_JS
    assert "querySelector" in turnstile.STATE_JS


def test_the_console_patch_lives_only_in_the_observer():
    """Wrapping a native is the most visible thing here; keep it opt-in."""
    assert "console.error" in turnstile.OBSERVER_JS
    assert "console.error" not in turnstile.STATE_JS
