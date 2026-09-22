"""Failure types, so the runner can tell "site blocked us" from "page changed"."""


class AwBotError(Exception):
    """Base class for all automation failures."""


class BotBlockedError(AwBotError):
    """The site served an access-denied / challenge page instead of content.

    Usually means UC mode needs a longer reconnect window, a fresh profile,
    or a different IP. Retrying the same run immediately rarely helps.
    """


class ThrottledError(AwBotError):
    """The enrollment host is refusing to serve us.

    Distinct from every other failure because the right response is to stop
    the batch, not to move on to the next lead: continuing just burns leads
    against a host that is no longer answering, and can leave half-entered
    applications behind.
    """


class LeadDataError(AwBotError):
    """A sheet row is missing a required field or has one we can't parse.

    Raised per lead so one bad row is skipped instead of killing the batch.
    """


class PageMismatchError(AwBotError):
    """We landed somewhere other than the page this step expected.

    Either a redirect we do not know about, or the site's markup changed and
    the step's verification needs updating.
    """


class RealInputError(AwBotError):
    """--real-input was asked for and could not be delivered for an element.

    Exists so the run stops rather than quietly carrying on with injected
    events. Those are the thing --real-input is there to avoid: they arrive
    with no pointer path, no key timings and `isTrusted: false`, so a session
    that silently degrades to them is being scored as automated on exactly the
    screens that matter, while the log reports success.

    Worth another browser: the usual causes -- the window losing focus, a
    field that scrolled out of the pointer's reach -- are properties of this
    browser and this moment rather than of the lead.
    """


class LeadRejectedError(AwBotError):
    """The form refused this lead's data and named what it objected to.

    Distinct from PageMismatchError because nothing is wrong with the run: the
    site looked at the lead and said no. It carries the verdict so the lead is
    bucketed rather than just counted as a failure, and it is never retried --
    the next browser would be told the same thing.
    """

    def __init__(self, message: str, verdict: str) -> None:
        super().__init__(message)
        self.verdict = verdict

