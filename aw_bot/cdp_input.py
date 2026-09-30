"""Pointer input dispatched by the browser, for runs with several browsers.

Why this exists
---------------

`--real-input` drives the machine's own mouse and keyboard, which is the
strongest thing available and can never be parallelised: one desktop, one
cursor. Without it, typing is already fine -- `send_keys` goes through
chromedriver to CDP `Input.dispatchKeyEvent`, so the events are the browser's
own and carry `isTrusted`, and human.py already gives them a per-field tempo,
log-normal gaps, typos and corrections.

Clicking is where the gap is, and only inside the enrollment frame.
`_pressed_click` deliberately refuses in there (human.py) because ActionChains
addresses the top-level viewport while that frame is taller than the window,
so a press aimed at something in it can land nowhere at all -- silently, since
perform() does not raise. Three leads died at step 6 that way. Inside the
frame it therefore falls through to `sb.click()`, which is a trusted native
click with **no dwell time**: mousedown and mouseup in the same instant,
identical on every click in the run. A press duration is one of the cheapest
things for a page to measure and nothing biological has one of zero.

CDP `Input.dispatchMouseEvent` closes that without touching the desktop. It
takes explicit coordinates, so the top-level-viewport limitation that stops
ActionChains does not apply -- the frame's offset is added to the element's
box and the point means the same thing to the window as it does to the frame.
Events enter through the browser's own input pipeline, so they carry
`isTrusted` exactly as a real click does.

What it does not claim
----------------------

The desktop cursor does not move. Anything correlating the browser's reported
pointer against the real one would see them disagree, and `--real-input`
remains the answer where that matters. This is the strongest input that can
run five browsers at once, not the strongest input.
"""

import random
import time

from . import real_input
from .config import RunConfig
from .logs import LOG


def available(sb) -> bool:
    """Can this driver dispatch CDP input?"""
    return hasattr(getattr(sb, "driver", None), "execute_cdp_cmd")


def _send(sb, event: str, **params) -> None:
    sb.driver.execute_cdp_cmd(
        "Input.dispatchMouseEvent", {"type": event, **params}
    )


def _path_to(x: float, y: float, cfg: RunConfig) -> list[tuple[float, float]]:
    """A curved approach to (x, y), as a list of points to move through.

    The same shape `_drift_to` draws with ActionChains and for the same
    reason: a hand accelerates into a move and decelerates out of it, so the
    trajectory bends and the spacing between samples is uneven. A straight
    line at constant speed is the thing a pointer-path classifier is built to
    pick out.
    """
    steps = max(4, cfg.mouse_steps)

    # Start somewhere off to the side, far enough that the approach is a real
    # move rather than a twitch.
    start_x = x + random.uniform(-260, 260)
    start_y = y + random.uniform(-150, 150)

    # Control point pulled off the straight line, which is what bends it.
    cp_x = (start_x + x) / 2 + random.uniform(-70, 70)
    cp_y = (start_y + y) / 2 + random.uniform(-70, 70)

    points = []
    for index in range(1, steps + 1):
        t = index / steps
        # Ease in and out, so the samples bunch at the ends and spread
        # through the middle -- which is what varying speed looks like when
        # it is sampled at a constant rate.
        eased = t * t * (3 - 2 * t)
        px = (1 - eased) ** 2 * start_x + 2 * (1 - eased) * eased * cp_x + eased ** 2 * x
        py = (1 - eased) ** 2 * start_y + 2 * (1 - eased) * eased * cp_y + eased ** 2 * y
        points.append((px + random.uniform(-1.5, 1.5), py + random.uniform(-1.5, 1.5)))

    # Land exactly on the target, not a pixel or two off it.
    points[-1] = (x, y)
    return points


def click(sb, element, cfg: RunConfig) -> bool:
    """Move to the element and click it with a real press duration.

    False means "this could not be done, use the ordinary click" -- never a
    half-finished click. Every refusal is a case where the ordinary path is
    still correct, so the caller loses a dwell time rather than a lead.
    """
    if not available(sb):
        LOG.debug("CDP input is not available on this driver")
        return False

    aimed = real_input.aim_point(sb, element)
    if aimed is None:
        # aim_point has already recorded why, and its reasons are real: the
        # element is off screen, too thin to hit, or something is drawn over
        # it. None of those get better by clicking anyway.
        LOG.debug("CDP click not aimed: %s", real_input.last_refusal())
        return False

    x, y, _origin = aimed

    try:
        # Approach, rather than teleporting onto the target. A click with no
        # preceding movement is as distinctive as one with no dwell.
        for px, py in _path_to(x, y, cfg):
            _send(sb, "mouseMoved", x=px, y=py, button="none", buttons=0)
            time.sleep(random.uniform(0.006, 0.02))

        # A beat on the target before pressing, the way a hand settles.
        time.sleep(random.uniform(0.04, 0.13))

        _send(sb, "mousePressed", x=x, y=y, button="left", buttons=1, clickCount=1)

        # The press itself. A finger is on a button for something like 60-140
        # milliseconds; `sb.click()` holds it for zero, every single time.
        time.sleep(random.uniform(0.06, 0.14))

        _send(sb, "mouseReleased", x=x, y=y, button="left", buttons=0, clickCount=1)
    except Exception as exc:
        # Half a click is worse than none: a press with no release leaves the
        # page holding the button down. Say so loudly rather than at debug --
        # the caller will click again, and that only works if the page is not
        # already mid-press.
        LOG.warning("CDP click failed partway (%s); releasing and falling back", exc)
        try:
            _send(sb, "mouseReleased", x=x, y=y, button="left", buttons=0, clickCount=1)
        except Exception:
            pass
        return False

    LOG.debug("CDP-clicked at (%.0f, %.0f) in the top-level viewport", x, y)
    return True
