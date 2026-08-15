"""Tests for --dry-run preview behaviour (NTH-004)."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from rst_to_md.config import SKIP_DIRS
from rst_to_md.converters import sphinx as sphinx_module
from rst_to_md.converters.rst import convert_directory
from rst_to_md.converters.sphinx import convert_sphinx_project


def test_rst_dry_run_writes_nothing(simple_project: Path, tmp_path: Path):
    out = tmp_path / "out"
    with mock.patch("pypandoc.convert_text", return_value="# x\n"):
        r = convert_directory(simple_project, out, dry_run=True)
    assert r == (2, 0, 0)
    assert not any(out.rglob("*.md"))


def test_rst_dry_run_lists_all(simple_project: Path, tmp_path: Path):
    out = tmp_path / "out"
    with mock.patch("pypandoc.convert_text", return_value="# x\n"):
        r = convert_directory(simple_project, out, dry_run=True)
    assert r[0] == 2  # matches discovered .rst count


def test_sphinx_dry_run_no_build(sphinx_min_project: Path, tmp_path: Path):
    out = tmp_path / "out"
    with mock.patch.object(sphinx_module, "build_sphinx_html") as build_mock:
        r = convert_sphinx_project(sphinx_min_project, out, dry_run=True)
    build_mock.assert_not_called()
    assert not (out / "_sphinx_build").exists()
    rst_count = len(
        [
            p
            for p in sphinx_min_project.rglob("*.rst")
            if p.parent.name not in SKIP_DIRS
        ]
    )
    assert r[0] == rst_count


def test_sphinx_dry_run_applies_skip_filters(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text("pass\n", encoding="utf-8")
    (src / "index.rst").write_text("Title\n=====\n", encoding="utf-8")
    skipdir = src / "examples"
    skipdir.mkdir()
    (skipdir / "ex.rst").write_text("x\n", encoding="utf-8")
    out = tmp_path / "out"
    r = convert_sphinx_project(src, out, dry_run=True)
    # only index.rst is planned; ex.rst under examples is skipped.
    assert r[0] == 1
