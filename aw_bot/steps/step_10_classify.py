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

PASS_THROUGH_SCREENS = (
    ("review your assurance wireless account information", "account review"),
)

CONTINUE_SELECTORS = (
    "button.order-button:not(.float-end)",
    'button:contains("Continue")',
)

MAX_PASS_THROUGH = 8

SETTLE_AFTER_CONTINUE = 15.0


QUALIFY_HEADING = "how do you qualify for california lifeline"

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
    /* Aim at the painted control, not the label.

       The label is the whole row -- the programme's name and its description
       -- so its centre, which is where a click is aimed, lands on text rather
       than on the box. That toggles the checkbox often enough to look like it
       works and misses often enough to fail a lead, which is exactly what it
       did: ticked on one run, refused to stay ticked on the next.

       `div.b-input` is the box actually drawn on screen and sits immediately
       after the input, the same arrangement the phone radios use. The id is
       addressed with an attribute selector because these ids start with a
       digit, which a bare `#id` cannot express. */
    const painted = box.nextElementSibling;
    const usePainted = painted && painted.classList.contains('b-input');
    return {
      id: box.id,
      selector: usePainted
        ? 'input[id="' + box.id + '"] + div.b-input'
        : 'label[for="' + box.id + '"]',
      aimedAt: usePainted ? 'painted control' : 'label',
      text: text,
      checked: box.checked,
      visible: visible(label) || visible(painted),
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
    joined = " | ".join(headings or []).lower()
    return next((name for signal, name in PASS_THROUGH_SCREENS if signal in joined), "")

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


ESIGN_SIGNAL = "e-signature consent"
HOUSEHOLD_SIGNAL = "do you live with another adult"

HOUSEHOLD_QUESTIONS = (
    ("live with another adult", "household_lives_with_adult"),
    ("receive a california lifeline discount", "household_adult_has_lifeline"),
    ("share income and living expenses", "household_shares_expenses"),
)

ATTESTATIONS_HEADING = "attestations"
_E911_LABEL = 'label[for="e911{answer}"]'
_SIGNATURE_CHECKBOX = (
    'label[for="sigCheck"]',
    'input[id="sigCheck"] + div.b-input',
)

_ATTESTATIONS_STATE_JS = """
const yes = document.getElementById('e911yes');
const no = document.getElementById('e911no');
const sig = document.getElementById('sigCheck');
return {
  hasE911: !!(yes && no),
  e911Yes: yes ? !!yes.checked : null,
  e911No: no ? !!no.checked : null,
  hasSignature: !!sig,
  signature: sig ? !!sig.checked : null
};
"""


_SETTLE_POLLS = 12


_HIT_TEST_JS = """
const el = document.querySelector(arguments[0]);
if (!el) return {found: false};
const r = el.getBoundingClientRect();
const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
const at = document.elementFromPoint(cx, cy);
const name = (n) => {
  if (!n) return null;
  const cls = (typeof n.className === 'string' && n.className.trim())
      ? '.' + n.className.trim().split(/\s+/).join('.') : '';
  return n.tagName.toLowerCase() + (n.id ? '#' + n.id : '') + cls;
};
return {
  found: true,
  size: Math.round(r.width) + 'x' + Math.round(r.height),
  at: Math.round(r.left) + ',' + Math.round(r.top),
  viewport: window.innerWidth + 'x' + window.innerHeight,
  onScreen: r.bottom > 0 && r.top < window.innerHeight
         && r.right > 0 && r.left < window.innerWidth,
  under: name(at),
  hits: !!(at && (at === el || el.contains(at) || at.contains(el)))
};
"""


def _click_and_confirm(sb, cfg: RunConfig, selectors, reads: str, holds, what: str) -> bool:
    if isinstance(selectors, str):
        selectors = (selectors,)

    for index, selector in enumerate(selectors):
        human_click(sb, selector, cfg)

        for _ in range(_SETTLE_POLLS):
            pause(cfg, 0.3)
            if holds(sb.execute_script(reads) or {}):
                return True

        where = sb.execute_script(_HIT_TEST_JS, selector) or {}
        LOG.warning(
            "Step 10: %s did not register via %s -- %s", what, selector,
            "element not on the page" if not where.get("found") else
            "%s at %s in a %s viewport, on screen: %s, a click there lands on %s (%s)" % (
                where.get("size"), where.get("at"), where.get("viewport"),
                where.get("onScreen"), where.get("under"),
                "the right element" if where.get("hits") else "something else",
            ),
        )
        if index + 1 < len(selectors):
            LOG.info("Step 10: trying %s instead", selectors[index + 1])
    return False


def _is_attestations_screen(headings: list[str]) -> bool:
    return ATTESTATIONS_HEADING in " | ".join(headings or []).lower()


def _answer_attestations(sb, cfg: RunConfig, lead, run_dir: Path) -> bool:
    app = cfg.application

    capture(sb, run_dir, f"{STEP_NAME}_attestations_as_found", save=cfg.save_artifacts)

    state = sb.execute_script(_ATTESTATIONS_STATE_JS) or {}
    if not state.get("hasE911") or not state.get("hasSignature"):
        LOG.error(
            "Step 10: the Attestations screen is not laid out as expected "
            "(911 question: %s, signature box: %s). Stopping.",
            state.get("hasE911"), state.get("hasSignature"),
        )
        return False

    answer = (app.wifi_911_acknowledged or "").strip().lower()
    if answer not in ("yes", "no"):
        LOG.error(
            "Step 10: wifi_911_acknowledged is %r; it has to be Yes or No.",
            app.wifi_911_acknowledged,
        )
        return False

    key = "e911Yes" if answer == "yes" else "e911No"
    if state.get(key):
        LOG.info("Step 10: the Wi-Fi 911 limitation is already acknowledged")
    else:
        LOG.info("Step 10: acknowledging the Wi-Fi 911 limitation -- %s", answer.title())
        if not _click_and_confirm(
            sb, cfg, _E911_LABEL.format(answer=answer), _ATTESTATIONS_STATE_JS,
            lambda s: s.get(key), "the Wi-Fi 911 acknowledgement",
        ):
            LOG.error(
                "Step 10: the Wi-Fi 911 acknowledgement would not stay on %r. "
                "Stopping rather than continuing with it unanswered.", answer.title(),
            )
            return False

    if not app.service_terms_agreed:
        LOG.error(
            "Step 10: service_terms_agreed is off, and this screen will not "
            "continue without it. Stopping."
        )
        return False

    if state.get("signature"):
        LOG.info("Step 10: the service terms are already agreed")
    else:
        LOG.info("Step 10: agreeing to the Assurance Wireless service terms")
        if not _click_and_confirm(
            sb, cfg, _SIGNATURE_CHECKBOX, _ATTESTATIONS_STATE_JS,
            lambda s: s.get("signature"), "the service terms box",
        ):
            LOG.error(
                "Step 10: the service terms box would not stay ticked, and the "
                "screen will not continue without it. Stopping."
            )
            return False

    capture(sb, run_dir, f"{STEP_NAME}_attestations", save=cfg.save_artifacts)
    advance_screen(
        sb, cfg, "Step 10", CONTINUE_SELECTORS,
        settle=SETTLE_AFTER_CONTINUE, first_look=cfg.step10_first_look,
    )
    return True


_HOUSEHOLD_QUESTION_JS = r"""
const hint = arguments[0];
const others = arguments[1] || [];
const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();

let block = null;
for (const el of document.querySelectorAll('div, li, section, fieldset, p, tr, td')) {
  const text = norm(el.innerText);
  if (!text.includes(hint)) continue;
  if (!el.querySelector('input[type=radio]')) continue;
  if (!block || el.innerText.length < block.innerText.length) block = el;
}
if (!block) return {found: false, reason: 'no block holds that question and a radio'};

const text = norm(block.innerText);
const bleed = others.filter(o => text.includes(o));
if (bleed.length) {
  return {found: false, reason: 'block also covers: ' + bleed.join('; '), text: text.slice(0, 200)};
}

const labelOf = (r) => {
  let t = '';
  if (r.id) {
    const lab = document.querySelector('label[for="' + r.id + '"]');
    if (lab) t = lab.innerText || '';
  }
  if (!t && r.closest('label')) t = r.closest('label').innerText || '';
  return t.replace(/\s+/g, ' ').trim();
};

/* The painted div drawn over the hidden radio, same as everywhere else on
   this site. A click aimed at the input itself lands on the div anyway. */
const selectorFor = (r) => {
  const painted = r.nextElementSibling;
  if (r.id && painted && painted.classList.contains('b-input')) {
    return 'input[id="' + r.id + '"] + div.b-input';
  }
  if (r.name && r.value && painted && painted.classList.contains('b-input')) {
    return 'input[name="' + r.name + '"][value="' + r.value + '"] + div.b-input';
  }
  if (r.id) return 'label[for="' + r.id + '"]';
  return null;
};

const radios = Array.from(block.querySelectorAll('input[type=radio]')).map(r => ({
  id: r.id || null,
  name: r.getAttribute('name') || null,
  value: r.value,
  checked: r.checked,
  label: labelOf(r),
  selector: selectorFor(r)
}));
return {found: true, text: text.slice(0, 200), radios: radios};
"""

_HOUSEHOLD_CHECKED_JS = """
const id = arguments[0];
const el = id ? document.getElementById(id) : null;
return el ? !!el.checked : null;
"""


_TICK_CERTIFICATIONS_JS = r"""
/* Scoped to the form on purpose. This app keeps its mobile navigation menu
   in a bare checkbox outside it --

     <application><input id="menu-switch" type="checkbox"> ...

   -- on every page, so an unscoped sweep ticks it, opens the nav drawer over
   the form, and then insists it stay ticked. Nothing outside the form is a
   certification. */
const boxes = Array.from(document.querySelectorAll('form input[type=checkbox]'))
    .filter(b => !b.disabled);
const out = [];
for (const box of boxes) {
  /* The label on these boxes holds no text at all -- it is the painted
     control and nothing else:

       <div aria-labelledby="cert2lbl" role="radiogroup" class="row">
         <div><div id="cert2lbl">I understand that violating the
              one-per-household benefit rule ... and potentially,
              prosecution by the United States government.</div></div>
         <div><label for="crt2" class="b-contain"><span></span>
              <input id="crt2"><div class="b-input"></div></label></div>
       </div>

     so label[for=] logged every certification as an empty string. The run's
     log is the record of what was agreed to on somebody's benefits
     application, and one of these mentions prosecution, so the wording has
     to be resolved -- it lives on the row's aria-labelledby target. */
  const label = box.id ? document.querySelector('label[for="' + box.id + '"]') : null;
  let text = ((label && label.innerText) || '').replace(/\s+/g, ' ').trim();
  if (!text) {
    const row = box.closest('[aria-labelledby]');
    const described = row && document.getElementById(row.getAttribute('aria-labelledby'));
    if (described) text = (described.innerText || '').replace(/\s+/g, ' ').trim();
  }
  /* Aim at the painted box, not the label: clicking the input itself lands
     on whatever is drawn over it. */
  const painted = box.nextElementSibling;
  const usePainted = painted && painted.classList.contains('b-input');
  let selector = null;
  if (usePainted && box.id) {
    selector = 'input[id="' + box.id + '"] + div.b-input';
  } else if (box.id) {
    selector = 'label[for="' + box.id + '"]';
  }
  out.push({
    id: box.id || null,
    selector: selector,
    text: text.slice(0, 160),
    checked: box.checked
  });
}
return out;
"""

_ALL_TICKED_JS = """
return Array.from(document.querySelectorAll('form input[type=checkbox]'))
    .filter(b => !b.disabled)
    .every(b => b.checked);
"""


PHONE_HEADING = "choose your phone"

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


def _choose_phone(sb, cfg: RunConfig, lead, run_dir: Path) -> bool:
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

    after = sb.execute_script(_PHONE_STATE_JS, wanted) or {}
    if not after.get("checked"):
        LOG.error(
            "Step 10: the %r phone option did not stay selected. Stopping "
            "rather than continuing with no device chosen.", wanted,
        )
        return False

    capture(sb, run_dir, f"{STEP_NAME}_phone", save=cfg.save_artifacts)
    advance_screen(
        sb, cfg, "Step 10", CONTINUE_SELECTORS,
        settle=SETTLE_AFTER_CONTINUE, first_look=cfg.step10_first_look,
    )
    return True


def _is_esign_screen(body: str) -> bool:
    return ESIGN_SIGNAL in (body or "").lower()


def _is_household_screen(body: str) -> bool:
    return HOUSEHOLD_SIGNAL in (body or "").lower()


def _is_qualify_screen(headings: list[str]) -> bool:
    return QUALIFY_HEADING in " | ".join(headings or []).lower()


def _choose_program(sb, cfg: RunConfig, lead, run_dir: Path) -> bool:
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

    if not sb.execute_script(_PROGRAM_CHECKED_JS, found["id"]):
        LOG.error(
            "Step 10: %s did not stay ticked, so the application would claim "
            "no qualifying programme. Stopping.", found["text"],
        )
        return False

    capture(sb, run_dir, f"{STEP_NAME}_qualifying_program", save=cfg.save_artifacts)
    advance_screen(
        sb, cfg, "Step 10", CONTINUE_SELECTORS,
        settle=SETTLE_AFTER_CONTINUE, first_look=cfg.step10_first_look,
    )
    return True


ESIGN_INITIALS_FIELD = "#esigintl"
ESIGN_NAME_FIELD = "#esigname"

_ESIGN_FILLED_JS = """
const initials = document.querySelector(arguments[0]);
const name = document.querySelector(arguments[1]);
return {
  initials: initials ? initials.value.trim() : null,
  name: name ? name.value.trim() : null
};
"""


def _signature_values(lead) -> tuple[str, str]:
    first = (getattr(lead, "first_name", "") or "").strip()
    last = (getattr(lead, "last_name", "") or "").strip()
    initials = f"{first[:1]}{last[:1]}".upper()
    return initials, " ".join(part for part in (first, last) if part)


def _answer_esign(sb, cfg: RunConfig, lead, run_dir: Path) -> bool:
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

    initials, full_name = _signature_values(lead)
    if not initials or not full_name:
        LOG.error(
            "Step 10: this lead has no usable name to sign with (%r / %r)",
            getattr(lead, "first_name", ""), getattr(lead, "last_name", ""),
        )
        return False

    for selector, value, what in (
        (ESIGN_INITIALS_FIELD, initials, "initials"),
        (ESIGN_NAME_FIELD, full_name, "signature"),
    ):
        try:
            human_type(sb, selector, value, cfg)
        except Exception as exc:
            LOG.error("Step 10: could not enter the %s (%s): %s", what, selector, exc)
            return False

    filled = sb.execute_script(
        _ESIGN_FILLED_JS, ESIGN_INITIALS_FIELD, ESIGN_NAME_FIELD
    ) or {}
    if not filled.get("initials") or not filled.get("name"):
        LOG.error(
            "Step 10: the consent screen did not keep what was typed "
            "(initials=%r, signature=%r). Stopping.",
            filled.get("initials"), filled.get("name"),
        )
        return False

    LOG.info("Step 10: signed the consent as %s (%s)", full_name, initials)
    capture(sb, run_dir, f"{STEP_NAME}_esignature", save=cfg.save_artifacts)
    advance_screen(
        sb, cfg, "Step 10", CONTINUE_SELECTORS,
        settle=SETTLE_AFTER_CONTINUE, first_look=cfg.step10_first_look,
    )
    return True


def _answer_one_household_question(sb, cfg: RunConfig, hint: str, answer: str) -> bool:
    others = [h for h, _ in HOUSEHOLD_QUESTIONS if h != hint]
    found = sb.execute_script(_HOUSEHOLD_QUESTION_JS, hint, others) or {}

    if not found.get("found"):
        LOG.error(
            "Step 10: could not find the household question %r on its own "
            "(%s). Not answering it by position. Stopping.",
            hint, found.get("reason") or "no reason given",
        )
        return False

    radios = found.get("radios") or []
    target = next(
        (r for r in radios
         if answer.strip().lower() in ((r.get("label") or "").strip().lower(),
                                       (r.get("value") or "").strip().lower())),
        None,
    )
    if target is None or not target.get("selector"):
        LOG.error(
            "Step 10: the household question %r offers no %r option; saw %s",
            hint, answer, [(r.get("value"), r.get("label")) for r in radios],
        )
        return False

    if target.get("checked"):
        LOG.info("Step 10: %s -- already %s", hint, answer)
        return True

    LOG.info("Step 10: %s -- %s", hint, answer)
    human_click(sb, target["selector"], cfg)
    pause(cfg, 0.4)

    if target.get("id"):
        held = sb.execute_script(_HOUSEHOLD_CHECKED_JS, target["id"])
        if held is False:
            LOG.error(
                "Step 10: %r did not stay on %r. Stopping rather than "
                "certifying something unintended.", hint, answer,
            )
            return False
    return True


def _answer_household(sb, cfg: RunConfig, lead, run_dir: Path) -> bool:
    app = cfg.application

    capture(sb, run_dir, f"{STEP_NAME}_household_as_found", save=cfg.save_artifacts)

    for hint, field in HOUSEHOLD_QUESTIONS:
        answer = getattr(app, field)
        if not _answer_one_household_question(sb, cfg, hint, answer):
            return False
        pause(cfg, 0.3)

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
    advance_screen(
        sb, cfg, "Step 10", CONTINUE_SELECTORS,
        settle=SETTLE_AFTER_CONTINUE, first_look=cfg.step10_first_look,
    )
    return True


def classify_lead(sb, cfg: RunConfig, lead, run_dir: Path, *, submit: bool = True) -> dict:
    LOG.info("Step 10: reading the decision screen for %s", lead.label)

    enter_enrollment_frame(sb, cfg, "Step 10")

    screen = sb.execute_script(_SCREEN_JS) or {}
    headings = screen.get("headings") or []

    for _ in range(MAX_PASS_THROUGH):
        seen = body_text(sb)

        answered = None
        if _is_qualify_screen(headings):
            answered = ("qualification", _choose_program)
        elif _is_phone_screen(headings):
            answered = ("phone choice", _choose_phone)
        elif _is_esign_screen(seen):
            answered = ("e-signature consent", _answer_esign)
        elif _is_attestations_screen(headings):
            answered = ("attestations", _answer_attestations)
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
            if not handler(sb, cfg, lead, run_dir):
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
            first_look=cfg.step10_first_look,
            allow_reclick=True,
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
    if not save:
        return
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        payload = dict(screen, verdict=verdict, why=why, body_text=body[:8000])
        (run_dir / f"{STEP_NAME}_screen.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        LOG.warning("Could not write the screen dump: %s", exc)
