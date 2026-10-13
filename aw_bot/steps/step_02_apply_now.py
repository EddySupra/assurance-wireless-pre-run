from pathlib import Path

from ..artifacts import capture
from ..config import RunConfig
from ..errors import PageMismatchError
from ..human import human_click
from ..logs import LOG
from ..page_utils import first_visible, settle, verify_on_site, wait_for_path

STEP_NAME = "step_02_apply_now"

CHECK_AVAILABILITY_PATH = "/lifeline-services/check-availability"
LANDING_PATHS = (CHECK_AVAILABILITY_PATH, "/apply-now")

APPLY_BUTTON_SELECTORS = (
    'a.btn-primary[href="/apply-now"]',
    'a[href="/apply-now"]',
)


def click_apply_now(sb, cfg: RunConfig, lead, run_dir: Path, *, submit: bool = True) -> dict:
    LOG.info("Step 2: clicking the Apply Now button")

    selector = first_visible(sb, APPLY_BUTTON_SELECTORS)
    if selector is None:
        raise PageMismatchError(
            "Step 2: no visible Apply Now button found on the start page. "
            f"Tried: {', '.join(APPLY_BUTTON_SELECTORS)}"
        )

    LOG.info("Using selector %s", selector)
    human_click(sb, selector, cfg)

    landed = wait_for_path(sb, LANDING_PATHS, cfg.page_timeout, "Step 2")
    settle(sb, cfg)
    verify_on_site(sb, "Step 2", expected_path=LANDING_PATHS)

    if landed != CHECK_AVAILABILITY_PATH:
        LOG.warning("Expected a redirect to %s but stayed on %s", CHECK_AVAILABILITY_PATH, landed)

    LOG.info("Landed on: %s", sb.get_current_url())
    LOG.info("Page title: %s", sb.get_title())

    return capture(sb, run_dir, STEP_NAME, save=cfg.save_artifacts)
