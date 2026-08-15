"""Tests for the live progress tracker (ProgressTracker + show_progress)."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest import mock

from rst_to_md import cli
from rst_to_md.converters.rst import convert_directory, convert_rst_to_md
from rst_to_md.converters.sphinx import convert_html_to_md
from rst_to_md.core.progress import ProgressTracker


class FakeTTY:
    """Minimal stream that pretends to be a terminal."""

    def __init__(self) -> None:
        self._parts: list[str] = []

    def isatty(self) -> bool:
        return True

    def write(self, text: str) -> int:
        self._parts.append(text)
        return len(text)

    def flush(self) -> None:
        pass

    def getvalue(self) -> str:
        return "".join(self._parts)


def test_tracker_counts_when_disabled():
    tr = ProgressTracker(total=3, enabled=False)
    tr.start()
    tr.update("ok")
    tr.update("error", "boom")
    tr.update("skipped")
    tr.finish()
    assert tr.count == 3
    assert tr.ok == 1 and tr.err == 1 and tr.skip == 1


def test_tracker_disabled_writes_nothing():
    tty = FakeTTY()
    tr = ProgressTracker(total=3, enabled=False, stream=tty)
    tr.start()
    tr.update("ok")
    tr.finish()
    assert tty.getvalue() == ""


def test_tracker_renders_on_tty():
    tty = FakeTTY()
    tr = ProgressTracker(total=3, enabled=True, stream=tty, desc="Converting RST")
    tr.start()
    tr.update("ok")
    tr.update("error", "boom")
    tr.update("skipped")
    tr.finish()
    out = tty.getvalue()
    assert "Converting RST" in out
    assert "1/3" in out  # first update
    assert "3/3" in out  # final
    assert "ok" in out and "err" in out and "skip" in out
    assert "/s" in out  # rate


def test_tracker_shows_error_message():
    tty = FakeTTY()
    tr = ProgressTracker(total=2, enabled=True, stream=tty)
    tr.start()
    tr.update("error", "boom in file.rst")
    assert "boom in file.rst" in tty.getvalue()


def test_leaf_rst_suppresses_ok_when_progress(caplog, tmp_path: Path):
    caplog.set_level(logging.INFO, logger="rst_to_md")
    src = tmp_path / "a.rst"
    src.write_text("x", encoding="utf-8")
    dst = tmp_path / "a.md"
    with mock.patch("pypandoc.convert_text", return_value="# x\n"):
        ok = convert_rst_to_md(src, dst, show_progress=True)
    assert ok is True
    assert "[OK]" not in caplog.text


def test_leaf_rst_suppresses_err_when_progress(caplog, tmp_path: Path):
    caplog.set_level(logging.INFO, logger="rst_to_md")
    src = tmp_path / "a.rst"
    src.write_text("x", encoding="utf-8")
    dst = tmp_path / "a.md"
    errs: list[str] = []
    with mock.patch(
        "pypandoc.convert_text", side_effect=RuntimeError("boom")
    ):
        ok = convert_rst_to_md(src, dst, show_progress=True, errors=errs)
    assert ok is False
    assert "[ERR]" not in caplog.text
    assert len(errs) == 1


def test_leaf_sphinx_suppresses_err_when_progress(caplog, tmp_path: Path):
    caplog.set_level(logging.INFO, logger="rst_to_md")
    html = tmp_path / "p.html"
    html.write_text("<html></html>", encoding="utf-8")
    md = tmp_path / "p.md"
    errs: list[str] = []
    with mock.patch(
        "html_to_markdown.convert", side_effect=RuntimeError("boom")
    ):
        ok = convert_html_to_md(html, md, show_progress=True, errors=errs)
    assert ok is False
    assert "[ERR]" not in caplog.text
    assert len(errs) == 1


def test_convert_directory_passes_show_progress(tmp_path: Path):
    inp = tmp_path / "docs"
    inp.mkdir()
    (inp / "a.rst").write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    seen: list[object] = []

    def fake(rst_path, md_path, *a, **k):
        seen.append(k.get("show_progress"))
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text("# x\n", encoding="utf-8")
        return True

    with mock.patch(
        "rst_to_md.converters.rst.convert_rst_to_md", side_effect=fake
    ):
        convert_directory(inp, out, show_progress=True)
    assert seen == [True]


def test_convert_directory_passes_show_progress_false(tmp_path: Path):
    inp = tmp_path / "docs"
    inp.mkdir()
    (inp / "a.rst").write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    seen: list[object] = []

    def fake(rst_path, md_path, *a, **k):
        seen.append(k.get("show_progress"))
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text("# x\n", encoding="utf-8")
        return True

    with mock.patch(
        "rst_to_md.converters.rst.convert_rst_to_md", side_effect=fake
    ):
        convert_directory(inp, out, show_progress=False)
    assert seen == [False]


def test_cli_no_progress_flag_parsed(tmp_path: Path):
    inp = tmp_path / "docs"
    inp.mkdir()
    out = tmp_path / "out"
    with mock.patch(
        "rst_to_md.cli.convert_directory", return_value=(0, 0, 0)
    ) as m:
        cli.main([str(inp), str(out), "--no-progress"])
    assert m.call_args.kwargs.get("show_progress") is False


def test_cli_default_progress_auto(tmp_path: Path):
    inp = tmp_path / "docs"
    inp.mkdir()
    out = tmp_path / "out"
    with mock.patch(
        "rst_to_md.cli.convert_directory", return_value=(0, 0, 0)
    ) as m:
        cli.main([str(inp), str(out)])
    # No flag => progress enabled (auto TTY detection happens inside the converter).
    assert m.call_args.kwargs.get("show_progress") is True
