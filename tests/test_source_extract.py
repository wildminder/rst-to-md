"""Tests for AST source extraction (WS3)."""

from __future__ import annotations

import ast
from pathlib import Path

from rst_to_md.core.source_extract import (
    ObjectInfo,
    build_source_map,
    find_source_roots,
    format_autosummary_signature,
)


def _args_of(source: str) -> ast.arguments:
    """Parse ``def f(<source>): pass`` and return its ``arguments`` node."""
    tree = ast.parse("def f(" + source + "): pass")
    func = tree.body[0]
    return func.args  # type: ignore[return-value]


def test_format_autosummary_signature_all_optional():
    assert format_autosummary_signature(_args_of("a=1, b=2")) == "(*[, a, b])"


def test_format_autosummary_signature_mixed():
    assert format_autosummary_signature(_args_of("a, b=1")) == "(a, b=1)"


def test_format_autosummary_signature_required_only():
    assert format_autosummary_signature(_args_of("a, b")) == "(a, b)"


def test_format_autosummary_signature_varargs():
    assert format_autosummary_signature(_args_of("*args, **kwargs")) == (
        "(*args, **kwargs)"
    )


def test_format_autosummary_signature_kwonly():
    # A required positional arg plus a keyword-only arg.
    assert format_autosummary_signature(_args_of("a, *, x")) == "(a, x)"


def test_build_source_map_finds_functions_classes_methods(tmp_path: Path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        'def foo(a, b=1):\n    """Foo."""\n    return a\n', encoding="utf-8"
    )
    (pkg / "mod.py").write_text(
        "class Bar:\n"
        '    """A bar."""\n'
        "\n"
        "    def baz(self, x):\n"
        '        """Baz."""\n'
        "        return x\n",
        encoding="utf-8",
    )
    # Scan root is the PARENT of the package so fqns keep the ``pkg`` prefix.
    source_map = build_source_map([tmp_path])
    assert "pkg.foo" in source_map
    assert "pkg.mod.Bar" in source_map
    assert "pkg.mod.Bar.baz" in source_map
    assert source_map["pkg.foo"].signature == "(a, b=1)"
    assert source_map["pkg.foo"].summary == "Foo."
    assert source_map["pkg.mod.Bar.baz"].summary == "Baz."


def test_build_source_map_summary_first_sentence(tmp_path: Path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        'def foo():\n'
        '    """First sentence here. Second sentence stays out.\n'
        '\n'
        '    More body text."""\n'
        "    pass\n",
        encoding="utf-8",
    )
    # Scan root is the PARENT of the package so fqns keep the ``pkg`` prefix.
    source_map = build_source_map([tmp_path])
    assert source_map["pkg.foo"].summary == "First sentence here."


def test_build_source_map_skips_dunder(tmp_path: Path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "class C:\n"
        '    """C."""\n'
        "\n"
        "    def __init__(self, x):\n"
        '        """Init."""\n'
        "        self.x = x\n"
        "\n"
        "    def __private(self):\n"
        '        """Hidden."""\n'
        "        pass\n"
        "\n"
        "    def public(self):\n"
        '        """Public."""\n'
        "        pass\n"
        "\n"
        "\n"
        "def _helper():\n"
        '    """Helper."""\n'
        "    pass\n",
        encoding="utf-8",
    )
    # Scan root is the PARENT of the package so fqns keep the ``pkg`` prefix.
    source_map = build_source_map([tmp_path])
    # __init__ is kept (captured under the class fqn) with a real signature.
    assert "pkg.C.__init__" in source_map
    assert source_map["pkg.C.__init__"].signature == "(self, x)"
    # Other dunders / private names are skipped.
    assert "pkg.C.__private" not in source_map
    assert "pkg._helper" not in source_map
    # Public members remain.
    assert "pkg.C.public" in source_map


def test_build_source_map_handles_syntax_error_file(tmp_path: Path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    # A valid module (the package __init__).
    (pkg / "__init__.py").write_text(
        'def ok():\n    """OK."""\n    pass\n', encoding="utf-8"
    )
    # A syntactically broken module that must NOT abort the whole map.
    (pkg / "broken.py").write_text("def (((\n", encoding="utf-8")
    # Scan root is the PARENT of the package so fqns keep the ``pkg`` prefix.
    source_map = build_source_map([tmp_path])
    assert "pkg.ok" in source_map
    assert source_map["pkg.ok"].summary == "OK."
    # The broken sibling produced no map entry (and did not abort the scan).
    assert "pkg.broken" not in source_map


def test_find_source_roots_finds_sibling_package(tmp_path: Path):
    # src_dir (docs) with a .rst that documents `librosa`; the `librosa/`
    # package lives BESIDE src_dir, so the scan root is the directory that
    # DIRECTLY contains the package (its parent), keeping the `librosa` prefix.
    src_dir = tmp_path / "docs"
    src_dir.mkdir()
    (src_dir / "index.rst").write_text(
        "Title\n=====\n\n.. currentmodule:: librosa.beat\n", encoding="utf-8"
    )
    librosa = tmp_path / "librosa"
    librosa.mkdir()
    (librosa / "__init__.py").write_text(
        'def load():\n    """Load audio."""\n    return []\n', encoding="utf-8"
    )
    roots = find_source_roots(src_dir, {"librosa"})
    # The directory directly containing the librosa package is the scan root
    # (so fqns keep the `librosa` prefix); the package dir itself is not.
    assert tmp_path in roots
    assert librosa not in roots
    source_map = build_source_map(roots)
    assert "librosa.load" in source_map


def test_find_source_roots_includes_src_subdir(tmp_path: Path):
    # A documented module located INSIDE src_dir (e.g. the test fixture's
    # sample_pkg) must be discoverable: the scan root is src_dir itself.
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "index.rst").write_text(
        "Title\n=====\n\n.. currentmodule:: sample_pkg\n", encoding="utf-8"
    )
    sample_pkg = src_dir / "sample_pkg"
    sample_pkg.mkdir()
    (sample_pkg / "__init__.py").write_text(
        "def beat_track(y=None, sr=None):\n    '''Beat.'''\n    return []\n",
        encoding="utf-8",
    )
    roots = find_source_roots(src_dir, {"sample_pkg"})
    # src_dir is the scan root that contains sample_pkg, so it must be present.
    assert src_dir in roots
    # And the map built from those roots actually finds the member.
    source_map = build_source_map(roots)
    assert "sample_pkg.beat_track" in source_map


def test_objectinfo_is_frozen():
    info = ObjectInfo("a.b", "function", "()", "Summary.", "Full.", 1)
    try:
        info.signature = "x"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("ObjectInfo should be frozen (immutable)")
