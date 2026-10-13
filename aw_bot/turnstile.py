import time

from .logs import LOG

OBSERVER_JS = r"""
(function () {
    'use strict';
    if (window.__awTurnstile && window.__awTurnstile.installed) { return; }

    /* Keep the page's own errors, so a failure can be explained without
       somebody having DevTools open at the right moment.

       The messages that actually name this failure only ever appear here:
       the COEP block that stops Cloudflare's script running, Turnstile's
       "already has been loaded" complaint, and the app's own
       "Cannot read properties of undefined (reading 'render')" when its
       callback runs against an API that never arrived. None of them reach
       Selenium unless browser logging is on, and turning that on has its own
       cost, so they are collected here instead. */
    try {
        var errors = [];
        window.__awPageErrors = errors;
        var keep = function (text) {
            try {
                errors.push({ at: Date.now(), text: String(text).slice(0, 400) });
                if (errors.length > 40) { errors.shift(); }
            } catch (e) {}
        };
        window.addEventListener('error', function (e) {
            if (e && e.message) {
                keep(e.message + (e.filename ? ' @ ' + e.filename : ''));
            } else if (e && e.target && e.target.src) {
                /* A resource that failed to load -- which is how a blocked
                   script announces itself to the page. */
                keep('failed to load: ' + e.target.src);
            }
        }, true);
        window.addEventListener('unhandledrejection', function (e) {
            keep('unhandled rejection: ' + (e && e.reason ? e.reason : '?'));
        });
        var realError = console.error;
        console.error = function () {
            try { keep(Array.prototype.join.call(arguments, ' ')); } catch (e) {}
            return realError.apply(this, arguments);
        };
        if (typeof window.__awMarkNative === 'function') {
            window.__awMarkNative(console.error);
        }
    } catch (e) {}

    /* Replaced at install time. False means watch only; see the note by the
       poller below for why that is the default. */
    var TRACE = __AW_TRACE__;

    var record = {
        installed: true,
        trace: TRACE,
        apiSeenAt: null,
        /* Has the app asked for a widget at all? Until this is true there is
           nothing to wait for, whatever the DOM looks like. */
        rendered: false,
        widgetId: null,
        sitekey: null,
        /* The options the app rendered with -- `appearance`, `action`, and
           whether it asked for the invisible/execute flavour. Worth having:
           an interaction-only widget that never draws is normal, and an
           always-visible one that never draws is not. */
        options: null,
        /* Filled by Turnstile's own callbacks. */
        token: null,
        tokenAt: null,
        errorCode: null,
        errorAt: null,
        expired: false,
        timedOut: false,
        /* Everything that happened, in order, for the failure dump. */
        events: []
    };
    window.__awTurnstile = record;

    var note = function (kind, detail) {
        try {
            record.events.push({
                kind: kind,
                detail: detail === undefined ? null : String(detail).slice(0, 200),
                at: Date.now()
            });
            if (record.events.length > 60) { record.events.shift(); }
        } catch (e) {}
    };

    /* Tee a callback the app supplied: call ours, then theirs, and never let
       ours break theirs. The app's own handler has to run untouched or the
       form stops working -- this is an observer, not an interceptor. */
    var tee = function (original, mine) {
        return function () {
            try { mine.apply(null, arguments); } catch (e) {}
            if (typeof original === 'function') {
                return original.apply(this, arguments);
            }
        };
    };

    var wrapRender = function (turnstile) {
        if (!turnstile || turnstile.__awWrapped) { return; }
        var realRender = turnstile.render;
        if (typeof realRender !== 'function') { return; }

        turnstile.render = function (container, options) {
            options = options || {};
            try {
                record.rendered = true;
                record.sitekey = options.sitekey || null;
                record.options = {
                    appearance: options.appearance || null,
                    execution: options.execution || null,
                    action: options.action || null,
                    size: options.size || null,
                    theme: options.theme || null
                };
                note('render', options.sitekey);

                options.callback = tee(options.callback, function (token) {
                    record.token = token || null;
                    record.tokenAt = Date.now();
                    record.errorCode = null;
                    record.expired = false;
                    note('token', token ? ('len=' + String(token).length) : 'empty');
                });
                /* The one that finally names the failure. Turnstile passes a
                   numeric code here -- 600010 and friends -- and until now
                   nothing in this project was listening for it. */
                options['error-callback'] = tee(options['error-callback'], function (code) {
                    record.errorCode = code === undefined ? 'unknown' : String(code);
                    record.errorAt = Date.now();
                    note('error', code);
                });
                options['expired-callback'] = tee(options['expired-callback'], function () {
                    record.expired = true;
                    record.token = null;
                    note('expired');
                });
                options['timeout-callback'] = tee(options['timeout-callback'], function () {
                    record.timedOut = true;
                    note('timeout');
                });
            } catch (e) {
                note('wrap-failed', e && e.message);
            }

            var id = realRender.call(this, container, options);
            try {
                record.widgetId = id === undefined ? null : id;
            } catch (e) {}
            return id;
        };

        /* The wrapper must not be visible to a `toString()` probe. The
           stealth layer registers the same way for its own patches; if it is
           not installed on this backend the mark is simply a no-op. */
        try {
            if (typeof window.__awMarkNative === 'function') {
                window.__awMarkNative(turnstile.render);
            }
        } catch (e) {}

        try {
            Object.defineProperty(turnstile, '__awWrapped', {
                value: true, enumerable: false, configurable: true
            });
        } catch (e) { turnstile.__awWrapped = true; }

        note('installed');
    };

    /* Watch for the API arriving, without touching the property it arrives
       on.

       This used to install an accessor pair on `window.turnstile` so the
       moment of assignment could be caught. That is also, exactly, what a
       script hooking Turnstile looks like -- and Cloudflare's loader is
       hardened against being hooked. Measured on this form: the script
       loaded (`onload` fired) and the host was reachable, and
       `window.turnstile` was still undefined afterwards, which is what a
       loader that has decided not to initialise looks like. Watching a
       property must not change whether it gets set.

       Polling reads. It never defines, redefines or intercepts anything, so
       there is nothing for the loader to object to. It costs a timer. */
    try {
        var started = Date.now();
        var poll = setInterval(function () {
            try {
                if (window.turnstile) {
                    if (!record.apiSeenAt) {
                        record.apiSeenAt = Date.now();
                        note('api-loaded');
                    }
                    if (TRACE) { wrapRender(window.turnstile); }
                    clearInterval(poll);
                    return;
                }
                /* Two minutes is longer than any screen waits. */
                if (Date.now() - started > 120000) { clearInterval(poll); }
            } catch (e) {
                clearInterval(poll);
            }
        }, 100);
    } catch (e) {}

    /* The intrusive half, off unless --trace-turnstile asks for it. It buys
       the sitekey and Cloudflare's own error code, which are worth having
       while diagnosing and not worth risking on a run that needs to work. */
    if (TRACE) {
        try {
            if (window.turnstile) { wrapRender(window.turnstile); }
        } catch (e) {}
        try {
            if (!window.turnstile) {
                var held;
                Object.defineProperty(window, 'turnstile', {
                    configurable: true,
                    enumerable: true,
                    get: function () { return held; },
                    set: function (value) {
                        held = value;
                        try { wrapRender(value); } catch (e) {}
                    }
                });
            }
        } catch (e) {}
    }
})();
"""


STATE_JS = r"""
const rec = window.__awTurnstile || null;

const visible = el => !!(el && (el.offsetParent || el.getClientRects().length));

/* A real widget container, never the <script> that loads the API. */
const holder = document.querySelector(
  'ngx-turnstile div[id^="cf-chl-widget"], .cf-turnstile, div[id^="cf-chl-widget"]'
);
const field = document.querySelector('input[name="cf-turnstile-response"]');
const frame = document.querySelector('iframe[src*="challenges.cloudflare.com"]');

/* The API's own answer, which is authoritative when the widget exists. */
let apiToken = null;
try {
  if (window.turnstile && typeof window.turnstile.getResponse === 'function') {
    apiToken = window.turnstile.getResponse(
      rec && rec.widgetId ? rec.widgetId : undefined
    ) || null;
  }
} catch (e) { /* throws when no widget has been rendered -- that is an answer too */ }

const token = (rec && rec.token) || apiToken || (field && field.value) || null;

return {
  /* Has the API script arrived? Useful context, never treated as "a widget
     is waiting for something". */
  apiLoaded: !!window.turnstile,
  observed: !!rec,
  /* The only honest definition of "there is a widget": the app rendered one,
     or one of its real DOM artefacts is on the page. */
  rendered: !!(rec && rec.rendered) || !!holder || !!frame,
  present: !!(rec && rec.rendered) || !!holder || !!frame || !!field,
  token: !!token,
  tokenLength: token ? String(token).length : 0,
  widgetShowing: visible(frame) || visible(holder),
  sitekey: rec ? rec.sitekey : null,
  options: rec ? rec.options : null,
  errorCode: rec ? rec.errorCode : null,
  expired: !!(rec && rec.expired),
  timedOut: !!(rec && rec.timedOut),
  events: rec ? rec.events.slice(-12) : []
};
"""


def _source(cfg=None) -> str:
    trace = bool(getattr(cfg, "trace_turnstile", False)) if cfg else False
    return OBSERVER_JS.replace("__AW_TRACE__", "true" if trace else "false")


def install(sb, cfg=None) -> bool:
    driver = getattr(sb, "driver", sb)
    if not hasattr(driver, "execute_cdp_cmd"):
        LOG.debug("No CDP on this driver; Turnstile will be read from the DOM only")
        return False
    if getattr(cfg, "trace_turnstile", False):
        LOG.warning(
            "Turnstile tracing is on. It installs an accessor on "
            "window.turnstile, which is what hooking the API looks like and "
            "which Cloudflare's loader can refuse to initialise against. Use "
            "it to diagnose, not for a run that needs to succeed."
        )
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument", {"source": _source(cfg)}
        )
        LOG.debug("Turnstile observer installed")
        return True
    except Exception as exc:
        LOG.debug("Could not install the Turnstile observer: %s", exc)
        return False


def install_now(sb, cfg=None) -> bool:
    try:
        sb.execute_script(_source(cfg))
        return True
    except Exception as exc:
        LOG.debug("Could not install the Turnstile observer in this document: %s", exc)
        return False


def state(sb) -> dict:
    try:
        return sb.execute_script(STATE_JS) or {}
    except Exception:
        return {}


def describe(status: dict) -> str:
    if not status:
        return "unreadable"
    if status.get("token"):
        return f"token held ({status.get('tokenLength')} chars)"
    if status.get("errorCode"):
        return f"failed with Cloudflare error {status['errorCode']}"
    if status.get("widgetShowing"):
        return "challenge on screen, waiting to be answered"
    if status.get("rendered"):
        return f"rendered (sitekey {status.get('sitekey') or '?'}), no token yet"
    if status.get("apiLoaded"):
        return "API loaded, no widget rendered"
    if (status.get("diagnosis") or {}).get("hostPresent"):
        return "the component is waiting and Cloudflare's script never loaded"
    return "not on this screen"


ERROR_MEANINGS = {
    "100": "the sitekey or its domain does not match this page",
    "102": "the sitekey is invalid for this hostname",
    "103": "the sitekey is invalid for this hostname",
    "104": "the sitekey is invalid for this hostname",
    "105": "the Turnstile API script is out of date",
    "106": "the sitekey is not allowed on this hostname",
    "110": "the sitekey is invalid, or the domain is not on its allowlist",
    "111": "the request came from an unexpected hostname",
    "200": "the widget was rendered but the page removed it before it finished",
    "300": "an internal Cloudflare error -- usually transient",
    "600": (
        "the challenge itself could not be completed in this browser. "
        "Cloudflare could not gather what it needs to score the visitor: the "
        "usual causes are storage being unavailable in a cross-origin frame "
        "(third-party cookies blocked, or storage partitioned), a system "
        "clock that is out of step, an extension interfering with the "
        "challenge frame, or an exit IP Cloudflare has already judged"
    ),
}


def explain_error(code) -> str:
    if not code:
        return ""
    text = str(code)
    for width in (3, 2):
        meaning = ERROR_MEANINGS.get(text[:width])
        if meaning:
            return f"Cloudflare Turnstile error {text}: {meaning}"
    return f"Cloudflare Turnstile error {text}"


_DIAGNOSE_JS = r"""
const tag = document.querySelector('script[src*="challenges.cloudflare.com/turnstile"]');
const host = document.querySelector('ngx-turnstile, .cf-turnstile');
return {
  apiLoaded: !!window.turnstile,
  scriptTag: tag ? tag.src : null,
  /* The component sets this before injecting the script. Present means the
     component is alive and waiting; absent means it never got that far. */
  onloadHook: typeof window.onloadTurnstileCallback,
  hostPresent: !!host,
  /* An empty host is the signature: the element exists, nothing is in it. */
  hostEmpty: host ? host.children.length === 0 : null,
  probe: window.__awTurnstileProbe || null,
  reload: window.__awTurnstileReload || null,
  /* Did the script's bytes actually arrive?
     A resource blocked before it runs still leaves a timing entry, and that
     entry says how much came over the wire. Nothing transferred, with the
     request over, is a request that was answered and then thrown away -- a
     COEP/CORP block looks exactly like that, and it does so whether or not
     an error event ever reaches a listener. This is the measurement the
     error collector kept missing. */
  scriptTiming: (function () {
    try {
      const hits = performance.getEntriesByType('resource').filter(
        e => e.name.indexOf('challenges.cloudflare.com/turnstile') !== -1
      );
      if (!hits.length) { return null; }
      const last = hits[hits.length - 1];
      return {
        name: last.name.slice(0, 160),
        transferred: last.transferSize,
        decoded: last.decodedBodySize,
        durationMs: Math.round(last.duration),
        count: hits.length
      };
    } catch (e) { return null; }
  })(),
  /* The page's own errors, which is where this failure actually names
     itself -- the COEP block, the duplicate-load complaint, the app's
     TypeError against an undefined API. */
  pageErrors: (window.__awPageErrors || []).slice(-15)
};
"""


_PROBE_JS = r"""
window.__awTurnstileProbe = 'pending';
try {
  fetch('https://challenges.cloudflare.com/turnstile/v0/api.js', {
    mode: 'no-cors', cache: 'no-store'
  }).then(function () {
    window.__awTurnstileProbe = 'reachable';
  }).catch(function (e) {
    window.__awTurnstileProbe = 'unreachable: ' + (e && e.message ? e.message : e);
  });
} catch (e) {
  window.__awTurnstileProbe = 'unreachable: ' + (e && e.message ? e.message : e);
}
return true;
"""


_RELOAD_JS = r"""
if (window.turnstile) { return 'already-loaded'; }
var existing = document.querySelector('script[src*="challenges.cloudflare.com/turnstile"]');
var src = (existing && existing.src) ? existing.src
  : 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=onloadTurnstileCallback';
window.__awTurnstileReload = 'pending';
try {
  var s = document.createElement('script');
  s.src = src;
  s.async = true;
  s.defer = true;
  s.onload = function () { window.__awTurnstileReload = 'loaded'; };
  s.onerror = function () { window.__awTurnstileReload = 'error'; };
  (document.head || document.documentElement).appendChild(s);
  return 'injected';
} catch (e) {
  window.__awTurnstileReload = 'error';
  return 'failed: ' + (e && e.message ? e.message : e);
}
"""


def diagnose(sb) -> dict:
    try:
        return sb.execute_script(_DIAGNOSE_JS) or {}
    except Exception:
        return {}


_ERROR_MEANINGS = (
    (
        "notsameoriginafterdefaultedtosameoriginbycoep",
        "the response was blocked by this page's Cross-Origin-Embedder-Policy "
        "because it arrived without a Cross-Origin-Resource-Policy header. "
        "Cloudflare normally sends that header, so something between here and "
        "them stripped it -- on this setup that means the proxy exit. Try a "
        "different --proxy-type (resident rather than mobile, or the other "
        "way round); it is not a browser setting.",
    ),
    (
        "already has been loaded",
        "Turnstile was asked to load twice and refused the second copy. The "
        "run no longer does this by itself; if it appears, the page loaded it "
        "twice on its own.",
    ),
    (
        "reading 'render'",
        "the app's onloadTurnstileCallback ran while window.turnstile was "
        "undefined, so its component threw instead of rendering the widget. "
        "This is the consequence of the script not initialising, not a "
        "separate fault.",
    ),
    (
        "err_blocked_by_client",
        "an extension blocked the request. Orbita should be started with "
        "--disable-extensions; check the profile is not overriding that.",
    ),
)


def _report_page_errors(sb, step_label: str, status: dict | None = None) -> None:
    status = status if status is not None else diagnose(sb)
    errors = status.get("pageErrors") or []
    if not errors:
        return

    LOG.error("%s: the page reported these errors:", step_label)
    explained = set()
    for entry in errors:
        text = str(entry.get("text") or "")
        LOG.error("    %s", text[:300])
        lowered = text.lower()
        for needle, meaning in _ERROR_MEANINGS:
            if needle in lowered and needle not in explained:
                explained.add(needle)
                LOG.error("  -> %s", meaning)


def ensure_api_loaded(sb, step_label: str, timeout: float = 20.0) -> bool:
    status = diagnose(sb)
    if status.get("apiLoaded"):
        return True

    try:
        sb.execute_script(_PROBE_JS)
        deadline = time.time() + 12.0
        while time.time() < deadline:
            probe = (diagnose(sb) or {}).get("probe")
            if probe and probe != "pending":
                break
            time.sleep(0.4)
    except Exception:
        pass
    status = diagnose(sb)
    probe = status.get("probe") or "not answered"

    if status.get("scriptTag"):
        LOG.error(
            "%s: the app's Turnstile script tag is in the page and "
            "window.turnstile was never defined (reachability=%s). The script "
            "was requested and did not initialise. Not re-requesting it: "
            "Turnstile refuses to load twice and the app's onload callback "
            "then throws on an undefined API, which is worse than the silence."
            " The causes worth checking, in order: the response being blocked "
            "before it runs -- a COEP/CORP block shows in the console as "
            "ERR_BLOCKED_BY_RESPONSE.NotSameOriginAfterDefaultedToSameOrigin"
            "ByCoep and usually means the proxy stripped Cloudflare's "
            "Cross-Origin-Resource-Policy header -- or the loader declining "
            "to initialise because something in the page looks like it is "
            "hooking the API (see --trace-turnstile).",
            step_label, probe,
        )
        timing = status.get("scriptTiming")
        if timing:
            LOG.error(
                "%s: the script request finished in %sms having transferred %s "
                "byte(s) (decoded %s). %s",
                step_label, timing.get("durationMs"), timing.get("transferred"),
                timing.get("decoded"),
                "Nothing arrived, so it was answered and discarded before it "
                "could run -- which is what a COEP/CORP block looks like."
                if not timing.get("decoded")
                else "The body did arrive, so it ran and chose not to "
                     "initialise rather than being blocked.",
            )
        else:
            LOG.error(
                "%s: no resource timing for the Turnstile script at all, so "
                "the request was never made.", step_label,
            )
        _report_page_errors(sb, step_label, status)
        return False

    LOG.warning(
        "%s: no Turnstile script was ever requested by the page. Requesting "
        "it so the form's own component can render its widget.", step_label,
    )
    try:
        outcome = sb.execute_script(_RELOAD_JS)
    except Exception as exc:
        LOG.debug("%s: could not request the Turnstile script: %s", step_label, exc)
        return False
    if outcome == "already-loaded":
        return True

    deadline = time.time() + timeout
    while time.time() < deadline:
        status = diagnose(sb)
        if status.get("apiLoaded"):
            LOG.info("%s: the Turnstile script loaded and defined its API", step_label)
            return True
        if status.get("reload") == "error":
            break
        time.sleep(0.4)

    status = diagnose(sb)
    LOG.error(
        "%s: Cloudflare's Turnstile script will not load (reload=%s, "
        "reachability=%s). Without it no widget can be created, the form's "
        "Continue stays disabled, and the application cannot be submitted "
        "however long it waits.",
        step_label, status.get("reload") or "?", status.get("probe") or "not answered",
    )
    return False


def reset(sb, step_label: str, status: dict | None = None) -> bool:
    status = status if status is not None else state(sb)

    if status.get("token"):
        LOG.debug("%s: not resetting Turnstile -- it is holding a token", step_label)
        return False
    if not status.get("rendered"):
        LOG.debug(
            "%s: nothing to reset -- the app has not rendered a Turnstile widget",
            step_label,
        )
        return False

    script = """
    try {
      if (!window.turnstile) { return 'no-api'; }
      const rec = window.__awTurnstile;
      const id = rec && rec.widgetId ? rec.widgetId : undefined;
      window.turnstile.reset(id);
      if (rec) { rec.errorCode = null; rec.expired = false; rec.timedOut = false; }
      return 'reset';
    } catch (e) {
      return 'error: ' + (e && e.message ? e.message : e);
    }
    """
    try:
        outcome = sb.execute_script(script)
    except Exception as exc:
        LOG.debug("%s: could not reset Turnstile: %s", step_label, exc)
        return False

    if outcome == "reset":
        LOG.info("%s: asked the Turnstile widget to try again", step_label)
        return True
    LOG.debug("%s: Turnstile reset did not apply (%s)", step_label, outcome)
    return False


def wait_for_token(sb, timeout: float, step_label: str, on_idle=None) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = state(sb)
        if status.get("token"):
            return status
        if status.get("errorCode"):
            return status
        if callable(on_idle):
            try:
                on_idle()
            except Exception:
                pass
        time.sleep(0.4)
    return state(sb)
