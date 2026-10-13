from pathlib import Path

from ..artifacts import capture
from ..config import RunConfig
from ..errors import PageMismatchError
from ..human import human_click
from ..lead import Lead
from ..logs import LOG
from ..page_utils import (
    enter_enrollment_frame,
    first_visible,
    settle,
    verify_on_site,
    wait_for_path,
)

STEP_NAME = "step_04_open_application"
APPLY_PATH = "/apply-now"

APPLY_BUTTON_SELECTORS = (
    'a.btn-primary[href="/apply-now"]',
    'a[href="/apply-now"]',
)


def open_application(
    sb, cfg: RunConfig, lead: Lead, run_dir: Path, *, submit: bool = True
) -> dict:
    LOG.info("Step 4: opening the application from the state page")

    selector = first_visible(sb, APPLY_BUTTON_SELECTORS)
    if selector is None:
        raise PageMismatchError(
            "Step 4: no visible Apply Now button on the state page. "
            f"Tried: {', '.join(APPLY_BUTTON_SELECTORS)}"
        )

    LOG.info("Using selector %s", selector)
    human_click(sb, selector, cfg)

    wait_for_path(sb, APPLY_PATH, cfg.page_timeout, "Step 4")
    settle(sb, cfg)
    verify_on_site(sb, "Step 4", expected_path=APPLY_PATH, min_body_chars=0)

    frame_url = enter_enrollment_frame(sb, cfg, "Step 4")
    _check_frame_carries_lead(frame_url, lead)

    LOG.info("Frame title: %s", sb.execute_script("return document.title"))
    inventory = capture(sb, run_dir, STEP_NAME, save=cfg.save_artifacts)

    sb.switch_to_default_content()
    return inventory


def _check_frame_carries_lead(frame_url: str, lead: Lead) -> None:
    if f"zip={lead.zip_code}" in frame_url:
        LOG.info("Application frame carries the lead's ZIP (%s)", lead.zip_code)
        return

    raise PageMismatchError(
        f"Step 4: the application frame URL does not carry ZIP {lead.zip_code} "
        f"for {lead.label}. The session may be holding a previous lead's ZIP "
        f"check. Frame URL: {frame_url}"
    )
