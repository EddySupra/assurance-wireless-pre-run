import os
import secrets
import sys
import threading
import time
from pathlib import Path

import requests

import run
from aw_bot import config as _config  # noqa: F401  (loads .env)
from aw_bot import gologin_backend
from aw_bot.logs import LOG

SESSION_MINUTES = 30
IP_ECHO = "https://api.ipify.org"
REUSE_COOLDOWN_SECONDS = 3600
MAX_SESSIONS_PER_PROFILE = 8
LEDGER = Path(__file__).resolve().parent / ".proxy_ips.txt"
_ledger_lock = threading.Lock()


def _settings() -> dict:
    values = {
        key: (os.environ.get(f"EVOMI_{key}") or "").strip()
        for key in ("HOST", "PORT", "USER", "PASS", "PROTOCOL")
    }
    missing = [k for k in ("HOST", "PORT", "USER", "PASS") if not values[k]]
    if missing:
        sys.exit("Fill in " + ", ".join(f"EVOMI_{k}" for k in missing) + " in .env first.")
    values["PROTOCOL"] = (values["PROTOCOL"] or "http").lower()
    return values


def _session_password(base: str) -> tuple[str, str]:
    session = secrets.token_hex(5)
    return f"{base}_session-{session}_lifetime-{SESSION_MINUTES}", session


def _proxy_url(cfg: dict, password: str) -> str:
    scheme = "socks5h" if cfg["PROTOCOL"] == "socks5" else "http"
    return f"{scheme}://{cfg['USER']}:{password}@{cfg['HOST']}:{cfg['PORT']}"


def _exit_ip(cfg: dict, password: str) -> str:
    url = _proxy_url(cfg, password)
    return requests.get(
        IP_ECHO, proxies={"http": url, "https": url}, timeout=20
    ).text.strip()


def _claim_ip(ip: str) -> bool:
    now = time.time()
    with _ledger_lock:
        recent = {}
        try:
            for line in LEDGER.read_text(encoding="utf-8").splitlines():
                seen_ip, _, stamp = line.partition(" ")
                if stamp and now - float(stamp) < REUSE_COOLDOWN_SECONDS:
                    recent[seen_ip] = float(stamp)
        except (OSError, ValueError):
            pass
        if ip in recent:
            return False
        recent[ip] = now
        LEDGER.write_text(
            "".join(f"{k} {v}\n" for k, v in recent.items()), encoding="utf-8"
        )
        return True


def _fresh_session(cfg: dict, worker_id: int) -> tuple[str, str, str]:
    last_error = "no session tried"
    for _ in range(MAX_SESSIONS_PER_PROFILE):
        password, session = _session_password(cfg["PASS"])
        try:
            ip = _exit_ip(cfg, password)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:100]}"
            continue
        if _claim_ip(ip):
            return password, session, ip
        LOG.info("[w%d] Evomi gave %s, used within the last hour -- new session", worker_id, ip)
        last_error = f"{ip} was used within the last hour"
    raise RuntimeError(
        f"No unused Evomi IP after {MAX_SESSIONS_PER_PROFILE} sessions ({last_error})"
    )


def attach_evomi_proxy(gl, profile_id: str, worker_id: int) -> None:
    cfg = _settings()
    password, session, ip = _fresh_session(cfg, worker_id)
    gl.update({
        "id": profile_id,
        "proxy": {
            "mode": cfg["PROTOCOL"],
            "host": cfg["HOST"],
            "port": int(cfg["PORT"]),
            "username": cfg["USER"],
            "password": password,
        },
    })
    LOG.info("[w%d] Attached an Evomi proxy: %s (session %s)", worker_id, ip, session)


def check_proxy(count: int = 4) -> int:
    cfg = _settings()
    seen = []
    for _ in range(count):
        password, session = _session_password(cfg["PASS"])
        scheme = "socks5h" if cfg["PROTOCOL"] == "socks5" else "http"
        url = f"{scheme}://{cfg['USER']}:{password}@{cfg['HOST']}:{cfg['PORT']}"
        try:
            ip = requests.get(
                IP_ECHO, proxies={"http": url, "https": url}, timeout=30
            ).text.strip()
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
    gologin_backend.proxy_provider = attach_evomi_proxy
    sys.exit(run.main())
