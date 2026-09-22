"""Tests for the screens step 10 clicks past rather than classifies.

The account review states no decision -- it reads the applicant's own details
back at them and offers Continue. Recording it as a verdict would file an
outcome the site never gave, so it is pressed through to whatever does state
one. The risk on the other side is clicking Continue on pages nobody has read,
on a federal benefits application, so the set is explicit and the number of
them bounded.

    python -m pytest tests -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot.steps import step_10_classify as step10  # noqa: E402

# The headings exactly as the run recorded them from the review screen.
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
    """These are verdicts. Pressing Continue on one would skip the answer."""
    for headings in (
        ["Income and Demographic Information"],
        ["ALMOST DONE! Upload Your Qualifying and Identity Proof Documents"],
        ["Consent to Transfer LifeLine Benefit"],
        ["Who is the Benefit Eligible Applicant?"],
    ):
        assert step10._pass_through(headings) == "", headings


def test_an_unknown_screen_is_not_clicked_past():
    """The default has to be "stop and let somebody look", not "press on"."""
    assert step10._pass_through(["Something nobody has seen before"]) == ""
    assert step10._pass_through([]) == ""
    assert step10._pass_through(None) == ""


def test_the_number_of_pages_clicked_through_is_bounded():
    """A wizard handing back page after page is one this step does not follow."""
    assert 1 <= step10.MAX_PASS_THROUGH <= 6


def test_each_continue_settles_before_the_screen_is_judged():
    """Same reason as step 9: the driver polling is what stalled the backend."""
    assert step10.SETTLE_AFTER_CONTINUE > 0
