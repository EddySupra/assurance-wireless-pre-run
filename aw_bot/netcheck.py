from dataclasses import dataclass

from .config import START_URL, RunConfig
from .gologin_backend import fetch_profiles, gologin_session
from .logs import LOG
from .page_utils import challenge_present, network_reputation_block

_EXIT_IP_JS = """
const done = arguments[arguments.length - 1];
fetch('https://api64.ipify.org?format=text')
  .then(r => r.text()).then(t => done(t.trim()))
  .catch(e => done('unknown'));
"""

_SENSOR_JS = """
const done = arguments[arguments.length - 1];
fetch('/akam/13/76b1f76d')
  .then(r => done('ok ' + r.status))
  .catch(e => done('BLOCKED: ' + e.message));
"""


@dataclass
class NetworkReport:
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
