"""Tests for autosummary table enrichment + generated stub pages (WS4, WS5).

These exercise the pure post-processors that fill otherwise-empty autosummary
table cells from an AST source map (built without importing the documented
package) and emit ``generated/<fqn>.md`` stub pages so the rewritten table
links resolve.
"""

from __future__ import annotations

from pathlib import Path

from rst_to_md.config import GENERATED_DIR_NAME
from rst_to_md.core.autosummary_enrich import (
    enrich_autosummary_table,
    enrich_file,
    extract_module_context,
    write_generated_stubs,
)
from rst_to_md.core.source_extract import (
    ObjectInfo,
    build_source_map,
    find_source_roots,
)


def _beat_map() -> dict[str, ObjectInfo]:
    """A minimal source map resembling ``librosa.beat``'s two functions."""
    return {
        "librosa.beat.beat_track": ObjectInfo(
            fqn="librosa.beat.beat_track",
            kind="function",
            signature="(*[, y, sr, onset_envelope])",
            summary="Dynamic programming beat tracker.",
            full_docstring=(
                "Dynamic programming beat tracker.\n\nTracks the beat in an audio time series."
            ),
            lineno=1,
        ),
        "librosa.beat.plp": ObjectInfo(
            fqn="librosa.beat.plp",
            kind="function",
            signature="(*[, y, sr, hop_length])",
            summary="Predominant local pulse (PLP) estimation.",
            full_docstring="Predominant local pulse (PLP) estimation.",
            lineno=10,
        ),
    }


# --------------------------------------------------------------------------- #
# WS4: enrich_autosummary_table
# --------------------------------------------------------------------------- #
def test_enrich_fills_empty_markdown_table():
    md = "| `beat_track` | |\n|---|---\n| `plp` | |\n"
    out = enrich_autosummary_table(md, "librosa.beat", _beat_map())
    # First cell rewritten to a link (code-span name) carrying the signature.
    assert "[`beat_track`](generated/librosa.beat.beat_track.md" in out
    assert "(*[, y, sr, onset_envelope])" in out
    # Second cell filled with the docstring summary.
    assert "Dynamic programming beat tracker." in out
    assert "[`plp`](generated/librosa.beat.plp.md" in out
    assert "Predominant local pulse (PLP) estimation." in out
    # No empty stub cells remain.
    assert "|  |" not in out
    assert "| |" not in out


def test_enrich_reproduces_beat_good_shape():
    """The librosa ``beat.md`` shape: a page with an autosummary table whose
    cells were empty (the documented package not imported). After enrichment the
    signatures + summaries appear and the empty ``|  |`` cells are gone.
    """
    bad_body = (
        "# librosa.beat\n"
        "\n"
        "Beat tracking and tempo functions.\n"
        "\n"
        "## Functions\n"
        "\n"
        "| `beat_track` | |\n"
        "|---|---\n"
        "| `plp` | |\n"
        "\n"
        "See the [index](index.md) for details.\n"
    )
    out = enrich_autosummary_table(bad_body, "librosa.beat", _beat_map())
    # Signatures + summaries now present.
    assert "(*[, y, sr, onset_envelope])" in out
    assert "Dynamic programming beat tracker." in out
    assert "(*[, y, sr, hop_length])" in out
    assert "Predominant local pulse (PLP) estimation." in out
    # No empty stub cells remain.
    assert "|  |" not in out
    assert "| |" not in out
    # Surrounding prose and links are preserved.
    assert "Beat tracking and tempo functions." in out
    assert "[index](index.md)" in out


def test_enrich_html_builder_table():
    """The html builder (or an already-linked table) presents the first cell as
    a link ``[name](generated/...md#fqn)``; the empty second cell is still filled
    and the link is preserved + signed.
    """
    md = (
        "| [beat_track](generated/librosa.beat.beat_track.md"
        "#librosa.beat.beat_track) | |\n|---|---\n"
    )
    out = enrich_autosummary_table(md, "librosa.beat", _beat_map())
    assert "[`beat_track`](generated/librosa.beat.beat_track.md" in out
    assert "Dynamic programming beat tracker." in out
    # The fqn anchor is preserved on the link.
    assert "generated/librosa.beat.beat_track.md#librosa.beat.beat_track" in out


def test_enrich_idempotent():
    md = "| `beat_track` | |\n|---|---\n"
    once = enrich_autosummary_table(md, "librosa.beat", _beat_map())
    twice = enrich_autosummary_table(once, "librosa.beat", _beat_map())
    assert once == twice


def test_enrich_skips_populated_row():
    md = "| `beat_track` | Existing description. |\n|---|---\n"
    out = enrich_autosummary_table(md, "librosa.beat", _beat_map())
    # An already-populated row is left untouched (no link injected over it).
    assert "Existing description." in out
    assert "[beat_track](generated/" not in out


def test_enrich_skips_unknown_name():
    md = "| `nonexistent` | |\n|---|---\n"
    out = enrich_autosummary_table(md, "librosa.beat", _beat_map())
    # A name not in the source map stays as a stub (unchanged).
    assert "| `nonexistent` | |" in out


def test_enrich_no_module_context_uses_bare_fqn():
    """Without a module context, a bare autosummary name resolves to a top-level
    fqn in the source map."""
    map_ = {
        "beat_track": ObjectInfo(
            fqn="beat_track",
            kind="function",
            signature="(y, sr)",
            summary="Bare fqn match.",
            full_docstring="",
            lineno=1,
        )
    }
    md = "| `beat_track` | |\n|---|---\n"
    out = enrich_autosummary_table(md, None, map_)
    assert "[`beat_track`](generated/beat_track.md" in out
    assert "Bare fqn match." in out


def test_enrich_does_not_touch_normal_data_table():
    md = "| Name | Description |\n|---|---|\n| Alice | A person. |\n| Bob | Another person. |\n"
    out = enrich_autosummary_table(md, "librosa.beat", _beat_map())
    # Ordinary data tables (no backtick name / link in the first cell) are left
    # completely untouched.
    assert out == md


# --------------------------------------------------------------------------- #
# WS4: extract_module_context
# --------------------------------------------------------------------------- #
def test_extract_module_context_last_currentmodule_wins(tmp_path: Path):
    rst = tmp_path / "page.rst"
    rst.write_text(
        ".. currentmodule:: a.b\n\nSome text.\n\n.. currentmodule:: c.d\n",
        encoding="utf-8",
    )
    assert extract_module_context(rst) == "c.d"


def test_extract_module_context_falls_back_to_automodule(tmp_path: Path):
    rst = tmp_path / "page.rst"
    rst.write_text(
        ".. automodule:: librosa.feature\n\n.. autofunction:: librosa.load\n",
        encoding="utf-8",
    )
    # No currentmodule; automodule names the module directly.
    assert extract_module_context(rst) == "librosa.feature"


def test_extract_module_context_none_without_directive(tmp_path: Path):
    rst = tmp_path / "page.rst"
    rst.write_text("Title\n=====\n\nBody text.\n", encoding="utf-8")
    assert extract_module_context(rst) is None


def test_extract_module_context_missing_file_returns_none(tmp_path: Path):
    assert extract_module_context(tmp_path / "nope.rst") is None


# --------------------------------------------------------------------------- #
# WS5: write_generated_stubs
# --------------------------------------------------------------------------- #
def test_write_generated_stubs_creates_files(tmp_path: Path):
    written = write_generated_stubs(tmp_path, _beat_map())
    assert len(written) == 2
    for f in written:
        assert f.exists()
    beat_page = tmp_path / GENERATED_DIR_NAME / "librosa.beat.beat_track.md"
    assert beat_page.is_file()
    content = beat_page.read_text(encoding="utf-8")
    assert content.startswith("# librosa.beat.beat_track\n")
    assert "(*[, y, sr, onset_envelope])" in content
    assert "Dynamic programming beat tracker." in content


def test_write_generated_stubs_anchor_target(tmp_path: Path):
    """The stub page heading text equals the fqn, which is the in-page anchor
    target (``generated/<fqn>.md#<fqn>``) the enriched table links to."""
    write_generated_stubs(tmp_path, _beat_map())
    beat_page = tmp_path / GENERATED_DIR_NAME / "librosa.beat.beat_track.md"
    content = beat_page.read_text(encoding="utf-8")
    assert "# librosa.beat.beat_track" in content
    # The same fqn appears as the link anchor in enriched output.
    enrich_line = enrich_autosummary_table("| `beat_track` | |", "librosa.beat", _beat_map())
    assert "generated/librosa.beat.beat_track.md#librosa.beat.beat_track" in enrich_line


def test_write_generated_stubs_idempotent(tmp_path: Path):
    write_generated_stubs(tmp_path, _beat_map())
    first = (tmp_path / GENERATED_DIR_NAME / "librosa.beat.beat_track.md").read_text(
        encoding="utf-8"
    )
    write_generated_stubs(tmp_path, _beat_map())
    second = (tmp_path / GENERATED_DIR_NAME / "librosa.beat.beat_track.md").read_text(
        encoding="utf-8"
    )
    assert first == second


def test_write_generated_stubs_under_generated_dir_only(tmp_path: Path):
    write_generated_stubs(tmp_path, _beat_map())
    gen_dir = tmp_path / GENERATED_DIR_NAME
    assert gen_dir.is_dir()
    # Stubs are confined to <base>/generated/<fqn>.md.
    files = sorted(gen_dir.iterdir())
    assert len(files) == 2
    assert all(f.name.endswith(".md") for f in files)
    # No stray top-level stub is created.
    assert not (tmp_path / "librosa.beat.beat_track.md").exists()


# --------------------------------------------------------------------------- #
# WS4 + WS5: end-to-end enrich_file
# --------------------------------------------------------------------------- #
def _sample_pkg_source_map(tmp_path: Path) -> dict[str, ObjectInfo]:
    pkg = tmp_path / "sample_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        'def beat_track(y=None, sr=None):\n    """Beat tracker."""\n    return []\n',
        encoding="utf-8",
    )
    roots = find_source_roots(tmp_path, {"sample_pkg"})
    return build_source_map(roots)


def test_enrich_file_enriches_and_writes_stubs(tmp_path: Path):
    source_map = _sample_pkg_source_map(tmp_path)

    md = tmp_path / "api" / "beat.md"
    md.parent.mkdir(parents=True)
    md.write_text(
        "# sample_pkg\n\n| `beat_track` | |\n|---|---\n",
        encoding="utf-8",
    )
    rst = tmp_path / "api" / "beat.rst"
    rst.write_text(".. currentmodule:: sample_pkg\n", encoding="utf-8")

    out = tmp_path / "out"
    out.mkdir()
    new_text = enrich_file(md, rst, source_map, output_dir=out)

    # The empty cell was filled from source.
    assert "Beat tracker." in new_text
    assert "Beat tracker." in md.read_text(encoding="utf-8")
    # Stub page written under output_dir/generated so the link resolves.
    assert (out / GENERATED_DIR_NAME / "sample_pkg.beat_track.md").is_file()


def test_enrich_file_passthrough_when_empty_map(tmp_path: Path):
    md = tmp_path / "page.md"
    md.write_text("# Page\n\nBody.\n", encoding="utf-8")
    rst = tmp_path / "page.rst"
    rst.write_text(".. currentmodule:: nowhere\n", encoding="utf-8")

    new_text = enrich_file(md, rst, {})
    # Empty map -> no enrichment; the original content is returned verbatim.
    assert new_text == "# Page\n\nBody.\n"
    # No stub pages are emitted.
    assert list((tmp_path / GENERATED_DIR_NAME).glob("*.md")) == []
