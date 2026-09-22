"""Step 9 -- "Who is the Benefit Eligible Applicant?", the first ELIGIBILITY screen.

Two choices: the person applying, or their child/dependent. The sheet holds one
adult per row together with that person's own DOB and SSN, so the answer is
always "I am the Eligible Applicant" -- `ApplicationConfig.eligible_applicant`
if that ever stops being true.

The choices are the same invisibly-styled radios as the earlier screens, which
is why the element inventory for this screen shows no inputs at all.
"""

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

# The group is called `flagBQP` -- benefit qualifying person -- which no
# readable hint would match, so the real work is done by answer_radio's
# fallback to the option's label text. The hints stay for when the site
# renames it to something more obvious.
APPLICANT_HINTS = ("bqp", "applicant", "eligible", "benefit")

# Seconds to wait for the eligibility lookup behind this screen's Continue.
#
# Was 240, sized when the busy ceiling above it was 900s. Both were built on
# the idea that this lookup takes minutes; nothing measured since has shown it
# coming back after one. A screen still spinning at 90s has not been slow, it
# has been refused, and waiting longer only delays the verdict.
ELIGIBILITY_TIMEOUT = 90


def choose_eligible_applicant(
    sb, cfg: RunConfig, lead: Lead, run_dir: Path, *, submit: bool = True
) -> dict:
    """Say who the benefit applicant is, then advance."""
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

    # This Continue is where the wizard leaves PERSONAL INFO behind and starts
    # actually checking the applicant, so it waits on a backend lookup rather
    # than a client-side render. Measured, it does not answer inside the normal
    # page timeout -- and answering slowly is not the same as not answering.
    advance_screen(sb, cfg, "Step 9", CONTINUE_SELECTORS, timeout=ELIGIBILITY_TIMEOUT)
    inventory = capture(sb, run_dir, STEP_NAME, save=cfg.save_artifacts)
    sb.switch_to_default_content()
    return inventory
