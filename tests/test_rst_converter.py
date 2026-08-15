"""Tests for the simple RST converter (P1, P3)."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from rst_to_md.converters import rst as rst_module
from rst_to_md.converters.rst import convert_directory, convert_rst_to_md


def test_convert_rst_to_md_returns_bool(tmp_path: Path):
    src = tmp_path / "a.rst"
    src.write_text("Title\n=====\n\nHello.\n", encoding="utf-8")
    dst = tmp_path / "nested" / "out" / "a.md"  # parent does not exist yet
    with mock.patch("pypandoc.convert_text", return_value="# Title\n\nHello.\n"):
        result = convert_rst_to_md(src, dst)
    assert result is True
    assert dst.exists()
    assert "Hello." in dst.read_text(encoding="utf-8")


def test_convert_rst_to_md_failure_returns_false(tmp_path: Path):
    src = tmp_path / "a.rst"
    src.write_text("Title\n=====\n", encoding="utf-8")
    dst = tmp_path / "a.md"
    with mock.patch("pypandoc.convert_text", side_effect=RuntimeError("boom")):
        result = convert_rst_to_md(src, dst)
    assert result is False
    # Failure must not create an output file.
    assert not dst.exists()


def test_convert_directory_deterministic_order(tmp_path: Path):
    """Processing order must be sorted regardless of rglob order (P3)."""
    input_dir = tmp_path / "docs"
    (input_dir / "b").mkdir(parents=True)
    (input_dir / "a").mkdir(parents=True)
    (input_dir / "b" / "z.rst").write_text("z", encoding="utf-8")
    (input_dir / "a" / "m.rst").write_text("m", encoding="utf-8")
    (input_dir / "a" / "a.rst").write_text("a", encoding="utf-8")

    output_dir = tmp_path / "out"
    order = []

    def fake_convert(src, dst, wrap="none", fmt="gfm", errors=None, show_progress=False):
        order.append(src.name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("x", encoding="utf-8")
        return True

    with mock.patch.object(rst_module, "convert_rst_to_md", side_effect=fake_convert):
        success, errors, _ = convert_directory(input_dir, output_dir)

    assert success == 3
    assert errors == 0
    # Sorted by full path: a/a.rst, a/m.rst, b/z.rst
    assert order == ["a.rst", "m.rst", "z.rst"]


def test_convert_directory_no_files(tmp_path: Path):
    input_dir = tmp_path / "empty"
    input_dir.mkdir()
    output_dir = tmp_path / "out"
    success, errors, skipped = convert_directory(input_dir, output_dir)
    assert (success, errors, skipped) == (0, 0, 0)


def test_convert_directory_returns_three_tuple(simple_project: Path):
    # IMP-003: simple mode must return (success, errors, skipped) with skipped=0.
    with mock.patch("pypandoc.convert_text", return_value="# x\n"):
        result = convert_directory(simple_project, simple_project.parent / "out")
    assert isinstance(result, tuple)
    assert len(result) == 3
    success, errors, skipped = result
    assert success == 2
    assert errors == 0
    assert skipped == 0


def test_rst_uses_shared_postprocess(tmp_path: Path):
    # IMP-005: simple mode must route through the shared post_process_markdown.
    import rst_to_md.core.postprocess as pp

    src = tmp_path / "a.rst"
    src.write_text("Title\n=====\n\nHello.\n", encoding="utf-8")
    dst = tmp_path / "a.md"
    with (
        mock.patch("pypandoc.convert_text", return_value="# Title\n\nHello.\n"),
        mock.patch(
            "rst_to_md.converters.rst.post_process_markdown",
            wraps=pp.post_process_markdown,
        ) as spy,
    ):
        convert_rst_to_md(src, dst)
    spy.assert_called()


# --------------------------------------------------------------------------- #
# NTH-001: incremental caching
# --------------------------------------------------------------------------- #
def test_convert_directory_skips_cached(simple_project: Path, tmp_path: Path):
    out = tmp_path / "out"
    with mock.patch("pypandoc.convert_text", return_value="# x\n"):
        r1 = convert_directory(simple_project, out)
        r2 = convert_directory(simple_project, out)
    assert r1[0] == 2 and r1[2] == 0
    assert r2[2] == 2 and r2[0] == 0  # all cached on second run


def test_convert_directory_cache_off_reconverts(simple_project: Path, tmp_path: Path):
    out = tmp_path / "out"
    with mock.patch("pypandoc.convert_text", return_value="# x\n"):
        convert_directory(simple_project, out)
        r2 = convert_directory(simple_project, out, use_cache=False)
    assert r2[0] == 2 and r2[2] == 0


def test_convert_directory_cache_after_source_change(simple_project: Path, tmp_path: Path):
    import os
    import time

    out = tmp_path / "out"
    with mock.patch("pypandoc.convert_text", return_value="# x\n"):
        convert_directory(simple_project, out)
        f = simple_project / "index.rst"
        time.sleep(0.02)
        os.utime(f, None)  # bump mtime to now (newer than the generated .md)
        r2 = convert_directory(simple_project, out)
    assert r2[0] == 1  # index.rst reconverted
    assert r2[2] == 1  # api.rst still cached


# --------------------------------------------------------------------------- #
# NTH-003: per-file error surfacing
# --------------------------------------------------------------------------- #
def test_convert_rst_to_md_records_error(tmp_path: Path):
    src = tmp_path / "a.rst"
    src.write_text("x", encoding="utf-8")
    dst = tmp_path / "a.md"
    errs: list[str] = []
    with mock.patch("pypandoc.convert_text", side_effect=RuntimeError("boom")):
        ok = convert_rst_to_md(src, dst, errors=errs)
    assert ok is False
    assert len(errs) == 1
    assert "a.rst" in errs[0]


def test_convert_rst_to_md_no_error_when_none(tmp_path: Path):
    src = tmp_path / "a.rst"
    src.write_text("x", encoding="utf-8")
    dst = tmp_path / "a.md"
    with mock.patch("pypandoc.convert_text", return_value="# x\n"):
        ok = convert_rst_to_md(src, dst)  # default errors=None must not raise
    assert ok is True
