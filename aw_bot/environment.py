"""What this browser tells the world about itself, and whether it adds up.

Nothing here changes the browser. It reads what the browser already reports and
says out loud where the story contradicts itself, because a contradiction is a
much louder signal than any single value. A profile claiming Chrome 151 in its
user agent while `userAgentData` says 118, or claiming Windows while
`navigator.platform` says MacIntel, or claiming a US benefit application from a
browser set to `Europe/Berlin`, is worse off than one with a plain, boring,
consistent identity -- and until now nothing in this project ever looked.

There is a second job, and on this site it is the more urgent one. Cloudflare
Turnstile is the gate on the eligible-applicant screen, it runs inside a
cross-origin iframe (Cloudflare's own, nested inside the enrollment app's,
nested inside assurancewireless.com), and it has prerequisites that have
nothing to do with how human the session looks:

    storage       A challenge that cannot read or write storage in its frame
                  cannot complete. Third-party cookies blocked, or storage
                  partitioned away from the embedder, and Turnstile fails with
                  a `600***` code however convincing the rest of the session is.

    the clock     Challenge payloads are time-bounded. A machine whose clock is
                  out by more than a minute or two fails them, and the failure
                  looks exactly like being blocked.

Both are cheap to check and neither was being checked. `(600)` is what this
form shows when it cannot continue, and `600***` is what Turnstile returns when
the challenge could not be completed -- so these are the first two things worth
ruling out before blaming an IP.
"""

import time

from .logs import LOG

# Read in one pass so the values are all from the same instant. Everything is
# wrapped: this runs on whatever page happens to be open at session start,
# which on a fresh profile is often `about:blank`, where half of these throw.
_IDENTITY_JS = r"""
const out = {};
const safe = (fn, fallback) => { try { return fn(); } catch (e) { return fallback; } };

out.userAgent   = safe(() => navigator.userAgent, null);
out.appVersion  = safe(() => navigator.appVersion, null);
out.platform    = safe(() => navigator.platform, null);
out.vendor      = safe(() => navigator.vendor, null);
out.language    = safe(() => navigator.language, null);
out.languages   = safe(() => (navigator.languages || []).slice(0, 6), []);
out.timezone    = safe(() => Intl.DateTimeFormat().resolvedOptions().timeZone, null);
out.tzOffsetMin = safe(() => new Date().getTimezoneOffset(), null);
out.cores       = safe(() => navigator.hardwareConcurrency, null);
out.memory      = safe(() => navigator.deviceMemory, null);
out.touch       = safe(() => navigator.maxTouchPoints, null);
out.webdriver   = safe(() => navigator.webdriver, null);
out.cookieOk    = safe(() => navigator.cookieEnabled, null);
out.pdfViewer   = safe(() => navigator.pdfViewerEnabled, null);
out.plugins     = safe(() => navigator.plugins.length, null);

out.screen = safe(() => ({
  w: screen.width, h: screen.height,
  availW: screen.availWidth, availH: screen.availHeight,
  depth: screen.colorDepth, dpr: window.devicePixelRatio
}), null);
out.window = safe(() => ({
  innerW: window.innerWidth, innerH: window.innerHeight,
  outerW: window.outerWidth, outerH: window.outerHeight
}), null);

/* User-Agent Client Hints: the half of the identity that a modern anti-bot
   layer actually reads, and the half most likely to disagree with the UA
   string because spoofing tools often rewrite one and forget the other. */
out.uaData = safe(() => {
  if (!navigator.userAgentData) { return null; }
  return {
    mobile: navigator.userAgentData.mobile,
    platform: navigator.userAgentData.platform,
    brands: (navigator.userAgentData.brands || []).map(
      b => ({ brand: b.brand, version: b.version })
    )
  };
}, null);

/* The automation artefacts, counted rather than described. Anything above
   zero on a profile that is supposed to look hand-driven is worth knowing. */
out.cdcKeys = safe(() => Object.keys(window).filter(
  k => k.indexOf('$cdc_') === 0 || k.indexOf('__webdriver') === 0 ||
       k.indexOf('__selenium') === 0 || k.indexOf('__driver') === 0
).length, null);

out.chrome = safe(() => !!window.chrome, null);
out.webgl = safe(() => {
  const c = document.createElement('canvas');
  const gl = c.getContext('webgl') || c.getContext('experimental-webgl');
  if (!gl) { return null; }
  const dbg = gl.getExtension('WEBGL_debug_renderer_info');
  return dbg ? {
    vendor: gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL),
    renderer: gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)
  } : null;
}, null);

out.now = Date.now();
return out;
"""


# Whether a challenge running in this document could actually do its job.
# Meant to be run *inside* the enrollment frame, where the answer differs from
# the top-level page -- which is the entire point.
_STORAGE_JS = r"""
const out = {framed: false, crossOrigin: null};
const safe = (fn, fallback) => { try { return fn(); } catch (e) { return fallback; } };

out.framed = safe(() => window.self !== window.top, false);
/* Reading the parent's origin throws when it is cross-origin, and that throw
   is the answer: a same-origin frame is not subject to third-party storage
   rules, a cross-origin one is. */
out.crossOrigin = safe(() => { void window.top.location.href; return false; }, true);

out.cookieEnabled = safe(() => navigator.cookieEnabled, null);

/* The real test, not the advertised one. navigator.cookieEnabled reports the
   global setting and happily says true in a frame where writes are dropped. */
out.cookieWrites = safe(() => {
  const probe = '__aw_probe_' + Date.now();
  document.cookie = probe + '=1; SameSite=None; Secure; path=/';
  const ok = document.cookie.indexOf(probe) !== -1;
  document.cookie = probe + '=; Max-Age=0; SameSite=None; Secure; path=/';
  return ok;
}, false);

out.localStorage = safe(() => {
  localStorage.setItem('__aw_probe', '1');
  localStorage.removeItem('__aw_probe');
  return true;
}, false);

out.sessionStorage = safe(() => {
  sessionStorage.setItem('__aw_probe', '1');
  sessionStorage.removeItem('__aw_probe');
  return true;
}, false);

/* Chrome's Storage Access API. `hasStorageAccess` resolving false in a
   cross-origin frame is exactly the state in which a Turnstile challenge
   cannot complete. Asynchronous, so the caller polls `out.storageAccess`. */
out.storageAccess = null;
safe(() => {
  if (document.hasStorageAccess) {
    document.hasStorageAccess().then(
      v => { window.__awStorageAccess = !!v; },
      () => { window.__awStorageAccess = null; }
    );
  }
});

return out;
"""


def _chrome_major(text: str) -> str:
    """The Chrome major version named in a UA string, or ''."""
    if not text:
        return ""
    marker = "Chrome/"
    at = text.find(marker)
    if at == -1:
        return ""
    return text[at + len(marker):].split(".")[0].strip()


def _brand_major(ua_data: dict) -> str:
    """The Chrome/Chromium major version in the client-hint brand list.

    Skips the GREASE entry -- the deliberately silly `Not=A?Brand` one -- which
    carries a meaningless version by design and would otherwise be read as a
    disagreement.
    """
    if not ua_data:
        return ""
    for brand in ua_data.get("brands") or []:
        name = (brand.get("brand") or "").lower()
        if "not" in name and "brand" in name:
            continue
        if "chrom" in name or "google chrome" in name:
            return str(brand.get("version") or "").split(".")[0].strip()
    return ""


def _platform_family(text: str) -> str:
    """Windows / macOS / Linux / Android / iOS, from whatever string is given."""
    low = (text or "").lower()
    if "windows" in low or "win32" in low or "win64" in low:
        return "Windows"
    if "mac" in low or "darwin" in low:
        return "macOS"
    if "android" in low:
        return "Android"
    if "iphone" in low or "ipad" in low or "ios" in low:
        return "iOS"
    if "linux" in low or "x11" in low:
        return "Linux"
    return ""


# Timezones that belong to the country a US benefits application should be
# coming from. Not exhaustive -- it only has to be good enough to catch a
# profile pointed at the wrong continent, which is the failure that matters.
_US_TIMEZONE_PREFIXES = (
    "America/", "US/", "Pacific/Honolulu", "Pacific/Pago_Pago", "Etc/GMT+",
)


def check(identity: dict, cfg=None) -> list[str]:
    """Everything about this identity that contradicts something else.

    Returns plain sentences, worst first. An empty list means the browser tells
    one consistent story -- which is all that is being asked of it.
    """
    problems: list[str] = []
    if not identity:
        return ["the browser reported nothing about itself"]

    ua = identity.get("userAgent") or ""
    ua_data = identity.get("uaData") or {}

    # -- the version told twice ---------------------------------------------
    ua_major = _chrome_major(ua)
    hint_major = _brand_major(ua_data)
    if ua_major and hint_major and ua_major != hint_major:
        problems.append(
            f"the user agent says Chrome {ua_major} but its client hints say "
            f"{hint_major}. Anything that reads both sees a browser lying to "
            f"one of them."
        )

    # -- the platform told three times --------------------------------------
    families = {
        "user agent": _platform_family(ua),
        "navigator.platform": _platform_family(identity.get("platform") or ""),
        "client hints": _platform_family((ua_data or {}).get("platform") or ""),
    }
    named = {where: fam for where, fam in families.items() if fam}
    if len(set(named.values())) > 1:
        detail = ", ".join(f"{where} says {fam}" for where, fam in named.items())
        problems.append(f"the operating system does not agree with itself: {detail}")

    # -- a desktop UA on a touch device, or the other way round -------------
    mobile_hint = (ua_data or {}).get("mobile")
    if mobile_hint is True and "Mobile" not in ua:
        problems.append(
            "client hints say this is a mobile browser but the user agent is a "
            "desktop one"
        )
    touch = identity.get("touch")
    if isinstance(touch, int) and touch > 0 and _platform_family(ua) in ("Windows", "macOS"):
        # Touch-screen laptops exist, so this is a note rather than a verdict.
        LOG.debug("Profile reports %d touch points on a desktop platform", touch)

    # -- language and place --------------------------------------------------
    languages = identity.get("languages") or []
    primary = (identity.get("language") or (languages[0] if languages else "") or "")
    if primary and not primary.lower().startswith("en"):
        problems.append(
            f"the browser's language is {primary!r}. This is a US federal "
            f"benefits application and the form is being filled in English."
        )
    if languages and primary and languages[0] != primary:
        problems.append(
            f"navigator.language is {primary!r} but navigator.languages starts "
            f"with {languages[0]!r}"
        )

    timezone = identity.get("timezone") or ""
    if timezone and not timezone.startswith(_US_TIMEZONE_PREFIXES):
        problems.append(
            f"the browser's timezone is {timezone!r}, which is not in the "
            f"United States. The applicant's address is, and the exit IP is "
            f"meant to be."
        )

    # -- automation artefacts ------------------------------------------------
    if identity.get("webdriver") is True:
        problems.append(
            "navigator.webdriver is true -- this browser is announcing that it "
            "is being driven"
        )
    if identity.get("cdcKeys"):
        problems.append(
            f"{identity['cdcKeys']} ChromeDriver global(s) are exposed on "
            f"window; any page can read them"
        )
    if identity.get("chrome") is False:
        problems.append("window.chrome is missing, which no real desktop Chrome does")

    # -- geometry ------------------------------------------------------------
    screen = identity.get("screen") or {}
    window_box = identity.get("window") or {}
    if screen.get("w") and window_box.get("outerW"):
        if window_box["outerW"] > screen["w"] or window_box.get("outerH", 0) > screen.get("h", 0):
            problems.append(
                f"the window ({window_box['outerW']}x{window_box.get('outerH')}) is "
                f"larger than the screen it claims to be on "
                f"({screen['w']}x{screen.get('h')})"
            )
    if window_box.get("outerW") == 0 or window_box.get("outerH") == 0:
        problems.append(
            "the window reports zero outer dimensions, which is what a headless "
            "browser does and what a window on a screen never does"
        )

    if identity.get("cookieOk") is False:
        problems.append(
            "cookies are disabled in this browser. The enrollment app keeps its "
            "session in one, and Turnstile needs storage of its own."
        )

    return problems


def audit(sb, cfg=None, worker_id: int = 1) -> dict:
    """Read the identity, say what is wrong with it, and hand it back.

    Never raises and never blocks the run: a contradiction is worth a warning
    in the log, not a refusal to start. The caller gets the raw reading so it
    can be written into the failure dump alongside everything else.
    """
    try:
        identity = sb.execute_script(_IDENTITY_JS) or {}
    except Exception as exc:
        LOG.debug("[w%d] Could not read the browser's identity: %s", worker_id, exc)
        return {}

    ua = identity.get("userAgent") or "?"
    LOG.info("[w%d] Browser identity: %s", worker_id, ua)
    LOG.info(
        "[w%d] %s | %s | %s | %s core(s) | screen %sx%s",
        worker_id,
        (identity.get("uaData") or {}).get("platform") or identity.get("platform") or "?",
        identity.get("timezone") or "?",
        ",".join(identity.get("languages") or []) or identity.get("language") or "?",
        identity.get("cores") or "?",
        (identity.get("screen") or {}).get("w") or "?",
        (identity.get("screen") or {}).get("h") or "?",
    )
    webgl = identity.get("webgl") or {}
    if webgl:
        LOG.debug("[w%d] GPU: %s / %s", worker_id, webgl.get("vendor"), webgl.get("renderer"))

    # The one contradiction the page cannot show you.
    #
    # Everything in `check` compares the browser's self-reports against each
    # other, so a profile whose user agent and client hints were rewritten
    # together stays perfectly consistent -- and still lies, because the
    # binary actually running is a different Chrome. That difference shows up
    # in TLS and HTTP/2 fingerprints, in engine behaviour, in everything the
    # UA cannot control. The driver knows the real version; ask it.
    try:
        caps = getattr(getattr(sb, "driver", sb), "capabilities", {}) or {}
        real = str(caps.get("browserVersion") or caps.get("version") or "")
        claimed = _chrome_major(ua)
        if real and claimed and real.split(".")[0] != claimed:
            LOG.warning(
                "[w%d] Fingerprint contradiction: the profile's user agent "
                "says Chrome %s but the browser actually running is %s. "
                "Anything comparing the two -- or comparing either against "
                "the TLS handshake -- sees a browser misrepresenting itself.",
                worker_id, claimed, real,
            )
    except Exception as exc:
        LOG.debug("[w%d] Could not compare the UA to the binary: %s", worker_id, exc)

    for problem in check(identity, cfg):
        LOG.warning("[w%d] Fingerprint contradiction: %s", worker_id, problem)

    skew = clock_skew(identity)
    if skew is not None and abs(skew) > 30:
        LOG.warning(
            "[w%d] This machine's clock is %.0fs off real time. Cloudflare "
            "Turnstile signs its challenges with a timestamp and rejects the "
            "ones that do not line up, which presents as a challenge that "
            "never completes rather than as a clock problem.",
            worker_id, skew,
        )

    return identity


def clock_skew(identity: dict | None = None, timeout: float = 4.0) -> float | None:
    """Seconds this machine's clock is ahead of real time, or None if unknown.

    Asked of an HTTP `Date` header rather than of NTP: it needs no extra
    dependency, and one HEAD request to a major CDN is indistinguishable from
    any other traffic. Best-effort by design -- an offline machine gets None
    and the caller says nothing.
    """
    try:
        import requests

        before = time.time()
        response = requests.head("https://www.cloudflare.com/cdn-cgi/trace", timeout=timeout)
        after = time.time()
        served = response.headers.get("Date")
        if not served:
            return None

        from email.utils import parsedate_to_datetime

        remote = parsedate_to_datetime(served).timestamp()
        # Compare against the midpoint of the request, so the round trip is not
        # counted as skew.
        return (before + after) / 2 - remote
    except Exception as exc:
        LOG.debug("Could not check the clock: %s", exc)
        return None


def storage_report(sb, label: str = "") -> dict:
    """Whether a challenge in *this* document could read and write storage.

    Call it from inside the enrollment frame. The answer at the top level is
    not the answer here, and here is where Turnstile runs.
    """
    try:
        report = sb.execute_script(_STORAGE_JS) or {}
    except Exception as exc:
        LOG.debug("%s: could not check frame storage: %s", label, exc)
        return {}

    # The Storage Access API answer arrives a tick later.
    if report.get("crossOrigin"):
        try:
            time.sleep(0.15)
            report["storageAccess"] = sb.execute_script(
                "return window.__awStorageAccess === undefined "
                "? null : window.__awStorageAccess;"
            )
        except Exception:
            pass

    if not report.get("framed"):
        return report

    blocked = []
    if report.get("cookieWrites") is False:
        blocked.append("cookies")
    if report.get("localStorage") is False:
        blocked.append("localStorage")
    if report.get("sessionStorage") is False:
        blocked.append("sessionStorage")

    if blocked:
        LOG.warning(
            "%s: this frame cannot write %s. It is a cross-origin frame, so "
            "that is third-party storage being blocked or partitioned -- and a "
            "Cloudflare Turnstile challenge running in here cannot complete "
            "without it. This is the most common cause of a `600` failure that "
            "looks like a bot block but is really a browser setting.",
            label or "frame", " or ".join(blocked),
        )
    else:
        LOG.debug(
            "%s: frame storage is writable (cross-origin=%s, storage access=%s)",
            label or "frame", report.get("crossOrigin"), report.get("storageAccess"),
        )

    return report
