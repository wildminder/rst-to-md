"""A tiny package used to exercise Sphinx autodoc rendering.

The class hierarchy and members intentionally mirror the aiogram ``Bot`` example
so the generated HTML reproduces the ``Bases:`` inheritance list and the
signature/parameter markup that the converter must preserve.
"""


class TelegramMessage:
    """Base class representing a Telegram message."""


class BaseBot:
    """Base class for bot implementations."""


class Bot(TelegramMessage, BaseBot):
    """Bot instance.

    A bot can send messages and download files.

    :param token: API token issued by @BotFather.
    :type token: str
    :raises ValueError: if the token is empty.
    """

    #: The bot token.
    token: str
    #: The bot id.
    id: int
    #: Arbitrary user context.
    context: object
    #: The currently authorized user (``me``).
    me: object

    def __init__(self, token: str, context: object = None) -> None:
        self.token = token
        self.context = context

    def download_file(self, file_id: str, destination: str) -> None:
        """Download a file by id to a destination path.

        :param file_id: Identifier of the file to download.
        :param destination: Local path to write the file to.
        :raises RuntimeError: if the download fails.
        """
        return None

    async def download(self, file_id: str) -> bytes:
        """Download a file and return its content.

        :param file_id: Identifier of the file to download.
        :returns: The file content as bytes.
        :rtype: bytes
        """
        return b""
