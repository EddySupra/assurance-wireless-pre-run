"""Step 10 -- read the screen the wizard stopped on and classify the lead.

This step submits nothing and clicks nothing. It exists to answer the question
the whole run is for: is this lead a sale, a document request, or someone who
already has the benefit elsewhere.

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
from ..page_utils import body_text, enter_enrollment_frame

STEP_NAME = "step_10_classify"

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


def classify_lead(sb, cfg: RunConfig, lead, run_dir: Path, *, submit: bool = True) -> dict:
    """Classify the screen after PERSONAL INFO. Returns the step inventory
    with `verdict` and `screen` added.

    `submit` is accepted for the uniform step signature and ignored: there is
    nothing here to submit.
    """
    LOG.info("Step 10: reading the decision screen for %s", lead.label)

    enter_enrollment_frame(sb, cfg, "Step 10")

    screen = sb.execute_script(_SCREEN_JS) or {}
    headings = screen.get("headings") or []
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
