"""Step 5 -- click "Start Application" inside the enrollment frame.

The frame's landing screen offers two paths. We take the purple panel's
`button.btn-outline`, which is the combined California LifeLine + federal
Lifeline application. The federal-only option is a plain text link with the
same label, which is why the selector is pinned to `button`.

This opens the 5-step wizard:
    PERSONAL INFO -> ELIGIBILITY -> PHONE OPTIONS -> DISCLOSURES -> SUBMIT PROOF
"""

import time
from pathlib import Path

from ..artifacts import capture
from ..config import RunConfig
from ..errors import PageMismatchError
from ..human import human_click
from ..logs import LOG
from ..page_utils import enter_enrollment_frame, first_visible

STEP_NAME = "step_05_start_application"

# The class the site actually uses on that button, then a text fallback scoped
# to `button` so it can't match the federal-only link.
# Not using fdprocessedid -- a form-filler extension injects it per page load.
START_SELECTORS = (
    "button.btn-outline",
    'button:contains("Start Application")',
)


def start_application(sb, cfg: RunConfig, lead, run_dir: Path, *, submit: bool = True) -> dict:
    """Click Start Application and wait for the first wizard screen.

    `lead` and `submit` are unused; this step only opens the wizard.
    """
    LOG.info("Step 5: starting the application (California + Federal)")

    enter_enrollment_frame(sb, cfg, "Step 5")

    selector = first_visible(sb, START_SELECTORS)
    if selector is None:
        raise PageMismatchError(
            "Step 5: no visible Start Application button inside the enrollment "
            f"frame. Tried: {', '.join(START_SELECTORS)}"
        )

    LOG.info("Using selector %s", selector)
    human_click(sb, selector, cfg)

    _wait_for_form(sb, cfg)
    _log_screen(sb)

    inventory = capture(sb, run_dir, STEP_NAME, save=cfg.save_artifacts)
    sb.switch_to_default_content()
    return inventory


def _wait_for_form(sb, cfg: RunConfig) -> int:
    """Wait for the wizard's fields to finish rendering. Returns the count.

    The wizard is an Angular app that renders client-side without changing the
    frame URL, so there's no navigation to wait on. Waiting for the *first*
    field isn't enough either -- the screen paints progressively, so a step
    that started typing then would race the render. Instead wait for the field
    count to hold steady.
    """
    deadline = time.time() + cfg.page_timeout
    previous = -1
    stable_reads = 0

    while time.time() < deadline:
        try:
            count = sb.execute_script(
                "return document.querySelectorAll('input, select, textarea').length"
            )
        except Exception:
            count = -1  # frame still swapping documents

        if count > 0 and count == previous:
            stable_reads += 1
            if stable_reads >= 2:  # unchanged across ~0.75s
                LOG.info("Wizard rendered %d form field(s)", count)
                return count
        else:
            stable_reads = 0

        previous = count
        time.sleep(0.25)

    raise PageMismatchError(
        f"Step 5: clicked Start Application but the form never settled within "
        f"{cfg.page_timeout}s"
    )


def _log_screen(sb) -> None:
    """Report which wizard screen we're on, from its headings and step rail."""
    try:
        headings = sb.execute_script(
            "return Array.from(document.querySelectorAll('h1,h2,h3,legend'))"
            ".map(e => e.innerText.trim()).filter(Boolean).slice(0, 10)"
        )
        LOG.info("Screen headings: %s", headings)
    except Exception as exc:
        LOG.warning("Could not read the screen headings: %s", exc)
