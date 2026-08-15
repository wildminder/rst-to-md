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


def test_version_in_init_matches_changelog():
    """CRIT-002: the single source of truth (__init__.__version__) must equal
    the top *released* CHANGELOG entry (the [Unreleased] section is ignored)."""
    import re

    import rst_to_md

    changelog = (REPO_ROOT / "CHANGELOG.md").read_text("utf-8")
    m = re.search(r"^## \[(?!Unreleased)(\d+\.\d+\.\d+)\]", changelog, re.M)
    assert m, "no released version heading found in CHANGELOG.md"
    assert rst_to_md.__version__ == m.group(1), (
        f"__version__ {rst_to_md.__version__} != CHANGELOG top release {m.group(1)}"
    )


def test_pyproject_version_is_dynamic():
    """CRIT-002: pyproject must NOT hardcode a version; it must declare the
    version dynamic and point hatchling at rst_to_md/__init__.py."""
    data = _load_pyproject()
    assert "version" not in data["project"], "static version must be removed"
    assert "version" in data["project"].get("dynamic", [])
    hatch = data.get("tool", {}).get("hatch", {}).get("version", {})
    assert hatch.get("path") == "rst_to_md/__init__.py"


def test_version_matches_installed_metadata():
    import importlib.metadata as md

    import rst_to_md

    try:
        installed = md.version("rst-to-md")
    except md.PackageNotFoundError:
        pytest.skip("rst-to-md not installed (editable install required)")
    assert installed == rst_to_md.__version__


def test_version_sources_consistent():
    """CRIT-002 regression guard: runtime version, installed metadata, and the
    CHANGELOG top release must never drift again."""
    import importlib.metadata as md
    import re

    import rst_to_md

    changelog = (REPO_ROOT / "CHANGELOG.md").read_text("utf-8")
    m = re.search(r"^## \[(?!Unreleased)(\d+\.\d+\.\d+)\]", changelog, re.M)
    assert m and rst_to_md.__version__ == m.group(1)
    try:
        assert md.version("rst-to-md") == rst_to_md.__version__
    except md.PackageNotFoundError:
        pytest.skip("rst-to-md not installed (editable install required)")


def test_wheel_metadata_version_matches_init(tmp_path: Path):
    """CRIT-002: a real build must stamp the wheel METADATA with __version__.
    Builds a wheel via `python -m build --wheel` into tmp and parses
    `Name`/`Version` from the METADATA. Skipped if `build` is unavailable."""
    import subprocess
    import sys
    import zipfile

    try:
        import build  # noqa: F401
    except ImportError:
        pytest.skip("python-build not installed")

    res = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr[-2000:]
    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as zf:
        metadata_names = [n for n in zf.namelist() if n.endswith("METADATA")]
        assert metadata_names
        metadata = zf.read(metadata_names[0]).decode("utf-8")
    import rst_to_md

    assert f"Version: {rst_to_md.__version__}" in metadata
    assert "Name: rst-to-md" in metadata
