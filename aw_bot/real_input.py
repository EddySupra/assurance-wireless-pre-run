"""Real OS-level mouse and keyboard, rather than synthetic browser events.

Everything WebDriver does -- `element.click()`, `send_keys`, ActionChains --
is injected into the page. The operating system never sees a mouse move or a
keypress, and neither does anything watching at that level. Akamai Bot Manager
is watching at that level: its sensor script (the `/akam/...` requests) reports
pointer paths, key timings and event trustedness, and a session that submits
form after form with no input telemetry at all scores as a bot.

This drives the real cursor and the real keyboard instead, through pyautogui,
so the events carry `isTrusted: true` and the sensor sees a person.

What that costs, and why this is opt-in:

  * It needs a visible window. Headless has no window to aim at.
  * It takes over the physical mouse and keyboard of this machine. Whatever
    has focus receives the keystrokes, so the run owns the desktop while it
    works -- don't use the machine for anything else.
  * One browser at a time. There is one cursor, so parallel workers would
    fight over it; `should_use` refuses anything but a single worker.

Every helper degrades to the caller's synthetic path on any failure, so real
input never costs reliability.
"""

import random
import threading
import time

from .logs import LOG

try:
    import pygetwindow

    WINDOWS_AVAILABLE = True
except Exception:  # pragma: no cover - platform dependent
    pygetwindow = None
    WINDOWS_AVAILABLE = False

try:
    import pyautogui

    # A move into a screen corner is pyautogui's abort gesture. The run moves
    # the pointer near window edges legitimately, and having it raise there
    # would fail a lead for no reason.
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
    AVAILABLE = True
except Exception as exc:  # pragma: no cover - depends on the display
    pyautogui = None
    AVAILABLE = False
    LOG.debug("pyautogui unavailable, real input disabled: %s", exc)


# Where the page's (0, 0) sits on the physical screen. Chrome exposes the
# window position and the viewport size; the difference between outer and
# inner height is the chrome above the page (tab strip, omnibox).
_VIEWPORT_ORIGIN_JS = """
return {
  x: window.screenX + (window.outerWidth - window.innerWidth) / 2,
  y: window.screenY + (window.outerHeight - window.innerHeight),
  w: window.innerWidth,
  h: window.innerHeight
};
"""

# An element's box in viewport coordinates. No scrolling here: the real wheel
# has already done that, and a scrollIntoView now would move the page out from
# under the coordinates we are about to aim at.
_ELEMENT_BOX_JS = """
const el = arguments[0];
const r = el.getBoundingClientRect();
return {x: r.left, y: r.top, w: r.width, h: r.height};
"""

# Is our element really the thing drawn at this point? A sticky header, a
# consent bar or a modal can sit over it, and a real click hits whatever is on
# top -- silently, because the click itself succeeds. Synthetic clicks never
# had this problem, which is why it only showed up with real input: step 4
# reported a successful click on Apply Now while the page never navigated.
_HIT_TEST_JS = r"""
const el = arguments[0], x = arguments[1], y = arguments[2];
const top = document.elementFromPoint(x, y);
if (!top) return {hit: false, what: 'nothing at that point'};
if (top === el || el.contains(top) || top.contains(el)) return {hit: true};
return {
  hit: false,
  what: (top.tagName || '?').toLowerCase() +
        (top.className && typeof top.className === 'string'
            ? '.' + top.className.trim().split(/\s+/).slice(0, 2).join('.')
            : '')
};
"""


def should_use(cfg) -> bool:
    """Is real input both wanted and usable for this run?"""
    if not getattr(cfg, "real_input", False):
        return False
    if not AVAILABLE:
        LOG.warning("real_input is on but pyautogui is unavailable; using synthetic input")
        return False
    if cfg.headless:
        LOG.warning("real_input needs a visible window; headless run uses synthetic input")
        return False
    # The browser has to be on this machine for the machine's cursor to reach
    # it. On a hosted backend it is not, and pyautogui would still type --
    # into whatever window here happens to have focus. That is an applicant's
    # SSN going into somebody's terminal, so this refuses rather than degrades
    # quietly the way the helpers below do.
    backend = (getattr(cfg, "browser_backend", "") or "").lower()
    if backend in ("browserless", "remote"):
        LOG.warning(
            "real_input drives this machine's mouse and keyboard, but the "
            "%s backend runs the browser elsewhere -- the keystrokes would go "
            "to whatever window is in front here. Using synthetic input.",
            backend,
        )
        return False
    if cfg.workers > 1:
        LOG.warning(
            "real_input needs the machine's one cursor to itself; %d workers "
            "would fight over it, so this run uses synthetic input",
            cfg.workers,
        )
        return False
    return True


def display_size() -> tuple[int, int] | None:
    """The real monitor's size in pixels, or None if it cannot be asked.

    Deliberately the *physical* display rather than anything the browser
    reports. A GoLogin profile's `screen.width/height` belong to its
    fingerprint and can name a monitor far larger than the one actually
    attached -- and the real mouse can only reach pixels that exist. A window
    sized to the fingerprint instead of to the hardware puts the lower half of
    the form at coordinates off the bottom of the screen, where every click
    and keystroke aimed at it goes nowhere.
    """
    if not AVAILABLE:
        return None
    try:
        width, height = pyautogui.size()
    except Exception as exc:
        LOG.debug("Could not read the display size: %s", exc)
        return None
    if not width or not height:
        return None
    return int(width), int(height)


def _matching_windows(title: str) -> list:
    """Windows whose caption carries this page's title."""
    stem = (title or "")[:40]
    if not stem:
        return []
    try:
        return [w for w in pygetwindow.getAllWindows() if w.title and stem in w.title]
    except Exception:
        return []


# What Orbita and Chrome put at the end of their window captions. Used only
# when the page title has not matched, so a navigation mid-look cannot leave
# the run with nothing to focus.
_BROWSER_CAPTIONS = ("Orbita", "Google Chrome", "Chromium")


def _browser_windows() -> list:
    try:
        return [
            w for w in pygetwindow.getAllWindows()
            if w.title and any(name in w.title for name in _BROWSER_CAPTIONS)
        ]
    except Exception:
        return []


def focus_window(sb, patience: float = 6.0) -> bool:
    """Bring the browser to the front, waiting for it if something else has it.

    `patience` is what stops a moment's distraction costing a lead. Windows
    will not hand the foreground to a process that does not already own it,
    so while somebody is typing in another window every attempt here fails --
    and the old version answered that by giving up at once, which turned
    "the operator typed a sentence" into a lead that could not be filled.
    Waiting a few seconds and asking again costs nothing and usually lands.

    This is not a nicety. pyautogui types wherever the operating system's focus
    happens to be, so if anything else is in front -- a terminal, the GoLogin
    app -- the applicant's details get typed into that instead, and the form is
    left half empty with no error anywhere. Aiming the mouse has the same
    problem: the click lands on whatever is drawn at those coordinates.
    """
    if not WINDOWS_AVAILABLE:
        return False
    try:
        title = sb.get_title() or ""
    except Exception:
        return False

    try:
        # Match on the page title, which Chrome puts at the front of its own.
        candidates = _matching_windows(title)
        if not candidates:
            # The title changes as the page navigates, and the window's copy
            # of it lags by a moment -- so a miss here is often just bad
            # timing rather than a missing window. Look again before giving
            # up, and fall back to naming the browser itself, which does not
            # change while the page does.
            time.sleep(0.4)
            candidates = _matching_windows(title) or _browser_windows()
        if not candidates:
            LOG.debug("No window matching %r to focus", title[:40])
            return False

        window = candidates[0]
        if window.isActive:
            return True

        if window.isMinimized:
            window.restore()

        # Ask politely, then use the bounce, then wait and start again. The
        # outer loop is the patient part: whatever is holding the foreground
        # usually lets go within a few seconds.
        deadline = time.time() + max(0.0, patience)
        announced = False
        while True:
            if _try_activate(window):
                return True
            if time.time() >= deadline:
                break
            if not announced:
                announced = True
                LOG.info(
                    "Something else has the foreground; waiting up to %.0fs for "
                    "the browser window. Leave the mouse and keyboard alone "
                    "while --real-input is running.", patience,
                )
            time.sleep(0.5)
            try:
                # Re-find it: a window that was closed and reopened underneath
                # us leaves a handle that can never become active.
                refreshed = _matching_windows(title) or _browser_windows()
                if refreshed:
                    window = refreshed[0]
            except Exception:
                pass

        LOG.debug("Browser window would not come to the front")
        return False
    except Exception as exc:
        # Anything else here means we cannot be sure what is in front, and the
        # caller must refuse rather than type the lead's SSN into whatever
        # window that turns out to be.
        LOG.debug("Could not focus the browser window: %s", exc)
        return False


def _try_activate(window) -> bool:
    """One round of asking a window to come forward. True if it did."""
    try:
        if window.isActive:
            return True
    except Exception:
        return False

    try:
        for attempt in range(2):
            try:
                window.activate()
            except Exception as exc:
                # Do not believe this exception. pygetwindow calls
                # SetForegroundWindow and then raises from ctypes.WinError()
                # without first checking whether it actually failed -- and on
                # success the last error code is 0, so the exception message
                # is the words "The operation completed successfully".
                #
                # Trusting it cost this project the entire --real-input
                # feature: focus_window returned False every time, every real
                # click and keystroke fell back to synthetic input, and the
                # run logged "using synthetic input" while appearing to be
                # doing the opposite. Check the window instead of the error.
                LOG.debug("activate() reported %r; checking the window itself", exc)

            time.sleep(random.uniform(0.12, 0.3))
            try:
                if window.isActive:
                    return True
            except Exception:
                pass

            if attempt == 0:
                # Windows refuses the foreground to a process that does not
                # already own it. Bouncing the window through minimize and
                # back is the long-standing way to claim it anyway.
                try:
                    window.minimize()
                    time.sleep(0.15)
                    window.restore()
                    time.sleep(0.25)
                except Exception:
                    break
        return False
    except Exception:
        return False


def _park_pointer_over_document(sb, box: dict) -> bool:
    """Put the cursor over the middle of the document about to be scrolled.

    Uses the same origin the clicks use, so inside the enrollment frame it
    lands inside the frame rather than on the page around it. Best-effort: a
    scroll aimed at the wrong document is better than no scroll at all, and
    the caller's later checks still have to pass.
    """

    origin = _viewport_origin(sb)
    if not origin:
        return False
    try:
        centre_x = origin["x"] + origin["fx"] + float(box.get("w") or 0) / 2
        centre_y = origin["y"] + origin["fy"] + float(box.get("h") or 0) / 2
        current = pyautogui.position()
        if abs(current[0] - centre_x) < 40 and abs(current[1] - centre_y) < 40:
            return True
        pyautogui.moveTo(int(centre_x), int(centre_y), duration=random.uniform(0.1, 0.25))
        # Record it, or the next action sees the pointer somewhere it did not
        # put it and reports the run's own move as a person taking the mouse.
        _set_expected_pos((int(centre_x), int(centre_y)))
        time.sleep(random.uniform(0.04, 0.12))
        return True
    except Exception as exc:
        LOG.debug("Could not park the pointer before scrolling: %s", exc)
        return False


def scroll_to(sb, element, cfg) -> bool:
    """Bring an element into view with the real wheel rather than a script.

    `scrollIntoView` moves the page instantly and leaves no wheel events. A
    sensor watching scroll behaviour sees the jump and nothing that caused it.

    The pointer is parked over the document being scrolled first, and that is
    not tidiness. The operating system delivers a wheel event to whatever is
    under the cursor, so wheeling while the pointer sits outside the
    enrollment frame scrolls the *outer* page instead -- which moves the frame
    and quietly invalidates the offset real clicks are aimed with.

    That failure is invisible to every check downstream, because they all
    convert through the same offset and so agree with each other: the hit test
    passes, `still_on_target` passes, the run logs "clicked with the real
    mouse", and the form never moves because the click landed somewhere else.
    Measured on step 6 -- a fully valid form, an enabled Continue, a reported
    successful click, and ninety seconds of nothing.
    """
    if not AVAILABLE:
        return False
    try:
        box = sb.execute_script(
            "const r = arguments[0].getBoundingClientRect();"
            "return {top: r.top, h: window.innerHeight, w: window.innerWidth};",
            element,
        )
        if not box:
            return False

        # How far off centre it is, in notches. Chrome scrolls ~100px a notch.
        offset = box["top"] - box["h"] / 2
        notches = round(offset / 100)
        if abs(notches) < 1:
            return True

        _park_pointer_over_document(sb, box)

        for _ in range(min(abs(notches), 12)):
            pyautogui.scroll(-1 if notches > 0 else 1, _pause=False)
            time.sleep(random.uniform(0.05, 0.14))
        time.sleep(random.uniform(0.1, 0.25))
        return True
    except Exception as exc:
        LOG.debug("Real scroll failed: %s", exc)
        return False


def reading_pause(cfg) -> None:
    """Pause the way someone does when a new screen appears.

    People do not act the instant a page paints; they look at it first. Each
    form screen here is filled within a second of rendering otherwise, which is
    a timing signature no person produces.
    """
    if not AVAILABLE:
        return
    time.sleep(random.uniform(0.6, 2.2))


# Where the enrollment iframe sits, measured from the top document while the
# driver was still in it. None means "not in a frame, measure directly".
#
# This exists because _VIEWPORT_ORIGIN_JS cannot be trusted inside a frame:
# `window.outerWidth/outerHeight` there are the *top-level window's*, while
# `innerWidth/innerHeight` are the *frame's*, so the formula subtracts one
# window's chrome from another window's viewport. This frame is taller than
# the screen, which made the result wildly negative -- every real click on
# steps 5 to 10 was aimed at a point well off the monitor, "succeeded", and
# did nothing. Because the hit test ran in the same frame coordinates, it
# agreed with the bad point and reported the target was there.
# Per thread, not per module.
#
# With several workers each drives its own browser, in its own window, with
# its own enrollment frame at its own offset. A module-level value means the
# last worker to enter a frame decides where every other worker aims -- so a
# click computed for window A is delivered into window B, lands on whatever
# happens to be there, and the hit test agrees because it runs in the same
# wrong coordinates. That is the single-worker "lead 2 always failed" bug
# again, except concurrent and therefore much harder to read.
_state = threading.local()


def set_frame_origin(data: dict | None) -> None:
    """Record the frame's position, measured from the top document."""
    _state.frame_origin = data


def _get_frame_origin() -> dict | None:
    return getattr(_state, "frame_origin", None)


def reset_for_new_session() -> None:
    """Forget everything measured against the browser that has just closed.

    This module keeps two pieces of state that describe *a* browser: where the
    enrollment frame sits inside the window, and where this module last left
    the pointer. Both are module-level, so without this they survive into the
    next lead's browser -- a different window, in a different place, with no
    frame open yet.

    The consequence was precise and repeatable. Lead one entered the frame and
    recorded its offset; lead two then started on the public pages with that
    offset still in force, so every screen coordinate was computed as though
    a frame were open. The Apply Now button came out somewhere off the
    viewport and was refused as unreachable -- on the second lead of every
    run, never the first.
    """
    _state.frame_origin = None
    _state.expected_pos = None


def _viewport_origin(sb) -> dict | None:
    """The screen origin of the top-level viewport, plus the frame's offset in it."""
    origin_now = _get_frame_origin()
    if origin_now:
        return dict(origin_now)
    try:
        origin = sb.execute_script(_VIEWPORT_ORIGIN_JS)
    except Exception as exc:
        LOG.debug("Could not read the viewport origin: %s", exc)
        return None
    if not origin:
        return None
    origin["fx"] = 0.0
    origin["fy"] = 0.0
    return origin


# Why the last aim was refused, so the caller can say which of the five
# reasons fired instead of printing one generic sentence for all of them.
def last_refusal() -> str:
    """Why the most recent screen_point returned None, in this thread."""
    return getattr(_state, "last_refusal", "") or (
        "could not work out where the element is on screen"
    )


def _refuse(reason: str) -> None:
    _state.last_refusal = reason
    LOG.debug("Not aiming: %s", reason)


def aim_point(sb, element) -> tuple[float, float, dict] | None:
    """A point to click inside this element, in top-level viewport coordinates.

    Returns (x, y, origin) or None with the reason recorded by _refuse.

    This is the geometry both input paths share. real_input adds the window's
    screen origin to it and drives the desktop cursor there; cdp_input hands
    the same point straight to the browser. Extracted rather than copied on
    purpose: the rules here were each arrived at by losing leads to their
    absence -- aiming at the visible intersection rather than the corner,
    refusing a sliver too thin to hit, refusing when something is drawn over
    the target -- and a second copy would eventually stop agreeing with this
    one about them.

    A point somewhere inside the element rather than dead centre: people do
    not click the exact middle of a button every time.
    """
    try:
        origin = _viewport_origin(sb)
        box = sb.execute_script(_ELEMENT_BOX_JS, element)
    except Exception as exc:
        _refuse(f"could not read its coordinates ({exc})")
        return None

    if not origin:
        _refuse("the viewport position could not be read")
        return None
    if not box or not box.get("w") or not box.get("h"):
        _refuse("it has no width or height, so it is not laid out")
        return None

    # Aim at the part of the element that is actually on screen.
    #
    # This used to bounds-check the element's *top-left corner* and refuse
    # anything outside the viewport. Two things were wrong with that. A tall
    # element scrolled so its top sits just above the fold has a negative
    # `top` while most of it is plainly visible and clickable -- refused. And
    # the corner is not where the click goes anyway: the aim point is the
    # centre, so the check was answering a question nobody asked.
    #
    # Measured: the Apply Now button failed this check on every lead after
    # the window was resized, because a shorter viewport put its top below
    # the fold, and the run reported "could not work out where the element
    # is on screen" for a button sitting in plain view.
    #
    # So: intersect the element with the viewport, and aim inside that.
    left = box["x"] + origin["fx"]
    top = box["y"] + origin["fy"]
    right = left + box["w"]
    bottom = top + box["h"]

    visible_left = max(left, 0.0)
    visible_top = max(top, 0.0)
    visible_right = min(right, float(origin["w"]))
    visible_bottom = min(bottom, float(origin["h"]))

    visible_w = visible_right - visible_left
    visible_h = visible_bottom - visible_top

    # A few pixels is not something a person can reliably hit, and neither
    # can this -- refuse rather than clip the edge of a control.
    if visible_w < 4 or visible_h < 4:
        _refuse(
            f"only {max(visible_w, 0):.0f}x{max(visible_h, 0):.0f} px of it is "
            f"inside the {origin['w']}x{origin['h']} viewport"
        )
        return None

    # Stay inside the middle 60% of the visible part so a near-miss still lands.
    jitter_x = (random.random() - 0.5) * visible_w * 0.6
    jitter_y = (random.random() - 0.5) * visible_h * 0.6

    viewport_x = visible_left + visible_w / 2 + jitter_x - origin["fx"]
    viewport_y = visible_top + visible_h / 2 + jitter_y - origin["fy"]

    # Refuse the click rather than land it on whatever is covering the target.
    try:
        hit = sb.execute_script(_HIT_TEST_JS, element, viewport_x, viewport_y) or {}
    except Exception as exc:
        _refuse(f"the hit test could not run ({exc})")
        return None

    if not hit.get("hit"):
        _refuse(
            f"{hit.get('what') or 'something'} is drawn over it at that point, "
            f"so a real click would hit that instead"
        )
        return None

    # Top-level viewport coordinates: the frame offset added back on, so the
    # point means the same thing to the window as it does to the frame.
    return (origin["fx"] + viewport_x, origin["fy"] + viewport_y, origin)


def screen_point(sb, element) -> tuple[int, int] | None:
    """Where to aim on the physical screen for this element, or None."""
    aimed = aim_point(sb, element)
    if aimed is None:
        return None
    top_x, top_y, origin = aimed

    screen = (
        int(origin["x"] + top_x),
        int(origin["y"] + top_y),
    )
    # Every conversion here goes through the same origin, so they all agree
    # with each other whether or not it is right. When the aim is wrong the
    # only evidence is the numbers themselves, so record them.
    LOG.debug(
        "aim: frame=(%.0f,%.0f) top=(%.0f,%.0f) window=(%.0f,%.0f) "
        "viewport=%sx%s -> screen=%s",
        top_x - origin["fx"], top_y - origin["fy"], top_x, top_y,
        origin["x"], origin["y"], origin["w"], origin["h"], screen,
    )
    return screen


def still_on_target(sb, element, point: tuple[int, int]) -> bool:
    """Is the element still under the cursor, now that it has arrived?

    The hit test in `screen_point` happens before the pointer starts moving,
    and the walk there takes a moment during which lazy images, banners and
    late fonts can reflow the page. Checking once more at the final position
    is what separates "clicked the button" from "clicked where the button was".
    """
    try:
        origin = _viewport_origin(sb)
        if not origin:
            return False
        # Back into the coordinates elementFromPoint expects: strip the screen
        # origin and the frame's offset, leaving a point inside this document.
        hit = sb.execute_script(
            _HIT_TEST_JS,
            element,
            point[0] - origin["x"] - origin["fx"],
            point[1] - origin["y"] - origin["fy"],
        ) or {}
    except Exception as exc:
        LOG.debug("Could not re-check the target: %s", exc)
        return False

    if not hit.get("hit"):
        LOG.debug("Target moved before the click; %s is there now", hit.get("what"))
        return False
    return True


# Where this module last left the cursor. Anything else is somebody's hand.
# Per thread for the same reason as the frame origin, though in practice
# --real-input is refused with more than one worker: there is one cursor.
def _get_expected_pos():
    return getattr(_state, "expected_pos", None)


def _set_expected_pos(value) -> None:
    _state.expected_pos = value

# How far the cursor may sit from where we left it before we call it a person.
# A few pixels of slack: some mice report sub-pixel drift when idle.
_HAND_TOLERANCE = 12


def yield_to_user(cfg, what: str = "") -> bool:
    """If somebody has taken the mouse, wait for them to finish.

    Real input drives the one cursor this machine has, so the moment a person
    touches it there are two things steering and the run's next click lands
    wherever the hand left the pointer. That is not hypothetical: it is what
    turned a run into "clicked Continue but the screen never changed" -- a
    click delivered to empty page, reported as a mystery.

    Rather than fight for the cursor, notice and wait. The run pauses while
    the mouse is moving, resumes once it has been still for a moment, and the
    caller re-aims afterwards -- so an accidental nudge costs a few seconds
    instead of the lead.

    Returns whether a person had in fact taken over.
    """
    expected = _get_expected_pos()
    if not AVAILABLE or expected is None:
        return False

    try:
        here = pyautogui.position()
    except Exception:
        return False

    if (
        abs(here[0] - expected[0]) <= _HAND_TOLERANCE
        and abs(here[1] - expected[1]) <= _HAND_TOLERANCE
    ):
        return False

    LOG.warning(
        "Somebody is using the mouse%s -- pausing until it is idle again",
        f" ({what})" if what else "",
    )

    # Wait for the cursor to stop moving, then a beat longer in case they are
    # mid-gesture. Capped so an abandoned machine cannot stall a batch.
    deadline = time.time() + 120
    last = here
    still_since = None
    while time.time() < deadline:
        time.sleep(0.25)
        try:
            now = pyautogui.position()
        except Exception:
            break
        if abs(now[0] - last[0]) > 2 or abs(now[1] - last[1]) > 2:
            still_since = None
            last = now
            continue
        still_since = still_since or time.time()
        if time.time() - still_since >= 1.5:
            break

    LOG.info("Mouse is idle again; carrying on")
    return True


def move_to(point: tuple[int, int], cfg) -> bool:
    """Walk the real cursor to a point along a curved, uneven path."""
    if not AVAILABLE:
        return False

    # Never wrestle a person for the pointer.
    yield_to_user(cfg, "before moving")

    try:
        start = pyautogui.position()
        target_x, target_y = point

        steps = max(6, cfg.mouse_steps)
        # A bowed path rather than a straight line: the control point sits off
        # to one side, so the cursor arcs the way a hand does.
        bow_x = (random.random() - 0.5) * 160
        bow_y = (random.random() - 0.5) * 160
        control_x = (start[0] + target_x) / 2 + bow_x
        control_y = (start[1] + target_y) / 2 + bow_y

        for index in range(1, steps + 1):
            t = index / steps
            # Ease in and out, so it starts slowly, runs, and settles.
            eased = t * t * (3 - 2 * t)
            inv = 1 - eased
            x = inv * inv * start[0] + 2 * inv * eased * control_x + eased * eased * target_x
            y = inv * inv * start[1] + 2 * inv * eased * control_y + eased * eased * target_y
            pyautogui.moveTo(int(x), int(y), duration=0, _pause=False)
            time.sleep(random.uniform(0.006, 0.02))

        # A small overshoot and correction, which is what hands actually do.
        if random.random() < 0.35:
            pyautogui.moveTo(
                target_x + random.randint(-6, 6),
                target_y + random.randint(-5, 5),
                duration=0, _pause=False,
            )
            time.sleep(random.uniform(0.04, 0.11))
            pyautogui.moveTo(target_x, target_y, duration=0, _pause=False)

        time.sleep(random.uniform(0.05, 0.16))
        _set_expected_pos((int(target_x), int(target_y)))
        return True
    except Exception as exc:
        LOG.debug("Real mouse move failed: %s", exc)
        return False


def click(cfg) -> bool:
    """Press and release where the cursor already is."""
    if not AVAILABLE:
        return False

    # A click is the one action that cannot be taken back, so refuse to make
    # it if the pointer is no longer where this module put it. The caller
    # re-aims and tries again rather than clicking whatever is under a hand.
    if yield_to_user(cfg, "before clicking"):
        LOG.info("Not clicking where the pointer was left; re-aiming first")
        return False

    try:
        pyautogui.mouseDown(_pause=False)
        time.sleep(random.uniform(0.05, 0.13))  # how long a real press lasts
        pyautogui.mouseUp(_pause=False)
        return True
    except Exception as exc:
        LOG.debug("Real click failed: %s", exc)
        return False


def type_text(text: str, cfg) -> bool:
    """Type on the real keyboard, one key at a time, at a person's pace."""
    if not AVAILABLE:
        return False

    # Typing goes to whatever holds focus. If a person has just clicked
    # somewhere else, these keystrokes are the lead's details going into
    # their window, so wait rather than spray them.
    yield_to_user(cfg, "before typing")

    low, high = cfg.type_delay
    try:
        for index, char in enumerate(str(text)):
            pyautogui.write(char, _pause=False)
            time.sleep(random.uniform(low, high))
            # The occasional longer beat, the way real typing stutters.
            if index and random.random() < 0.07:
                time.sleep(random.uniform(0.2, 0.55))
        return True
    except Exception as exc:
        LOG.debug("Real typing failed: %s", exc)
        return False


def clear_field(cfg) -> bool:
    """Select all and delete, on the real keyboard."""
    if not AVAILABLE:
        return False
    try:
        pyautogui.hotkey("ctrl", "a", _pause=False)
        time.sleep(random.uniform(0.04, 0.1))
        pyautogui.press("delete", _pause=False)
        time.sleep(random.uniform(0.04, 0.1))
        return True
    except Exception as exc:
        LOG.debug("Real clear failed: %s", exc)
        return False


def idle_wander(cfg) -> None:
    """Drift the cursor a little while nothing is happening.

    A pointer that teleports between fields and is otherwise perfectly still
    is its own signal. This is cheap and only runs between actions.
    """
    if not AVAILABLE or random.random() > 0.3:
        return

    try:
        x, y = pyautogui.position()
        for _ in range(random.randint(2, 5)):
            x, y = x + random.randint(-40, 40), y + random.randint(-30, 30)
            pyautogui.moveTo(x, y, duration=0, _pause=False)
            time.sleep(random.uniform(0.02, 0.07))
        # Record where this left the cursor. Without it the next action sees
        # the pointer somewhere it did not put it and reports the run's own
        # wandering as a person's hand -- which is exactly what happened:
        # every action after a wander paused for a mouse nobody had touched.
        _set_expected_pos((int(x), int(y)))
    except Exception:
        pass
