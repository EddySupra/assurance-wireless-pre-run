from pathlib import Path

from ..artifacts import capture
from ..config import RunConfig
from ..errors import PageMismatchError
from ..human import human_select, human_type
from ..lead import Lead
from ..logs import LOG
from ..page_utils import (
    advance_screen,
    answer_radio,
    enter_enrollment_frame,
    read_radios,
)

STEP_NAME = "step_07_service_address"

STREET = "#serviceAddressStreet1"
UNIT = "#serviceAddressStreet2"
CITY = "#serviceAddressCity"
STATE = "#serviceAddressState"
ZIP = "#serviceAddressZip"

CONTINUE_SELECTORS = (
    "button.order-button",
    'button:contains("Continue")',
)

ANSWERS = (
    ("temporary address", ("temporary", "temp"), "No"),
    ("mailing same as home", ("mailing", "sameas"), "Yes"),
)

def fill_service_address(
    sb, cfg: RunConfig, lead: Lead, run_dir: Path, *, submit: bool = True
) -> dict:
    LOG.info("Step 7: filling the service address for %s", lead.label)

    enter_enrollment_frame(sb, cfg, "Step 7")
    _verify_screen(sb)

    _type_checked(sb, STREET, lead.street, "street", cfg)

    if lead.unit:
        _type_checked(sb, UNIT, lead.unit, "apartment/unit", cfg)
    else:
        LOG.warning(
            "No apartment/unit for this lead. If %s is a multi-unit address the "
            "application cannot be approved without it.", lead.street
        )

    _verify_prefilled(sb, CITY, lead.city, "city", cfg)
    _verify_prefilled(sb, ZIP, lead.zip_code, "ZIP", cfg)
    _set_state(sb, lead, cfg)

    radios = read_radios(sb)
    for label, hints, answer in ANSWERS:
        answer_radio(sb, radios, label, hints, answer, cfg)

    filled = capture(sb, run_dir, f"{STEP_NAME}_filled", save=cfg.save_artifacts)

    if not submit:
        LOG.warning("Stopping before Continue -- address filled only")
        sb.switch_to_default_content()
        return filled

    _continue(sb, cfg)
    inventory = capture(sb, run_dir, STEP_NAME, save=cfg.save_artifacts)
    sb.switch_to_default_content()
    return inventory


def _verify_screen(sb) -> None:
    try:
        sb.wait_for_element_visible(STREET, timeout=10)
    except Exception as exc:
        headings = []
        try:
            headings = sb.execute_script(
                "return Array.from(document.querySelectorAll('h1,h2,h3'))"
                ".map(e => e.innerText.trim()).filter(Boolean).slice(0, 6)"
            )
        except Exception:
            pass
        raise PageMismatchError(
            f"Step 7: expected the address screen but {STREET} is not there. "
            f"Headings: {headings}"
        ) from exc


def _type_checked(sb, selector: str, value: str, label: str, cfg: RunConfig) -> None:
    human_type(sb, selector, value, cfg)
    actual = (sb.get_attribute(selector, "value") or "").strip()
    if actual.upper() != value.strip().upper():
        raise PageMismatchError(
            f"Step 7: typed {label} into {selector} but the field holds {actual!r}"
        )
    LOG.info("Entered %s: %s", label, value)


def _verify_prefilled(sb, selector: str, expected: str, label: str, cfg: RunConfig) -> None:
    actual = (sb.get_attribute(selector, "value") or "").strip()
    if actual.upper() == expected.strip().upper():
        LOG.info("%s already prefilled correctly: %s", label.capitalize(), actual)
        return
    LOG.warning("%s was %r, expected %r -- retyping", label.capitalize(), actual, expected)
    _type_checked(sb, selector, expected, label, cfg)


def _set_state(sb, lead: Lead, cfg: RunConfig) -> None:
    state = lead.state.strip().upper()
    current = (sb.get_attribute(STATE, "value") or "").strip().upper()
    if current.endswith(state) and current:
        LOG.info("State already set to %s", current)
        return
    human_select(sb, STATE, state, cfg)
    LOG.info("Selected state: %s", state)


def _continue(sb, cfg: RunConfig) -> None:
    advance_screen(sb, cfg, "Step 7", CONTINUE_SELECTORS)
