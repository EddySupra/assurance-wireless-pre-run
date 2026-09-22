"""Step 1 -- open the Assurance Wireless start page and confirm we really
landed on it (not a bot wall, not a redirect we don't know about).

Nothing lead-specific happens here, so this step takes no lead data.
"""

from pathlib import Path

from ..artifacts import capture
from ..config import RunConfig
from ..logs import LOG
from ..page_utils import settle, verify_on_site

STEP_NAME = "step_01_start_page"


def open_start_page(sb, cfg: RunConfig, lead, run_dir: Path, *, submit: bool = True) -> dict:
    """Navigate to the start page. Returns the page element inventory.

    Raises BotBlockedError or PageMismatchError if the landing is not usable.

    `lead` and `submit` are unused here -- every step takes the same shape so
    the runner can drive them all the same way.
    """
    LOG.info("Step 1: opening %s", cfg.start_url)

    # uc_open_with_reconnect briefly detaches the driver during load, which is
    # what keeps UC mode from being fingerprinted. Plain sb.open() would undo
    # the whole point of running in UC mode.
    sb.uc_open_with_reconnect(cfg.start_url, reconnect_time=cfg.reconnect_time)

    settle(sb, cfg)
    verify_on_site(sb, "Step 1", expected_path="/")

    if "assurance" not in (sb.get_title() or "").lower():
        # Not fatal -- they may have changed the title -- but worth flagging.
        LOG.warning("Page title does not mention Assurance: %r", sb.get_title())

    LOG.info("Landed on: %s", sb.get_current_url())
    LOG.info("Page title: %s", sb.get_title())

    return capture(sb, run_dir, STEP_NAME, save=cfg.save_artifacts)
