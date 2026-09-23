"""Tests for the modal that asks to be tried again.

The app says, in as many words:

    "A communication delay has occurred please click dismiss and then click
     'Next' to re-try. If the delay persists you may see this message, repeat
     the process."

That is an instruction, not a verdict. Reading it as "the form rejected the
data" threw a lead away on the one failure the site had explicitly told us how
to recover from. The other half matters too: "repeat the process" is not an
invitation to resubmit a benefits application without limit, so the retries
are counted and bounded.

    python -m pytest tests -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot.page_utils import (  # noqa: E402
    MAX_RETRY_PROMPTS,
    is_progress_modal,
    is_retryable_message,
    is_throttle_message,
    rejection_verdict,
)

# The modal exactly as the run recorded it, including the mangled quotes the
# site renders around Next.
DELAY_MODAL = (
    "Important: A communication delay has occurred please click dismiss and "
    "then click �Next� to re-try. If the delay persists you may see "
    "this message, repeat the process."
)


def test_the_delay_modal_is_recognised_as_retryable():
    assert is_retryable_message(DELAY_MODAL) is True


def test_it_does_not_depend_on_the_mangled_quotes():
    """The site renders the quotes around Next as replacement characters."""
    assert is_retryable_message(DELAY_MODAL.replace("�", '"')) is True
    assert is_retryable_message(DELAY_MODAL.replace("�", "")) is True


def test_case_does_not_matter():
    assert is_retryable_message(DELAY_MODAL.upper()) is True


def test_it_is_not_confused_with_a_refusal():
    """A throttle means stop the batch; this means press the button again."""
    assert is_throttle_message(DELAY_MODAL) is False


def test_it_is_not_confused_with_a_verdict():
    """Otherwise the lead gets filed with an outcome the site never gave."""
    assert rejection_verdict(DELAY_MODAL) == ""


def test_it_is_not_confused_with_a_spinner():
    assert is_progress_modal(DELAY_MODAL) is False


def test_a_real_refusal_is_still_a_refusal():
    """The new signal must not swallow the ones already handled."""
    assert is_retryable_message(
        "Important: The application can not be processed at this time."
    ) is False
    assert is_retryable_message(
        "Important: Sorry, that's an invalid email address. Be sure it's correct."
    ) is False


def test_an_unrelated_modal_is_not_retried():
    assert is_retryable_message("Please confirm your selection.") is False
    assert is_retryable_message("") is False
    assert is_retryable_message(None) is False


def test_the_retries_are_bounded():
    """"Repeat the process" is not licence to resubmit an application forever."""
    assert 1 <= MAX_RETRY_PROMPTS <= 5


# -- the host's own backend being down ---------------------------------------
#
# "Important: API is offline. Please contact Solix." arrives through the form
# the same way a rejected field does, so without this it was filed as a fact
# about the applicant and the lead was thrown away. The identity lookup never
# ran, so nothing was recorded and another browser costs nothing.

from aw_bot.page_utils import is_vendor_outage  # noqa: E402
from aw_bot import runner  # noqa: E402


def test_the_hosts_outage_message_is_recognised():
    assert is_vendor_outage(
        "Step 9: the form rejected the data -- Important: API is offline. "
        "Please contact Solix."
    ) is True


def test_recognition_ignores_case_and_surrounding_text():
    assert is_vendor_outage("IMPORTANT: API IS OFFLINE.") is True
    assert is_vendor_outage("please contact Solix for assistance") is True


def test_a_real_rejection_is_not_mistaken_for_an_outage():
    """These want opposite handling, so the line between them matters.

    A rejected field fails the same way on every browser and retrying it
    resubmits the applicant, which is what makes the host start refusing.
    """
    for message in (
        "Step 9: the form rejected the data -- Please enter a valid address.",
        "Step 6: the email address is not deliverable",
        "Step 9: clicked Continue but the screen never changed",
        "",
    ):
        assert is_vendor_outage(message) is False, message


def test_an_outage_is_worth_another_browser_but_a_rejection_is_not():
    """What the runner actually keys on to decide whether to retry."""
    outage = "Step 9: the form rejected the data -- Important: API is offline."
    rejection = "Step 9: the form rejected the data -- Please enter a valid address."

    # Step 9 is past the public pages, so neither would be retried on that
    # basis alone -- the outage check is what separates them.
    assert runner._before_the_form(outage) is False
    assert runner._before_the_form(rejection) is False
    assert is_vendor_outage(outage) is True
    assert is_vendor_outage(rejection) is False
