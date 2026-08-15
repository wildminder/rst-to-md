"""Tests that the public API is importable after the restructure (P8.1)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

import rst_to_md
from rst_to_md import (
    ConversionError,
    RstToMdError,
    SphinxBuildError,
    build_sphinx_html,
    check_sphinx_installed,
    convert_directory,
    convert_html_to_md,
    convert_rst_to_md,
    convert_sphinx_project,
    is_sphinx_project,
)
from rst_to_md.converters.rst import convert_directory as rst_convert_directory
from rst_to_md.converters.sphinx import (
    build_stub_sitecustomize,
)
from rst_to_md.converters.sphinx import (
    convert_sphinx_project as sphinx_convert_project,
)
from rst_to_md.core.postprocess import post_process_markdown
from rst_to_md.exceptions import RstToMdError as ExcRstToMdError


def test_version_present():
    assert isinstance(rst_to_md.__version__, str)


def test_public_symbols_importable():
    # Simply importing the names above is the assertion.
    assert callable(convert_rst_to_md)
    assert callable(convert_directory)
    assert callable(convert_sphinx_project)
    assert callable(is_sphinx_project)
    assert callable(build_sphinx_html)
    assert callable(convert_html_to_md)
    assert callable(check_sphinx_installed)


def test_exception_hierarchy():
    assert issubclass(ConversionError, RstToMdError)
    assert issubclass(SphinxBuildError, RstToMdError)
    assert issubclass(ExcRstToMdError, Exception)


def test_converter_reexports_consistent():
    # The package-level and module-level functions should be the same objects.
    assert rst_convert_directory is convert_directory
    assert sphinx_convert_project is convert_sphinx_project


def test_postprocess_importable():
    assert callable(post_process_markdown)
    assert callable(build_stub_sitecustomize)


def test_sphinx_markdown_builder_importable():
    # Step 0: the direct Markdown builder dependency must be importable and
    # register a builder named "markdown".
    if importlib.util.find_spec("sphinx_markdown_builder") is None:
        pytest.skip("sphinx-markdown-builder not installed")
    from sphinx_markdown_builder import MarkdownBuilder

    assert MarkdownBuilder.name == "markdown"


def test_convert_directory_contract(tmp_path: Path):
    # IMP-003: the public convert_directory returns a 3-tuple
    # (success, errors, skipped) for parity with convert_sphinx_project.
    src = tmp_path / "docs"
    src.mkdir()
    result = convert_directory(src, tmp_path / "out")
    assert isinstance(result, tuple)
    assert len(result) == 3
    assert result[2] == 0
