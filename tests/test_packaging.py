"""Tests for project packaging metadata (P0)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_pyproject() -> dict:
    try:
        import tomllib

        return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text("utf-8"))
    except ModuleNotFoundError:
        try:
            import tomli  # type: ignore

            return tomli.loads((REPO_ROOT / "pyproject.toml").read_text("utf-8"))
        except ImportError as exc:  # pragma: no cover - tomli missing
            pytest.skip(f"tomllib/tomli unavailable: {exc}")


def test_pyproject_parses():
    data = _load_pyproject()
    assert data["project"]["name"] == "rst-to-md"
    deps = data["project"]["dependencies"]
    assert isinstance(deps, list)
    # 4 runtime deps: pypandoc-binary, sphinx, html-to-markdown, beautifulsoup4.
    # sphinx-markdown-builder is VENDORED (rst_to_md/_vendor), not a PyPI dep.
    assert len(deps) == 4
    assert any("beautifulsoup4" in d for d in deps)
    assert not any("sphinx-markdown-builder" in d for d in deps)
    # The vendored builder must be present in the tree.
    vendored = REPO_ROOT / "rst_to_md" / "_vendor" / "sphinx_markdown_builder"
    assert (vendored / "translator.py").is_file()
    assert (vendored / "builder.py").is_file()
    # No tab-indented dependency lines (TOML 1.0 disallows tabs for indentation).
    raw = (REPO_ROOT / "pyproject.toml").read_text("utf-8")
    for line in raw.splitlines():
        stripped = line.lstrip(" ")
        if stripped.startswith('"') or stripped.startswith("'"):
            assert not line.startswith("\t"), "dependency line uses a tab for indentation"


def test_sphinx_markdown_builder_vendored():
    """The markdown builder is vendored into rst_to_md/_vendor (not a PyPI dep),
    so it is always available and patchable. It is loaded at runtime via PYTHONPATH
    shadowing (bare name `sphinx_markdown_builder`), so we verify the files exist
    and that the converter wires the vendored path + bare module name."""
    vendored = REPO_ROOT / "rst_to_md" / "_vendor" / "sphinx_markdown_builder"
    assert (vendored / "__init__.py").is_file(), "vendored __init__ missing"
    assert (vendored / "translator.py").is_file(), "vendored translator missing"
    assert (vendored / "builder.py").is_file(), "vendored builder missing"

    # The converter must reference the bare module name (loaded via PYTHONPATH).
    sphinx_src = (REPO_ROOT / "rst_to_md" / "converters" / "sphinx.py").read_text("utf-8")
    assert '"sphinx_markdown_builder"' in sphinx_src, (
        "converter must register the vendored builder by its bare module name"
    )
    assert "_vendor" in sphinx_src, (
        "converter must prepend rst_to_md/_vendor to PYTHONPATH for the subprocess"
    )


def test_license_file_exists():
    assert (REPO_ROOT / "LICENSE").is_file()
    assert "MIT License" in (REPO_ROOT / "LICENSE").read_text("utf-8")


def test_version_in_init_is_1_2_1():
    import rst_to_md

    # CRIT-001: runtime version must match the CHANGELOG top entry (1.2.1).
    assert rst_to_md.__version__ == "1.2.1"


def test_pyproject_version_is_1_2_1():
    data = _load_pyproject()
    assert data["project"]["version"] == "1.2.1"


def test_version_matches_installed_metadata():
    import importlib.metadata as md

    import rst_to_md

    try:
        installed = md.version("rst-to-md")
    except md.PackageNotFoundError:
        pytest.skip("rst-to-md not installed (editable install required)")
    assert installed == rst_to_md.__version__


def test_version_sources_consistent():
    import rst_to_md

    # Regression guard: the two version sources must never drift again.
    data = _load_pyproject()
    assert rst_to_md.__version__ == data["project"]["version"]
