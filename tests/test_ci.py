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
