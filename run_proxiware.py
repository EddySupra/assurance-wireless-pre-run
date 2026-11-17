import os
import secrets
import sys

import requests

import run
import run_evomi
from aw_bot import config as _config  # noqa: F401  (loads .env)
from aw_bot import environment, gologin_backend
from aw_bot.logs import LOG

MAX_SESSIONS_PER_PROFILE = 8
SESSION_TOKEN = "{session}"


def _settings() -> dict:
    values = {
        key: (os.environ.get(f"PROXIWARE_{key}") or "").strip()
        for key in ("HOST", "PORT", "USER", "PASS", "PROTOCOL")
    }
    missing = [k for k in ("HOST", "PORT", "USER", "PASS") if not values[k]]
    if missing:
        sys.exit("Fill in " + ", ".join(f"PROXIWARE_{k}" for k in missing) + " in .env first.")
    values["PROTOCOL"] = (values["PROTOCOL"] or "http").lower()
    if SESSION_TOKEN not in values["USER"] and SESSION_TOKEN not in values["PASS"]:
        LOG.warning(
            "Neither PROXIWARE_USER nor PROXIWARE_PASS contains %s, so every "
            "connection depends on the gateway's own rotation. Repeated IPs "
            "are still skipped, but you may burn several sessions per profile.",
            SESSION_TOKEN,
        )
    return values


def _credentials(cfg: dict) -> tuple[str, str, str]:
    session = secrets.token_hex(5)
    user = cfg["USER"].replace(SESSION_TOKEN, session)
    password = cfg["PASS"].replace(SESSION_TOKEN, session)
    return user, password, session


def _exit_ip(cfg: dict, user: str, password: str) -> str:
    return run_evomi._exit_ip({**cfg, "USER": user}, password)


def _fresh_session(cfg: dict, worker_id: int) -> tuple[str, str, str, str]:
    last_error = "no session tried"
    for _ in range(MAX_SESSIONS_PER_PROFILE):
        user, password, session = _credentials(cfg)
        try:
            ip = _exit_ip(cfg, user, password)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:100]}"
            continue
        if run_evomi._claim_ip(ip):
            return user, password, session, ip
        LOG.info("[w%d] Proxiware gave %s, used within the last hour -- new session", worker_id, ip)
        last_error = f"{ip} was used within the last hour"
    raise RuntimeError(
        f"No unused Proxiware IP after {MAX_SESSIONS_PER_PROFILE} sessions ({last_error})"
    )


def attach_proxiware_proxy(gl, profile_id: str, worker_id: int) -> None:
    cfg = _settings()
    user, password, session, ip = _fresh_session(cfg, worker_id)
    gl.update({
        "id": profile_id,
        "proxy": {
            "mode": cfg["PROTOCOL"],
            "host": cfg["HOST"],
            "port": int(cfg["PORT"]),
            "username": user,
            "password": password,
        },
    })
    LOG.info("[w%d] Attached a Proxiware proxy: %s (session %s)", worker_id, ip, session)
    environment.EXPECTED_BY_WORKER[worker_id] = {"ip": ip, **run_evomi._locate(ip)}


def check_proxy(count: int = 4) -> int:
    cfg = _settings()
    seen = []
    for _ in range(count):
        user, password, session = _credentials(cfg)
        try:
            ip = _exit_ip(cfg, user, password)
        except Exception as exc:
            print(f"session {session}: FAILED ({type(exc).__name__}: {str(exc)[:100]})")
            return 1
        print(f"session {session}: exit IP {ip}")
        seen.append(ip)
    distinct = len(set(seen))
    print(f"\n{distinct} distinct IP(s) from {count} new sessions.")
    if distinct < count:
        print("Some sessions share an IP; the session option may not be taking effect.")
        return 1
    print("Each new session got its own IP.")
    return 0


if __name__ == "__main__":
    if "--check-proxy" in sys.argv:
        sys.exit(check_proxy())
    _settings()
    environment.CHECK_WEBRTC = (os.environ.get("PROXIWARE_CHECK_WEBRTC") or "").strip() == "1"
    gologin_backend.proxy_provider = attach_proxiware_proxy
    sys.exit(run.main())
