"""Step 2 -- click the header "Apply Now" button to enter the application.

Mirrors what the agents do by hand: the magenta `btn-primary` CTA in the site
header. Still no lead data used at this point.

/apply-now is a redirect -- it lands on the "Let's see if Lifeline service is
available in your area" page, which is where the ZIP + email entry happens in
step 3. Both paths are accepted so a direct /apply-now render would still pass.
"""

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

# The header CTA first -- that's the one the agents click. The plain href is a
# fallback in case the button's styling classes get reshuffled; the start page
# carries three links to /apply-now, and any of them lands the same place.
APPLY_BUTTON_SELECTORS = (
    'a.btn-primary[href="/apply-now"]',
    'a[href="/apply-now"]',
)


def click_apply_now(sb, cfg: RunConfig, lead, run_dir: Path, *, submit: bool = True) -> dict:
    """Click Apply Now and confirm we reached the application entry page.

    `lead` and `submit` are unused; the signature is uniform across steps.
    """
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
