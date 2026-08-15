"""Integration tests running the real conversion pipeline on fixtures (P6)."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from rst_to_md.converters.rst import convert_directory
from rst_to_md.converters.sphinx import (
    check_sphinx_installed,
    convert_sphinx_project,
)
from rst_to_md.exceptions import SphinxBuildError

# These tests exercise the full pipeline and require sphinx + html_to_markdown.
pytestmark = pytest.mark.skipif(
    not check_sphinx_installed(),
    reason="sphinx not installed",
)


def _html_to_markdown_available() -> bool:
    try:
        import html_to_markdown  # noqa: F401

        return True
    except ImportError:
        return False


def test_sphinx_min_conversion(sphinx_min_project: Path, output_dir: Path):
    if not _html_to_markdown_available():
        pytest.skip("html_to_markdown not installed")

    success, errors, skipped = convert_sphinx_project(
        sphinx_min_project, output_dir, lightweight=True
    )

    assert errors == 0
    assert success >= 2  # index + guide
    assert (output_dir / "index.md").is_file()
    assert (output_dir / "guide.md").is_file()

    index_md = (output_dir / "index.md").read_text("utf-8")
    assert "sphinx_min documentation" in index_md

    guide_md = (output_dir / "guide.md").read_text("utf-8")
    # Link rewriting: index.html -> index.md
    assert "index.md" in guide_md

    # Lightweight mode must not copy assets.
    assert not (output_dir / "_images").exists()
    # Build directory must be cleaned up.
    assert not (output_dir / "_sphinx_build").exists()


def test_simple_conversion(simple_project: Path, output_dir: Path):
    try:
        success, errors, _ = convert_directory(simple_project, output_dir)
    except Exception as exc:  # pragma: no cover - depends on pandoc binary
        pytest.skip(f"pypandoc/pandoc unavailable: {exc}")
    assert errors == 0
    assert success == 2
    assert (output_dir / "index.md").is_file()
    assert (output_dir / "api.md").is_file()
    # Link rewriting in simple mode too.
    assert "api.md" in (output_dir / "index.md").read_text("utf-8")


_FIXTURE_FALLBACK = Path(__file__).resolve().parent / "fixtures" / "sphinx_fallback"


def test_sphinx_fallback_recovers_with_mock(tmp_path: Path):
    """IMP-001: a build that crashes (non-napoleon) is recovered by the
    mock-all fallback, which still emits Markdown.

    The first build is simulated to fail; the converter must retry once with
    ``mock_all_imports=True`` (passing the conf's top-level imports) and then
    succeed. This exercises the real retry path against the real fixture conf.
    """
    if not _html_to_markdown_available():
        pytest.skip("html_to_markdown not installed")

    out = tmp_path / "out"
    calls = []

    def fake_build(
        src_dir,
        build_dir,
        sphinx_opts=None,
        verbose=False,
        lightweight=True,
        stub_modules=None,
        mock_all_imports=False,
        builder="html",
        build_workers=0,
        autosummary_generate="auto",
    ):
        calls.append((stub_modules, mock_all_imports))
        if len(calls) == 1:
            raise SphinxBuildError("simulated crash")
        html_dir = build_dir / "html"
        html_dir.mkdir(parents=True, exist_ok=True)
        (html_dir / "index.html").write_text("<html><body>content</body></html>", encoding="utf-8")
        return True

    with (
        mock.patch("rst_to_md.converters.sphinx.build_sphinx_html", side_effect=fake_build),
        mock.patch("html_to_markdown.convert", return_value="# x\n"),
    ):
        success, errors, skipped = convert_sphinx_project(_FIXTURE_FALLBACK, out, lightweight=True)

    assert success == 1
    assert errors == 0
    assert (out / "index.md").is_file()
    # The fallback retry must mock ALL imports (including importable ones) and
    # pass the conf's top-level imports as the stub set.
    assert len(calls) == 2
    assert calls[1][1] is True  # mock_all_imports
    assert "crashpkg" in calls[1][0]
