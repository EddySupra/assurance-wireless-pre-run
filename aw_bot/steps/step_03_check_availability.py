"""Step 3 -- enter the lead's ZIP and email, then submit the availability check.

First step that uses customer data. Only two of the lead's fields are needed
here; the rest go in on the application pages after this.

Submitting sends us to a per-state page chosen from the ZIP, which doubles as
a check that the row's ZIP and State columns agree.
"""

from pathlib import Path

from ..artifacts import capture
from ..config import RunConfig
from ..errors import PageMismatchError
from ..human import human_click, human_type
from ..lead import STATE_ABBREV_TO_NAME, Lead
from ..logs import LOG
from ..page_utils import body_text, first_visible, normalize_path, settle, verify_on_site

STEP_NAME = "step_03_check_availability"

# Where a successful ZIP check lands: a per-state page whose slug starts with
# the state name, e.g. .../states/california-lifeline-free-government-phone-service
STATE_PAGE_PREFIX = "/lifeline-services/states/"

ZIP_SELECTOR = 'input[name="zipInput"]'
EMAIL_SELECTOR = 'input[name="emailInput"]'

# The onclick handler is the most stable identifier on this button -- it's the
# function that actually submits, so it outlives restyling and copy changes.
# Text next, then the styling class. Deliberately NOT using fdprocessedid: a
# form-filler extension injects that at runtime and it changes every load.
SUBMIT_SELECTORS = (
    'button[onclick*="submitOE"]',
    'button:contains("Check Lifeline Availability")',
    "button.btn-info",
)

# Rough read on the outcome so the log says something useful either way.
NEGATIVE_HINTS = (
    "not available",
    "isn't available",
    "is not currently available",
    "we do not offer",
    "does not offer",
    "sorry",
)
POSITIVE_HINTS = (
    "available in your area",
    "you may qualify",
    "good news",
    "continue",
    "eligible",
)


def check_availability(
    sb, cfg: RunConfig, lead: Lead, run_dir: Path, *, submit: bool = True
) -> dict:
    """Fill ZIP + email and submit. With submit=False, stop before submitting."""
    LOG.info("Step 3: availability check for %s", lead.label)

    _fill(sb, ZIP_SELECTOR, lead.zip_code, "ZIP", cfg)
    _fill(sb, EMAIL_SELECTOR, lead.email, "email", cfg)

    if not submit:
        LOG.warning("Stopping before submit -- fields filled only")
        return capture(sb, run_dir, f"{STEP_NAME}_filled", save=cfg.save_artifacts)

    selector = first_visible(sb, SUBMIT_SELECTORS)
    if selector is None:
        raise PageMismatchError(
            "Step 3: no visible submit button found. "
            f"Tried: {', '.join(SUBMIT_SELECTORS)}"
        )

    before = normalize_path(sb.get_current_url())
    LOG.info("Submitting via %s", selector)
    human_click(sb, selector, cfg)

    _await_response(sb, before, cfg)
    settle(sb, cfg)
    verify_on_site(sb, "Step 3")

    LOG.info("Landed on: %s", sb.get_current_url())
    LOG.info("Page title: %s", sb.get_title())
    _verify_state_page(sb, lead)
    _report_outcome(sb)

    return capture(sb, run_dir, STEP_NAME, save=cfg.save_artifacts)


def _fill(sb, selector: str, value: str, label: str, cfg: RunConfig) -> None:
    """Type a value and read it back, so a silently-rejected entry (input
    masks, maxlength, a field that wasn't really ready) fails here rather
    than three pages later.
    """
    human_type(sb, selector, value, cfg)

    actual = sb.get_attribute(selector, "value") or ""
    if actual.strip() != value:
        raise PageMismatchError(
            f"Step 3: typed {label} {value!r} but the field holds {actual.strip()!r}"
        )
    LOG.info("Entered %s: %s", label, value)


def _await_response(sb, before_path: str, cfg: RunConfig) -> None:
    """Give the submit a chance to navigate. It may instead answer in place,
    so a URL that never changes is not treated as a failure.
    """
    try:
        sb.wait_for_ready_state_complete(timeout=cfg.page_timeout)
    except Exception:
        pass

    for _ in range(40):  # ~10s
        if normalize_path(sb.get_current_url()) != before_path:
            LOG.info("Navigated to a new page after submit")
            return
        sb.sleep(0.25)

    LOG.info("URL unchanged after submit -- result appears to render in place")


def _verify_state_page(sb, lead: Lead) -> None:
    """The ZIP decides which state page we get, so the landing URL is a free
    cross-check that the sheet's ZIP and State columns agree.

    A mismatch fails the lead: an application whose ZIP and state disagree
    gets rejected downstream anyway, and it's cheaper to catch it here.
    """
    path = normalize_path(sb.get_current_url())

    if not path.startswith(STATE_PAGE_PREFIX):
        LOG.warning(
            "Expected a %s... page after the ZIP check but landed on %s -- "
            "check the screenshot",
            STATE_PAGE_PREFIX,
            path,
        )
        return

    slug = path[len(STATE_PAGE_PREFIX) :]
    expected = STATE_ABBREV_TO_NAME.get(lead.state, "").replace(" ", "-")

    if expected and not slug.startswith(expected):
        raise PageMismatchError(
            f"Step 3: ZIP {lead.zip_code} sent us to the {slug.split('-')[0]!r} "
            f"state page, but the sheet says state {lead.state!r}. The ZIP and "
            f"State columns for this row disagree."
        )

    LOG.info("State page matches the lead's state (%s)", lead.state)


def _report_outcome(sb) -> None:
    text = body_text(sb).lower()
    negative = [h for h in NEGATIVE_HINTS if h in text]
    positive = [h for h in POSITIVE_HINTS if h in text]

    if negative and not positive:
        LOG.warning("Page reads like a rejection (matched %s)", negative)
    elif positive:
        LOG.info("Page reads like it accepted the ZIP (matched %s)", positive)
    else:
        LOG.warning("Could not tell the outcome from the page text -- check the screenshot")
