"""Open the enrollment app directly, skipping the four pages that lead to it.

Steps 1-4 exist to walk the public site the way a person would: start page,
Apply Now, ZIP check, state page. That is the right thing for a real run, and
it costs two to three minutes before the wizard even appears -- which is a poor
way to spend a test cycle when the thing being worked on is screen 6 or 9.

The application is served from its own URL and loads on its own:

    https://vmuappcloud.solixinc.com/VMUWeb/public/order?lang=en&zip=<zip>&email=<enc>

where `enc` is the lead's email with `@` replaced by `|`, reversed, then
base64 -- verified against the URL the site itself builds.

This is a development shortcut, not a substitute for the real path. It skips
whatever session state the outer pages set up, so a screen can behave
differently here than it does in a full run. Map a screen with this, then
confirm it without it.
"""

import base64
from pathlib import Path

from ..artifacts import capture
from ..config import RunConfig
from ..errors import PageMismatchError
from ..lead import Lead
from ..logs import LOG
from ..page_utils import settle

STEP_NAME = "step_00_direct_frame"

FRAME_BASE = "https://vmuappcloud.solixinc.com/VMUWeb/public/order"


def encode_email(email: str) -> str:
    """The site's own encoding: @ becomes |, reverse, then base64."""
    swapped = (email or "").strip().lower().replace("@", "|")
    return base64.b64encode(swapped[::-1].encode("utf-8")).decode("ascii")


def frame_url(lead: Lead) -> str:
    return f"{FRAME_BASE}?lang=en&zip={lead.zip_code}&email={encode_email(lead.email)}"


def open_application_frame(
    sb, cfg: RunConfig, lead: Lead, run_dir: Path, *, submit: bool = True
) -> dict:
    """Load the wizard straight from its own URL."""
    url = frame_url(lead)
    LOG.warning(
        "Direct-frame mode: skipping steps 1-4 and opening the application "
        "itself. Screens can behave differently without the session the public "
        "pages set up -- confirm anything mapped here with a full run."
    )
    LOG.info("Opening %s", url)

    sb.open(url)
    settle(sb, cfg)

    if "solixinc.com" not in (sb.get_current_url() or ""):
        raise PageMismatchError(
            f"Direct frame: expected the enrollment app but landed on "
            f"{sb.get_current_url()}"
        )

    LOG.info("Application title: %s", sb.get_title())
    return capture(sb, run_dir, STEP_NAME, save=cfg.save_artifacts)
