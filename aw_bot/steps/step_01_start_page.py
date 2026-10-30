import time
from pathlib import Path

from ..artifacts import capture
from ..config import RunConfig
from ..logs import LOG
from ..page_utils import body_text, settle, verify_on_site

STEP_NAME = "step_01_start_page"


def open_start_page(sb, cfg: RunConfig, lead, run_dir: Path, *, submit: bool = True) -> dict:
    LOG.info("Step 1: opening %s", cfg.start_url)

    sb.uc_open_with_reconnect(cfg.start_url, reconnect_time=cfg.reconnect_time)

    settle(sb, cfg)
    if len(body_text(sb).strip()) < 50:
        LOG.warning("Step 1: the start page is still blank -- waiting for a stalled script to time out")
        deadline = time.time() + 20
        while time.time() < deadline and len(body_text(sb).strip()) < 50:
            time.sleep(0.5)
    verify_on_site(sb, "Step 1", expected_path="/")

    if "assurance" not in (sb.get_title() or "").lower():
        LOG.warning("Page title does not mention Assurance: %r", sb.get_title())

    LOG.info("Landed on: %s", sb.get_current_url())
    LOG.info("Page title: %s", sb.get_title())

    return capture(sb, run_dir, STEP_NAME, save=cfg.save_artifacts)
