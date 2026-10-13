class AwBotError(Exception):
    pass


class BotBlockedError(AwBotError):
    pass


class ThrottledError(AwBotError):
    pass


class LeadDataError(AwBotError):
    pass


class PageMismatchError(AwBotError):
    pass


class RealInputError(AwBotError):
    pass


class LeadRejectedError(AwBotError):
    def __init__(self, message: str, verdict: str) -> None:
        super().__init__(message)
        self.verdict = verdict
