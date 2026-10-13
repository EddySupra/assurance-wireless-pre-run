import re
from dataclasses import dataclass, field
from datetime import date, datetime

from .errors import LeadDataError
from .logs import LOG

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "first_name": ("firstname", "first", "fname"),
    "last_name": ("lastname", "last", "lname"),
    "dob": ("dateofbirth", "dob", "birthdate", "birthday"),
    "ssn_last4": ("last4ssn", "ssnlast4", "last4ofssn", "last4", "ssn"),
    "street": ("streetaddress", "street", "address", "addressline1", "address1"),
    "unit": ("apt", "unit", "aptunit", "apartment", "suite", "addressline2", "address2"),
    "city": ("city",),
    "state": ("state", "st"),
    "zip_code": ("zipcode", "zip", "postalcode", "postal"),
    "email": ("email", "emailaddress", "emailaddr"),
    "phone": (
        "pnum", "phone", "phonenumber", "phonenum", "contactnumber", "contactphone",
        "cell", "cellphone", "mobile", "mobilenumber", "bestnumber", "callback",
    ),
}

COLUMN_FALLBACK: dict[str, str] = {
    "first_name": "A",
    "last_name": "B",
    "dob": "C",
    "ssn_last4": "D",
    "street": "E",
    "unit": "F",
    "city": "G",
    "state": "H",
    "zip_code": "I",
    "email": "J",
    "phone": "K",
}

REQUIRED = ("first_name", "last_name", "dob", "ssn_last4", "street", "city", "state", "zip_code", "email")
OPTIONAL = ("unit", "phone")

DOB_FORMATS = ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%m/%d/%y")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME",
    "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "puerto rico": "PR",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}


STATE_ABBREV_TO_NAME = {abbrev: name for name, abbrev in STATE_NAMES.items()}


def normalize_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(header or "").lower())


@dataclass
class Lead:
    first_name: str
    last_name: str
    dob: str
    ssn_last4: str
    street: str
    city: str
    state: str
    zip_code: str
    email: str
    unit: str = ""
    phone: str = ""
    row_number: int | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        where = f"row {self.row_number}" if self.row_number else "lead"
        return f"{where} ({self.first_name} {self.last_name})"

    def for_log(self) -> dict:
        return {
            "row": self.row_number,
            "name": f"{self.first_name} {self.last_name}",
            "dob": self.dob,
            "ssn_last4": "****",
            "address": f"{self.street} {self.unit}".strip(),
            "city_state_zip": f"{self.city}, {self.state} {self.zip_code}",
            "email": self.email,
            "phone": self.phone or "(blank)",
        }

    @classmethod
    def from_mapping(cls, raw: dict[str, object], row_number: int | None = None) -> "Lead":
        warnings: list[str] = []

        missing = [f for f in REQUIRED if not str(raw.get(f, "") or "").strip()]
        if missing:
            raise LeadDataError(
                f"Row {row_number}: missing required field(s): {', '.join(missing)}"
            )

        lead = cls(
            first_name=_clean(raw["first_name"]),
            last_name=_clean(raw["last_name"]),
            dob=_parse_dob(raw["dob"], row_number, warnings),
            ssn_last4=_parse_ssn_last4(raw["ssn_last4"], row_number),
            street=_clean(raw["street"]),
            unit=_clean(raw.get("unit", "")),
            city=_clean(raw["city"]),
            state=_parse_state(raw["state"], row_number),
            zip_code=_parse_zip(raw["zip_code"], row_number),
            email=_parse_email(raw["email"], row_number),
            phone=_parse_phone(raw.get("phone", ""), warnings),
            row_number=row_number,
            warnings=warnings,
        )

        for message in warnings:
            LOG.warning("%s: %s", lead.label, message)
        return lead


def sample_lead() -> Lead:
    return Lead.from_mapping(
        {
            "first_name": "EVELIA",
            "last_name": "SOTO",
            "dob": "07/28/1957",
            "ssn_last4": "1957",
            "street": "1267 ROSS ST",
            "unit": "",
            "city": "POMONA",
            "state": "CA",
            "zip_code": "91767",
            "email": "eveliasfe@gmail.com",
            "phone": "(909) 555-0123",
        },
        row_number=0,
    )


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _parse_zip(value: object, row: int | None) -> str:
    digits = _digits(value)
    if not digits:
        raise LeadDataError(f"Row {row}: ZIP code {value!r} has no digits")

    zip_code = digits[:5]
    if len(zip_code) < 5:
        zip_code = zip_code.zfill(5)
    return zip_code


def _parse_ssn_last4(value: object, row: int | None) -> str:
    digits = _digits(value)
    if not digits:
        raise LeadDataError(f"Row {row}: Last 4 SSN {value!r} has no digits")

    if len(digits) > 4:
        digits = digits[-4:]
    return digits.zfill(4)


def _parse_phone(value: object, warnings: list[str]) -> str:
    digits = _digits(value)
    if not digits:
        return ""

    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]

    if len(digits) != 10:
        warnings.append(
            f"phone {value!r} is not 10 digits -- leaving the phone field blank"
        )
        return ""

    return digits


def _parse_state(value: object, row: int | None) -> str:
    text = _clean(value)
    if len(text) == 2 and text.isalpha():
        return text.upper()

    abbrev = STATE_NAMES.get(text.lower())
    if abbrev:
        return abbrev

    raise LeadDataError(f"Row {row}: state {value!r} is not a US state or 2-letter code")


def _parse_email(value: object, row: int | None) -> str:
    email = _clean(value).lower()
    if not EMAIL_RE.match(email):
        raise LeadDataError(f"Row {row}: email {value!r} is not a valid address")
    return email


def _parse_dob(value: object, row: int | None, warnings: list[str]) -> str:
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        text = _clean(value)
        parsed = None
        for fmt in DOB_FORMATS:
            try:
                parsed = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue
        if parsed is None:
            raise LeadDataError(
                f"Row {row}: date of birth {value!r} is not in a recognized "
                f"format (expected MM/DD/YYYY)"
            )

    age = _age(parsed)
    if age < 18:
        warnings.append(f"date of birth {parsed:%m/%d/%Y} makes this applicant {age} -- under 18")
    elif age > 120:
        warnings.append(f"date of birth {parsed:%m/%d/%Y} gives an age of {age} -- likely a typo")

    return f"{parsed:%m/%d/%Y}"


def _age(born: date) -> int:
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
