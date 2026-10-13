import os
from contextlib import contextmanager
from urllib.parse import quote, urlencode

from .config import RunConfig
from .errors import AwBotError
from .logs import LOG
from .sb_shim import SBShim

DEFAULT_HOST = "production-sfo.browserless.io"

FALLBACK_TIMEOUT_MS = 120_000


class BrowserlessError(AwBotError):
    pass


def _token(cfg: RunConfig) -> str:
    token = (getattr(cfg, "browserless_token", "") or "").strip()
    if not token:
        token = (
            os.getenv("BROWSERLESS_TOKEN") or os.getenv("BROWSERLESS_API") or ""
        ).strip()

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
    params = {"token": _token(cfg)}

    if getattr(cfg, "browserless_stealth", True):
        params["stealth"] = "true"

    proxy = (getattr(cfg, "browserless_proxy", "") or "").strip()
    if proxy:
        params["proxy"] = proxy
        country = (getattr(cfg, "browserless_proxy_country", "") or "").strip()
        if country:
            params["proxyCountry"] = country.lower()

    timeout_ms = int(timeout_override or getattr(cfg, "browserless_timeout_ms", 0) or 0)
    if timeout_ms:
        params["timeout"] = str(timeout_ms)

    return f"wss://{_host(cfg)}?{urlencode(params, quote_via=quote)}"


def open_live_view(bridge, cfg: RunConfig, worker_id: int = 1) -> str:
    live_ms = getattr(bridge, "session_timeout_ms", 0) or FALLBACK_TIMEOUT_MS

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
            "interactable": True,
        }, session_id=session_id)
    except Exception as exc:
        LOG.warning("[w%d] Browserless would not open a live view: %s", worker_id, exc)
        return ""

    url = (result or {}).get("liveURL") or ""
    if not url:
        LOG.warning("[w%d] Browserless returned no live view URL (%s)", worker_id, result)
        return ""

    LOG.info("[w%d] Watch this session live: %s", worker_id, url)

    if getattr(cfg, "browserless_live_open", True):
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception as exc:
            LOG.debug("[w%d] Could not open a browser for the live view: %s", worker_id, exc)
    return url


def describe(cfg: RunConfig) -> str:
    bits = [_host(cfg)]
    if getattr(cfg, "browserless_stealth", True):
        bits.append("stealth")
    proxy = (getattr(cfg, "browserless_proxy", "") or "").strip()
    if proxy:
        country = (getattr(cfg, "browserless_proxy_country", "") or "").strip()
        bits.append(f"{proxy} proxy{f' ({country.upper()})' if country else ''}")
    return "Browserless (" + ", ".join(bits) + ")"


def _is_400(exc: Exception) -> bool:
    return "400" in str(exc)


def _connect_error(host: str, exc: Exception) -> BrowserlessError:
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

        version = bridge.browser_version
        LOG.info("[w%d] Remote browser is Chrome %s", worker_id, version or "?")
        driver_path = resolve_chromedriver(version, cfg.gologin.chromedriver_path)

        driver = attach_driver(address, driver_path, cfg)

        try:
            width, height = (int(n) for n in cfg.window_size.split(","))
            driver.set_window_size(width, height)
        except Exception as exc:
            LOG.debug("[w%d] Could not size the remote window: %s", worker_id, exc)

        stealth.apply(driver, cfg, "browserless")
        turnstile.install(driver, cfg)
        environment.audit(driver, cfg, worker_id)

        if getattr(cfg, "browserless_live_view", False):
            open_live_view(bridge, cfg, worker_id)

        yield SBShim(driver, timeout=cfg.page_timeout)
    finally:
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
            LOG.info(
                "[w%d] --keep-open does not apply to a hosted browser; the "
                "session ends with the run. Watch it live from the "
                "Browserless dashboard instead.", worker_id,
            )
        bridge.stop()
