"""Step 6 -- fill the PERSONAL INFO screen (wizard screen 1 of 5).

Per-field notes worth keeping:

* Middle Initial is deliberately left blank -- it isn't in the sheet and the
  form treats it as optional.
* Phone is optional too. A row with a malformed number arrives here blank
  (lead parsing warns and drops it) rather than putting a wrong callback
  number on the application.
* Email arrives prefilled from the frame URL, so it's verified rather than
  retyped.
* Date of birth is three dependent dropdowns: the day list is empty until a
  month and year are chosen, so the order month -> year -> day is required.
  Option values are matched numerically, which sidesteps dobMonth using
  zero-padded values ("07") while dobYear uses plain ones ("1957").
"""

import time
from pathlib import Path

from ..artifacts import capture
from ..config import RunConfig
from ..errors import PageMismatchError
from ..human import human_select, human_type
from ..lead import Lead
from ..logs import LOG
from ..page_utils import advance_screen, enter_enrollment_frame

STEP_NAME = "step_06_personal_info"

FIRST_NAME = "#firstName"
MIDDLE_INITIAL = "#middleInitial"
LAST_NAME = "#lastName"
PHONE = "#phoneNumber"
EMAIL = "#email"
SSN = "#ssn"
DOB_MONTH = "#dobMonth"
DOB_DAY = "#dobDay"
DOB_YEAR = "#dobYear"

# :not(.float-end) matters -- a modal's Dismiss button is also
# `button.order-button`, so the bare class can click the wrong thing once an
# error dialog is open.
CONTINUE_SELECTORS = (
    "button.order-button:not(.float-end)",
    'button:contains("Continue")',
)

def fill_personal_info(
    sb, cfg: RunConfig, lead: Lead, run_dir: Path, *, submit: bool = True
) -> dict:
    """Fill screen 1 and advance. With submit=False, stop before Continue."""
    LOG.info("Step 6: filling PERSONAL INFO for %s", lead.label)

    enter_enrollment_frame(sb, cfg, "Step 6")

    _type(sb, FIRST_NAME, lead.first_name, "first name", cfg)
    _type(sb, LAST_NAME, lead.last_name, "last name", cfg)
    LOG.info("Leaving middle initial blank (not in the sheet, optional)")

    if lead.phone:
        _type(sb, PHONE, lead.phone, "phone", cfg)
    else:
        LOG.warning("No phone number for this lead -- leaving the field blank")

    _verify_email(sb, lead, cfg)
    _type(sb, SSN, lead.ssn_last4, "SSN last 4", cfg, secret=True)
    _select_dob(sb, lead, cfg)

    filled = capture(sb, run_dir, f"{STEP_NAME}_filled", save=cfg.save_artifacts)

    if not submit:
        LOG.warning("Stopping before Continue -- PERSONAL INFO filled only")
        sb.switch_to_default_content()
        return filled

    _continue(sb, cfg)
    inventory = capture(sb, run_dir, STEP_NAME, save=cfg.save_artifacts)
    sb.switch_to_default_content()
    return inventory


def _type(sb, selector: str, value: str, label: str, cfg: RunConfig, secret: bool = False) -> None:
    """Type a value and read it back, so a field that silently rejected the
    input fails here instead of several screens later.
    """
    shown = "****" if secret else value

    human_type(sb, selector, value, cfg)

    actual = (sb.get_attribute(selector, "value") or "").strip()
    if actual != value:
        raise PageMismatchError(
            f"Step 6: typed {label} into {selector} but the field holds "
            f"{'a different value' if secret else repr(actual)}"
        )
    LOG.info("Entered %s: %s", label, shown)


def _verify_email(sb, lead: Lead, cfg: RunConfig) -> None:
    """The frame URL prefills this. Retype only if it's wrong or missing."""
    sb.wait_for_element_visible(EMAIL, timeout=cfg.page_timeout)
    current = (sb.get_attribute(EMAIL, "value") or "").strip().lower()

    if current == lead.email:
        LOG.info("Email already prefilled correctly: %s", lead.email)
        return

    LOG.warning("Email was %r, expected %r -- retyping", current, lead.email)
    _type(sb, EMAIL, lead.email, "email", cfg)


def _select_dob(sb, lead: Lead, cfg: RunConfig) -> None:
    """Set the three DOB dropdowns in the order the form requires."""
    month, day, year = lead.dob.split("/")

    _select_numeric(sb, DOB_MONTH, int(month), "DOB month", cfg)
    _select_numeric(sb, DOB_YEAR, int(year), "DOB year", cfg)

    # The day list is populated from the chosen month/year, so it only exists
    # now. February 29 is exactly why year has to be set before day.
    _wait_for_day_options(sb, cfg)
    _select_numeric(sb, DOB_DAY, int(day), "DOB day", cfg)


def _select_numeric(sb, selector: str, number: int, label: str, cfg: RunConfig) -> None:
    """Pick the option whose value (or failing that, its text) equals `number`.

    Matching on the number rather than an exact string keeps this working
    whether the site uses "07", "7", or "July (7)".
    """
    element_id = selector.lstrip("#")
    options = sb.execute_script(
        "const el = document.getElementById(arguments[0]);"
        "return el ? Array.from(el.options).map(o => [o.value, o.text.trim()]) : null;",
        element_id,
    )
    if not options:
        raise PageMismatchError(f"Step 6: dropdown {selector} not found")

    match = next(
        (value for value, text in options if _as_int(value) == number or _as_int(text) == number),
        None,
    )
    if match is None:
        raise PageMismatchError(
            f"Step 6: {label} {number} is not an option in {selector}. "
            f"Available: {[o[0] for o in options if o[0]][:15]}"
        )

    human_select(sb, selector, match, cfg)
    LOG.info("Selected %s: %s", label, match)


def _as_int(text: str) -> int | None:
    stripped = (text or "").strip()
    return int(stripped) if stripped.isdigit() else None


def _wait_for_day_options(sb, cfg: RunConfig) -> None:
    deadline = time.time() + cfg.page_timeout

    while time.time() < deadline:
        try:
            count = sb.execute_script(
                "const el = document.getElementById('dobDay');"
                "return el ? el.options.length : 0;"
            )
            if count and count > 1:
                return
        except Exception:
            pass
        time.sleep(0.25)

    raise PageMismatchError(
        "Step 6: the DOB day dropdown never populated after selecting month "
        "and year"
    )


def _continue(sb, cfg: RunConfig) -> None:
    advance_screen(sb, cfg, "Step 6", CONTINUE_SELECTORS)
