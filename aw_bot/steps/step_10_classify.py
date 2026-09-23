"""Step 10 -- read the screen the wizard stopped on and classify the lead.

It exists to answer the question the whole run is for: is this lead a sale, a
document request, or someone who already has the benefit elsewhere.

It presses Continue on the screens that state no decision -- currently the
account review, which reads the applicant's own details back at them. Those
are pages between verdicts rather than verdicts, and classifying one would
record an outcome the site never gave. Everything else it only reads.

Worth being explicit about what that Continue does on the review screen: it
consents to Assurance Wireless pre-populating a California LifeLine
application with the details collected so far. That is a step beyond gathering
Assurance Wireless's own information, and it is clicked because this run is
meant to reach the eligibility decision, which sits behind it.

It is also how the rest of the wizard gets mapped. Whatever screen the step
before it lands on, this records the headings, fields and buttons into the run's
artifacts, so a screen that is not yet recognised comes back as `unknown` with
everything needed to add it to `classify.py` -- rather than a guessed verdict.

The wizard's own rail is PERSONAL INFO -> ELIGIBILITY -> PHONE OPTIONS ->
DISCLOSURES -> SUBMIT PROOF, so there are screens still to map between the
address screen and the one that states a decision. Each run that ends `unknown`
here is what tells us the next one to implement.
"""

import json
from pathlib import Path

from ..artifacts import capture
from ..classify import UNKNOWN, classify_screen
from ..config import RunConfig
from ..logs import LOG
from ..human import human_click, human_type, pause
from ..page_utils import (
    advance_screen,
    answer_radio,
    body_text,
    enter_enrollment_frame,
    read_radios,
)

STEP_NAME = "step_10_classify"

# Screens that state no decision and exist only to be acknowledged.
#
# The account review is the first of these: it reads the applicant's own
# details back at them and offers Continue. Classifying it would be wrong --
# it is not a verdict, it is a page between two verdicts -- so the run presses
# Continue and carries on to whatever does state one.
#
# Matched on headings, lowercased.
PASS_THROUGH_SCREENS = (
    ("review your assurance wireless account information", "account review"),
)

CONTINUE_SELECTORS = (
    "button.order-button:not(.float-end)",
    'button:contains("Continue")',
)

# How many screens to work through before giving up. Five are known between
# step 9 and the verdict -- account review, qualifying programme, phone
# choice, e-signature consent, one-per-household -- so this allows a little
# room beyond them and no more. A wizard that keeps handing back pages is one
# this step does not understand, and pressing Continue indefinitely on a
# benefits application is not a thing to do on a guess.
MAX_PASS_THROUGH = 8

# Seconds to sit still after each pass-through Continue, for the same reason
# step 9 does it: the screens behind this point wait on a backend, and the
# driver polling at them is what stopped that backend answering.
SETTLE_AFTER_CONTINUE = 15.0


# The California LifeLine qualification screen, which asks which government
# programme the applicant is enrolled in. Not a decision the site is stating --
# a question it is asking -- so the run answers it and continues.
QUALIFY_HEADING = "how do you qualify for california lifeline"

# The options are checkboxes hidden behind painted labels, the same pattern as
# the radios on the earlier screens: clicking the input itself lands on
# whatever is drawn over it, so the label is what has to be clicked.
_FIND_PROGRAM_JS = r"""
const wanted = (arguments[0] || '').toLowerCase().trim();
const boxes = Array.from(
    document.querySelectorAll('input[type=checkbox][name="programDocumentType"]')
);
const seen = [];
const visible = el => !!(el && (el.offsetParent || el.getClientRects().length));

for (const box of boxes) {
  const label = box.id ? document.querySelector('label[for="' + box.id + '"]') : null;
  const text = ((label && label.innerText) || '').replace(/\s+/g, ' ').trim();
  seen.push(text);
  /* Either direction: the configured wording may be shorter than the label
     on screen, or the other way round when the site rewords an option. */
  const low = text.toLowerCase();
  if (text && (low.indexOf(wanted) !== -1 || wanted.indexOf(low) !== -1)) {
    return {
      id: box.id,
      selector: 'label[for="' + box.id + '"]',
      text: text,
      checked: box.checked,
      visible: visible(label),
      options: seen
    };
  }
}
return {options: seen};
"""

_PROGRAM_CHECKED_JS = """
const box = document.getElementById(arguments[0]);
return box ? box.checked : null;
"""


def _pass_through(headings: list[str]) -> str:
    """The name of the acknowledge-and-continue screen, or "" if this is not one."""
    joined = " | ".join(headings or []).lower()
    return next((name for signal, name in PASS_THROUGH_SCREENS if signal in joined), "")

# Headings, the step rail, and any panel the wizard uses to announce a decision.
_SCREEN_JS = """
const pick = (sel, limit) => Array.from(document.querySelectorAll(sel))
    .map(e => (e.innerText || '').trim()).filter(Boolean).slice(0, limit);
return {
  headings: pick('h1,h2,h3,h4,legend', 12),
  buttons:  pick('button, a.btn, input[type=submit]', 12),
  alerts:   pick('.alert, .modal-body, [class*="error"]', 8),
  steps:    pick('.nav-item, .step, [class*="wizard"] li', 12)
};
"""


# The two screens between the qualifying programme and the decision. Matched
# on their own distinctive wording rather than headings, because both put the
# text that identifies them in the body.
ESIGN_SIGNAL = "e-signature consent"
HOUSEHOLD_SIGNAL = "do you live with another adult"

# The three household questions, in the order they appear, paired with the
# config field that answers each. The hints are matched against the question's
# own text so a reworded question still finds its answer.
HOUSEHOLD_QUESTIONS = (
    ("live with another adult", "household_lives_with_adult"),
    ("receive a california lifeline discount", "household_adult_has_lifeline"),
    ("share income and living expenses", "household_shares_expenses"),
)

# Every certification box on the household screen. They are ticked, not read:
# the screen will not continue without them.
_TICK_CERTIFICATIONS_JS = r"""
const boxes = Array.from(document.querySelectorAll('input[type=checkbox]'))
    .filter(b => !b.disabled);
const out = [];
for (const box of boxes) {
  const label = box.id ? document.querySelector('label[for="' + box.id + '"]') : null;
  out.push({
    id: box.id || null,
    selector: box.id ? 'label[for="' + box.id + '"]' : null,
    text: ((label && label.innerText) || '').replace(/\s+/g, ' ').trim().slice(0, 120),
    checked: box.checked
  });
}
return out;
"""

_ALL_TICKED_JS = """
return Array.from(document.querySelectorAll('input[type=checkbox]'))
    .filter(b => !b.disabled)
    .every(b => b.checked);
"""


# "Choose your phone", the device-selection screen.
PHONE_HEADING = "choose your phone"

# The two options are radios that share an id -- `id="deviceType"` on both --
# so a label[for=] cannot tell them apart and `read_radios` has nothing unique
# to key on. Their `value` does distinguish them, and each has the painted
# control as its immediate next sibling:
#
#   <span class="b-contain">
#     <input type="radio" id="deviceType" name="deviceType" value="free">
#     <div class="b-input"></div>          <- what is actually on screen
#   </span>
#
# So the adjacent-sibling selector is what reaches the right one. Clicking the
# input itself would land on the div drawn over it, the same as every other
# radio on this site.
_PHONE_SELECTOR = 'input[name="deviceType"][value="{value}"] + div.b-input'

_PHONE_STATE_JS = """
const wanted = arguments[0];
const radios = Array.from(document.querySelectorAll('input[name="deviceType"]'));
const hit = radios.find(r => r.value === wanted) || null;
return {
  offered: radios.map(r => r.value),
  found: !!hit,
  checked: hit ? hit.checked : null
};
"""


def _is_phone_screen(headings: list[str]) -> bool:
    return PHONE_HEADING in " | ".join(headings or []).lower()


def _choose_phone(sb, cfg: RunConfig, run_dir: Path) -> bool:
    """Pick the configured device and continue. False to stop."""
    wanted = cfg.application.phone_option
    state = sb.execute_script(_PHONE_STATE_JS, wanted) or {}

    if not state.get("found"):
        LOG.error(
            "Step 10: no phone option with value %r on this screen. "
            "Offered: %s", wanted, state.get("offered") or [],
        )
        return False

    if state.get("checked"):
        LOG.info("Step 10: the %r phone option is already selected", wanted)
    else:
        LOG.info("Step 10: choosing the %r phone option", wanted)
        human_click(sb, _PHONE_SELECTOR.format(value=wanted), cfg)
        pause(cfg, 0.4)

    # Confirm it took. A painted radio that swallowed the click leaves the
    # screen with no device chosen and Continue refusing to move.
    after = sb.execute_script(_PHONE_STATE_JS, wanted) or {}
    if not after.get("checked"):
        LOG.error(
            "Step 10: the %r phone option did not stay selected. Stopping "
            "rather than continuing with no device chosen.", wanted,
        )
        return False

    capture(sb, run_dir, f"{STEP_NAME}_phone", save=cfg.save_artifacts)
    advance_screen(sb, cfg, "Step 10", CONTINUE_SELECTORS, settle=SETTLE_AFTER_CONTINUE)
    return True


def _is_esign_screen(body: str) -> bool:
    return ESIGN_SIGNAL in (body or "").lower()


def _is_household_screen(body: str) -> bool:
    return HOUSEHOLD_SIGNAL in (body or "").lower()


def _is_qualify_screen(headings: list[str]) -> bool:
    return QUALIFY_HEADING in " | ".join(headings or []).lower()


def _choose_program(sb, cfg: RunConfig, run_dir: Path) -> bool:
    """Tick the configured qualifying programme and continue. False to stop.

    Refuses rather than guesses. The programme is a claim about the applicant
    -- which government assistance they are enrolled in, on their federal
    benefits application -- so an option that cannot be found by name is a
    reason to stop and let somebody look, never a reason to tick the nearest
    one. The same goes for a tick that does not register: continuing would
    submit the application asserting nothing, or worse, something unintended.
    """
    wanted = cfg.application.qualifying_program
    found = sb.execute_script(_FIND_PROGRAM_JS, wanted) or {}

    if not found.get("id"):
        LOG.error(
            "Step 10: no qualifying programme on this screen matches %r. "
            "Offered: %s. Not guessing at one -- set "
            "ApplicationConfig.qualifying_program to match.",
            wanted, found.get("options") or [],
        )
        return False

    if not found.get("visible"):
        # Everything past the first three is behind "Show More Programs".
        LOG.info("Step 10: expanding the programme list to reach %r", found["text"])
        try:
            human_click(sb, 'button:contains("Show More Programs")', cfg)
            pause(cfg, 0.4)
        except Exception as exc:
            LOG.error(
                "Step 10: %r is hidden behind 'Show More Programs' and that "
                "could not be pressed (%s)", found["text"], exc,
            )
            return False

    if found.get("checked"):
        LOG.info("Step 10: %s is already ticked", found["text"])
    else:
        LOG.info("Step 10: qualifying through %s", found["text"])
        human_click(sb, found["selector"], cfg)
        pause(cfg, 0.4)

    # Confirm it took. A painted checkbox that swallowed the click leaves the
    # form claiming no programme at all.
    if not sb.execute_script(_PROGRAM_CHECKED_JS, found["id"]):
        LOG.error(
            "Step 10: %s did not stay ticked, so the application would claim "
            "no qualifying programme. Stopping.", found["text"],
        )
        return False

    capture(sb, run_dir, f"{STEP_NAME}_qualifying_program", save=cfg.save_artifacts)
    advance_screen(
        sb, cfg, "Step 10", CONTINUE_SELECTORS, settle=SETTLE_AFTER_CONTINUE
    )
    return True


def _answer_esign(sb, cfg: RunConfig, run_dir: Path) -> bool:
    """Agree to the E-Signature Consent and enter the initials. False to stop."""
    app = cfg.application
    radios = read_radios(sb)
    if radios and not answer_radio(
        sb, radios, "e-signature consent", ("consent", "agree", "esign"),
        app.esign_consent, cfg,
    ):
        LOG.error(
            "Step 10: could not answer the E-Signature Consent with %r. "
            "Options were: %s", app.esign_consent, [r.get("label") for r in radios],
        )
        return False

    # The initials box. The full-name field beside it is prefilled by the site.
    for selector in ('input[name="initials"]', "#initials", 'input[id*="nitial"]'):
        try:
            if sb.is_element_visible(selector):
                human_type(sb, selector, app.esign_initials, cfg)
                break
        except Exception:
            continue
    else:
        LOG.warning(
            "Step 10: no initials field found on the consent screen; "
            "continuing in case the site does not require one"
        )

    capture(sb, run_dir, f"{STEP_NAME}_esignature", save=cfg.save_artifacts)
    advance_screen(sb, cfg, "Step 10", CONTINUE_SELECTORS, settle=SETTLE_AFTER_CONTINUE)
    return True


def _answer_household(sb, cfg: RunConfig, run_dir: Path) -> bool:
    """Answer the one-per-household certification. False to stop.

    Each question is answered from its own config field rather than a shared
    default, so the three cannot silently drift into agreeing with each other.
    Refuses if a question cannot be matched: a certification about somebody's
    living arrangements is not a thing to answer by guessing which button is
    nearest.
    """
    app = cfg.application

    for hint, field in HOUSEHOLD_QUESTIONS:
        answer = getattr(app, field)
        radios = read_radios(sb)
        if not radios:
            LOG.error("Step 10: the household screen has no answerable questions")
            return False
        if not answer_radio(sb, radios, hint, (hint,), answer, cfg):
            LOG.error(
                "Step 10: could not answer %r with %r. Options were: %s",
                hint, answer, [r.get("label") for r in radios],
            )
            return False
        LOG.info("Step 10: %s -- %s", hint, answer)
        pause(cfg, 0.3)

    # The certifications. The screen will not continue without them, and the
    # last one is the electronic signature.
    for box in sb.execute_script(_TICK_CERTIFICATIONS_JS) or []:
        if box.get("checked") or not box.get("selector"):
            continue
        LOG.info("Step 10: certifying -- %s", box.get("text"))
        human_click(sb, box["selector"], cfg)
        pause(cfg, 0.3)

    if not sb.execute_script(_ALL_TICKED_JS):
        LOG.error(
            "Step 10: not every certification stayed ticked, so the screen "
            "would be submitted incomplete. Stopping."
        )
        return False

    capture(sb, run_dir, f"{STEP_NAME}_household", save=cfg.save_artifacts)
    advance_screen(sb, cfg, "Step 10", CONTINUE_SELECTORS, settle=SETTLE_AFTER_CONTINUE)
    return True


def classify_lead(sb, cfg: RunConfig, lead, run_dir: Path, *, submit: bool = True) -> dict:
    """Classify the screen after PERSONAL INFO. Returns the step inventory
    with `verdict` and `screen` added.

    `submit=False` stops at the first acknowledge-and-continue screen rather
    than pressing its button, so a dry run reaches the review page and leaves
    the consent on it unclicked.
    """
    LOG.info("Step 10: reading the decision screen for %s", lead.label)

    enter_enrollment_frame(sb, cfg, "Step 10")

    screen = sb.execute_script(_SCREEN_JS) or {}
    headings = screen.get("headings") or []

    # Click past the screens that only ask to be acknowledged, and answer the
    # one that asks how the applicant qualifies, so the verdict is read from a
    # screen that actually states something.
    for _ in range(MAX_PASS_THROUGH):
        seen = body_text(sb)

        # The screens that ask something. Each is answered from config and
        # then continued past; any of them refusing stops the lead rather
        # than carrying on with the question unanswered.
        answered = None
        if _is_qualify_screen(headings):
            answered = ("qualification", _choose_program)
        elif _is_phone_screen(headings):
            answered = ("phone choice", _choose_phone)
        elif _is_esign_screen(seen):
            answered = ("e-signature consent", _answer_esign)
        elif _is_household_screen(seen):
            answered = ("one-per-household certification", _answer_household)

        if answered:
            label, handler = answered
            if not submit:
                LOG.warning(
                    "Step 10: on the %s screen; stopping before it is "
                    "answered (dry run)", label,
                )
                break
            LOG.info("Step 10: answering the %s screen", label)
            if not handler(sb, cfg, run_dir):
                break
            enter_enrollment_frame(sb, cfg, "Step 10")
            screen = sb.execute_script(_SCREEN_JS) or {}
            headings = screen.get("headings") or []
            continue

        name = _pass_through(headings)
        if not name:
            break
        if not submit:
            LOG.warning(
                "Step 10: on the %s screen; stopping before Continue (dry run)", name
            )
            break

        LOG.info("Step 10: %s screen -- continuing past it", name)
        capture(sb, run_dir, f"{STEP_NAME}_{name.replace(' ', '_')}", save=cfg.save_artifacts)
        advance_screen(
            sb, cfg, "Step 10", CONTINUE_SELECTORS,
            settle=SETTLE_AFTER_CONTINUE,
        )
        enter_enrollment_frame(sb, cfg, "Step 10")
        screen = sb.execute_script(_SCREEN_JS) or {}
        headings = screen.get("headings") or []
    else:
        LOG.warning(
            "Step 10: still being handed pages to acknowledge after %d of them; "
            "reading this one as it stands rather than clicking on blindly.",
            MAX_PASS_THROUGH,
        )

    body = body_text(sb)

    LOG.info("Screen headings: %s", headings)
    if screen.get("steps"):
        LOG.info("Wizard rail: %s", screen["steps"])
    if screen.get("alerts"):
        LOG.info("On-screen alerts: %s", screen["alerts"])
    LOG.info("Buttons offered: %s", screen.get("buttons"))

    verdict, why = classify_screen(headings, body)

    if verdict == UNKNOWN:
        LOG.warning("UNRECOGNISED SCREEN -- %s", why)
        LOG.warning(
            "This lead is not classified. The screen is dumped under %s; add its "
            "wording to aw_bot/classify.py to teach the run what it means.",
            run_dir,
        )
    else:
        LOG.info("VERDICT: %s -- %s", verdict.upper(), why)

    inventory = capture(sb, run_dir, STEP_NAME, save=cfg.save_artifacts)
    _dump_screen(run_dir, screen, body, verdict, why, save=cfg.save_artifacts)

    sb.switch_to_default_content()
    inventory["verdict"] = verdict
    inventory["screen"] = why
    return inventory


def _dump_screen(
    run_dir: Path, screen: dict, body: str, verdict: str, why: str, save: bool
) -> None:
    """Write the screen's text next to the step's other artifacts.

    The element inventory `capture` writes lists fields and buttons but not the
    words on the page, and the words are what classification turns on.
    """
    if not save:
        return
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        payload = dict(screen, verdict=verdict, why=why, body_text=body[:8000])
        (run_dir / f"{STEP_NAME}_screen.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
    except Exception as exc:  # never fail a verdict over a dump
        LOG.warning("Could not write the screen dump: %s", exc)
