import random
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

    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
    AVAILABLE = True
except Exception as exc:  # pragma: no cover - depends on the display
    pyautogui = None
    AVAILABLE = False
    LOG.debug("pyautogui unavailable, real input disabled: %s", exc)


_VIEWPORT_ORIGIN_JS = """
return {
  x: window.screenX + (window.outerWidth - window.innerWidth) / 2,
  y: window.screenY + (window.outerHeight - window.innerHeight),
  w: window.innerWidth,
  h: window.innerHeight
};
"""

_ELEMENT_BOX_JS = """
const el = arguments[0];
const r = el.getBoundingClientRect();
return {x: r.left, y: r.top, w: r.width, h: r.height};
"""

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
    if not getattr(cfg, "real_input", False):
        return False
    if not AVAILABLE:
        LOG.warning("real_input is on but pyautogui is unavailable; using synthetic input")
        return False
    if cfg.headless:
        LOG.warning("real_input needs a visible window; headless run uses synthetic input")
        return False
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
    stem = (title or "")[:40]
    if not stem:
        return []
    try:
        return [w for w in pygetwindow.getAllWindows() if w.title and stem in w.title]
    except Exception:
        return []


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
    if not WINDOWS_AVAILABLE:
        return False
    try:
        title = sb.get_title() or ""
    except Exception:
        return False

    try:
        candidates = _matching_windows(title)
        if not candidates:
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
                refreshed = _matching_windows(title) or _browser_windows()
                if refreshed:
                    window = refreshed[0]
            except Exception:
                pass

        LOG.debug("Browser window would not come to the front")
        return False
    except Exception as exc:
        LOG.debug("Could not focus the browser window: %s", exc)
        return False


def _try_activate(window) -> bool:
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
                LOG.debug("activate() reported %r; checking the window itself", exc)

            time.sleep(random.uniform(0.12, 0.3))
            try:
                if window.isActive:
                    return True
            except Exception:
                pass

            if attempt == 0:
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
    global _expected_pos

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
        _expected_pos = (int(centre_x), int(centre_y))
        time.sleep(random.uniform(0.04, 0.12))
        return True
    except Exception as exc:
        LOG.debug("Could not park the pointer before scrolling: %s", exc)
        return False


def scroll_to(sb, element, cfg) -> bool:
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
    if not AVAILABLE:
        return
    time.sleep(random.uniform(0.6, 2.2))


_frame_origin: dict | None = None


def set_frame_origin(data: dict | None) -> None:
    global _frame_origin
    _frame_origin = data


def reset_for_new_session() -> None:
    global _frame_origin, _expected_pos
    _frame_origin = None
    _expected_pos = None


def _viewport_origin(sb) -> dict | None:
    if _frame_origin:
        return dict(_frame_origin)
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


_last_refusal: str = ""


def last_refusal() -> str:
    return _last_refusal or "could not work out where the element is on screen"


def _refuse(reason: str) -> None:
    global _last_refusal
    _last_refusal = reason
    LOG.debug("Not aiming: %s", reason)


def screen_point(sb, element) -> tuple[int, int] | None:
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

    if visible_w < 4 or visible_h < 4:
        _refuse(
            f"only {max(visible_w, 0):.0f}x{max(visible_h, 0):.0f} px of it is "
            f"inside the {origin['w']}x{origin['h']} viewport"
        )
        return None

    jitter_x = (random.random() - 0.5) * visible_w * 0.6
    jitter_y = (random.random() - 0.5) * visible_h * 0.6

    viewport_x = visible_left + visible_w / 2 + jitter_x - origin["fx"]
    viewport_y = visible_top + visible_h / 2 + jitter_y - origin["fy"]

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

    screen = (
        int(origin["x"] + origin["fx"] + viewport_x),
        int(origin["y"] + origin["fy"] + viewport_y),
    )

    LOG.debug(
        "aim: doc=(%.0f,%.0f) box=(%.0f,%.0f %.0fx%.0f) "
        "origin=(%.0f,%.0f) frame=(%.0f,%.0f) viewport=%sx%s -> screen=%s",
        viewport_x, viewport_y, box["x"], box["y"], box["w"], box["h"],
        origin["x"], origin["y"], origin["fx"], origin["fy"],
        origin["w"], origin["h"], screen,
    )
    return screen


def still_on_target(sb, element, point: tuple[int, int]) -> bool:
    try:
        origin = _viewport_origin(sb)
        if not origin:
            return False
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


_expected_pos: tuple[int, int] | None = None

_HAND_TOLERANCE = 12


def yield_to_user(cfg, what: str = "") -> bool:
    if not AVAILABLE or _expected_pos is None:
        return False

    try:
        here = pyautogui.position()
    except Exception:
        return False

    if (
        abs(here[0] - _expected_pos[0]) <= _HAND_TOLERANCE
        and abs(here[1] - _expected_pos[1]) <= _HAND_TOLERANCE
    ):
        return False

    LOG.warning(
        "Somebody is using the mouse%s -- pausing until it is idle again",
        f" ({what})" if what else "",
    )

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
    if not AVAILABLE:
        return False

    yield_to_user(cfg, "before moving")

    global _expected_pos
    try:
        start = pyautogui.position()
        target_x, target_y = point

        steps = max(6, cfg.mouse_steps)
        bow_x = (random.random() - 0.5) * 160
        bow_y = (random.random() - 0.5) * 160
        control_x = (start[0] + target_x) / 2 + bow_x
        control_y = (start[1] + target_y) / 2 + bow_y

        for index in range(1, steps + 1):
            t = index / steps
            eased = t * t * (3 - 2 * t)
            inv = 1 - eased
            x = inv * inv * start[0] + 2 * inv * eased * control_x + eased * eased * target_x
            y = inv * inv * start[1] + 2 * inv * eased * control_y + eased * eased * target_y
            pyautogui.moveTo(int(x), int(y), duration=0, _pause=False)
            time.sleep(random.uniform(0.006, 0.02))

        if random.random() < 0.35:
            pyautogui.moveTo(
                target_x + random.randint(-6, 6),
                target_y + random.randint(-5, 5),
                duration=0, _pause=False,
            )
            time.sleep(random.uniform(0.04, 0.11))
            pyautogui.moveTo(target_x, target_y, duration=0, _pause=False)

        time.sleep(random.uniform(0.05, 0.16))
        _expected_pos = (int(target_x), int(target_y))
        return True
    except Exception as exc:
        LOG.debug("Real mouse move failed: %s", exc)
        return False


def click(cfg) -> bool:
    if not AVAILABLE:
        return False

    if yield_to_user(cfg, "before clicking"):
        LOG.info("Not clicking where the pointer was left; re-aiming first")
        return False

    try:
        pyautogui.mouseDown(_pause=False)
        time.sleep(random.uniform(0.05, 0.13))
        pyautogui.mouseUp(_pause=False)
        return True
    except Exception as exc:
        LOG.debug("Real click failed: %s", exc)
        return False


def type_text(text: str, cfg) -> bool:
    if not AVAILABLE:
        return False

    yield_to_user(cfg, "before typing")

    low, high = cfg.type_delay
    try:
        for index, char in enumerate(str(text)):
            pyautogui.write(char, _pause=False)
            time.sleep(random.uniform(low, high))
            if index and random.random() < 0.07:
                time.sleep(random.uniform(0.2, 0.55))
        return True
    except Exception as exc:
        LOG.debug("Real typing failed: %s", exc)
        return False


def clear_field(cfg) -> bool:
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
    if not AVAILABLE or random.random() > 0.3:
        return

    global _expected_pos
    try:
        x, y = pyautogui.position()
        for _ in range(random.randint(2, 5)):
            x, y = x + random.randint(-40, 40), y + random.randint(-30, 30)
            pyautogui.moveTo(x, y, duration=0, _pause=False)
            time.sleep(random.uniform(0.02, 0.07))
        _expected_pos = (int(x), int(y))
    except Exception:
        pass
