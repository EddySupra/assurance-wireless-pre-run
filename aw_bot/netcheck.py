"""Is a profile's network fit to run leads on?

The expensive way to discover a flagged proxy is to send a real applicant
through eight screens and watch the ninth hang. This asks the same question
with one page load and no lead data at all: open the public start page, see
what comes back, and report.

Three things decide the answer:

    exit IP     which address the profile actually goes out on, so a change of
                proxy can be confirmed rather than assumed
    verdict     whether the site served the page, an Akamai "Access Denied", a
                Cloudflare challenge, or the "botnet activity detected"
                judgement on the whole network
    sensor      whether Akamai's bot sensor (`/akam/...`) loads. Blocked, the
                site scores the session as a bot no matter how clean the IP is

Run it before a batch, and after changing proxies:

    python run.py --check-network
"""

from dataclasses import dataclass

from .config import START_URL, RunConfig
from .gologin_backend import fetch_profiles, gologin_session
from .logs import LOG
from .page_utils import challenge_present, network_reputation_block

# Asked from inside the page, so it goes through the profile's proxy rather
# than this machine's connection.
_EXIT_IP_JS = """
const done = arguments[arguments.length - 1];
fetch('https://api64.ipify.org?format=text')
  .then(r => r.text()).then(t => done(t.trim()))
  .catch(e => done('unknown'));
"""

# Akamai's sensor endpoint. A blocked request here is self-inflicted -- see
# GoLoginConfig.disable_extensions.
_SENSOR_JS = """
const done = arguments[arguments.length - 1];
fetch('/akam/13/76b1f76d')
  .then(r => done('ok ' + r.status))
  .catch(e => done('BLOCKED: ' + e.message));
"""


@dataclass
class NetworkReport:
    """What one profile's network looks like to the site."""

    profile_id: str
    name: str
    exit_ip: str = "?"
    verdict: str = "?"
    sensor: str = "?"

    @property
    def usable(self) -> bool:
        return self.verdict == "ok" and self.sensor.startswith("ok")

    def line(self) -> str:
        mark = "OK  " if self.usable else "BAD "
        return (
            f"  {mark} {self.name[:22]:24} {self.exit_ip:42} "
            f"{self.verdict:28} sensor={self.sensor}"
        )


def check_profile(cfg: RunConfig, profile_id: str, name: str) -> NetworkReport:
    """Load the start page once on this profile and report what came back."""
    report = NetworkReport(profile_id=profile_id, name=name)

    try:
        with gologin_session(cfg, profile_id, worker_id=1) as sb:
            sb.driver.set_script_timeout(60)
            sb.open(START_URL)

            try:
                report.exit_ip = sb.driver.execute_async_script(_EXIT_IP_JS)
            except Exception:
                report.exit_ip = "unknown"

            report.verdict = _verdict(sb)

            # Only meaningful once the site actually served us a page.
            if report.verdict == "ok":
                try:
                    report.sensor = sb.driver.execute_async_script(_SENSOR_JS)
                except Exception as exc:
                    report.sensor = f"error: {type(exc).__name__}"
            else:
                report.sensor = "n/a"
    except Exception as exc:
        report.verdict = f"could not start: {type(exc).__name__}"

    return report


def _verdict(sb) -> str:
    """What the site served: the page, a block, or a challenge."""
    reputation = network_reputation_block(sb)
    if reputation:
        return "BOTNET: network flagged"

    try:
        title = (sb.get_title() or "").lower()
    except Exception:
        title = ""

    if "access denied" in title:
        return "Akamai: access denied"
    if challenge_present(sb):
        return "Cloudflare challenge"
    if "assurance" in title:
        return "ok"
    return f"unexpected page: {title[:30]!r}"


def check_network(cfg: RunConfig, limit: int = 0) -> int:
    """Check every profile and print a table. Returns a process exit code."""
    profiles = [p for p in fetch_profiles(cfg.gologin.token) if p.get("id")]
    if cfg.gologin.profile_ids:
        wanted = set(cfg.gologin.profile_ids)
        profiles = [p for p in profiles if p["id"] in wanted]
    if limit:
        profiles = profiles[:limit]

    if not profiles:
        print("No profiles to check.")
        return 1

    print(f"Checking {len(profiles)} profile(s) against {START_URL}\n")
    reports = []
    for profile in profiles:
        LOG.info("Checking %s", profile.get("name", profile["id"]))
        report = check_profile(cfg, profile["id"], profile.get("name") or "<unnamed>")
        reports.append(report)
        print(report.line(), flush=True)

    usable = [r for r in reports if r.usable]
    print(f"\n{len(usable)} of {len(reports)} profile(s) can reach the site cleanly.")

    if not usable:
        print(
            "\nNone of these profiles is usable. If the verdict says the network\n"
            "is flagged, that is the exit IP's reputation and no setting in this\n"
            "repo changes it -- the profiles need proxies on a different range.\n"
            "Change them in the GoLogin app (profile -> Proxy) and re-run this."
        )
        return 1

    if len(usable) < len(reports):
        print(
            "\nRun with only the good ones:\n"
            "  python run.py --gologin-profile " + ",".join(r.profile_id for r in usable)
        )
    return 0
