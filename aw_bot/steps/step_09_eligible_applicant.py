from pathlib import Path

from ..artifacts import capture
from ..config import RunConfig
from ..errors import PageMismatchError
from ..lead import Lead
from ..logs import LOG
from ..page_utils import (
    advance_screen,
    answer_radio,
    enter_enrollment_frame,
    read_radios,
)

STEP_NAME = "step_09_eligible_applicant"

CONTINUE_SELECTORS = (
    "button.order-button:not(.float-end)",
    'button:contains("Continue")',
)

APPLICANT_HINTS = ("bqp", "applicant", "eligible", "benefit")

SETTLE_AFTER_CONTINUE = 30.0

ELIGIBILITY_TIMEOUT = 90


def choose_eligible_applicant(
    sb, cfg: RunConfig, lead: Lead, run_dir: Path, *, submit: bool = True
) -> dict:
    LOG.info("Step 9: choosing the benefit eligible applicant for %s", lead.label)

    enter_enrollment_frame(sb, cfg, "Step 9")

    radios = read_radios(sb)
    if not radios:
        raise PageMismatchError(
            "Step 9: expected the eligible-applicant choice but the screen has "
            "no radio buttons."
        )

    answer = cfg.application.eligible_applicant
    if not answer_radio(sb, radios, "eligible applicant", APPLICANT_HINTS, answer, cfg):
        raise PageMismatchError(
            f"Step 9: could not select {answer!r}. Options were: "
            f"{[r.get('label') for r in radios]}"
        )

    filled = capture(sb, run_dir, f"{STEP_NAME}_filled", save=cfg.save_artifacts)

    if not submit:
        LOG.warning("Stopping before Continue -- applicant chosen only")
        sb.switch_to_default_content()
        return filled

    advance_screen(
        sb, cfg, "Step 9", CONTINUE_SELECTORS,
        timeout=ELIGIBILITY_TIMEOUT,
        settle=SETTLE_AFTER_CONTINUE,
    )
    inventory = capture(sb, run_dir, STEP_NAME, save=cfg.save_artifacts)
    sb.switch_to_default_content()
    return inventory
