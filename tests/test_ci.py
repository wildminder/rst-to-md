"""Tests that CI / pre-commit configuration files are valid (P8.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

yaml = pytest.importorskip("yaml")


def test_ci_workflow_valid():
    path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert path.is_file(), "CI workflow missing"
    data = yaml.safe_load(path.read_text("utf-8"))
    assert "jobs" in data
    assert "lint-type-test" in data["jobs"]
    matrix = data["jobs"]["lint-type-test"]["strategy"]["matrix"]
    assert "3.13" in matrix["python-version"]


def test_precommit_config_valid():
    path = REPO_ROOT / ".pre-commit-config.yaml"
    assert path.is_file(), "pre-commit config missing"
    data = yaml.safe_load(path.read_text("utf-8"))
    ids = [hook["id"] for repo in data["repos"] for hook in repo["hooks"]]
    assert "ruff" in ids
    assert "trailing-whitespace" in ids


def test_ruff_mypy_version_aligned():
    """NTH-005: ruff target-version and mypy python_version must agree on the
    minimum Python version (regex parse, no tomllib needed for 3.8 compat)."""
    import re

    text = (REPO_ROOT / "pyproject.toml").read_text("utf-8")

    ruff = re.search(r'target-version\s*=\s*"py(\d+)"', text)
    mypy = re.search(r'python_version\s*=\s*"(\d+)\.(\d+)"', text)
    assert ruff, "ruff target-version not found in pyproject.toml"
    assert mypy, "mypy python_version not found in pyproject.toml"

    ruff_full = ruff.group(1)  # e.g. "310"
    ruff_version = f"{ruff_full[0]}.{ruff_full[1:]}"  # "3.10"
    mypy_version = f"{mypy.group(1)}.{mypy.group(2)}"  # "3.10"

    assert ruff_version == mypy_version, (
        f"ruff target-version py{ruff_full} ({ruff_version}) != mypy python_version {mypy_version}"
    )


def _minimum_python_from_requires(text: str) -> str:
    import re

    m = re.search(r'requires-python\s*=\s*">=(\d+)\.(\d+)"', text)
    assert m, "requires-python not found in pyproject.toml"
    return f"{m.group(1)}.{m.group(2)}"


def test_python_version_sources_consistent():
    """IMP-006: requires-python, trove classifiers, the CI matrix, and the
    ruff/mypy tooling targets must all agree on the minimum Python version."""
    import re

    text = (REPO_ROOT / "pyproject.toml").read_text("utf-8")
    minimum = _minimum_python_from_requires(text)  # e.g. "3.10"
    major, minor = minimum.split(".")

    # 1. Classifiers: no classifier below the minimum; the minimum is present.
    classifier_versions = re.findall(r'"Programming Language :: Python :: (\d+\.\d+)"', text)
    assert classifier_versions, "no Python version classifiers found"
    assert minimum in classifier_versions
    for v in classifier_versions:
        assert tuple(map(int, v.split("."))) >= (int(major), int(minor)), (
            f"classifier {v} is below requires-python {minimum}"
        )

    # 2. CI matrix: no leg below the minimum; the minimum is tested.
    ci = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8"))
    matrix = ci["jobs"]["lint-type-test"]["strategy"]["matrix"]["python-version"]
    assert minimum in matrix
    for leg in matrix:
        assert tuple(map(int, str(leg).split("."))) >= (int(major), int(minor)), (
            f"CI leg {leg} is below requires-python {minimum}"
        )

    # 3. Tooling targets equal the minimum (extends NTH-005's ruff==mypy rule).
    ruff = re.search(r'target-version\s*=\s*"py(\d)(\d+)"', text)
    mypy = re.search(r'python_version\s*=\s*"(\d+)\.(\d+)"', text)
    assert ruff and mypy
    assert f"{ruff.group(1)}.{ruff.group(2)}" == minimum
    assert f"{mypy.group(1)}.{mypy.group(2)}" == minimum


def test_coverage_floor_configured():
    """NTH-008: a coverage floor must be configured so accidental coverage
    loss fails the run. The floor must be a sane percentage and must not be
    silently disabled (fail_under = 0 would be a no-op)."""
    import re

    text = (REPO_ROOT / "pyproject.toml").read_text("utf-8")
    m = re.search(r"fail_under\s*=\s*(\d+)", text)
    assert m, "fail_under not configured in pyproject.toml"
    floor = int(m.group(1))
    assert 0 < floor <= 100, f"fail_under={floor} is not a sane percentage"
    # The floor must live under [tool.coverage.report] (regex parse, no
    # tomllib needed, consistent with the other guards in this module).
    assert "[tool.coverage.report]" in text
