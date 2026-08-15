"""RST to Markdown Converter Package."""

from __future__ import annotations

__version__ = "1.4.3"
__author__ = "Wildminder"

from .converters.rst import convert_directory, convert_rst_to_md
from .converters.sphinx import (
    build_sphinx_html,
    check_sphinx_installed,
    convert_html_to_md,
    convert_sphinx_project,
    is_sphinx_project,
)
from .core.html_clean import (
    clean_sphinx_html,
    extract_content_html,
    normalize_autodoc_html,
)
from .core.postprocess import strip_sphinx_chrome
from .exceptions import ConversionError, RstToMdError, SphinxBuildError

__all__ = [
    "convert_rst_to_md",
    "convert_directory",
    "convert_sphinx_project",
    "is_sphinx_project",
    "build_sphinx_html",
    "convert_html_to_md",
    "check_sphinx_installed",
    "extract_content_html",
    "normalize_autodoc_html",
    "clean_sphinx_html",
    "strip_sphinx_chrome",
    "RstToMdError",
    "ConversionError",
    "SphinxBuildError",
    "__version__",
]
