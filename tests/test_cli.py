"""Tests for the CLI layer (P5)."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from rst_to_md import cli


def test_version_exits(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "rst-to-md 1.2.1" in capsys.readouterr().out


def test_invalid_input_dir_returns_2():
    assert cli.main(["/this/path/does/not/exist"]) == 2


def test_simple_mode_success(tmp_path: Path):
    inp = tmp_path / "docs"
    inp.mkdir()
    out = tmp_path / "out"
    with mock.patch(
        "rst_to_md.cli.convert_directory", return_value=(3, 0, 0)
    ) as m:
        code = cli.main([str(inp), str(out)])
    assert code == 0
    m.assert_called_once()


def test_simple_mode_errors_return_1(tmp_path: Path):
    inp = tmp_path / "docs"
    inp.mkdir()
    out = tmp_path / "out"
    with mock.patch("rst_to_md.cli.convert_directory", return_value=(1, 2, 0)):
        code = cli.main([str(inp), str(out)])
    assert code == 1


def test_cli_simple_uses_three_tuple(tmp_path: Path):
    # IMP-003: the CLI must unpack the 3-tuple returned by convert_directory
    # (success, errors, skipped) without raising.
    inp = tmp_path / "docs"
    inp.mkdir()
    out = tmp_path / "out"
    with mock.patch(
        "rst_to_md.cli.convert_directory", return_value=(3, 0, 0)
    ) as m:
        code = cli.main([str(inp), str(out)])
    assert code == 0
    m.assert_called_once()


def test_sphinx_non_project_returns_2(tmp_path: Path):
    inp = tmp_path / "docs"
    inp.mkdir()  # no conf.py
    out = tmp_path / "out"
    with mock.patch("rst_to_md.cli.check_sphinx_installed", return_value=True):
        code = cli.main([str(inp), str(out), "--sphinx"])
    assert code == 2


def test_sphinx_not_installed_returns_1(tmp_path: Path):
    inp = tmp_path / "docs"
    inp.mkdir()
    (inp / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"
    with mock.patch("rst_to_md.cli.check_sphinx_installed", return_value=False):
        code = cli.main([str(inp), str(out), "--sphinx"])
    assert code == 1


def test_sphinx_mode_dispatch(tmp_path: Path):
    inp = tmp_path / "docs"
    inp.mkdir()
    (inp / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"
    with mock.patch(
        "rst_to_md.cli.check_sphinx_installed", return_value=True
    ), mock.patch(
        "rst_to_md.cli.convert_sphinx_project", return_value=(2, 0, 1)
    ) as m:
        code = cli.main([str(inp), str(out), "--sphinx"])
    assert code == 0
    m.assert_called_once()


def test_verbose_logging_emits_input_dir(tmp_path: Path, capsys):
    inp = tmp_path / "docs"
    inp.mkdir()
    out = tmp_path / "out"
    with mock.patch("rst_to_md.cli.convert_directory", return_value=(0, 0, 0)):
        cli.main([str(inp), str(out), "-v"])
    err = capsys.readouterr().err
    assert "Input directory" in err


# --------------------------------------------------------------------------- #
# NTH-001/002/003/004/006: CLI flag plumbing
# --------------------------------------------------------------------------- #
def test_cli_no_cache_flag_parsed(tmp_path: Path):
    inp = tmp_path / "docs"
    inp.mkdir()
    out = tmp_path / "out"
    with mock.patch(
        "rst_to_md.cli.convert_directory", return_value=(0, 0, 0)
    ) as m:
        cli.main([str(inp), str(out), "--no-cache"])
    assert m.call_args.kwargs.get("use_cache") is False


def test_cli_default_cache_on(tmp_path: Path):
    inp = tmp_path / "docs"
    inp.mkdir()
    out = tmp_path / "out"
    with mock.patch(
        "rst_to_md.cli.convert_directory", return_value=(0, 0, 0)
    ) as m:
        cli.main([str(inp), str(out)])
    assert m.call_args.kwargs.get("use_cache") is True


def test_cli_workers_parsed(tmp_path: Path):
    inp = tmp_path / "docs"
    inp.mkdir()
    out = tmp_path / "out"
    with mock.patch(
        "rst_to_md.cli.convert_directory", return_value=(0, 0, 0)
    ) as m:
        cli.main([str(inp), str(out), "--workers", "4"])
    assert m.call_args.kwargs.get("max_workers") == 4


def test_cli_default_workers_serial(tmp_path: Path):
    inp = tmp_path / "docs"
    inp.mkdir()
    out = tmp_path / "out"
    with mock.patch(
        "rst_to_md.cli.convert_directory", return_value=(0, 0, 0)
    ) as m:
        cli.main([str(inp), str(out)])
    assert m.call_args.kwargs.get("max_workers") == 1


def test_cli_report_parsed(tmp_path: Path):
    inp = tmp_path / "docs"
    inp.mkdir()
    out = tmp_path / "out"
    report = tmp_path / "r.json"
    with mock.patch(
        "rst_to_md.cli.convert_directory", return_value=(0, 0, 0)
    ) as m:
        cli.main([str(inp), str(out), "--report", str(report)])
    assert m.call_args.kwargs.get("report_path") == report


def test_cli_dry_run_parsed(tmp_path: Path):
    inp = tmp_path / "docs"
    inp.mkdir()
    out = tmp_path / "out"
    with mock.patch(
        "rst_to_md.cli.convert_directory", return_value=(0, 0, 0)
    ) as m:
        cli.main([str(inp), str(out), "--dry-run"])
    assert m.call_args.kwargs.get("dry_run") is True


def test_cli_builder_parsed(tmp_path: Path):
    inp = tmp_path / "docs"
    inp.mkdir()
    (inp / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"
    with mock.patch(
        "rst_to_md.cli.check_sphinx_installed", return_value=True
    ), mock.patch(
        "rst_to_md.cli.convert_sphinx_project", return_value=(0, 0, 0)
    ) as m:
        cli.main([str(inp), str(out), "--sphinx", "--builder", "singlehtml"])
    assert m.call_args.kwargs.get("builder") == "singlehtml"


def test_cli_sphinx_markdown_builder(sphinx_min_project: Path, tmp_path: Path):
    """End-to-end: `rst-to-md --sphinx -b markdown` produces .md directly
    (no HTML stage) through the real CLI entry point."""
    out = tmp_path / "out"
    code = cli.main(
        [str(sphinx_min_project), str(out), "--sphinx", "-b", "markdown"]
    )
    assert code == 0
    assert (out / "index.md").exists()
    assert (out / "guide.md").exists()
    # System pages must not leak into the Markdown output.
    assert not (out / "genindex.md").exists()


def test_cli_sphinx_default_is_markdown(tmp_path: Path):
    """The default Sphinx builder is now the direct Markdown builder."""
    inp = tmp_path / "docs"
    inp.mkdir()
    (inp / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"
    with mock.patch(
        "rst_to_md.cli.check_sphinx_installed", return_value=True
    ), mock.patch(
        "rst_to_md.cli.convert_sphinx_project", return_value=(0, 0, 0)
    ) as m:
        cli.main([str(inp), str(out), "--sphinx"])
    assert m.call_args.kwargs.get("builder") == "markdown"


def test_cli_sphinx_html_fallback(tmp_path: Path):
    """The legacy HTML pipeline remains available via --builder html."""
    inp = tmp_path / "docs"
    inp.mkdir()
    (inp / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"
    with mock.patch(
        "rst_to_md.cli.check_sphinx_installed", return_value=True
    ), mock.patch(
        "rst_to_md.cli.convert_sphinx_project", return_value=(0, 0, 0)
    ) as m:
        cli.main([str(inp), str(out), "--sphinx", "--builder", "html"])
    assert m.call_args.kwargs.get("builder") == "html"


def test_cli_build_workers_parsed(tmp_path: Path):
    """--build-workers is forwarded to convert_sphinx_project (parallel build)."""
    inp = tmp_path / "docs"
    inp.mkdir()
    (inp / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"
    with mock.patch(
        "rst_to_md.cli.check_sphinx_installed", return_value=True
    ), mock.patch(
        "rst_to_md.cli.convert_sphinx_project", return_value=(0, 0, 0)
    ) as m:
        cli.main([str(inp), str(out), "--sphinx", "--build-workers", "4"])
    assert m.call_args.kwargs.get("build_workers") == 4


def test_cli_build_workers_default_auto(tmp_path: Path):
    """--build-workers defaults to 0 (auto = CPU count)."""
    inp = tmp_path / "docs"
    inp.mkdir()
    (inp / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"
    with mock.patch(
        "rst_to_md.cli.check_sphinx_installed", return_value=True
    ), mock.patch(
        "rst_to_md.cli.convert_sphinx_project", return_value=(0, 0, 0)
    ) as m:
        cli.main([str(inp), str(out), "--sphinx"])
    assert m.call_args.kwargs.get("build_workers") == 0


def test_cli_sphinx_resolves_source_subdir(tmp_path: Path):
    """Pointing --sphinx at a docs/ dir whose conf.py lives in docs/source/
    must resolve the project dir and dispatch to it (torchaudio layout)."""
    inp = tmp_path / "docs"
    source = inp / "source"
    source.mkdir(parents=True)
    (source / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"
    with mock.patch(
        "rst_to_md.cli.check_sphinx_installed", return_value=True
    ), mock.patch(
        "rst_to_md.cli.convert_sphinx_project", return_value=(1, 0, 0)
    ) as m:
        code = cli.main([str(inp), str(out), "--sphinx"])
    assert code == 0
    # The resolved project dir (docs/source) is passed, not docs/.
    assert m.call_args[0][0] == source


def test_cli_sphinx_no_conf_anywhere_returns_2(tmp_path: Path):
    """No conf.py in the input dir or its common subdirs -> exit code 2."""
    inp = tmp_path / "docs"
    inp.mkdir()
    out = tmp_path / "out"
    with mock.patch("rst_to_md.cli.check_sphinx_installed", return_value=True):
        code = cli.main([str(inp), str(out), "--sphinx"])
    assert code == 2
