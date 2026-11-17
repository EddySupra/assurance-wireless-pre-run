import time
from pathlib import Path

from ..artifacts import capture
from ..config import RunConfig
from ..errors import PageMismatchError, ThrottledError
from ..human import human_click
from ..lead import Lead
from ..logs import LOG
from .step_03_check_availability import check_availability
from ..page_utils import (
    enter_enrollment_frame,
    first_visible,
    normalize_path,
    settle,
    verify_on_site,
)

STEP_NAME = "step_04_open_application"
APPLY_PATH = "/apply-now"
BOUNCE_PATH = "/lifeline-services/check-availability"

APPLY_BUTTON_SELECTORS = (
    'a.btn-primary[href="/apply-now"]',
    'a[href="/apply-now"]',
)


class _Bounced(Exception):
    pass


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

    try:
        _wait_for_apply_page(sb, cfg)
    except _Bounced:
        LOG.warning(
            "Step 4: Apply Now sent us back to the empty ZIP form -- filling the "
            "ZIP check again and trying once more"
        )
        check_availability(sb, cfg, lead, run_dir)
        selector = first_visible(sb, APPLY_BUTTON_SELECTORS)
        if selector is None:
            raise PageMismatchError(
                "Step 4: no visible Apply Now button on the state page after "
                "redoing the ZIP check"
            )
        human_click(sb, selector, cfg)
        try:
            _wait_for_apply_page(sb, cfg)
        except _Bounced as exc:
            raise ThrottledError(str(exc)) from exc
    settle(sb, cfg)
    verify_on_site(sb, "Step 4", expected_path=APPLY_PATH, min_body_chars=0)

    frame_url = enter_enrollment_frame(sb, cfg, "Step 4")
    _check_frame_carries_lead(frame_url, lead)

    LOG.info("Frame title: %s", sb.execute_script("return document.title"))
    inventory = capture(sb, run_dir, STEP_NAME, save=cfg.save_artifacts)

    sb.switch_to_default_content()
    return inventory


def _wait_for_apply_page(sb, cfg: RunConfig) -> None:
    deadline = time.time() + cfg.frame_timeout
    bounced_since = None

    while time.time() < deadline:
        path = normalize_path(sb.get_current_url())
        if path == APPLY_PATH:
            return
        if path == BOUNCE_PATH:
            bounced_since = bounced_since or time.time()
            if time.time() - bounced_since >= 2.0:
                raise _Bounced(
                    "Step 4: Apply Now sent the browser back to the empty ZIP form "
                    "instead of the application, even after redoing the ZIP check. "
                    "The site did not register this ZIP/email check."
                )
        else:
            bounced_since = None
        time.sleep(0.1)

    raise PageMismatchError(
        f"Step 4: URL never reached {APPLY_PATH} within {cfg.frame_timeout}s "
        f"(still on {sb.get_current_url()})"
    )


def _check_frame_carries_lead(frame_url: str, lead: Lead) -> None:
    if f"zip={lead.zip_code}" in frame_url:
        LOG.info("Application frame carries the lead's ZIP (%s)", lead.zip_code)
        return

    raise PageMismatchError(
        f"Step 4: the application frame URL does not carry ZIP {lead.zip_code} "
        f"for {lead.label}. The session may be holding a previous lead's ZIP "
        f"check. Frame URL: {frame_url}"
    )
