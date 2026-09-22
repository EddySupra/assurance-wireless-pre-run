"""Reading the wizard's verdict off the screen it stops on.

The site never states a decision outright. It routes the applicant to one of
three screens, and which screen that is *is* the answer:

    good           "Income and Demographic Information" -- through the
                   attestations with no proof documents and no transfer
                   consent. The only bucket that is a sale.
    need documents "ALMOST DONE! Upload Your Qualifying and Identity Proof
                   Documents" -- approval is blocked on proof the agent does
                   not have.
    rejected       "Consent to Transfer LifeLine Benefit" -- the applicant
                   already has California LifeLine through another carrier.

Anything else is `unknown`, deliberately: a screen we have not seen before is
for a human to look at, not for this to guess at. Every unknown screen is
logged with its headings so it can be added here.

Signals are matched against the screen's headings first and its body text
second, both lowercased. Heading matches are the reliable ones; the body-text
fallback exists because the wizard sometimes renders the same decision as a
panel rather than a heading.
"""

from dataclasses import dataclass, field

GOOD = "good"
NEED_DOCUMENTS = "need documents"
REJECTED = "rejected"
UNKNOWN = "unknown"

# Not a decision the wizard reaches -- the form refuses the lead's own data
# before it will consider them at all. Worth its own bucket rather than being
# filed as a run failure: the lead is not bad, the contact detail is, and that
# is something an agent can fix and retry.
BAD_EMAIL = "bad email"

# The applicant already has Assurance Wireless service. Announced after the
# eligible-applicant screen as a modal rather than by routing to a screen of
# its own:
#
#   "Our records show that you are currently an Assurance Wireless customer.
#    For more information log into My Account, visit FAQ "About Your Account"
#    or call Customer Care 888-321-5880."
#
# Kept apart from `rejected`, which means the applicant has a LifeLine benefit
# with *another* carrier and could consent to move it. This one is already on
# this carrier, so there is nothing to transfer in and the agent's next step is
# a different conversation entirely.
AW_TRANSFER = "aw transfer"

VERDICTS = (GOOD, NEED_DOCUMENTS, REJECTED, AW_TRANSFER, BAD_EMAIL, UNKNOWN)

# Verdicts that end the application for this lead, in the order they are
# tested. Rejected and need-documents come first: a screen can mention income
# in passing while its actual purpose is to ask for documents.
TERMINAL = (REJECTED, NEED_DOCUMENTS, GOOD)


@dataclass(frozen=True)
class Screen:
    """One recognisable wizard screen and what landing on it means."""

    verdict: str
    label: str
    headings: tuple[str, ...] = ()
    body: tuple[str, ...] = field(default=())

    def match(self, headings: list[str], body: str) -> str | None:
        """The signal that identified this screen, or None."""
        joined = " | ".join(headings).lower()
        for signal in self.headings:
            if signal in joined:
                return f"heading {signal!r}"
        for signal in self.body:
            if signal in body:
                return f"body {signal!r}"
        return None


SCREENS = (
    Screen(
        verdict=REJECTED,
        label="Consent to Transfer LifeLine Benefit",
        headings=("consent to transfer",),
        body=(
            "you currently receive a california lifeline benefit with another "
            "service provider",
        ),
    ),
    Screen(
        verdict=NEED_DOCUMENTS,
        label="Upload Your Qualifying and Identity Proof Documents",
        headings=("upload your qualifying", "proof documents"),
        body=("upload your qualifying and identity proof documents",),
    ),
    Screen(
        verdict=GOOD,
        label="Income and Demographic Information",
        headings=("income and demographic",),
        body=("income and demographic information",),
    ),
)


def classify_screen(headings: list[str], body: str) -> tuple[str, str]:
    """Return (verdict, why) for the screen the wizard stopped on."""
    lowered = (body or "").lower()
    by_verdict = {screen.verdict: screen for screen in SCREENS}

    for verdict in TERMINAL:
        screen = by_verdict.get(verdict)
        if screen is None:
            continue
        why = screen.match(headings or [], lowered)
        if why:
            return verdict, f"{screen.label} (matched {why})"

    return UNKNOWN, f"unrecognised screen; headings: {headings or []}"


def is_terminal(verdict: str) -> bool:
    """Does this verdict end the application for the lead?"""
    return verdict in TERMINAL
