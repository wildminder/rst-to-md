"""Tests for parallel (ThreadPoolExecutor) conversion (NTH-002)."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from rst_to_md.converters.rst import convert_directory
from rst_to_md.converters.sphinx import convert_sphinx_project


def test_rst_parallel_same_result_as_serial(simple_project: Path, tmp_path: Path):
    out_serial = tmp_path / "serial"
    out_par = tmp_path / "par"
    with mock.patch("pypandoc.convert_text", return_value="# x\n"):
        r_serial = convert_directory(simple_project, out_serial, max_workers=1)
        r_par = convert_directory(simple_project, out_par, max_workers=4)
    assert r_serial == r_par
    serial_files = {p.relative_to(out_serial) for p in out_serial.rglob("*.md")}
    par_files = {p.relative_to(out_par) for p in out_par.rglob("*.md")}
    assert serial_files == par_files


def test_rst_parallel_counts_correct(simple_project: Path, tmp_path: Path):
    out = tmp_path / "out"

    def fake_convert(text, *a, **k):
        if "api" in text:
            raise RuntimeError("boom")
        return "# x\n"

    with mock.patch("pypandoc.convert_text", side_effect=fake_convert):
        r = convert_directory(simple_project, out, max_workers=2)
    # simple_project has index.rst + api.rst; api fails -> 1 error, 1 success.
    assert r[0] == 1
    assert r[1] == 1


def test_sphinx_parallel_same_result_as_serial(
    sphinx_min_project: Path, tmp_path: Path
):
    out_serial = tmp_path / "serial"
    out_par = tmp_path / "par"
    with mock.patch("html_to_markdown.convert", return_value="# x\n"):
        r_serial = convert_sphinx_project(
            sphinx_min_project, out_serial, max_workers=1, use_cache=False
        )
        r_par = convert_sphinx_project(
            sphinx_min_project, out_par, max_workers=4, use_cache=False
        )
    assert r_serial[:2] == r_par[:2]
    serial_files = {p.relative_to(out_serial) for p in out_serial.rglob("*.md")}
    par_files = {p.relative_to(out_par) for p in out_par.rglob("*.md")}
    assert serial_files == par_files
