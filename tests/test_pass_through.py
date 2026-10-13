import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot.steps import step_10_classify as step10  # noqa: E402

REVIEW_HEADINGS = [
    "Review your Assurance Wireless Account information",
    "Address",
    "Service/Mailing/Home/e911 Registered Address",
    "Customer Info",
    "Name",
    "Email",
    "Phone",
    "Social Security Number",
    "Date of Birth",
    "Contact/Security",
]


def test_the_account_review_is_clicked_past():
    assert step10._pass_through(REVIEW_HEADINGS) == "account review"


def test_the_match_does_not_depend_on_case():
    assert step10._pass_through([h.upper() for h in REVIEW_HEADINGS])
    assert step10._pass_through([h.lower() for h in REVIEW_HEADINGS])


def test_a_screen_that_states_a_decision_is_not_clicked_past():
    for headings in (
        ["Income and Demographic Information"],
        ["ALMOST DONE! Upload Your Qualifying and Identity Proof Documents"],
        ["Consent to Transfer LifeLine Benefit"],
        ["Who is the Benefit Eligible Applicant?"],
    ):
        assert step10._pass_through(headings) == "", headings


def test_an_unknown_screen_is_not_clicked_past():
    assert step10._pass_through(["Something nobody has seen before"]) == ""
    assert step10._pass_through([]) == ""
    assert step10._pass_through(None) == ""


def test_the_number_of_pages_clicked_through_is_bounded():
    assert 5 < step10.MAX_PASS_THROUGH <= 12


def test_each_continue_settles_before_the_screen_is_judged():
    assert step10.SETTLE_AFTER_CONTINUE > 0
