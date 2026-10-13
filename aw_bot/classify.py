from dataclasses import dataclass, field

GOOD = "good"
NEED_DOCUMENTS = "need documents"
REJECTED = "rejected"
UNKNOWN = "unknown"

BAD_EMAIL = "bad email"

AW_TRANSFER = "aw transfer"

VERDICTS = (GOOD, NEED_DOCUMENTS, REJECTED, AW_TRANSFER, BAD_EMAIL, UNKNOWN)

TERMINAL = (REJECTED, NEED_DOCUMENTS, GOOD)


@dataclass(frozen=True)
class Screen:
    verdict: str
    label: str
    headings: tuple[str, ...] = ()
    body: tuple[str, ...] = field(default=())

    def match(self, headings: list[str], body: str) -> str | None:
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
        verdict=NEED_DOCUMENTS,
        label="California Household Worksheet",
        headings=("california household worksheet",),
        body=("california household worksheet",),
    ),
    Screen(
        verdict=GOOD,
        label="Income and Demographic Information",
        headings=("income and demographic",),
        body=("income and demographic information",),
    ),
)


def classify_screen(headings: list[str], body: str) -> tuple[str, str]:
    lowered = (body or "").lower()

    for verdict in TERMINAL:
        for screen in SCREENS:
            if screen.verdict != verdict:
                continue
            why = screen.match(headings or [], lowered)
            if why:
                return verdict, f"{screen.label} (matched {why})"

    return UNKNOWN, f"unrecognised screen; headings: {headings or []}"


def is_terminal(verdict: str) -> bool:
    return verdict in TERMINAL
