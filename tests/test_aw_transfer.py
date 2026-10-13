import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot.classify import AW_TRANSFER, BAD_EMAIL, REJECTED, VERDICTS  # noqa: E402
from aw_bot.page_utils import rejection_verdict  # noqa: E402

MODAL = (
    "Important Our records show that you are currently an Assurance Wireless "
    "customer. For more information log into My Account, visit FAQ \"About "
    "Your Account\" or call Customer Care 888-321-5880. Dismiss"
)


def test_the_modal_is_read_as_an_aw_transfer():
    assert rejection_verdict(MODAL) == AW_TRANSFER


def test_the_match_does_not_depend_on_case():
    assert rejection_verdict(MODAL.upper()) == AW_TRANSFER
    assert rejection_verdict(MODAL.lower()) == AW_TRANSFER


def test_the_shorter_phrasing_is_matched_too():
    assert rejection_verdict(
        "You are already an Assurance Wireless customer."
    ) == AW_TRANSFER


def test_it_is_kept_apart_from_an_ordinary_rejection():
    assert AW_TRANSFER != REJECTED
    assert AW_TRANSFER in VERDICTS


def test_the_bad_email_refusal_still_reads_as_bad_email():
    assert rejection_verdict(
        "Important: Sorry, that's an invalid email address. Be sure it's correct."
    ) == BAD_EMAIL


def test_an_unrelated_modal_is_still_unrecognised():
    assert rejection_verdict("Please confirm your selection.") == ""
    assert rejection_verdict("") == ""
    assert rejection_verdict(None) == ""


def test_merely_naming_the_company_is_not_enough():
    assert rejection_verdict(
        "Assurance Wireless takes the security of your personal information "
        "seriously."
    ) == ""
