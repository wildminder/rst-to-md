"""A bot class whose signature references the cross-page BaseSession type."""

from session.base import BaseSession


class Bot:
    """A bot that uses a session.

    :param session: the session instance.
    :type session: BaseSession
    :param token: the bot token.
    :type token: str
    """

    def __init__(self, session: BaseSession | None = None, token: str = "") -> None:
        self.session = session
        self.token = token

    def connect(self) -> BaseSession:
        """Return the active session.

        :returns: the session.
        """
        return self.session
