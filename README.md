# Assurance Wireless Pre-Run

Automates the Assurance Wireless application using customer-provided lead data,
so field agents can process customers faster. Built page by page.

## Where the browser runs

`--backend gologin` (the default) is the one to use for real runs.

`--backend browserless` puts the browser on Browserless's hosted fleet, with
their stealth handling and residential exits, and needs `BROWSERLESS_TOKEN` in
`.env`. It works, but not for a whole lead: Browserless ends a session at the
plan's ceiling — 120s on the shared cloud, measured — and one lead needs
longer than that, since the eligibility lookup alone runs for minutes. The run
says so on startup and again if the browser is taken away mid-form. A
dedicated or self-hosted deployment raises the ceiling.

Browserless v2 dropped WebDriver (`/webdriver` answers 501), so this backend
attaches chromedriver to the remote browser through `aw_bot/cdp_bridge.py`,
which serves a local DevTools endpoint and forwards CDP to them. The step
modules do not know the difference.

## Looking like a browser somebody is using

Three layers, kept apart because they answer different questions.

`aw_bot/stealth.py` handles what the browser *is*. On GoLogin both of its tiers
stay off on purpose: Orbita is a normally launched browser with a coherent
profile identity, and layering a second fingerprint over the first creates
contradictions that are louder than any of the values being hidden.

`aw_bot/human.py` handles what the session *does* — pointer paths that curve,
keystroke gaps drawn from a per-field tempo rather than a flat range, and a
pointer that drifts during waits instead of freezing between fields. The reason
this is not decoration: a behavioural scorer reads the shape of a distribution,
and a uniform random gap has a rectangular one that no hand produces.

`--real-input` goes further and drives the machine's actual mouse and keyboard,
so the events carry real trust and real timing rather than being injected. It
is the strongest version of all of this and it is off by default, because it
takes over the desktop: it needs a visible window, one worker, and the machine
to itself for the length of the run.

`aw_bot/environment.py` checks that the story holds together and says so in the
log at startup — user agent against client hints, platform against
`navigator.platform`, language and timezone against a US benefits application,
window against screen. It changes nothing; it only reports.

## Turnstile, and what "(600)" means

The eligible-applicant screen is gated by Cloudflare Turnstile, rendered
explicitly and invisibly when Continue is pressed. There is no checkbox, no
`.cf-turnstile` container and no `cf-turnstile-response` input to read, which
is why `aw_bot/turnstile.py` watches the widget's own callbacks instead of the
DOM. It records the sitekey it was rendered with, the token it issued, and —
the useful one — the error code it failed with.

That code matters because Turnstile's failures are six digits beginning
`600***`, and this form reports every failure it has as `Unable to continue …
(600)`. The two are indistinguishable on screen, so a refused challenge used to
be reported as a rejected applicant, sending whoever read the log off to check
the lead's data. The run now names it, and fails in seconds rather than after
the ten-minute spinner the app shows before giving up.

A `600` failure is usually one of: storage unavailable in the cross-origin
frame, a machine clock out of step, an extension in the challenge frame, or an
exit IP already judged. The run checks the first two by itself. For the first,
`--allow-third-party-storage` keeps cookies and storage working in the nested
frame; turn it on when the frame storage check warns.
