"""Step 8 -- contact preferences, account PIN and security questions.

The third and last PERSONAL INFO screen. Nothing here comes off the sheet: the
answers are the fixed ones in `cfg.application`, because this is a pre-run that
stops at the decision screen rather than completing an enrollment. See
`ApplicationConfig` for what that assumption costs if it ever changes.

The screen has three parts:

    preferences  Language, how to be contacted, print format -- invisible
                 radios, handled the same way as the address screen's
    account PIN  6-15 digits, entered twice. The form rejects anything
                 personal or guessable, which is why it is not derived from
                 the lead
    security     Three questions picked from one list, each with an answer.
                 The three have to be different from each other
"""

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
    validation_errors,
)

STEP_NAME = "step_08_contact_and_security"

PIN = "#customerPIN"
PIN_CONFIRM = "#customerPIN2"
QUESTIONS = ("#securityQuestion0", "#securityQuestion1", "#securityQuestion2")
ANSWERS = ("#secretAnswer0", "#secretAnswer1", "#secretAnswer2")

CONTINUE_SELECTORS = (
    "button.order-button:not(.float-end)",
    'button:contains("Continue")',
)

# Each preference radio group, matched on its group name. The wording of the
# options is the label text the site paints next to the hidden input.
PREFERENCES = (
    ("language", ("language", "lang")),
    ("contact method", ("contact", "reach", "bestway")),
    ("print preference", ("print", "communication", "format")),
)

# Read the security-question dropdowns' real options, so three different
# questions can be chosen without hard-coding wording the site may reword.
_OPTIONS_JS = """
const el = document.getElementById(arguments[0]);
if (!el) return null;
return Array.from(el.options)
    .map(o => [o.value, (o.text || '').trim()])
    .filter(o => o[0] && !/^-|select/i.test(o[1]));
"""


def fill_contact_and_security(
    sb, cfg: RunConfig, lead: Lead, run_dir: Path, *, submit: bool = True
) -> dict:
    """Fill the screen and advance. With submit=False, stop before Continue."""
    LOG.info("Step 8: contact preferences and account security for %s", lead.label)

    enter_enrollment_frame(sb, cfg, "Step 8")
    _verify_screen(sb)

    app = cfg.application
    radios = read_radios(sb)
    for (label, hints), answer in zip(
        PREFERENCES, (app.language, app.contact_method, app.print_preference)
    ):
        answer_radio(sb, radios, label, hints, answer, cfg)

    _set_pin(sb, app.account_pin, cfg)
    _set_security_questions(sb, app.security_answers, cfg)

    filled = capture(sb, run_dir, f"{STEP_NAME}_filled", save=cfg.save_artifacts)

    if not submit:
        LOG.warning("Stopping before Continue -- preferences and security filled only")
        sb.switch_to_default_content()
        return filled

    advance_screen(sb, cfg, "Step 8", CONTINUE_SELECTORS)
    inventory = capture(sb, run_dir, STEP_NAME, save=cfg.save_artifacts)
    sb.switch_to_default_content()
    return inventory


def _verify_screen(sb) -> None:
    try:
        sb.wait_for_element_visible(PIN, timeout=10)
    except Exception as exc:
        raise PageMismatchError(
            f"Step 8: expected the PIN/security screen but {PIN} is not there."
        ) from exc


def _set_pin(sb, pin: str, cfg: RunConfig) -> None:
    if not (pin.isdigit() and 6 <= len(pin) <= 15):
        raise PageMismatchError(
            f"Step 8: account_pin must be 6-15 digits; config has {len(pin)} "
            f"character(s). Fix ApplicationConfig.account_pin."
        )

    human_type(sb, PIN, pin, cfg)
    human_type(sb, PIN_CONFIRM, pin, cfg)

    # Both fields are type=password, so read them back rather than trusting
    # that a keystroke-masked field took what was typed.
    for selector, label in ((PIN, "PIN"), (PIN_CONFIRM, "PIN confirmation")):
        if (sb.get_attribute(selector, "value") or "") != pin:
            raise PageMismatchError(f"Step 8: {label} did not take the configured value")
    LOG.info("Account PIN set (%d digits)", len(pin))


def _set_security_questions(sb, answers: tuple, cfg: RunConfig) -> None:
    """Pick three different questions and answer each one."""
    if len(answers) < len(QUESTIONS):
        raise PageMismatchError(
            f"Step 8: {len(QUESTIONS)} security answers are needed but config "
            f"has {len(answers)}. Fix ApplicationConfig.security_answers."
        )

    chosen: list[str] = []
    for index, (question_sel, answer_sel) in enumerate(zip(QUESTIONS, ANSWERS)):
        options = sb.execute_script(_OPTIONS_JS, question_sel.lstrip("#"))
        if not options:
            raise PageMismatchError(f"Step 8: no options in {question_sel}")

        value = next((v for v, _ in options if v not in chosen), None)
        if value is None:
            raise PageMismatchError(
                f"Step 8: {question_sel} offers no question that is not already "
                f"used. The three must differ."
            )
        chosen.append(value)

        human_select(sb, question_sel, value, cfg)
        human_type(sb, answer_sel, answers[index], cfg)

        text = next((t for v, t in options if v == value), value)
        LOG.info("Security question %d: %s", index + 1, text)

    errors = validation_errors(sb)
    if errors:
        # The site rejects answers it considers personal or guessable, and it
        # says so inline rather than waiting for Continue.
        LOG.warning("Form is flagging the security answers: %s", errors)
