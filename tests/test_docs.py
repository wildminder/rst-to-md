"""Tests for documentation accuracy (P7, P8.5)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_readme_has_architecture_diagram():
    readme = (REPO_ROOT / "README.md").read_text("utf-8")
    assert "flowchart TD" in readme  # mermaid diagram present


def test_readme_has_badges():
    readme = (REPO_ROOT / "README.md").read_text("utf-8")
    assert "img.shields.io" in readme


def test_readme_does_not_claim_rust_speed():
    readme = (REPO_ROOT / "README.md").read_text("utf-8")
    # The old inaccurate "Rust-based 150-280 MB/s" claim must be gone.
    assert "Rust-based" not in readme
    assert "150-280 MB/s" not in readme


def test_changelog_exists():
    assert (REPO_ROOT / "CHANGELOG.md").is_file()


def test_contributing_exists():
    assert (REPO_ROOT / "CONTRIBUTING.md").is_file()


def test_napoleon_coupling_documented():
    # IMP-004: the private-name coupling must be documented with a grep-able
    # COUPLING marker in the source, and noted in the design doc.
    sphinx_src = (REPO_ROOT / "rst_to_md" / "converters" / "sphinx.py").read_text("utf-8")
    assert "COUPLING:" in sphinx_src
    assert "sphinx.ext.napoleon._skip_member" in sphinx_src

    design = (REPO_ROOT / "docs" / "design" / "output-conventions.md").read_text("utf-8")
    assert "napoleon" in design.lower()


def test_backend_split_documented():
    # IMP-005: the intentional two-backend split must be documented, and each
    # converter module must name its own backend in its docstring.
    design = (REPO_ROOT / "docs" / "design" / "output-conventions.md").read_text("utf-8")
    assert "pypandoc" in design
    assert "html_to_markdown" in design
    assert "Two conversion backends" in design

    rst_src = (REPO_ROOT / "rst_to_md" / "converters" / "rst.py").read_text("utf-8")
    assert "pypandoc" in rst_src

    sphinx_src = (REPO_ROOT / "rst_to_md" / "converters" / "sphinx.py").read_text("utf-8")
    assert "html_to_markdown" in sphinx_src


def test_docs_mention_caching():
    # NTH-001: incremental caching must be documented.
    design = (REPO_ROOT / "docs" / "design" / "output-conventions.md").read_text("utf-8")
    assert "cache" in design.lower() or "incremental" in design.lower()


def test_docs_mention_builder():
    # NTH-006: the Sphinx builder override must be documented.
    design = (REPO_ROOT / "docs" / "design" / "output-conventions.md").read_text("utf-8")
    assert "builder" in design.lower()


def test_docs_mention_parallel_build():
    # Performance: the parallel Sphinx build (-j / --build-workers) must be
    # documented, and the CHANGELOG must note it.
    design = (REPO_ROOT / "docs" / "design" / "output-conventions.md").read_text("utf-8")
    assert "build_workers" in design
    assert "-j" in design

    changelog = (REPO_ROOT / "CHANGELOG.md").read_text("utf-8")
    assert "build-workers" in changelog or "build_workers" in changelog


def test_docs_mention_markdown_builder():
    # P11: the direct Markdown builder (default pipeline) must be documented in
    # the design doc, the CHANGELOG, and the README.
    design = (REPO_ROOT / "docs" / "design" / "output-conventions.md").read_text("utf-8")
    assert "sphinx-markdown-builder" in design
    assert "convert_built_md" in design
    assert "Direct Markdown builder" in design

    changelog = (REPO_ROOT / "CHANGELOG.md").read_text("utf-8")
    assert "1.4.0" in changelog
    assert "sphinx-markdown-builder" in changelog
    # The vendored/patched builder (D1/D2/D3 fixes) must be documented.
    assert "1.4.1" in changelog
    assert "Vendored" in changelog or "vendored" in changelog

    readme = (REPO_ROOT / "README.md").read_text("utf-8")
    assert "sphinx-markdown-builder" in readme
    assert "vendored" in readme


def test_docs_mention_vendored_builder():
    # The vendored builder + autodoc formatting fixes (D1/D2/D3) must be
    # documented in the design doc.
    design = (REPO_ROOT / "docs" / "design" / "output-conventions.md").read_text("utf-8")
    assert "rst_to_md/_vendor/sphinx_markdown_builder" in design
    assert "desc_annotation" in design
    assert "Vendored" in design or "vendored" in design


def test_docs_mention_xref_flattening():
    # XREF: the signature cross-reference flattening must be documented in the
    # design doc (§10.9) and the CHANGELOG.
    design = (REPO_ROOT / "docs" / "design" / "output-conventions.md").read_text("utf-8")
    assert "10.9" in design
    assert "cross-reference" in design.lower()
    assert "desc_depth" in design
    assert "plain text" in design.lower()

    changelog = (REPO_ROOT / "CHANGELOG.md").read_text("utf-8")
    assert "XREF" in changelog
    assert "cross-reference" in changelog.lower()


def test_docs_mention_autosummary_enrichment():
    # WS4/WS5: the autosummary source-enrichment (fill empty tables from an AST
    # source map without importing the documented package, and emit generated/
    # stub pages) must be documented in the design doc (§10.10) and the CHANGELOG.
    design = (REPO_ROOT / "docs" / "design" / "output-conventions.md").read_text("utf-8")
    assert "10.10" in design
    assert "autosummary" in design.lower()
    # The key idea: enrichment uses an AST source map, not an import.
    assert "source map" in design.lower() or "source_map" in design
    # Stub pages are emitted under generated/ so the table links resolve.
    assert "generated/" in design

    changelog = (REPO_ROOT / "CHANGELOG.md").read_text("utf-8")
    assert "1.4.2" in changelog
    assert "autosummary" in changelog.lower()


def test_docs_mention_autosummary_cli_flag():
    # WS2: the --autosummary-generate CLI flag must be documented in the README.
    readme = (REPO_ROOT / "README.md").read_text("utf-8")
    assert "--autosummary-generate" in readme
