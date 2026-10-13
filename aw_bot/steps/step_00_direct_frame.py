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
    swapped = (email or "").strip().lower().replace("@", "|")
    return base64.b64encode(swapped[::-1].encode("utf-8")).decode("ascii")


def frame_url(lead: Lead) -> str:
    return f"{FRAME_BASE}?lang=en&zip={lead.zip_code}&email={encode_email(lead.email)}"


def open_application_frame(
    sb, cfg: RunConfig, lead: Lead, run_dir: Path, *, submit: bool = True
) -> dict:
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
