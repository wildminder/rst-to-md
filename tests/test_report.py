"""Tests for the JSON summary report (NTH-003)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from rst_to_md.converters.rst import convert_directory
from rst_to_md.converters.sphinx import convert_sphinx_project


def test_report_written_with_counts(simple_project: Path, tmp_path: Path):
    out = tmp_path / "out"
    report = tmp_path / "report.json"
    with mock.patch("pypandoc.convert_text", return_value="# x\n"):
        r = convert_directory(simple_project, out, report_path=report)
    assert report.is_file()
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["summary"]["success"] == r[0]
    assert data["summary"]["errors"] == r[1]
    assert data["summary"]["skipped"] == r[2]
    assert len(data["files"]) == r[0] + r[2]


def test_report_lists_per_file_errors(simple_project: Path, tmp_path: Path):
    out = tmp_path / "out"
    report = tmp_path / "report.json"

    from rst_to_md.converters import rst as rst_mod

    def fake_convert(rst_path, md_path, *a, **k):
        if rst_path.name == "api.rst":
            return False
        return True

    with mock.patch.object(rst_mod, "convert_rst_to_md", side_effect=fake_convert):
        convert_directory(simple_project, out, report_path=report)
    data = json.loads(report.read_text(encoding="utf-8"))
    errors = [f for f in data["files"] if f["status"] == "error"]
    assert len(errors) == 1
    assert "api.rst" in errors[0]["path"]


def test_no_report_when_none(simple_project: Path, tmp_path: Path):
    out = tmp_path / "out"
    with mock.patch("pypandoc.convert_text", return_value="# x\n"):
        convert_directory(simple_project, out)  # no report_path
    assert not (tmp_path / "report.json").exists()


def test_sphinx_report_written(sphinx_min_project: Path, tmp_path: Path):
    out = tmp_path / "out"
    report = tmp_path / "report.json"
    with mock.patch("html_to_markdown.convert", return_value="# x\n"):
        r = convert_sphinx_project(sphinx_min_project, out, report_path=report, use_cache=False)
    assert report.is_file()
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["summary"]["success"] == r[0]
