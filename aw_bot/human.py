import math
import random
import time

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from . import real_input
from .config import RunConfig
from .errors import RealInputError
from .logs import LOG

DWELL = {
    "micro": (0.04, 0.32),
    "short": (0.10, 0.50),
    "medium": (0.30, 1.20),
    "long": (0.60, 2.00),
}

_NEIGHBOURS = {
    "a": "qwsz", "b": "vghn", "c": "xdfv", "d": "serfcx", "e": "wsdr",
    "f": "drtgvc", "g": "ftyhbv", "h": "gyujnb", "i": "ujko", "j": "huikmn",
    "k": "jiolm", "l": "kop", "m": "njk", "n": "bhjm", "o": "iklp",
    "p": "ol", "q": "wa", "r": "edft", "s": "awedxz", "t": "rfgy",
    "u": "yhji", "v": "cfgb", "w": "qase", "x": "zsdc", "y": "tghu",
    "z": "asx",
}


_tempo = 1.0


def new_operator() -> float:
    global _tempo
    _tempo = min(1.3, max(0.55, random.lognormvariate(0.0, 0.26)))
    return _tempo


def _skewed(low: float, high: float, scale: float = 1.0) -> float:
    low, high = float(low), float(high)
    if high <= low:
        return max(0.0, low * scale)

    spread = high - low
    draw = random.lognormvariate(math.log(spread * 0.38 + 1e-6), 0.55)
    value = low + draw

    if value > high:
        value = (
            high - abs(random.gauss(0, spread * 0.12))
            if random.random() > 0.06
            else min(value, high + spread * 1.5)
        )

    return max(low * 0.7, value) * scale * _tempo


def pause(cfg: RunConfig, scale: float = 1.0) -> None:
    if not cfg.human_like:
        return
    low, high = cfg.action_pause
    time.sleep(_skewed(low, high, scale))


def dwell(cfg: RunConfig, kind: str = "short") -> None:
    if not cfg.human_like:
        return
    low, high = DWELL.get(kind, DWELL["short"])
    time.sleep(_skewed(low, high))


def rest(sb, cfg: RunConfig, kind: str = "short") -> None:
    if not cfg.human_like:
        return

    low, high = DWELL.get(kind, DWELL["short"])
    total = _skewed(low, high)

    if total < 0.6:
        time.sleep(total)
        return

    spent = 0.0
    restlessness = random.uniform(0.15, 0.75)

    while spent < total:
        slice_ = min(_skewed(0.2, 1.4), total - spent)
        time.sleep(slice_)
        spent += slice_
        if random.random() < restlessness:
            idle_drift(sb, cfg)


def idle_drift(sb, cfg: RunConfig) -> None:
    if not cfg.human_like:
        return

    kind = random.choices(
        ("tremor", "settle", "nudge", "still"), weights=(46, 24, 20, 10), k=1
    )[0]
    if kind == "still":
        return

    try:
        chain = ActionChains(sb.driver)

        if kind == "tremor":
            for _ in range(random.randint(2, 5)):
                chain.move_by_offset(random.randint(-3, 3), random.randint(-3, 3))
                chain.pause(_skewed(0.02, 0.16))

        elif kind == "settle":
            target_x = random.randint(-70, 70)
            target_y = random.randint(-45, 45)
            control_x = target_x * random.uniform(0.2, 0.8) + random.randint(-18, 18)
            control_y = target_y * random.uniform(0.2, 0.8) + random.randint(-14, 14)
            steps = random.randint(5, 11)
            prev_x = prev_y = 0.0
            for i in range(1, steps + 1):
                t = i / steps
                cur_x = 2 * (1 - t) * t * control_x + t * t * target_x
                cur_y = 2 * (1 - t) * t * control_y + t * t * target_y
                chain.move_by_offset(int(cur_x - prev_x), int(cur_y - prev_y))
                chain.pause(random.uniform(0.008, 0.03) + t * 0.035)
                prev_x, prev_y = cur_x, cur_y

        else:
            chain.move_by_offset(random.randint(-22, 22), random.randint(-16, 16))
            chain.pause(_skewed(0.05, 0.3))

        chain.perform()
    except Exception:
        pass


def warm_up(sb, cfg: RunConfig, duration: float | None = None) -> None:
    if not cfg.human_like or not cfg.warm_up_seconds:
        return

    low, high = cfg.warm_up_seconds
    duration = duration if duration is not None else random.uniform(low, high)
    if duration <= 0:
        return

    driver = sb.driver
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        ActionChains(driver).move_to_element(body).perform()
        time.sleep(random.uniform(0.2, 0.5))
    except Exception:
        time.sleep(min(duration, 2.0))
        return

    LOG.debug("Warming up the pointer for %.1fs", duration)
    end = time.time() + duration
    while time.time() < end:
        try:
            dx, dy = random.randint(-180, 180), random.randint(-120, 120)
            steps = random.randint(5, 12)
            chain = ActionChains(driver)
            for _ in range(steps):
                chain.move_by_offset(
                    dx // steps + random.randint(-4, 4),
                    dy // steps + random.randint(-4, 4),
                )
                chain.pause(random.uniform(0.01, 0.07))
            chain.perform()

            time.sleep(random.uniform(0.12, 0.55))

            if random.random() < 0.25:
                driver.execute_script(
                    "window.scrollBy(0, arguments[0]);", random.randint(-60, 80)
                )
                time.sleep(random.uniform(0.1, 0.3))
        except Exception:
            break


def smooth_scroll(sb, delta: float, cfg: RunConfig) -> None:
    delta = float(delta or 0)
    if abs(delta) < 1:
        return

    if not cfg.human_like:
        try:
            sb.execute_script("window.scrollBy(0, arguments[0]);", delta)
        except Exception:
            pass
        return

    steps = max(4, min(18, int(abs(delta) / random.uniform(38, 70))))
    done = 0.0
    try:
        for index in range(1, steps + 1):
            progress = 1 - (1 - index / steps) ** 2
            target = delta * progress
            hop = target - done
            hop += random.uniform(-2.0, 2.0)
            sb.execute_script("window.scrollBy(0, arguments[0]);", hop)
            done += hop
            time.sleep(random.uniform(0.012, 0.045))

        remainder = delta - done
        if abs(remainder) >= 1:
            sb.execute_script("window.scrollBy(0, arguments[0]);", remainder)

        time.sleep(random.uniform(0.05, 0.18))
    except Exception as exc:
        LOG.debug("Smooth scroll failed (%s); jumping instead", exc)
        try:
            sb.execute_script("window.scrollBy(0, arguments[0]);", delta - done)
        except Exception:
            pass


def scroll_element_into_view(sb, element, cfg: RunConfig) -> None:
    try:
        offset = sb.driver.execute_script(
            "const r = arguments[0].getBoundingClientRect();"
            "return r.top + r.height / 2 - window.innerHeight / 2;",
            element,
        )
    except Exception:
        return
    if offset is None:
        return
    smooth_scroll(sb, offset, cfg)


def human_click(sb, selector: str, cfg: RunConfig, timeout: int | None = None) -> None:
    timeout = timeout or cfg.page_timeout

    if not cfg.human_like:
        sb.click(selector, timeout=timeout)
        return

    element = sb.wait_for_element_visible(selector, timeout=timeout)

    if real_input.should_use(cfg):
        if _real_click(sb, element, selector, cfg):
            LOG.info("Clicked %s with the real mouse", selector)
            return
        _refuse_synthetic("click", selector, cfg)

    _drift_to(sb, selector, cfg)
    pause(cfg, 0.4)

    if _pressed_click(sb, selector, cfg):
        return

    try:
        sb.click(selector, timeout=timeout)
    except WebDriverException:
        LOG.debug("Pointer click on %s failed; clicking directly", selector)
        sb.click(selector, timeout=timeout)


def _blame(cfg: RunConfig, reason: str, selector: str) -> None:
    LOG.warning("Real input on %s: %s", selector, reason)


def _refuse_synthetic(what: str, selector: str, cfg: RunConfig) -> None:
    if getattr(cfg, "allow_synthetic_fallback", False):
        LOG.warning(
            "Could not %s %s for real; falling back to synthetic input "
            "(--allow-synthetic-fallback is on)", what, selector,
        )
        return

    raise RealInputError(
        f"Could not {what} {selector} with the real mouse and keyboard after "
        f"three attempts. Refusing to fall back to synthetic input: those "
        f"events carry no pointer path and isTrusted=false, which is the thing "
        f"--real-input is there to avoid. Check that the browser window is in "
        f"front, fully on screen, and that nothing else is taking the pointer. "
        f"Pass --allow-synthetic-fallback to continue anyway."
    )


def _pressed_click(sb, selector: str, cfg: RunConfig) -> bool:
    try:
        if sb.driver.execute_script("return window.self !== window.top;"):
            return False
    except Exception:
        return False

    try:
        element = sb.find_element(selector)
        chain = ActionChains(sb.driver)
        chain.move_to_element(element)
        chain.pause(random.uniform(0.03, 0.12))
        chain.click_and_hold(element)
        chain.pause(random.uniform(0.06, 0.14))
        chain.release(element)
        chain.perform()
        return True
    except Exception as exc:
        LOG.debug("Pressed click on %s not possible (%s); plain click", selector, exc)
        return False


def human_type(sb, selector: str, value: str, cfg: RunConfig) -> None:
    if not cfg.human_like:
        sb.type(selector, value)
        return

    element = sb.wait_for_element_visible(selector, timeout=cfg.page_timeout)

    if real_input.should_use(cfg):
        if _real_type(sb, element, selector, value, cfg):
            LOG.info("Typed %s on the real keyboard", selector)
            return
        _refuse_synthetic("type into", selector, cfg)

    sb.wait_for_element_visible(selector, timeout=cfg.page_timeout)
    _drift_to(sb, selector, cfg)
    pause(cfg, 0.3)

    element = sb.wait_for_element_visible(selector, timeout=cfg.page_timeout)
    try:
        element.click()
        element.clear()
    except WebDriverException:
        sb.type(selector, "")

    text = str(value)
    low, high = cfg.type_delay

    tempo = random.uniform(0.82, 1.28) * _tempo
    for index, char in enumerate(text):
        try:
            if (
                cfg.typo_chance
                and index
                and char.isalpha()
                and random.random() < cfg.typo_chance
            ):
                wrong = _neighbour(char)
                if wrong:
                    element.send_keys(wrong)
                    time.sleep(random.uniform(0.10, 0.28))
                    element.send_keys(Keys.BACK_SPACE)
                    time.sleep(random.uniform(0.12, 0.30))

            element.send_keys(char)
        except WebDriverException:
            LOG.debug("Lost %s while typing; filling the remainder directly", selector)
            sb.type(selector, value)
            return

        _sync_input(sb, element)

        time.sleep(_keystroke_delay(text, index, low, high, tempo))

    _commit_field(sb, element)


def _keystroke_delay(
    text: str, index: int, low: float, high: float, tempo: float
) -> float:
    char = text[index]
    previous = text[index - 1] if index else ""

    middle = (low + high) / 2
    delay = (middle * tempo) + random.expovariate(1 / max(middle * 0.45, 0.01))
    delay = max(low * 0.6, min(delay, high * 3.5))

    if char.isupper() and not previous.isupper():
        delay += random.uniform(0.04, 0.13)

    if char.isdigit():
        delay *= 0.7 if previous.isdigit() else 1.25

    if previous in " @.,-/":
        delay += random.uniform(0.04, 0.16)

    if char == " ":
        delay += random.uniform(0.05, 0.18)

    if index and random.random() < 0.06:
        delay += random.uniform(0.22, 0.65)

    return delay


def _neighbour(char: str) -> str:
    options = _NEIGHBOURS.get(char.lower(), "")
    if not options:
        return ""
    wrong = random.choice(options)
    return wrong.upper() if char.isupper() else wrong


def _sync_input(sb, element) -> None:
    return


def _commit_field(sb, element) -> None:
    try:
        element.send_keys(Keys.TAB)
        return
    except WebDriverException:
        LOG.debug("Could not Tab out of the field; dispatching change instead")

    try:
        sb.driver.execute_script(
            "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));", element
        )
    except WebDriverException:
        pass


_SELECT_STATE_JS = """
const el = arguments[0], wanted = arguments[1];
const values = Array.from(el.options).map(o => o.value);
return {
  count: values.length,
  selected: el.selectedIndex,
  target: values.indexOf(wanted),
  value: el.value,
  disabled: el.disabled
};
"""


def human_select(sb, selector: str, option_value: str, cfg: RunConfig) -> None:
    if cfg.human_like:
        sb.wait_for_element_visible(selector, timeout=cfg.page_timeout)

    if real_input.should_use(cfg) and _real_select(sb, selector, option_value, cfg):
        LOG.info("Chose %s on %s with the real keyboard", option_value, selector)
        return

    if cfg.human_like:
        _drift_to(sb, selector, cfg)
        pause(cfg, 0.3)

    sb.select_option_by_value(selector, option_value)

    if cfg.human_like:
        pause(cfg, 0.3)


def _real_select(sb, selector: str, option_value: str, cfg: RunConfig) -> bool:
    try:
        element = sb.wait_for_element_visible(selector, timeout=cfg.page_timeout)
        state = sb.execute_script(_SELECT_STATE_JS, element, str(option_value)) or {}
    except WebDriverException as exc:
        LOG.debug("Could not read %s before choosing: %s", selector, exc)
        return False

    target = state.get("target", -1)
    if state.get("disabled") or target is None or target < 0:
        return False

    if state.get("value") == str(option_value):
        return True

    if not _real_click(sb, element, selector, cfg):
        return False

    steps = target - int(state.get("selected", 0) or 0)
    key = Keys.ARROW_DOWN if steps > 0 else Keys.ARROW_UP
    remaining = abs(steps)
    if remaining > 40:
        return False

    try:
        for index in range(remaining):
            element.send_keys(key)
            left = remaining - index
            time.sleep(random.uniform(0.05, 0.16) + (0.12 if left <= 2 else 0.0))
        element.send_keys(Keys.ENTER)
    except WebDriverException as exc:
        LOG.debug("Arrowing through %s failed: %s", selector, exc)
        return False

    pause(cfg, 0.3)

    try:
        landed = sb.execute_script("return arguments[0].value;", element)
    except WebDriverException:
        return False
    if landed != str(option_value):
        LOG.debug(
            "%s ended on %r rather than %r; using the scripted path",
            selector, landed, option_value,
        )
        return False
    return True


def _drift_to(sb, selector: str, cfg: RunConfig) -> None:
    try:
        sb.scroll_to(selector)
    except Exception:
        pass

    try:
        element = sb.find_element(selector)
    except Exception as exc:
        LOG.debug("Could not find %s to drift the pointer to it: %s", selector, exc)
        return

    try:
        sb.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center', inline:'center'});", element
        )
    except Exception:
        pass

    room = _room_around(sb, element)
    if room is None:
        return

    try:
        start_x = _offset_within(room["left"], room["right"], 280, 30)
        start_y = _offset_within(room["up"], room["down"], 160, 20)
        if start_x == 0 and start_y == 0:
            start_y = min(20, room["up"]) or min(20, room["down"])

        cp_x = start_x * random.uniform(0.2, 0.8) + random.uniform(-25, 25)
        cp_y = start_y * random.uniform(0.2, 0.8) + random.uniform(-25, 25)
        cp_x = max(-room["left"], min(room["right"], cp_x))
        cp_y = max(-room["up"], min(room["down"], cp_y))

        steps = max(4, cfg.mouse_steps)
        chain = ActionChains(sb.driver)
        chain.move_to_element_with_offset(element, start_x, start_y)

        prev_x, prev_y = float(start_x), float(start_y)
        for i in range(1, steps + 1):
            t = i / steps
            cur_x = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * cp_x
            cur_y = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * cp_y
            cur_x += random.uniform(-1.5, 1.5)
            cur_y += random.uniform(-1.5, 1.5)
            cur_x = max(-room["left"], min(room["right"], cur_x))
            cur_y = max(-room["up"], min(room["down"], cur_y))

            chain.move_by_offset(int(cur_x - prev_x), int(cur_y - prev_y))
            edge = min(t, 1 - t)
            chain.pause(random.uniform(0.004, 0.010) + (0.5 - edge) * 0.02)
            prev_x, prev_y = cur_x, cur_y

        chain.move_to_element(element)
        chain.pause(random.uniform(0.05, 0.15))
        chain.perform()
    except Exception as exc:
        LOG.debug("Could not drift the pointer to %s: %s", selector, exc)

        if room.get("framed") and "out of bounds" in str(exc).lower():
            from .page_utils import bring_framed_element_into_view

            if bring_framed_element_into_view(sb, selector, cfg):
                try:
                    element = sb.find_element(selector)
                except Exception:
                    return
                _short_drift(sb, element, selector)
                return

        _short_drift(sb, element, selector)


def _short_drift(sb, element, selector: str) -> None:
    try:
        chain = ActionChains(sb.driver)
        chain.move_to_element(element)
        for _ in range(random.randint(2, 4)):
            chain.move_by_offset(random.randint(-6, 6), random.randint(-4, 4))
            chain.pause(random.uniform(0.02, 0.09))
        chain.move_to_element(element)
        chain.pause(random.uniform(0.04, 0.12))
        chain.perform()
    except Exception as exc:
        LOG.debug("Short drift to %s did not work either: %s", selector, exc)


def _room_around(sb, element) -> dict | None:
    try:
        box = sb.driver.execute_script(
            """
            const r = arguments[0].getBoundingClientRect();
            return {cx: r.left + r.width / 2, cy: r.top + r.height / 2,
                    w: window.innerWidth, h: window.innerHeight,
                    framed: window.self !== window.top};
            """,
            element,
        )
    except Exception:
        return None

    if not box or not box.get("w") or not box.get("h"):
        return None

    margin = 4
    room = {
        "left": max(0, int(box["cx"] - margin)),
        "right": max(0, int(box["w"] - box["cx"] - margin)),
        "up": max(0, int(box["cy"] - margin)),
        "down": max(0, int(box["h"] - box["cy"] - margin)),
        "framed": bool(box.get("framed")),
    }

    if room["framed"]:
        for side in ("left", "right", "up", "down"):
            room[side] = min(room[side], 40)

    return room


def _offset_within(back: int, forward: int, reach: int, minimum: int) -> int:
    back, forward = min(back, reach), min(forward, reach)
    if back < minimum and forward < minimum:
        return 0
    if back < minimum:
        return random.randint(minimum, forward)
    if forward < minimum:
        return -random.randint(minimum, back)
    if random.random() < 0.5:
        return -random.randint(minimum, back)
    return random.randint(minimum, forward)


def _will_receive_keys(sb, element, timeout: float = 1.0) -> bool:
    deadline = time.time() + timeout
    while True:
        try:
            state = sb.execute_script(
                "return {inField: document.activeElement === arguments[0],"
                "        windowFocused: document.hasFocus(),"
                "        framed: window.self !== window.top};",
                element,
            ) or {}
        except WebDriverException:
            return False

        if state.get("inField"):
            if state.get("framed") or state.get("windowFocused"):
                return True

        if time.time() >= deadline:
            return False
        time.sleep(0.1)


def _reach_framed(sb, selector: str, cfg: RunConfig) -> bool:
    try:
        from .page_utils import bring_framed_element_into_view

        return bool(bring_framed_element_into_view(sb, selector, cfg))
    except Exception as exc:
        LOG.debug("Could not bring %s into reach: %s", selector, exc)
        return False


def _real_click(sb, element, selector: str, cfg: RunConfig) -> bool:
    for attempt in (1, 2, 3):
        if not real_input.focus_window(sb):
            _blame(cfg, "could not bring the browser window to the front", selector)
            if attempt < 3:
                continue
            return False

        real_input.scroll_to(sb, element, cfg)
        point = real_input.screen_point(sb, element)
        if point is None and _reach_framed(sb, selector, cfg):
            point = real_input.screen_point(sb, element)
        if point is None:
            _blame(cfg, real_input.last_refusal(), selector)
            return False
        if not real_input.move_to(point, cfg):
            _blame(cfg, "could not move the pointer there", selector)
            return False
        pause(cfg, 0.3)

        if not real_input.still_on_target(sb, element, point):
            if attempt < 3:
                LOG.debug("%s moved out from under the pointer; aiming again", selector)
                continue
            _blame(
                cfg,
                "the pointer arrived and something else was under it "
                "(the page moved, or the window is not where it was measured)",
                selector,
            )
            return False

        if not real_input.click(cfg):
            if attempt < 3:
                LOG.info("Re-aiming at %s after the pointer was taken", selector)
                continue
            _blame(cfg, "the pointer was taken by somebody else mid-click", selector)
            return False
        break
    else:
        return False

    LOG.debug("Real-clicked %s", selector)
    real_input.idle_wander(cfg)
    return True


def _real_type(sb, element, selector: str, value: str, cfg: RunConfig) -> bool:
    for attempt in (1, 2, 3):
        if attempt > 1:
            LOG.debug("Aiming at %s again (attempt %d)", selector, attempt)
            pause(cfg, 0.5)
        if _real_type_once(sb, element, selector, value, cfg):
            return True
        try:
            element = sb.wait_for_element_visible(selector, timeout=cfg.page_timeout)
        except Exception:
            return False
    return False


def _real_type_once(sb, element, selector: str, value: str, cfg: RunConfig) -> bool:
    if not real_input.focus_window(sb):
        _blame(cfg, "could not bring the browser window to the front", selector)
        return False

    real_input.scroll_to(sb, element, cfg)
    point = real_input.screen_point(sb, element)
    if point is None and _reach_framed(sb, selector, cfg):
        point = real_input.screen_point(sb, element)
    if point is None:
        _blame(cfg, real_input.last_refusal(), selector)
        return False
    if not real_input.move_to(point, cfg):
        _blame(cfg, "could not move the pointer to the field", selector)
        return False
    if not real_input.still_on_target(sb, element, point):
        _blame(
            cfg,
            "the pointer arrived and the field was not under it -- the page "
            "moved, or the window is not where it was measured",
            selector,
        )
        return False
    if not real_input.click(cfg):
        _blame(cfg, "could not click into the field to focus it", selector)
        return False

    pause(cfg, 0.25)

    if not _will_receive_keys(sb, element):
        _blame(
            cfg,
            "the caret is not in this field, or the browser window is not in "
            "front, so nothing was typed",
            selector,
        )
        return False

    real_input.clear_field(cfg)

    if not real_input.type_text(value, cfg):
        _blame(cfg, "the keyboard would not send the characters", selector)
        return False

    if not _field_holds(element, value):
        _blame(
            cfg,
            f"typed {len(str(value))} character(s) and the field did not take "
            f"them, so the keystrokes went to another window",
            selector,
        )
        return False

    LOG.debug("Real-typed into %s", selector)
    return True


def _field_holds(element, value, timeout: float = 2.0) -> bool:
    expected = str(value).strip()
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            actual = (element.get_attribute("value") or "").strip()
        except WebDriverException:
            return False

        if actual == expected:
            return True

        try:
            limit = element.get_attribute("maxlength") or ""
        except WebDriverException:
            limit = ""
        if limit.isdigit() and int(limit) > 0 and actual == expected[: int(limit)]:
            return True

        time.sleep(0.1)

    return False
