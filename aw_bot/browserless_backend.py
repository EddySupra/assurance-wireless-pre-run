"""Running the browser on Browserless instead of this machine.

Browserless hosts Chrome and hands back a CDP endpoint; nothing launches
locally. That makes it a peer of the GoLogin backend rather than a
replacement for SeleniumBase: both supply a browser whose identity is
maintained by somebody else, and both go out through a proxy pool that is not
this office's connection.

Why it is worth trying here: the eligibility screen's Turnstile widget scores
the session, and every lever inside our own browser has now been measured and
levelled -- fingerprint identical to an unpatched Orbita, trusted clicks,
stepped scrolling, human pacing. What is left is the browser fleet and the
exit IP, which is exactly what this changes.

How it connects, and why it is not the obvious way: Browserless v2 speaks CDP
over a WebSocket and nothing else. Selenium and WebDriver were dropped in
their v2 rewrite, and `POST /webdriver` answers 501 Not Implemented on every
shared-cloud region -- measured against this account, with the same token that
drives CDP fine, so it is not a plan or credential problem. Rather than port
ten step modules, `human.py` and `page_utils.py` to Playwright, this attaches
chromedriver to the remote browser through `cdp_bridge`, which serves a local
DevTools endpoint and forwards it. Every existing step runs unchanged.

Because the hosted browser is a headless Linux Chrome -- it reports
`HeadlessChrome` on `X11; Linux x86_64`, measured -- the project's own stealth
layer applies here as it does on the SeleniumBase backends. That is already
what `stealth_fingerprint="auto"` resolves to for anything that is not
GoLogin, and for the same reason: unlike an Orbita profile, Browserless does
not hand us a coherent consumer fingerprint to leave alone.

Deliberately not included: Browserless's captcha-solving calls. Turnstile on
that screen is a human-verification control on a federally funded Lifeline
application, and clearing it automatically is the thing this project already
decided not to do when it ruled out VPN rotation to dodge rate limits. This
backend is "a different browser on a different network", not "answer the
check for us". The site's Agent Login remains the supported route for volume.
"""

import os
from contextlib import contextmanager
from urllib.parse import quote, urlencode

from .config import RunConfig
from .errors import AwBotError
from .logs import LOG
from .sb_shim import SBShim

DEFAULT_HOST = "production-sfo.browserless.io"

# The session ceiling is the PLAN's, and it is not discoverable: there is no
# endpoint that reports it, and asking for more than it allows is refused at
# the websocket handshake with a bare HTTP 400 naming no parameter.
#
# So this does not clamp to a guess. It asks for what the flow wants, and
# falls back to this known-safe value only if the handshake actually refuses
# -- which is the difference between "your plan is smaller than you think"
# and "this code decided for you". Measured on the shared cloud: 120_000 is
# accepted and 123_750 is refused. Measured after an upgrade on this same
# account: 1_800_000 accepted, 3_600_000 refused. A hardcoded ceiling would
# have silently held that upgraded plan to two minutes.
FALLBACK_TIMEOUT_MS = 120_000


class BrowserlessError(AwBotError):
    """Browserless could not give us a usable browser."""


def _token(cfg: RunConfig) -> str:
    token = (getattr(cfg, "browserless_token", "") or "").strip()
    if not token:
        token = (
            os.getenv("BROWSERLESS_TOKEN") or os.getenv("BROWSERLESS_API") or ""
        ).strip()

    # Strip the wrappers a pasted credential arrives in. Docs write keys as
    # <YOUR_TOKEN>, and .env files are not shell, so quotes are not special
    # there either -- both get sent verbatim and the service answers "Invalid
    # API key", which sends you looking at the key rather than at the two
    # characters around it. Cost an hour once; cheaper to just handle.
    for pair in ("<>", '""', "''"):
        if len(token) > 2 and token[0] == pair[0] and token[-1] == pair[1]:
            token = token[1:-1].strip()

    if not token:
        raise BrowserlessError(
            "No Browserless token. Put BROWSERLESS_TOKEN in .env, or pass "
            "--browserless-token. The dashboard at browserless.io shows it."
        )
    return token


def _host(cfg: RunConfig) -> str:
    host = (getattr(cfg, "browserless_host", "") or DEFAULT_HOST).strip()
    return host.replace("https://", "").replace("wss://", "").strip("/")


def websocket_endpoint(cfg: RunConfig, timeout_override: int | None = None) -> str:
    """The wss:// URL this backend -- and any CDP client -- connects to.

    The token goes in the query string because that is what the service
    accepts on this route; it is never logged (see `describe`).
    """
    params = {"token": _token(cfg)}

    # Browserless's own anti-detection, which is part of the point of using it.
    if getattr(cfg, "browserless_stealth", True):
        params["stealth"] = "true"

    # Their residential pool, as an alternative to GoLogin's. `proxyCountry`
    # only means anything when proxy=residential is set.
    proxy = (getattr(cfg, "browserless_proxy", "") or "").strip()
    if proxy:
        params["proxy"] = proxy
        country = (getattr(cfg, "browserless_proxy_country", "") or "").strip()
        if country:
            params["proxyCountry"] = country.lower()

    # How long Browserless keeps the session before reclaiming it. Asked for
    # in full; `browserless_session` handles a plan that refuses it.
    timeout_ms = int(timeout_override or getattr(cfg, "browserless_timeout_ms", 0) or 0)
    if timeout_ms:
        params["timeout"] = str(timeout_ms)

    return f"wss://{_host(cfg)}?{urlencode(params, quote_via=quote)}"


def open_live_view(bridge, cfg: RunConfig, worker_id: int = 1) -> str:
    """Ask Browserless for a URL that shows this session, and open it.

    The hosted browser is headless in a data centre, so there is no window
    here to watch. `Browserless.liveURL` answers with a page that streams the
    session and accepts mouse and keyboard -- which is also the honest way to
    do --solve-challenges on this backend, since a person can click the
    widget themselves.

    Returns the URL, or "" if the service would not give one. Never fatal: a
    run that cannot be watched is still a run.
    """
    # `timeout` is how long the minted URL stays valid, and it defaults to
    # 30_000 -- thirty seconds, not the session's length. That default is
    # useless here: the start page alone takes ~36s to load through the
    # residential proxy, so a link minted before the first navigation is dead
    # before the first page finishes, and the viewer shows a tab that never
    # connects rather than an error. Mint it for the whole session instead.
    #
    # It cannot exceed the plan's maximum session duration, and minting it
    # never extends that session -- the browser still ends when it was
    # always going to.
    # The live URL cannot outlive the session it shows, and asking for more
    # than the plan allows is refused the same way the session is.
    live_ms = getattr(bridge, "session_timeout_ms", 0) or FALLBACK_TIMEOUT_MS

    # Minted against a page, not against the browser.
    #
    # `Browserless.liveURL` is reached over the browser connection but has to
    # be scoped to a page session, and asking for it browser-level still
    # answers with a perfectly ordinary-looking URL. Opening that URL shows
    # "Couldn't attach to the requested page. Is your browser running?" --
    # which reads as a dead session or a broken bridge, when the only thing
    # wrong is that nobody said which page. Confirmed both ways by
    # screenshotting each URL from a second browser.
    try:
        targets = bridge.call("Target.getTargets").get("targetInfos", [])
        page = next((t for t in targets if t.get("type") == "page"), None)
        if page is None:
            LOG.warning("[w%d] No page to show a live view of yet", worker_id)
            return ""

        session_id = bridge.call(
            "Target.attachToTarget", {"targetId": page["targetId"], "flatten": True}
        ).get("sessionId")

        result = bridge.call("Browserless.liveURL", {
            "timeout": live_ms,
            "quality": int(getattr(cfg, "browserless_live_quality", 70)),
            # The viewer takes mouse and keyboard, which is what makes this
            # usable for answering a challenge by hand rather than just
            # watching one go by.
            "interactable": True,
        }, session_id=session_id)
    except Exception as exc:
        LOG.warning("[w%d] Browserless would not open a live view: %s", worker_id, exc)
        return ""

    url = (result or {}).get("liveURL") or ""
    if not url:
        LOG.warning("[w%d] Browserless returned no live view URL (%s)", worker_id, result)
        return ""

    # Loud on purpose: the URL is the only way to see this run, and it is
    # worth nothing once the session ends a couple of minutes from now.
    LOG.info("[w%d] Watch this session live: %s", worker_id, url)

    if getattr(cfg, "browserless_live_open", True):
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception as exc:
            LOG.debug("[w%d] Could not open a browser for the live view: %s", worker_id, exc)
    return url


def describe(cfg: RunConfig) -> str:
    """A description safe to log -- never includes the token."""
    bits = [_host(cfg)]
    if getattr(cfg, "browserless_stealth", True):
        bits.append("stealth")
    proxy = (getattr(cfg, "browserless_proxy", "") or "").strip()
    if proxy:
        country = (getattr(cfg, "browserless_proxy_country", "") or "").strip()
        bits.append(f"{proxy} proxy{f' ({country.upper()})' if country else ''}")
    return "Browserless (" + ", ".join(bits) + ")"


def _is_400(exc: Exception) -> bool:
    """Whether the handshake was refused as a bad request.

    That is how a plan says "not that long" -- there is no richer signal.
    """
    return "400" in str(exc)


def _connect_error(host: str, exc: Exception) -> BrowserlessError:
    """Turn a websocket handshake failure into something actionable."""
    detail = str(exc)
    lowered = detail.lower()

    if "401" in detail or "unauthorized" in lowered or "invalid api key" in lowered:
        return BrowserlessError(
            f"{host} refused the token. Check BROWSERLESS_TOKEN in .env -- and "
            f"that it belongs to this host: a dedicated-plan token is refused "
            f"by the shared cloud and vice versa, which reads as a bad token "
            f"when the token is fine."
        )
    if "429" in detail or "too many" in lowered:
        return BrowserlessError(
            f"{host} has no session slot free (429). The plan's concurrency is "
            f"already in use -- lower --workers, or wait for the running "
            f"sessions to finish."
        )
    if "400" in detail:
        return BrowserlessError(
            f"{host} refused the session options (400). It answers this with "
            f"no detail, so work out which option by removing them. A "
            f"`timeout` above the plan's ceiling causes this, and the backend "
            f"already retries once at {FALLBACK_TIMEOUT_MS / 1000:.0f}s -- so "
            f"a 400 surviving that is something else in the query, most "
            f"likely a proxy option this plan does not carry. Try "
            f"--browserless-proxy none."
        )
    if "403" in detail:
        return BrowserlessError(
            f"{host} rejected the session options (403). `proxy=residential` "
            f"is plan-gated; try --browserless-proxy none to see whether that "
            f"is what is being refused."
        )
    return BrowserlessError(f"Could not connect to Browserless at {host}: {detail}")


@contextmanager
def browserless_session(cfg: RunConfig, worker_id: int = 1):
    """Connect to a hosted browser and yield an sb-shaped handle."""
    from . import environment, stealth, turnstile
    from .cdp_bridge import CdpBridge
    from .gologin_backend import attach_driver, resolve_chromedriver

    host = _host(cfg)
    LOG.info("[w%d] Connecting to %s", worker_id, describe(cfg))

    wanted_ms = int(getattr(cfg, "browserless_timeout_ms", 0) or 0)
    bridge = CdpBridge(websocket_endpoint(cfg))
    bridge.session_timeout_ms = wanted_ms
    driver = None
    try:
        try:
            address = bridge.start()
        except Exception as exc:
            # A plan that will not grant the session length asked for refuses
            # the handshake outright, with a 400 that names nothing. Retrying
            # at the known-safe length turns "Browserless is broken" into a
            # run that works and a line saying what it cost -- and, when the
            # plan is bigger than that, never runs at all.
            if _is_400(exc) and wanted_ms > FALLBACK_TIMEOUT_MS:
                LOG.warning(
                    "[w%d] This plan refused a %.0fs session; retrying at %.0fs. "
                    "Leads needing longer than that will be cut off mid-form -- "
                    "the eligibility lookup on step 9 alone runs for minutes.",
                    worker_id, wanted_ms / 1000, FALLBACK_TIMEOUT_MS / 1000,
                )
                bridge = CdpBridge(websocket_endpoint(cfg, FALLBACK_TIMEOUT_MS))
                bridge.session_timeout_ms = FALLBACK_TIMEOUT_MS
                try:
                    address = bridge.start()
                except Exception as exc2:
                    raise _connect_error(host, exc2) from exc2
            else:
                raise _connect_error(host, exc) from exc

        LOG.info(
            "[w%d] Session granted for up to %.0fs",
            worker_id, (bridge.session_timeout_ms or 0) / 1000,
        )

        # chromedriver refuses a browser whose major it does not match, so the
        # remote Chrome decides which driver is fetched -- the same rule the
        # GoLogin backend follows for Orbita, and the same resolver.
        version = bridge.browser_version
        LOG.info("[w%d] Remote browser is Chrome %s", worker_id, version or "?")
        driver_path = resolve_chromedriver(version, cfg.gologin.chromedriver_path)

        driver = attach_driver(address, driver_path, cfg)

        # The hosted browser opens at its own default size. The form's layout
        # -- and every screen-point calculation that follows it -- assumes the
        # window this project asks for everywhere else.
        try:
            width, height = (int(n) for n in cfg.window_size.split(","))
            driver.set_window_size(width, height)
        except Exception as exc:
            LOG.debug("[w%d] Could not size the remote window: %s", worker_id, exc)

        # Before the first navigation: these install on new documents, so a
        # page that is already open has had its look.
        stealth.apply(driver, cfg, "browserless")
        turnstile.install(driver, cfg)
        environment.audit(driver, cfg, worker_id)

        # Also before the first navigation, so somebody watching sees the
        # whole run and not just whatever it reached while they were
        # opening the tab.
        if getattr(cfg, "browserless_live_view", False):
            open_live_view(bridge, cfg, worker_id)

        yield SBShim(driver, timeout=cfg.page_timeout)
    finally:
        # Said before anything else, because it explains whatever error is on
        # its way up. When Browserless reclaims the session the browser simply
        # vanishes, and every Selenium call after that fails with a transport
        # error naming a local port -- which reads as "the site blocked us"
        # or "the bridge is broken" when it is neither.
        if bridge.upstream_closed:
            LOG.error(
                "[w%d] The hosted browser went away after %.0fs, on a session "
                "granted %.0fs. Browserless ends a session at its ceiling "
                "whatever the run is in the middle of. This is the plan, not "
                "the site and not the form.",
                worker_id, bridge.session_seconds,
                (getattr(bridge, "session_timeout_ms", 0) or 0) / 1000,
            )

        if driver is not None:
            try:
                driver.quit()
            except Exception as exc:
                LOG.debug("[w%d] Browserless session did not close cleanly: %s", worker_id, exc)
        if cfg.keep_open:
            # Worth saying rather than silently ignoring: the browser being
            # kept open is in a data centre, so there is nothing here to look
            # at. Browserless's dashboard shows the live session instead.
            LOG.info(
                "[w%d] --keep-open does not apply to a hosted browser; the "
                "session ends with the run. Watch it live from the "
                "Browserless dashboard instead.", worker_id,
            )
        bridge.stop()
