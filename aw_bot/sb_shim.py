"""A SeleniumBase-shaped face over a plain Selenium driver.

The step modules were written against SeleniumBase's `sb` object. GoLogin hands
back a raw `webdriver.Chrome` attached to its Orbita browser, and SeleniumBase
has no way to attach to a browser someone else started -- so rather than rewrite
every step, this exposes the handful of `sb.*` calls the steps actually use.

Only what `aw_bot` calls is implemented. If a step starts using a new
SeleniumBase method, add it here; anything missing raises AttributeError at the
call site rather than failing silently.
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from selenium.common.exceptions import (
    NoSuchWindowException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from .errors import AwBotError
from .logs import LOG

DEFAULT_TIMEOUT = 30


class ShimError(AwBotError):
    """A shim call could not be satisfied (element missing, timeout, ...)."""


# SeleniumBase's own extension to CSS, e.g. button:contains("Start Application").
# Real CSS has no :contains, so a browser rejects it outright -- it has to be
# rewritten as XPath before it reaches Selenium.
_CONTAINS = re.compile(
    r"""^([^\s>]*?):contains\(\s*(["'])(.*?)\2\s*\)$""", re.DOTALL
)


def _text(value) -> str:
    """A str, whatever the driver handed back.

    A window that is closing can answer `current_url` or `title` with bytes
    instead of a string, and callers downstream do string work on it -- one
    lead died on `rstrip("/")` against a bytes URL.
    """
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value if isinstance(value, str) else ("" if value is None else str(value))


def _by(selector: str) -> tuple[str, str]:
    """SeleniumBase guesses CSS vs XPath from the selector; so do we."""
    if selector.startswith(("/", "(", "./")):
        return By.XPATH, selector

    match = _CONTAINS.match(selector.strip())
    if match:
        return By.XPATH, _contains_xpath(*match.group(1, 3))

    if ":contains(" in selector:
        raise ShimError(
            f"Selector {selector!r} uses :contains() in a form this shim cannot "
            f"translate. Write it as tag:contains(\"text\"), or as XPath."
        )
    return By.CSS_SELECTOR, selector


def _contains_xpath(prefix: str, text: str) -> str:
    """Turn `tag.class:contains("x")` into the XPath that means the same thing."""
    tag, classes, element_id = "*", [], ""
    for index, part in enumerate(re.split(r"([.#])", prefix or "")):
        if index == 0:
            tag = part or "*"
        elif part == ".":
            classes.append("class")
        elif part == "#":
            classes.append("id")
        elif classes and classes[-1] == "class":
            classes[-1] = f'contains(concat(" ", normalize-space(@class), " "), " {part} ")'
        elif classes and classes[-1] == "id":
            classes.pop()
            element_id = f'@id="{part}"'

    quoted = f'"{text}"' if '"' not in text else f"'{text}'"
    tests = [t for t in classes if t.startswith("contains(")]
    if element_id:
        tests.append(element_id)
    tests.append(f"contains(normalize-space(.), {quoted})")
    return f"//{tag}[{' and '.join(tests)}]"


class SBShim:
    """Wraps a Selenium driver in the slice of the SeleniumBase API we use."""

    def __init__(self, driver, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.driver = driver
        self.timeout = timeout

    # -- navigation ---------------------------------------------------------

    def open(self, url: str) -> None:
        """Navigate, surviving a page-load timeout.

        On a residential proxy the page is routinely interactive and complete
        enough to work with well before every subresource has arrived, so a
        timeout here is not a failed load -- `_landed_on` checks whether we
        actually got there before deciding.
        """
        try:
            self.driver.get(url)
        except TimeoutException:
            if not self._landed_on(url):
                raise
            LOG.warning("Page load for %s timed out, but the page is up; continuing", url)

    def uc_open_with_reconnect(self, url: str, reconnect_time: float = 0) -> None:
        """SeleniumBase's stealth-load, which has no meaning here.

        UC mode detaches its patched chromedriver during the load so the page's
        fingerprinting sees a clean browser. With GoLogin the fingerprint is the
        profile's, not chromedriver's, so a normal navigation is the right call;
        `reconnect_time` just becomes a settle pause.
        """
        self.open(url)
        if reconnect_time:
            time.sleep(min(float(reconnect_time), 5.0))

    def _landed_on(self, url: str) -> bool:
        """Did the navigation get us onto the host we asked for?"""
        try:
            wanted = urlparse(url).netloc.lower()
            here = urlparse(self.driver.current_url).netloc.lower()
        except WebDriverException:
            return False
        return bool(here) and (here == wanted or here.endswith(wanted) or wanted.endswith(here))

    def get_current_url(self) -> str:
        try:
            return _text(self.driver.current_url)
        except NoSuchWindowException:
            self._recover_window()
            return _text(self.driver.current_url)

    def get_title(self) -> str:
        try:
            return _text(self.driver.title)
        except NoSuchWindowException:
            self._recover_window()
            return _text(self.driver.title)

    def _recover_window(self) -> None:
        """Point the driver at a window that still exists.

        A renderer that times out or an Orbita startup tab being swapped out
        leaves the driver holding a handle to nothing, and every later call
        then fails with "no such window" no matter what the browser is showing.
        """
        handles = self.driver.window_handles  # raises if the browser is really gone
        if not handles:
            raise ShimError("The browser has no windows left open.")
        LOG.warning("Lost the active window; switching to one of %d open", len(handles))
        self.driver.switch_to.window(handles[-1])

    def get_page_source(self) -> str:
        return self.driver.page_source

    def execute_script(self, script: str, *args):
        return self.driver.execute_script(script, *args)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    # "interactive" counts as ready: the driver navigates with the "eager"
    # page-load strategy, which hands control back at DOMContentLoaded, and on
    # a slow proxy "complete" can trail that by a minute of trackers and fonts
    # that no step needs.
    READY_STATES = ("complete", "interactive")

    def wait_for_ready_state_complete(self, timeout: int | None = None) -> bool:
        deadline = time.time() + (timeout or self.timeout)
        while time.time() < deadline:
            try:
                if self.driver.execute_script("return document.readyState") in self.READY_STATES:
                    return True
            except WebDriverException:
                pass  # mid-navigation; the document is being swapped out
            time.sleep(0.2)
        LOG.warning("Page never left readyState 'loading' within %ss", timeout or self.timeout)
        return False

    # -- finding and waiting ------------------------------------------------

    def find_element(self, selector: str):
        return self.driver.find_element(*_by(selector))

    def find_elements(self, selector: str) -> list:
        return self.driver.find_elements(*_by(selector))

    def wait_for_element_present(self, selector: str, timeout: int | None = None):
        return self._wait(EC.presence_of_element_located, selector, timeout, "appear in the DOM")

    def wait_for_element_visible(self, selector: str, timeout: int | None = None):
        return self._wait(EC.visibility_of_element_located, selector, timeout, "become visible")

    # SeleniumBase spells this both ways in places; the alias is free.
    wait_for_element = wait_for_element_visible

    def is_element_present(self, selector: str) -> bool:
        return bool(self.find_elements(selector))

    def is_element_visible(self, selector: str) -> bool:
        try:
            return any(el.is_displayed() for el in self.find_elements(selector))
        except WebDriverException:
            return False

    def _wait(self, condition, selector: str, timeout: int | None, what: str):
        wait = WebDriverWait(self.driver, timeout or self.timeout)
        try:
            return wait.until(condition(_by(selector)))
        except TimeoutException as exc:
            raise ShimError(
                f"Element {selector!r} did not {what} within {timeout or self.timeout}s"
            ) from exc

    # -- interaction --------------------------------------------------------

    def click(self, selector: str, timeout: int | None = None) -> None:
        element = self.wait_for_element_visible(selector, timeout)
        before = self._handles()

        try:
            element.click()
        except WebDriverException:
            # Sticky headers and mid-render overlays intercept the real click;
            # the scripted one still hits the element the step meant.
            #
            # It is a genuine last resort, not an equivalent: a native click
            # reaches the page as a trusted event, and `element.click()` in
            # script does not (measured in this browser -- WebDriver click
            # isTrusted True, JS click isTrusted False). On a form behind
            # Cloudflare that difference is the difference between being
            # scored as a person and being handed a challenge, so scroll the
            # element under the pointer and try natively once more before
            # giving up on a trusted click.
            LOG.debug("Native click on %s intercepted; retrying after scroll", selector)
            try:
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center', inline:'center'});",
                    element,
                )
                element.click()
            except WebDriverException:
                LOG.warning(
                    "Falling back to a scripted click on %s -- this arrives as an "
                    "untrusted event, which anti-bot scoring can tell apart from a "
                    "person's click", selector,
                )
                self.driver.execute_script("arguments[0].click();", element)

        self._follow_new_window(before)

    def _handles(self) -> list:
        try:
            return list(self.driver.window_handles)
        except WebDriverException:
            return []

    def _follow_new_window(self, before: list) -> None:
        """Move to a tab the click opened, the way SeleniumBase does.

        SeleniumBase's own click switches to a window that a click spawns, and
        the steps were written expecting that: the site's "Apply Now" links
        open a new tab, so without this the driver stays pointed at the old one
        -- or at a handle the browser has since closed, which then fails every
        later call with "no such window".
        """
        after = self._handles()
        if len(after) <= len(before):
            return

        new = [h for h in after if h not in before]
        if not new:
            return
        LOG.info("Click opened a new window; switching to it")
        try:
            self.driver.switch_to.window(new[-1])
        except WebDriverException as exc:
            LOG.warning("Could not switch to the new window: %s", exc)

    def type(self, selector: str, text: str, timeout: int | None = None) -> None:
        """Clear the field, then enter `text`.

        send_keys fires real key events, so Angular sees the input as typed --
        but `clear()` does not, and a field cleared without an event leaves the
        model holding the old value.
        """
        element = self.wait_for_element_visible(selector, timeout)
        try:
            element.clear()
        except WebDriverException:
            self.driver.execute_script("arguments[0].value = '';", element)
        self._sync_angular(element)
        if text:
            element.send_keys(text)

    def get_attribute(self, selector: str, name: str, timeout: int | None = None):
        return self.wait_for_element_present(selector, timeout).get_attribute(name)

    def get_text(self, selector: str, timeout: int | None = None) -> str:
        return self.wait_for_element_present(selector, timeout).text

    def get_value(self, selector: str, timeout: int | None = None):
        return self.get_attribute(selector, "value", timeout)

    # Angular binds <select> through ngModel, which listens for `change`.
    # Selenium's Select sets the option directly, and when the value it sets is
    # the one already selected there is no state transition and no event -- the
    # screen looks right while the form's model stays empty. Same failure the
    # radios had on the eligible-applicant screen, where Continue then did
    # nothing at all. Firing both events explicitly keeps the model in step.
    _SYNC_ANGULAR_JS = (
        "const el = arguments[0];"
        "el.dispatchEvent(new Event('input', {bubbles: true}));"
        "el.dispatchEvent(new Event('change', {bubbles: true}));"
    )

    def select_option_by_value(self, selector: str, value: str, timeout: int | None = None) -> None:
        element = self.wait_for_element_visible(selector, timeout)
        Select(element).select_by_value(value)
        self._sync_angular(element)

    def select_option_by_text(self, selector: str, text: str, timeout: int | None = None) -> None:
        element = self.wait_for_element_visible(selector, timeout)
        Select(element).select_by_visible_text(text)
        self._sync_angular(element)

    def _sync_angular(self, element) -> None:
        try:
            self.driver.execute_script(self._SYNC_ANGULAR_JS, element)
        except WebDriverException as exc:
            LOG.debug("Could not fire change events on the element: %s", exc)

    def scroll_to(self, selector: str, timeout: int | None = None) -> None:
        element = self.wait_for_element_present(selector, timeout)
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element
        )

    # -- frames and windows -------------------------------------------------

    def switch_to_frame(self, selector, timeout: int | None = None) -> None:
        if isinstance(selector, str):
            frame = self.wait_for_element_present(selector, timeout)
        else:
            frame = selector  # already an element, or an index
        self.driver.switch_to.frame(frame)

    def switch_to_default_content(self) -> None:
        self.driver.switch_to.default_content()

    def switch_to_window(self, index: int) -> None:
        self.driver.switch_to.window(self.driver.window_handles[index])

    # -- artifacts ----------------------------------------------------------

    def save_screenshot(self, name: str, folder: str | None = None) -> str:
        path = Path(folder) / name if folder else Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.driver.save_screenshot(str(path))
        return str(path)

    def console_logs(self, limit: int = 60) -> list[dict]:
        """Whatever the browser has logged, newest last.

        The enrollment app reports its server failures on screen as a bare
        code -- "Unable to continue ... (600)" -- which says nothing about what
        actually failed. The console usually carries the request behind it.
        Not every driver exposes this, so an empty list is a normal answer.
        """
        try:
            entries = self.driver.get_log("browser") or []
        except Exception as exc:
            LOG.debug("Browser console log is unavailable: %s", exc)
            return []
        return entries[-limit:]

    def network_summary(self, limit: int = 40) -> dict:
        """What the app asked for and what came back, from one log drain.

        `get_log("performance")` empties the buffer, so pending requests and
        answered ones have to be derived from the same read or the second
        caller gets nothing.

        This exists because "(600)" says nothing. The app reports a bare code
        and the console stays silent, so the only way to learn what the server
        objected to is to read the response that carried it -- its URL, its
        status, and whether it failed outright.
        """
        try:
            entries = self.driver.get_log("performance") or []
        except Exception as exc:
            LOG.debug("Performance log is unavailable: %s", exc)
            return {"pending": [], "responses": [], "failed": []}

        sent: dict[str, dict] = {}
        answered: set = set()
        responses: list[dict] = []
        failed: list[dict] = []

        for entry in entries:
            try:
                message = json.loads(entry.get("message", "{}")).get("message", {})
            except Exception:
                continue
            method = message.get("method", "")
            params = message.get("params", {})
            request_id = params.get("requestId")
            if not request_id:
                continue

            if method == "Network.requestWillBeSent":
                request = params.get("request", {})
                sent[request_id] = {
                    "url": (request.get("url") or "")[:300],
                    "method": request.get("method"),
                    "postData": (request.get("postData") or "")[:900],
                }
            elif method == "Network.responseReceived":
                answered.add(request_id)
                response = params.get("response", {})
                responses.append({
                    "url": (response.get("url") or "")[:300],
                    "status": response.get("status"),
                    "statusText": response.get("statusText"),
                    "method": (sent.get(request_id) or {}).get("method"),
                    "postData": (sent.get(request_id) or {}).get("postData", "")[:900],
                })
            elif method == "Network.loadingFailed":
                answered.add(request_id)
                origin = sent.get(request_id) or {}
                failed.append({
                    "url": origin.get("url", "?"),
                    "method": origin.get("method"),
                    "error": params.get("errorText"),
                })

        pending = [
            r for rid, r in sent.items()
            if rid not in answered and not r["url"].startswith("data:")
        ]
        return {
            "pending": pending[-limit:],
            "responses": responses[-limit:],
            "failed": failed[-limit:],
        }

    def pending_requests(self, limit: int = 40) -> list[dict]:
        """Requests that were sent but never answered, newest last.

        The enrollment app hangs with a spinner rather than reporting an error,
        so nothing reaches the console. Pairing Network.requestWillBeSent with
        Network.responseReceived shows which call went out and never came back,
        which is the only way to name what the screen is waiting on.
        """
        try:
            entries = self.driver.get_log("performance") or []
        except Exception as exc:
            LOG.debug("Performance log is unavailable: %s", exc)
            return []

        sent: dict[str, dict] = {}
        answered: set = set()
        for entry in entries:
            try:
                message = json.loads(entry.get("message", "{}")).get("message", {})
            except Exception:
                continue
            method = message.get("method", "")
            params = message.get("params", {})
            request_id = params.get("requestId")
            if not request_id:
                continue
            if method == "Network.requestWillBeSent":
                request = params.get("request", {})
                sent[request_id] = {
                    "url": (request.get("url") or "")[:300],
                    "method": request.get("method"),
                }
            elif method in ("Network.responseReceived", "Network.loadingFailed"):
                answered.add(request_id)

        pending = [r for rid, r in sent.items() if rid not in answered]
        # Data URIs and analytics beacons are noise; the app's own calls are not.
        pending = [r for r in pending if not r["url"].startswith("data:")]
        return pending[-limit:]

    # -- UC-mode-only calls -------------------------------------------------

    def uc_gui_click_captcha(self) -> None:
        """UC mode's captcha click, which does not exist outside UC mode.

        page_utils calls this only when a challenge is actually on screen and
        logs whatever comes back, so raising here is the honest answer: the run
        carries on, and the log says the challenge was left alone.
        """
        raise ShimError(
            "uc_gui_click_captcha is a UC-mode feature and is unavailable on a "
            "GoLogin profile. Clear the challenge by hand (--keep-open), or use "
            "a profile/proxy that is not being challenged."
        )
