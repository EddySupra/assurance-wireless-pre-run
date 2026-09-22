"""Human-paced typing, clicking and mouse movement.

Three reasons this exists: an agent watching the run can follow what it's
doing and take over mid-form; instant field fills are one of the cheaper
signals a bot-detection layer looks for; and Akamai's sensor -- which this
site runs, and which is what `/akam/` in the GoLogin notes refers to -- does
not score a page on its fingerprint alone. It scores the *session*: pointer
paths, the gaps between keystrokes, whether anything moved before the form
was filled. A browser with a flawless fingerprint that fills eleven fields in
two seconds without the mouse ever moving still reads as a bot, which is why
the stealth module on its own is only half the job.

So the pacing here is not decoration. Timings are drawn from ranges rather
than fixed, moves are curved rather than straight, and typing carries the
hesitations and occasional corrections that real typing has.

Every helper degrades to the plain SeleniumBase call when cfg.human_like is
off (`--fast`) or when the fancy path fails, so pacing never costs reliability.
"""

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

# Four tiers of idling, because a person's pauses are not one distribution.
# Between two keystrokes it is milliseconds; between reading a question and
# answering it, seconds. A run that uses a single range for both has a
# recognisable rhythm regardless of how wide that range is.
DWELL = {
    "micro": (0.04, 0.32),    # within a field
    "short": (0.12, 1.10),    # between fields
    "medium": (0.40, 3.00),   # between sections
    "long": (1.00, 7.00),     # reading a screen before answering it
}

# Neighbours on a QWERTY keyboard. A typo that a real hand makes is the key
# next to the intended one, not a random letter from the alphabet.
_NEIGHBOURS = {
    "a": "qwsz", "b": "vghn", "c": "xdfv", "d": "serfcx", "e": "wsdr",
    "f": "drtgvc", "g": "ftyhbv", "h": "gyujnb", "i": "ujko", "j": "huikmn",
    "k": "jiolm", "l": "kop", "m": "njk", "n": "bhjm", "o": "iklp",
    "p": "ol", "q": "wa", "r": "edft", "s": "awedxz", "t": "rfgy",
    "u": "yhji", "v": "cfgb", "w": "qase", "x": "zsdc", "y": "tghu",
    "z": "asx",
}


# The person at the keyboard, for this lead.
#
# A run that draws every gap from the same range has one pace, and that pace is
# the run's signature however wide the range is: across a batch every lead's
# distribution is identical, because it is. Real operators differ from each
# other, and the same operator differs across a morning.
#
# Reset by new_operator() when a lead starts.
_tempo = 1.0


def new_operator() -> float:
    """Pick a pace for this lead. Returns it, mostly for the log."""
    global _tempo
    # Log-normal around 1.0: most leads near the middle, a few notably brisker
    # or more hesitant, and no hard edges at either end.
    _tempo = min(2.2, max(0.55, random.lognormvariate(0.0, 0.26)))
    return _tempo


def _skewed(low: float, high: float, scale: float = 1.0) -> float:
    """A delay between `low` and `high`, shaped the way waiting actually is.

    `random.uniform` gives a rectangle: every gap equally likely, a hard floor
    and a hard ceiling. Nothing a person does has that shape. Real pauses
    cluster a little above the minimum and trail off, with the occasional long
    one where attention wandered -- which is a log-normal, near enough.

    The ceiling is respected most of the time but not absolutely: a maximum
    that is never exceeded is itself a measurable edge, so a few per cent of
    draws run past it.
    """
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
    """Idle the way a person does between actions."""
    if not cfg.human_like:
        return
    low, high = cfg.action_pause
    time.sleep(_skewed(low, high, scale))


def dwell(cfg: RunConfig, kind: str = "short") -> None:
    """Idle for one of the named tiers. See DWELL."""
    if not cfg.human_like:
        return
    low, high = DWELL.get(kind, DWELL["short"])
    time.sleep(_skewed(low, high))


def rest(sb, cfg: RunConfig, kind: str = "short") -> None:
    """Idle the way a person does -- which is to say, not perfectly still.

    `dwell` sleeps, and a sleeping run produces a viewport where the pointer's
    position is a step function: it teleports to a field, freezes for two
    seconds, teleports to the next. Between those jumps the page records
    nothing at all.

    Real hands rest on the mouse and the mouse drifts. Over a form with eleven
    fields the difference is the difference between a dozen isolated pointer
    events and a continuous track, and a continuous track is what a behavioural
    scorer is built to expect. This costs nothing the sleep was not already
    costing -- the drift happens *during* the wait, not after it.
    """
    if not cfg.human_like:
        return

    low, high = DWELL.get(kind, DWELL["short"])
    total = _skewed(low, high)

    # Short waits are not worth splitting; a twitch every 200ms is its own
    # pattern and nothing is gained by it.
    if total < 0.6:
        time.sleep(total)
        return

    spent = 0.0
    # How fidgety this particular wait is. Deciding it once per wait rather
    # than per slice gives the pause a character instead of an average.
    restlessness = random.uniform(0.15, 0.75)

    while spent < total:
        # Uneven slices, so the gaps between movements are not themselves
        # regular. Never a click: whatever is under the pointer while the form
        # is thinking is not ours to press.
        slice_ = min(_skewed(0.2, 1.4), total - spent)
        time.sleep(slice_)
        spent += slice_
        if random.random() < restlessness:
            idle_drift(sb, cfg)


def idle_drift(sb, cfg: RunConfig) -> None:
    """Pointer movement of the kind a hand resting on a mouse produces.

    Four different things, chosen at random, because a hand at rest does not
    do one thing. The version this replaces always did the same one -- two or
    three equal-ish hops -- which over a run is as much a pattern as not
    moving at all.

        tremor    a few pixels of shake without going anywhere. The commonest,
                  because it is what a hand actually does.
        settle    a short curved drift to somewhere nearby, decelerating, the
                  way a hand repositions without thinking about it.
        nudge     one small deliberate movement, as if adjusting grip.
        still     nothing. A hand is sometimes simply still, and a run that
                  twitches at every opportunity has its own rhythm.

    Every failure is swallowed: this runs inside wait loops that must keep
    running whatever the page does.
    """
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
            # A curve rather than a line: sample a quadratic toward a nearby
            # point, easing out as it arrives.
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

        else:  # nudge
            chain.move_by_offset(random.randint(-22, 22), random.randint(-16, 16))
            chain.pause(_skewed(0.05, 0.3))

        chain.perform()
    except Exception:
        # Ran off the viewport edge, or the page navigated underneath. The
        # wait is what matters; the drift is a bonus.
        pass


def warm_up(sb, cfg: RunConfig, duration: float | None = None) -> None:
    """Move the mouse around a freshly loaded page before touching anything.

    The sensor starts collecting the moment the page fires, and the first few
    seconds are the ones that decide the score. A session whose first recorded
    pointer event is the one that lands on the first form field -- with no
    approach, no drift, nothing before it -- is the clearest behavioural tell
    the run has, and it costs a few seconds to not have it.

    Best-effort throughout: this is padding, and a page that will not take a
    mouse move is not a reason to fail a step.
    """
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
        # No body to anchor on (an interstitial, a frame still loading). The
        # idle still has value -- a page that sits for a moment before being
        # touched beats one that is typed into the instant it renders.
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
                # Per-step jitter: a path made of equal offsets is a straight
                # line, and a straight line is not a hand.
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
            # Ran the pointer off the viewport edge, or the page navigated
            # underneath. Either way the warm-up has done its job.
            break


def smooth_scroll(sb, delta: float, cfg: RunConfig) -> None:
    """Scroll by `delta` the way a wheel does, not the way a script does.

    `window.scrollBy(0, n)` and `scrollIntoView()` move the page in a single
    frame. Nothing physical does that: a wheel arrives as a burst of discrete
    notches, a trackpad as a decelerating glide, and either way the scroll
    position is sampled by the page across many frames rather than once. A
    single jump is one of the cheapest behavioural tells there is, and this
    run was producing one before every field it touched.

    So: several steps, sized unevenly, easing out at the end, with a short
    pause between them. Falls back to the plain jump if anything here fails,
    because a field that cannot be reached is worse than one reached
    abruptly.
    """
    delta = float(delta or 0)
    if abs(delta) < 1:
        return

    if not cfg.human_like:
        try:
            sb.execute_script("window.scrollBy(0, arguments[0]);", delta)
        except Exception:
            pass
        return

    # More steps for a longer journey, but never a fixed number: a constant
    # step count is its own signature.
    steps = max(4, min(18, int(abs(delta) / random.uniform(38, 70))))
    done = 0.0
    try:
        for index in range(1, steps + 1):
            # Ease out: most of the distance early, settling at the end.
            progress = 1 - (1 - index / steps) ** 2
            target = delta * progress
            hop = target - done
            # A little jitter so no two steps are the same size.
            hop += random.uniform(-2.0, 2.0)
            sb.execute_script("window.scrollBy(0, arguments[0]);", hop)
            done += hop
            time.sleep(random.uniform(0.012, 0.045))

        remainder = delta - done
        if abs(remainder) >= 1:
            sb.execute_script("window.scrollBy(0, arguments[0]);", remainder)

        # A beat after arriving, the way a hand comes off the wheel.
        time.sleep(random.uniform(0.05, 0.18))
    except Exception as exc:
        LOG.debug("Smooth scroll failed (%s); jumping instead", exc)
        try:
            sb.execute_script("window.scrollBy(0, arguments[0]);", delta - done)
        except Exception:
            pass


def scroll_element_into_view(sb, element, cfg: RunConfig) -> None:
    """Bring an element into view by scrolling to it, not snapping to it."""
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
    """Move the pointer to the element, settle, then click it."""
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

    # Press, hold briefly, release -- a finger is on the button for something
    # like 60-140ms. `element.click()` sends mousedown and mouseup in the same
    # instant, so every click in the run has a dwell time of zero, identical
    # every time. That is measurable and no hand produces it.
    if _pressed_click(sb, selector, cfg):
        return

    try:
        sb.click(selector, timeout=timeout)
    except WebDriverException:
        # Something moved under the pointer (Angular re-render, sticky header).
        # A direct click still gets the job done.
        LOG.debug("Pointer click on %s failed; clicking directly", selector)
        sb.click(selector, timeout=timeout)


def _blame(cfg: RunConfig, reason: str, selector: str) -> None:
    """Say which step of the real-input attempt failed, and why it matters.

    At WARNING rather than DEBUG on purpose. Real input has six ways to fail
    and they need completely different answers -- focus lost to another
    window, an element off the bottom of the screen, a page that reflowed
    mid-move, somebody touching the mouse. Reporting only "could not click
    it" sends whoever reads the log looking at the page, which is the one
    place the problem usually is not, and forces a re-run with --verbose to
    learn anything at all. That cost two leads to find out.
    """
    LOG.warning("Real input on %s: %s", selector, reason)


def _refuse_synthetic(what: str, selector: str, cfg: RunConfig) -> None:
    """Stop, rather than quietly finish the job with injected events.

    A silent fall back to synthetic input is the worst of both worlds. The run
    reports success and carries on, while the events reaching the page have no
    pointer path behind them, no key timings, and `isTrusted: false` -- which
    is precisely what --real-input exists to avoid, arriving on precisely the
    screens where it matters. The old warning was easy to miss in a long log
    and nothing acted on it.

    So when real input was asked for and could not be delivered, the lead
    fails and says why. The runner gives it another browser, which is usually
    all it needs: the causes are the window losing focus or a field moving out
    of the pointer's reach, not anything about this applicant.

    `--allow-synthetic-fallback` restores the old behaviour for when getting
    the form filled matters more than how it was filled.
    """
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
    """Click with a real press duration. False means "use the plain click".

    Goes through ActionChains, so the events are the browser's own and carry
    isTrusted -- the press duration is added on top of a genuine click, not
    in place of one.
    """
    try:
        # Not inside the enrollment frame.
        #
        # ActionChains addresses the top-level viewport, and this frame is
        # taller than the window, so a press aimed at an element in it can
        # land nowhere -- silently. perform() does not raise, so this
        # reported success while clicking empty page, and because it reported
        # success the caller never fell through to the plain click that
        # works. Measured: three leads died at step 6 because step 5's button
        # was "clicked" and the wizard never moved.
        #
        # Inside the frame, reliability wins: sb.click() is still a trusted
        # native click, it just has no dwell time.
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
    """Focus the field and type it out one character at a time."""
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

    # Re-find after the move: an Angular re-render can stale the reference.
    element = sb.wait_for_element_visible(selector, timeout=cfg.page_timeout)
    try:
        element.click()
        element.clear()
    except WebDriverException:
        sb.type(selector, "")  # fall back to clearing through SeleniumBase

    text = str(value)
    low, high = cfg.type_delay

    # One hand per field, not one hand per run.
    #
    # Keystroke-dynamics scoring does not look at the mean gap between
    # characters, it looks at the *distribution* -- and a gap drawn fresh from
    # the same uniform range for every character has a flat, rectangular
    # distribution that nothing biological produces. Real typing is fast
    # within a familiar word and slow at the boundaries, and each typist has a
    # baseline speed that holds across a field rather than being re-rolled at
    # every letter.
    #
    # So: pick a speed for this field and vary around it. The effect on any
    # single gap is small; the effect on the shape of the distribution is the
    # whole point.
    tempo = random.uniform(0.82, 1.28) * _tempo
    for index, char in enumerate(text):
        try:
            # Occasionally hit the neighbouring key and correct it. Real
            # typing into a form has corrections in it, and a run of hundreds
            # of fields with not one backspace among them is its own pattern.
            # Kept rare, and never on the digits that matter: a stray
            # keystroke in an SSN or date field can trip the form's own
            # validation and cost the lead.
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
            # Lost the element mid-word -- finish the value the blunt way so
            # the field still ends up correct, then stop pacing it.
            LOG.debug("Lost %s while typing; filling the remainder directly", selector)
            sb.type(selector, value)
            return

        _sync_input(sb, element)

        time.sleep(_keystroke_delay(text, index, low, high, tempo))

    _commit_field(sb, element)


def _keystroke_delay(
    text: str, index: int, low: float, high: float, tempo: float
) -> float:
    """How long to wait after typing text[index].

    Modelled on what a hand actually does rather than on a single range:

      * the gap is log-normal-ish around this typist's baseline, so most
        keystrokes cluster and a few run long -- which is the shape real
        inter-key intervals have, and a uniform draw does not
      * a shift (the capital at the start of a name) costs a beat, because two
        keys have to be pressed
      * digits in a run -- a ZIP, a phone number, the last four of an SSN --
        come out faster than prose, and the first digit costs more than the
        rest because that is where the hand moves to the number row
      * the boundaries are where people slow down: after a space, after an
        `@`, after a dot in an address or an email
      * and occasionally the hand just stops, mid-word, for no reason the
        page can see
    """
    char = text[index]
    previous = text[index - 1] if index else ""

    # Baseline for this typist, with a long right tail. `expovariate` supplies
    # the tail; the floor keeps it from producing an impossible zero.
    middle = (low + high) / 2
    delay = (middle * tempo) + random.expovariate(1 / max(middle * 0.45, 0.01))
    delay = max(low * 0.6, min(delay, high * 3.5))

    if char.isupper() and not previous.isupper():
        delay += random.uniform(0.04, 0.13)   # reaching for shift

    if char.isdigit():
        # A run of digits is muscle memory; the first one is a hand move.
        delay *= 0.7 if previous.isdigit() else 1.25

    if previous in " @.,-/":
        delay += random.uniform(0.04, 0.16)   # a boundary to think at

    if char == " ":
        delay += random.uniform(0.05, 0.18)

    # The stutter: rare, and never so long that a validator times out.
    if index and random.random() < 0.06:
        delay += random.uniform(0.22, 0.65)

    return delay


def _neighbour(char: str) -> str:
    """A key next to this one on the keyboard, matching its case."""
    options = _NEIGHBOURS.get(char.lower(), "")
    if not options:
        return ""
    wrong = random.choice(options)
    return wrong.upper() if char.isupper() else wrong


def _sync_input(sb, element) -> None:
    """Deliberately does nothing per keystroke. Kept for the call sites.

    This used to dispatch `new Event('input')` after every character. That was
    counter-productive twice over:

    * `send_keys` already fires a real, trusted `input` event per keystroke,
      so the extra one was a duplicate the page had to reconcile.
    * A hand-built Event carries `isTrusted: false`. Firing one alongside each
      genuine keystroke gives a page a per-character stream of events that no
      keyboard can produce -- measured here: JS-dispatched events are
      untrusted, real ones are not. On a form behind Cloudflare that is a
      signal paid for on every field, for no benefit.

    The model sync that actually matters happens once, when the field is left
    (see _commit_field), which is also when a person's browser fires it.
    """
    return


def _commit_field(sb, element) -> None:
    """Leave the field the way a person does, so `change` fires for real.

    Angular validators here run on `change` and on blur, not on every
    keystroke, so a field that is typed into and never left stays marked
    untouched and the wizard's Next button waits on a validity it was never
    told about.

    Pressing Tab is how a person leaves a field, and it makes the browser
    fire `change` and `blur` itself -- trusted, in the right order, once. The
    previous version dispatched a synthetic `change` instead, which arrives
    with `isTrusted: false` and tells a watching script that whatever filled
    this form was not a keyboard. Scripted dispatch is kept only for the case
    where the key cannot be sent at all.
    """
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


# What a <select> looks like from the outside, and where the wanted option is.
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
    """Choose a dropdown option the way somebody at the keyboard does.

    A native <select> is the one control this project was setting without ever
    touching it: `select_option_by_value` assigns the value and dispatches the
    events, so the page sees three dropdowns change with no click, no keypress
    and no pointer within a hundred pixels of them. On a form that watches
    interaction that is more conspicuous than any of the text fields, because
    a text field at least had keystrokes.

    So: focus it with a real click, walk to the option with the arrow keys,
    and commit with Enter -- which is exactly how the control is designed to
    be driven from a keyboard, and produces the same trusted key events and
    the same single `change` a person produces.

    Deliberately NOT by clicking the option elements. The docstring this
    replaces was right about that: the rendered list of a native select is an
    operating-system popup the DOM cannot address, and clicking <option> nodes
    is what broke these forms before. Arrow keys drive the closed control.

    Falls back to the scripted assignment whenever the real path cannot be
    used or does not take, because a dropdown left unset fails the lead.
    """
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
    """Open the dropdown for real and arrow to the option. False means fall back."""
    try:
        element = sb.wait_for_element_visible(selector, timeout=cfg.page_timeout)
        state = sb.execute_script(_SELECT_STATE_JS, element, str(option_value)) or {}
    except WebDriverException as exc:
        LOG.debug("Could not read %s before choosing: %s", selector, exc)
        return False

    target = state.get("target", -1)
    if state.get("disabled") or target is None or target < 0:
        # Not an option on this screen; the scripted path will report it.
        return False

    if state.get("value") == str(option_value):
        return True  # already where we want it

    if not _real_click(sb, element, selector, cfg):
        return False

    # Arrow from where it is to where it should be. A person scanning a list
    # does not move at a constant rate, so the gaps vary and the last step or
    # two are slower, the way they are when the right one comes into view.
    steps = target - int(state.get("selected", 0) or 0)
    key = Keys.ARROW_DOWN if steps > 0 else Keys.ARROW_UP
    remaining = abs(steps)
    if remaining > 40:
        # A very long list is not walked one row at a time by anybody.
        return False

    try:
        for index in range(remaining):
            element.send_keys(key)
            left = remaining - index
            time.sleep(random.uniform(0.05, 0.16) + (0.12 if left <= 2 else 0.0))
        # Commit. On an open native dropdown this is what closes it and fires
        # `change`; on a focused closed one it is harmless.
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
    """Walk the pointer over to the element instead of teleporting to it.

    The path is a quadratic Bezier from a random offset nearby onto the
    element, sampled at cfg.mouse_steps points with a pixel or two of jitter
    on each. The curve matters more than it sounds: a hand accelerates into a
    move and decelerates out of it, so the trajectory bends. A series of
    straight segments between waypoints -- which is what the previous
    hop-based version produced -- has a constant direction within each
    segment and a sharp corner at every joint, and that shape is exactly what
    a pointer-path classifier is built to pick out.
    """
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

    # Where the approach can start without leaving the viewport. Offsets here
    # are measured from the element's centre, and WebDriver refuses the whole
    # chain with "move target out of bounds" if any point falls outside the
    # window -- so an offset picked blind fails on every element near an edge,
    # which on these screens is most of them. Measured rather than assumed.
    room = _room_around(sb, element)
    if room is None:
        return


    try:
        # Start somewhere off to the side, far enough away that the approach
        # is a real move rather than a twitch, but inside what actually fits.
        start_x = _offset_within(room["left"], room["right"], 280, 30)
        start_y = _offset_within(room["up"], room["down"], 160, 20)
        if start_x == 0 and start_y == 0:
            # Nowhere to approach from: the element fills the viewport.
            start_y = min(20, room["up"]) or min(20, room["down"])

        # Control point pulled off the straight line, which is what gives the
        # path its bend. Clamped the same way: the curve bulges away from the
        # straight line, so an unclamped control point can push the middle of
        # the path outside the window even when both ends are inside it.
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
            # Quadratic Bezier from (start) through (cp) to the centre (0, 0).
            cur_x = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * cp_x
            cur_y = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * cp_y
            cur_x += random.uniform(-1.5, 1.5)
            cur_y += random.uniform(-1.5, 1.5)
            # The jitter above can nudge a point over the edge on its own.
            cur_x = max(-room["left"], min(room["right"], cur_x))
            cur_y = max(-room["up"], min(room["down"], cur_y))

            chain.move_by_offset(int(cur_x - prev_x), int(cur_y - prev_y))
            # Slower at the ends, quicker through the middle: the same
            # ease-in/ease-out a hand has.
            edge = min(t, 1 - t)
            chain.pause(random.uniform(0.004, 0.010) + (0.5 - edge) * 0.02)
            prev_x, prev_y = cur_x, cur_y

        chain.move_to_element(element)
        chain.pause(random.uniform(0.05, 0.15))
        chain.perform()
    except Exception as exc:
        # Out-of-bounds moves and stale elements are common here and never
        # worth failing a step over; the click/type still follows.
        LOG.debug("Could not drift the pointer to %s: %s", selector, exc)

        # "Out of bounds" inside the enrollment frame means the field is not
        # where the pointer can reach, and only the outer page can change
        # that. Scroll it there and try once more -- reactively, so the cost
        # of stepping out of the frame is paid only when it is needed.
        if room.get("framed") and "out of bounds" in str(exc).lower():
            from .page_utils import bring_framed_element_into_view

            if bring_framed_element_into_view(sb, selector, cfg):
                try:
                    # The handle above went stale when we left the frame.
                    element = sb.find_element(selector)
                except Exception:
                    return
                _short_drift(sb, element, selector)
                return

        _short_drift(sb, element, selector)


def _short_drift(sb, element, selector: str) -> None:
    """A small in-place approach that cannot land out of bounds.

    The long approach above measures its room against `window.innerWidth/
    Height`, and inside the enrollment iframe those are the *frame's*
    dimensions -- while WebDriver bounds-checks pointer moves against the
    top-level viewport, which a cross-origin frame cannot measure. So a start
    offset that is comfortably inside the frame can still be outside the
    window, and the whole chain is refused. That is not a rare edge case here:
    every screen from step 5 on lives in that frame, so without this fallback
    the fancy path failed on essentially every field and the pointer never
    moved at all.

    This version anchors on the element -- which is on screen, or it could not
    be clicked -- and stays within a few pixels of it, so the coordinates are
    valid whatever the frame offset is. Less of a journey than the Bezier, but
    real movement onto the target rather than none.
    """
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
    """How far the pointer can travel from this element's centre, per side.

    Returns pixel budgets keyed left/right/up/down, each already inside a
    small margin so a rounded coordinate cannot land on the boundary itself.
    None means the element could not be measured, in which case the caller
    skips the drift rather than guessing.
    """
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
        # These numbers describe the frame, and WebDriver checks the top-level
        # window. The frame's own offset inside that window is unknowable from
        # in here (it is cross-origin), so the only safe budget is a small one
        # measured from a point already known to be on screen: the element.
        for side in ("left", "right", "up", "down"):
            room[side] = min(room[side], 40)

    return room


def _offset_within(back: int, forward: int, reach: int, minimum: int) -> int:
    """A signed offset up to `reach`, fitting the room actually available.

    Prefers the roomier side, so an element against the left edge is
    approached from the right rather than not at all.
    """
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


def _reach_framed(sb, selector: str, cfg: RunConfig) -> bool:
    """Scroll the outer page so a field inside the enrollment frame is reachable.

    Only meaningful inside that frame, and only when the aim has already
    failed -- scrolling the page around the form is not something to do
    speculatively before every click.

    Imported here rather than at the top because page_utils imports this
    module; the same deferred import is used by _drift_to for the same reason.
    """
    try:
        from .page_utils import bring_framed_element_into_view

        return bool(bring_framed_element_into_view(sb, selector, cfg))
    except Exception as exc:
        LOG.debug("Could not bring %s into reach: %s", selector, exc)
        return False


def _real_click(sb, element, selector: str, cfg: RunConfig) -> bool:
    """Click with the machine's own mouse. False means "fall back".

    Tried twice: the first attempt can lose the pointer to somebody's hand or
    to the page reflowing under it, and in both cases aiming again is the
    right answer rather than giving up on real input for this element.
    """
    for attempt in (1, 2, 3):
        # Without focus the click lands on whatever is drawn in front of the
        # browser, so refuse rather than click blind.
        if not real_input.focus_window(sb):
            _blame(cfg, "could not bring the browser window to the front", selector)
            if attempt < 3:
                continue
            return False

        real_input.scroll_to(sb, element, cfg)
        point = real_input.screen_point(sb, element)
        if point is None and _reach_framed(sb, selector, cfg):
            # Inside the enrollment frame the wheel scrolls the frame, and a
            # frame taller than the window cannot bring its own lower fields
            # into reach -- only the page around it can. Measured: #dobMonth
            # aimed at with "only 298x1 px of it is inside the viewport",
            # sitting one pixel above the fold with nothing able to move it.
            point = real_input.screen_point(sb, element)
        if point is None:
            _blame(cfg, real_input.last_refusal(), selector)
            return False
        if not real_input.move_to(point, cfg):
            _blame(cfg, "could not move the pointer there", selector)
            return False
        pause(cfg, 0.3)

        # The page may have reflowed while the pointer was travelling.
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
            # Refused because the pointer is no longer where we left it --
            # somebody has the mouse. yield_to_user has already waited for
            # them to stop, so a second run at it usually lands.
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
    """Focus the field with the real mouse, then type on the real keyboard.

    Verifies the field actually took the value before claiming success: if the
    click landed somewhere else the keystrokes went somewhere else too, and
    silently carrying on would fill the form with gaps -- or type an
    applicant's SSN into whatever window was in front.

    Tried three times, for the same reason clicking is: the window can lose
    focus, the page can reflow under the pointer between aiming and arriving,
    and a field can scroll as the frame settles. None of those say the real
    keyboard cannot be used here, only that this particular attempt missed --
    and aiming again is a far better answer than dropping to injected events.
    """
    for attempt in (1, 2, 3):
        if attempt > 1:
            LOG.debug("Aiming at %s again (attempt %d)", selector, attempt)
            pause(cfg, 0.5)
        if _real_type_once(sb, element, selector, value, cfg):
            return True
        # Re-find the element: a reflow between attempts staled the handle,
        # and typing into a stale one fails for a reason that is not the
        # keyboard's.
        try:
            element = sb.wait_for_element_visible(selector, timeout=cfg.page_timeout)
        except Exception:
            return False
    return False


def _real_type_once(sb, element, selector: str, value: str, cfg: RunConfig) -> bool:
    """One attempt at aiming, clicking and typing. See _real_type."""
    # Same reporting as the click path: six ways to fail, each needing a
    # different answer, and a bare "could not type it" names none of them.
    if not real_input.focus_window(sb):
        _blame(cfg, "could not bring the browser window to the front", selector)
        return False

    real_input.scroll_to(sb, element, cfg)
    point = real_input.screen_point(sb, element)
    if point is None and _reach_framed(sb, selector, cfg):
        # Same as the click path: a field low in the enrollment frame can only
        # be brought into reach by the page around it.
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
    real_input.clear_field(cfg)

    if not real_input.type_text(value, cfg):
        _blame(cfg, "the keyboard would not send the characters", selector)
        return False

    if not _field_holds(element, value):
        # The most informative failure of the lot: the aim, the click and the
        # keystrokes all reported success, and the field is still not holding
        # the value. That means the keystrokes went somewhere else -- which is
        # exactly the case that must never be papered over, because
        # "somewhere else" is whatever window has focus.
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
    """Wait briefly for the field to actually show what was typed.

    Real keystrokes travel through the operating system's input queue, so the
    browser has not necessarily processed the last one by the time pyautogui
    returns. Reading the value in that same instant is a race -- and a short
    field loses it more often than a long one, because there are fewer
    keystrokes of elapsed time sitting behind the final character.

    Measured on the personal-info screen: `#ssn`, four characters behind a
    `password` input with an `onlynumber` directive, fell back to synthetic
    input on every run, while `#firstName` on the same screen did not. The
    typing had worked; the check just asked too early.

    This stays a real check rather than a softened one. A field that never
    takes the value still fails, which is what stops an applicant's details
    being typed into whatever window happened to have focus.
    """
    expected = str(value).strip()
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            actual = (element.get_attribute("value") or "").strip()
        except WebDriverException:
            return False

        if actual == expected:
            return True

        # A field that caps its own length has not failed to take the value,
        # it has taken as much of it as it accepts.
        try:
            limit = element.get_attribute("maxlength") or ""
        except WebDriverException:
            limit = ""
        if limit.isdigit() and int(limit) > 0 and actual == expected[: int(limit)]:
            return True

        time.sleep(0.1)

    return False
