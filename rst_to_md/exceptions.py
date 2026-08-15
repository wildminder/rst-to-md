"""Custom exceptions for rst_to_md."""

from __future__ import annotations


class RstToMdError(Exception):
    """Base class for all rst_to_md errors."""


class ConversionError(RstToMdError):
    """Raised when a single file conversion fails."""


class SphinxBuildError(RstToMdError):
    """Raised when the Sphinx HTML build step fails."""
