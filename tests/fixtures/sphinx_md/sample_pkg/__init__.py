"""A tiny package used to exercise the direct Markdown builder parity test.

The class hierarchy and members mirror a typical autodoc target so the
generated Markdown reproduces the ``Bases:``/inheritance list and the
signature/member markup that the converter must preserve.
"""


class Base:
    """Base class for the calculator."""


class Calculator(Base):
    """A simple calculator.

    :param precision: Number of decimal places to round to.
    :type precision: int
    :raises ValueError: if the precision is negative.
    """

    def __init__(self, precision: int = 2) -> None:
        self.precision = precision

    @property
    def scale(self) -> int:
        """The current scale factor.

        :returns: the scale as an int.
        """
        return self.precision

    def add(self, a: int, b: int) -> int:
        """Return the sum of two integers.

        :param a: first operand.
        :param b: second operand.
        :returns: the sum.
        """
        return a + b
