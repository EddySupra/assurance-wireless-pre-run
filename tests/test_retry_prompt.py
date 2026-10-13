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

DELAY_MODAL = (
    "Important: A communication delay has occurred please click dismiss and "
    "then click �Next� to re-try. If the delay persists you may see "
    "this message, repeat the process."
)


def test_the_delay_modal_is_recognised_as_retryable():
    assert is_retryable_message(DELAY_MODAL) is True


def test_it_does_not_depend_on_the_mangled_quotes():
    assert is_retryable_message(DELAY_MODAL.replace("�", '"')) is True
    assert is_retryable_message(DELAY_MODAL.replace("�", "")) is True


def test_case_does_not_matter():
    assert is_retryable_message(DELAY_MODAL.upper()) is True


def test_it_is_not_confused_with_a_refusal():
    assert is_throttle_message(DELAY_MODAL) is False


def test_it_is_not_confused_with_a_verdict():
    assert rejection_verdict(DELAY_MODAL) == ""


def test_it_is_not_confused_with_a_spinner():
    assert is_progress_modal(DELAY_MODAL) is False


def test_a_real_refusal_is_still_a_refusal():
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
    assert 1 <= MAX_RETRY_PROMPTS <= 5


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
    for message in (
        "Step 9: the form rejected the data -- Please enter a valid address.",
        "Step 6: the email address is not deliverable",
        "Step 9: clicked Continue but the screen never changed",
        "",
    ):
        assert is_vendor_outage(message) is False, message


def test_an_outage_is_worth_another_browser_but_a_rejection_is_not():
    outage = "Step 9: the form rejected the data -- Important: API is offline."
    rejection = "Step 9: the form rejected the data -- Please enter a valid address."

    assert runner._before_the_form(outage) is False
    assert runner._before_the_form(rejection) is False
    assert is_vendor_outage(outage) is True
    assert is_vendor_outage(rejection) is False


from aw_bot.page_utils import _REQUIRED_STATE_JS, _log_required_state  # noqa: E402


def test_the_state_script_reads_properties_not_attributes():
    assert "el.checked" in _REQUIRED_STATE_JS
    assert "getAttribute('checked')" not in _REQUIRED_STATE_JS


def test_it_groups_radios_by_name():
    assert "getAttribute('name')" in _REQUIRED_STATE_JS
    assert "out.groups" in _REQUIRED_STATE_JS


def test_it_reports_required_ness_and_what_the_app_marked_invalid():
    assert "el.required" in _REQUIRED_STATE_JS
    assert "ng-invalid" in _REQUIRED_STATE_JS


class _Broken:
    def execute_script(self, *a, **k):
        raise RuntimeError("frame went away")


def test_a_failure_to_read_the_state_is_not_fatal():
    _log_required_state(_Broken(), "Step 8")


class _Quiet:
    def execute_script(self, *a, **k):
        return {"groups": {}, "fields": [], "invalid": []}


def test_an_empty_screen_still_logs_without_raising():
    _log_required_state(_Quiet(), "Step 8")
