"""Shared pytest fixtures for rst_to_md tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def simple_project(tmp_path: Path) -> Path:
    """Copy the simple RST fixture into a temp dir and return its path."""
    dest = tmp_path / "simple"
    shutil.copytree(FIXTURES_DIR / "simple", dest)
    return dest


@pytest.fixture
def sphinx_min_project(tmp_path: Path) -> Path:
    """Copy the minimal Sphinx fixture into a temp dir and return its path."""
    dest = tmp_path / "sphinx_min"
    shutil.copytree(FIXTURES_DIR / "sphinx_min", dest)
    return dest


@pytest.fixture
def sphinx_md_project(tmp_path: Path) -> Path:
    """Copy the direct Markdown builder parity fixture into a temp dir."""
    dest = tmp_path / "sphinx_md"
    shutil.copytree(FIXTURES_DIR / "sphinx_md", dest)
    return dest


@pytest.fixture
def sphinx_md_xref_project(tmp_path: Path) -> Path:
    """Copy the cross-page autodoc signature xref fixture into a temp dir.

    Documents a type (BaseSession) on its own page so a reference to it from
    another class's signature becomes a cross-page pending_xref -> reference
    node (the case that produced ambiguous `[Type](page.md#fq.name)` links).
    """
    dest = tmp_path / "sphinx_md_xref"
    shutil.copytree(FIXTURES_DIR / "sphinx_md_xref", dest)
    return dest


@pytest.fixture
def sphinx_md_autosummary_project(tmp_path: Path) -> Path:
    """Copy the autosummary source-enrichment fixture into a temp dir.

    The page (``index.rst``) carries ``.. currentmodule:: sample_pkg`` plus an
    ``.. autosummary::`` table; ``sample_pkg`` lives inside the docs tree and is
    importable, so the ``auto`` ladder may generate real tables, and the AST
    source map enriches any remaining stub cells without importing the package.
    """
    dest = tmp_path / "sphinx_md_autosummary"
    shutil.copytree(FIXTURES_DIR / "sphinx_md_autosummary", dest)
    return dest


@pytest.fixture
def sphinx_local_directives_project(tmp_path: Path) -> Path:
    """Copy the local-directive regression fixture into a temp dir.

    ``conf.py`` puts its own directory on ``sys.path``, imports the LOCAL
    ``custom_directives`` module, and registers its ``Echo`` class as the
    ``.. echo::`` directive used by ``index.rst``. The local module is not
    importable from the parent process, so the stubbing machinery must detect
    its locality and never shadow it with a ``_DummyModule`` (the torchaudio
    ``custom_directives`` crash).
    """
    dest = tmp_path / "sphinx_local_directives"
    shutil.copytree(FIXTURES_DIR / "sphinx_local_directives", dest)
    return dest


@pytest.fixture
def sphinx_stubbed_directive_project(tmp_path: Path) -> Path:
    """Copy the stubbed-directive regression fixture into a temp dir.

    ``conf.py`` imports a directive class from a guaranteed-missing package
    and registers it. The import must keep working via a ``_DummyModule``,
    and the ``run_directive`` guard must degrade the unusable directive to a
    system message instead of aborting the whole build.
    """
    dest = tmp_path / "sphinx_stubbed_directive"
    shutil.copytree(FIXTURES_DIR / "sphinx_stubbed_directive", dest)
    return dest


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """A fresh output directory."""
    dest = tmp_path / "out"
    dest.mkdir()
    return dest
