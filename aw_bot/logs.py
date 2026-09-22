"""Console + file logging, one log file per run."""

import logging
import sys
from datetime import datetime
from pathlib import Path

LOG = logging.getLogger("aw_bot")


def run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def setup(run_dir: Path, verbose: bool = False) -> logging.Logger:
    LOG.setLevel(logging.DEBUG if verbose else logging.INFO)
    LOG.handlers.clear()
    # SeleniumBase configures the root logger, so propagating would print
    # every line twice.
    LOG.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%H:%M:%S"))
    LOG.addHandler(console)

    run_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(run_dir / "run.log", encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s  %(levelname)-7s %(name)s  %(message)s")
    )
    LOG.addHandler(file_handler)

    return LOG
