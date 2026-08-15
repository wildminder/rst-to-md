"""A session base class, documented on its own page (cross-page xref target)."""


class BaseSession:
    """The base session used by a bot."""

    def __init__(self, token: str) -> None:
        self.token = token
