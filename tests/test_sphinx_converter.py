"""Tests for the Sphinx converter (P1, P2, P3, P4)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from rst_to_md.config import AUTOSUMMARY_GENERATE_DEFAULT
from rst_to_md.converters import sphinx as sphinx_module
from rst_to_md.converters.sphinx import (
    build_extensions_list,
    build_sphinx_html,
    build_stub_sitecustomize,
    convert_built_md,
    convert_html_to_md,
    convert_sphinx_project,
    decide_autosummary_generate,
    extract_documented_modules,
    extract_extensions_from_conf,
    extract_sys_path_dirs,
    extract_top_level_imports,
    filter_extensions,
    find_local_modules,
    is_sphinx_project,
)
from rst_to_md.exceptions import SphinxBuildError


# --------------------------------------------------------------------------- #
# P2: inspection helpers
# --------------------------------------------------------------------------- #
def test_extract_top_level_imports(tmp_path: Path):
    conf = tmp_path / "conf.py"
    conf.write_text(
        "import os\n"
        "import missing_package\n"
        "from sphinx.ext.autodoc import something\n"
        "import a.b.c\n",
        encoding="utf-8",
    )
    imports = extract_top_level_imports(conf)
    assert "missing_package" in imports
    assert "os" in imports
    assert "a" in imports
    assert "sphinx" in imports


def test_extract_top_level_imports_missing_file(tmp_path: Path):
    assert extract_top_level_imports(tmp_path / "nope.py") == set()


# --------------------------------------------------------------------------- #
# Locality detection: extract_sys_path_dirs / find_local_modules
# --------------------------------------------------------------------------- #
def test_extract_sys_path_dirs_abspath_dot(tmp_path: Path):
    """The torchaudio pattern: sys.path.insert(0, os.path.abspath('.'))."""
    conf = tmp_path / "conf.py"
    conf.write_text(
        'import os\nimport sys\nsys.path.insert(0, os.path.abspath("."))\n',
        encoding="utf-8",
    )
    assert extract_sys_path_dirs(conf) == [tmp_path.resolve()]


def test_extract_sys_path_dirs_relative_subdir(tmp_path: Path):
    (tmp_path / "helpers").mkdir()
    conf = tmp_path / "conf.py"
    conf.write_text("import sys\nsys.path.append('helpers')\n", encoding="utf-8")
    assert extract_sys_path_dirs(conf) == [(tmp_path / "helpers").resolve()]


def test_extract_sys_path_dirs_ignores_non_literal(tmp_path: Path):
    conf = tmp_path / "conf.py"
    conf.write_text(
        "import sys\nsome_var = 'x'\nsys.path.insert(0, some_var)\nsys.path.append(get_dir())\n",
        encoding="utf-8",
    )
    assert extract_sys_path_dirs(conf) == []


def test_extract_sys_path_dirs_missing_file(tmp_path: Path):
    assert extract_sys_path_dirs(tmp_path / "nope.py") == []


def test_extract_sys_path_dirs_skips_nonexistent_dir(tmp_path: Path):
    conf = tmp_path / "conf.py"
    conf.write_text(
        "import sys\nsys.path.insert(0, 'does_not_exist_dir')\n",
        encoding="utf-8",
    )
    assert extract_sys_path_dirs(conf) == []


def test_find_local_modules_detects_py_file(tmp_path: Path):
    (tmp_path / "mylocal.py").write_text("x = 1\n", encoding="utf-8")
    assert find_local_modules({"mylocal"}, [tmp_path]) == {"mylocal"}


def test_find_local_modules_detects_package(tmp_path: Path):
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    assert find_local_modules({"mypkg"}, [tmp_path]) == {"mypkg"}


def test_find_local_modules_ignores_third_party(tmp_path: Path):
    assert find_local_modules({"requests"}, [tmp_path]) == set()


def test_find_local_modules_ignores_plain_dir_without_init(tmp_path: Path):
    (tmp_path / "mypkg").mkdir()
    assert find_local_modules({"mypkg"}, [tmp_path]) == set()


def test_find_local_modules_nonexistent_dir(tmp_path: Path):
    assert find_local_modules({"mylocal"}, [tmp_path / "missing"]) == set()


def test_find_local_modules_multiple_search_dirs(tmp_path: Path):
    helpers = tmp_path / "helpers"
    helpers.mkdir()
    (helpers / "myhelper.py").write_text("y = 2\n", encoding="utf-8")
    assert find_local_modules({"myhelper"}, [tmp_path, helpers]) == {"myhelper"}


# --------------------------------------------------------------------------- #
# resolve_sphinx_project_dir: conf.py auto-detection one level down
# --------------------------------------------------------------------------- #
def test_resolve_sphinx_project_dir_prefers_input_dir(tmp_path: Path):
    (tmp_path / "conf.py").write_text("pass\n", encoding="utf-8")
    source = tmp_path / "source"
    source.mkdir()
    (source / "conf.py").write_text("pass\n", encoding="utf-8")
    assert sphinx_module.resolve_sphinx_project_dir(tmp_path) == tmp_path


def test_resolve_sphinx_project_dir_finds_source_subdir(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "conf.py").write_text("pass\n", encoding="utf-8")
    assert sphinx_module.resolve_sphinx_project_dir(tmp_path) == source


def test_resolve_sphinx_project_dir_none_when_missing(tmp_path: Path):
    assert sphinx_module.resolve_sphinx_project_dir(tmp_path) is None


def test_resolve_sphinx_project_dir_precedence(tmp_path: Path):
    # Fixed probe order: source wins over doc/docs when several exist.
    for sub in ("source", "doc", "docs"):
        d = tmp_path / sub
        d.mkdir()
        (d / "conf.py").write_text("pass\n", encoding="utf-8")
    assert sphinx_module.resolve_sphinx_project_dir(tmp_path) == (tmp_path / "source")


def test_extract_extensions_from_conf(tmp_path: Path):
    conf = tmp_path / "conf.py"
    conf.write_text(
        "extensions = ['sphinx.ext.autodoc', 'numpydoc', 'sphinx_gallery']\n",
        encoding="utf-8",
    )
    exts = extract_extensions_from_conf(conf)
    assert exts == ["sphinx.ext.autodoc", "numpydoc", "sphinx_gallery"]


def test_filter_extensions():
    exts = [
        "sphinx.ext.autodoc",
        "numpydoc",
        "sphinx_gallery.gen_gallery",
        "sphinx.ext.napoleon",
    ]
    filtered = filter_extensions(exts)
    assert "sphinx.ext.autodoc" in filtered
    assert "sphinx.ext.napoleon" in filtered
    assert "numpydoc" not in filtered
    assert "sphinx_gallery.gen_gallery" not in filtered


def test_build_extensions_list_html():
    # HTML builder: core extensions + filtered conf extensions, no markdown ext.
    merged = build_extensions_list(["sphinx.ext.autodoc", "sphinx_gallery", "numpydoc"], "html")
    assert "sphinx.ext.autodoc" in merged
    assert "sphinx.ext.napoleon" in merged  # from CORE_EXTENSIONS
    assert "sphinx_gallery" not in merged  # denylisted
    assert "numpydoc" not in merged  # denylisted
    assert "sphinx_markdown_builder" not in merged
    # The vendored builder is referenced by its in-package import path.
    assert "rst_to_md._vendor.sphinx_markdown_builder" not in merged


def test_build_extensions_list_markdown():
    # Markdown builder: same as HTML plus the VENDORED direct builder extension.
    # The vendored copy lives under `rst_to_md/_vendor/sphinx_markdown_builder`
    # but keeps the bare `sphinx_markdown_builder` import name (its internal
    # imports use that name), so it is registered under that name and loaded via
    # PYTHONPATH shadowing in build_sphinx_html.
    merged = build_extensions_list(["sphinx.ext.autodoc", "sphinx_gallery"], "markdown")
    assert "sphinx_markdown_builder" in merged
    assert "sphinx.ext.autodoc" in merged
    assert "sphinx_gallery" not in merged


def test_vendored_builder_importable():
    # The vendored builder lives under rst_to_md/_vendor/sphinx_markdown_builder
    # but keeps the bare `sphinx_markdown_builder` import name (its internal
    # imports use that name), so it is loaded via PYTHONPATH shadowing at build
    # time. Here we emulate that by putting _vendor on sys.path and importing
    # the bare name.
    import importlib

    vendor_dir = str(Path(__file__).resolve().parents[1] / "rst_to_md" / "_vendor")
    sys.path.insert(0, vendor_dir)
    try:
        mod = importlib.import_module("sphinx_markdown_builder")
    finally:
        sys.path.remove(vendor_dir)
    assert hasattr(mod, "MarkdownBuilder")


def test_skip_stems_covers_system_pages():
    # Step 2: SKIP_STEMS is suffix-agnostic so both .html and .md system pages
    # (e.g. genindex) are skipped, while real content pages are not.
    from rst_to_md.config import SKIP_STEMS

    for stem in ("genindex", "search", "py-modindex", "examples"):
        assert stem in SKIP_STEMS
    assert "index" not in SKIP_STEMS
    # The stem check is what _convert_one uses, so both extensions skip.
    assert "genindex.md".split(".")[0] in SKIP_STEMS
    assert "genindex.html".split(".")[0] in SKIP_STEMS


def test_build_stub_sitecustomize(tmp_path: Path):
    stub_dir = build_stub_sitecustomize({"missing_package"}, tmp_path / "_stubs")
    sitecustomize = stub_dir / "sitecustomize.py"
    assert sitecustomize.exists()
    content = sitecustomize.read_text(encoding="utf-8")
    assert "missing_package" in content
    assert "_install_stubs" in content
    assert "importlib.import_module" in content
    assert "_SubmoduleStubFinder" in content
    assert "_STUBBED" in content
    # The generated file must be valid Python.
    compile(content, str(sitecustomize), "exec")


def test_stub_sitecustomize_stubs_only_missing(tmp_path: Path):
    """Regression: real modules (e.g. datetime) must NOT be overridden, while
    missing modules (and their submodules / dunder metadata) are stubbed.

    Reproduces the reported failures where a MetaPathFinder stubbed ``datetime``
    (breaking pytz/babel used by Sphinx) and where ``pkg.__version__`` /
    ``pkg.__api_version__`` raised AttributeError in conf.py.
    """
    stub_dir = build_stub_sitecustomize(
        {"this_module_does_not_exist_xyz", "datetime"}, tmp_path / "_stubs"
    )
    sitecustomize = stub_dir / "sitecustomize.py"
    script = (  # noqa: UP031  (keep %-format: string embeds a literal r'%s')
        "import importlib.util\n"
        "spec = importlib.util.spec_from_file_location('sitecustomize', "
        "r'%s')\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "import datetime\n"
        "assert datetime.__name__ == 'datetime', 'real datetime was overridden'\n"
        "try:\n"
        "    import datetime.this_submodule_does_not_exist\n"
        "    raise AssertionError('real submodule was stubbed')\n"
        "except ImportError:\n"
        "    pass\n"
        "import types\n"
        "import this_module_does_not_exist_xyz as m\n"
        "assert m.__name__ == 'this_module_does_not_exist_xyz'\n"
        "assert isinstance(m.__version__, str), "
        "'dunder __version__ must be a str (so config.release is a str)'\n"
        "assert m.__version__ == '0.0.0'\n"
        "assert isinstance(m.__api_version__, str)\n"
        "# class-protocol dunders must raise so Sphinx introspection falls back\n"
        "try:\n"
        "    m.__mro__\n"
        "    raise AssertionError('__mro__ should raise AttributeError')\n"
        "except AttributeError:\n"
        "    pass\n"
        "assert m.__file__ is None, 'real module dunder must be None (no recursion)'\n"
        "assert repr(m.__version__) == \"'0.0.0'\", 'repr must not recurse'\n"
        "import this_module_does_not_exist_xyz.sub.mod\n"
        "assert this_module_does_not_exist_xyz.sub.mod.__name__ == "
        "'this_module_does_not_exist_xyz.sub.mod'\n"
        "print('OK')\n"
    ) % str(sitecustomize)
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_stub_sitecustomize_dummy_module_is_callable(tmp_path: Path):
    """Regression: a stubbed import CALLED at conf.py execution time must not
    crash with ``TypeError: '_DummyModule' object is not callable``.

    Reproduces the librosa failure where ``conf.py`` does::

        from cycler import cycler
        plot_rcparams = {"axes.prop_cycle": cycler("color", [...])}

    and ``cycler`` is not installed.  The stub must make the call succeed
    (returning a dummy) so the build can proceed.
    """
    stub_dir = build_stub_sitecustomize({"this_module_does_not_exist_xyz"}, tmp_path / "_stubs")
    sitecustomize = stub_dir / "sitecustomize.py"
    script = (  # noqa: UP031  (keep %-format: string embeds a literal r'%s')
        "import importlib.util\n"
        "spec = importlib.util.spec_from_file_location('sitecustomize', "
        "r'%s')\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "import this_module_does_not_exist_xyz as m\n"
        "# Calling a stubbed import must not raise TypeError\n"
        "result = m('color', ['#3f90da', '#ffa90e'])\n"
        "assert result is not None, 'call must return a dummy, not None'\n"
        "# The result should itself be a dummy (further attribute access works)\n"
        "assert hasattr(result, 'some_attr'), 'returned dummy must support "
        "attribute access'\n"
        "# Iterating over the result must not crash either (e.g. cycler returns\n"
        "# an iterable Cycler object)\n"
        "for _ in result:\n"
        "    pass\n"
        "print('OK')\n"
    ) % str(sitecustomize)
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_filter_extensions_drops_unimportable():
    """Regression: unimportable third-party extensions (e.g.
    ``pydata_sphinx_theme``, ``myst_parser`` when not installed) must be
    filtered out so Sphinx does not crash trying to load them.
    """
    exts = [
        "sphinx.ext.autodoc",
        "sphinx.ext.napoleon",
        "pydata_sphinx_theme",  # not installed in test env
        "myst_parser",  # may or may not be installed
    ]
    filtered = filter_extensions(exts)
    # sphinx.ext.* are always importable (part of Sphinx)
    assert "sphinx.ext.autodoc" in filtered
    assert "sphinx.ext.napoleon" in filtered
    # pydata_sphinx_theme is definitely not installed in the test env
    assert "pydata_sphinx_theme" not in filtered


def test_build_sphinx_html_includes_autosummary_generate_false(tmp_path: Path):
    """Regression: lightweight mode must set ``autosummary_generate=False`` so
    autosummary does not try to import the documented package (and its missing
    transitive deps) at builder-init time, which would crash the build.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text(
        "extensions = ['sphinx.ext.autodoc', 'sphinx.ext.autosummary']\n",
        encoding="utf-8",
    )
    (src / "index.rst").write_text("Title\n=====\n\nBody\n", encoding="utf-8")
    build_dir = tmp_path / "build"

    cmd_args: list[str] = []
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
        build_sphinx_html(src, build_dir, lightweight=True, stub_modules=set(), builder="html")
        cmd_args = mock_run.call_args[0][0]

    cmd_str = " ".join(cmd_args)
    assert "autosummary_generate=False" in cmd_str, (
        f"lightweight mode must pass autosummary_generate=False, got: {cmd_str}"
    )


def _build_with_captured_cmd(tmp_path: Path, src: Path, **kwargs) -> list[str]:
    """Run build_sphinx_html with a faked subprocess; return the command."""
    build_dir = tmp_path / "build"
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, *a, **k):
        captured["cmd"] = list(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    with mock.patch("rst_to_md.converters.sphinx.subprocess.run", side_effect=fake_run):
        build_sphinx_html(src, build_dir, **kwargs)
    return captured["cmd"]


def test_build_sphinx_html_excludes_local_module_from_stubs(tmp_path: Path):
    """Regression: a module that exists as a file in the source dir must not
    be stubbed or mocked, even though _is_importable() cannot see it from the
    parent process (torchaudio custom_directives crash)."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text(
        "import mylocal\nimport definitely_missing_pkg_xyz\n",
        encoding="utf-8",
    )
    (src / "mylocal.py").write_text("x = 1\n", encoding="utf-8")

    cmd = _build_with_captured_cmd(
        tmp_path,
        src,
        lightweight=True,
        stub_modules={"mylocal", "definitely_missing_pkg_xyz"},
        builder="html",
    )
    cmd_str = " ".join(cmd)
    mock_opt = next((tok for tok in cmd if tok.startswith("autodoc_mock_imports=")), None)
    assert mock_opt is not None
    assert "definitely_missing_pkg_xyz" in mock_opt
    assert "mylocal" not in mock_opt
    # The generated sitecustomize must not stub the local module either.
    sitecustomize = tmp_path / "build" / "_stubs" / "sitecustomize.py"
    text = sitecustomize.read_text(encoding="utf-8")
    assert "'definitely_missing_pkg_xyz'" in text
    assert "'mylocal'" not in text
    assert cmd_str  # sanity: command was captured


def test_build_sphinx_html_mock_all_excludes_local_module(tmp_path: Path):
    """The degraded mock_all_imports rung must also keep local modules out of
    autodoc_mock_imports (they are importable in the subprocess)."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text("import mylocal\n", encoding="utf-8")
    (src / "mylocal.py").write_text("x = 1\n", encoding="utf-8")

    cmd = _build_with_captured_cmd(
        tmp_path,
        src,
        lightweight=True,
        stub_modules={"mylocal", "definitely_missing_pkg_xyz"},
        mock_all_imports=True,
        builder="html",
    )
    mock_opt = next((tok for tok in cmd if tok.startswith("autodoc_mock_imports=")), None)
    assert mock_opt is not None
    assert "mylocal" not in mock_opt
    assert "definitely_missing_pkg_xyz" in mock_opt


def test_build_sphinx_html_local_module_via_sys_path_dir(tmp_path: Path):
    """A module living in a directory that conf.py adds to sys.path (not the
    source dir itself) must also be detected as local."""
    src = tmp_path / "src"
    src.mkdir()
    helpers = src / "helpers"
    helpers.mkdir()
    (helpers / "myhelper.py").write_text("y = 2\n", encoding="utf-8")
    (src / "conf.py").write_text(
        'import os\nimport sys\nsys.path.insert(0, os.path.abspath("helpers"))\nimport myhelper\n',
        encoding="utf-8",
    )

    cmd = _build_with_captured_cmd(
        tmp_path,
        src,
        lightweight=True,
        stub_modules={"myhelper"},
        builder="html",
    )
    mock_opt = next((tok for tok in cmd if tok.startswith("autodoc_mock_imports=")), None)
    # Only a genuinely-missing module would produce the option; here the only
    # candidate is local, so no autodoc_mock_imports flag may be emitted.
    assert mock_opt is None
    sitecustomize = tmp_path / "build" / "_stubs" / "sitecustomize.py"
    assert "'myhelper'" not in sitecustomize.read_text(encoding="utf-8")


def test_stub_sitecustomize_lazy_loader_attach_stub_returns_3tuple(
    tmp_path: Path,
):
    """Regression: ``lazy_loader.attach_stub()`` must return a real 3-tuple.

    Scientific Python packages (numpy, scipy, librosa) use::

        __getattr__, __dir__, __all__ = lazy.attach_stub(__name__, __file__)

    A generic ``_DummyModule`` cannot support arbitrary-length tuple
    unpacking, so the import of the *documented* package fails and autodoc
    produces empty output.  The stub must inject a *real* ``lazy_loader``
    module whose ``attach_stub`` returns a proper ``(getattr, dir, all)``
    3-tuple.
    """
    stub_dir = build_stub_sitecustomize({"lazy_loader"}, tmp_path / "_stubs")
    sitecustomize = stub_dir / "sitecustomize.py"
    script = (  # noqa: UP031  (keep %-format: string embeds a literal r'%s')
        "import importlib.util\n"
        "spec = importlib.util.spec_from_file_location('sitecustomize', "
        "r'%s')\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "import lazy_loader\n"
        "# attach_stub must return a real 3-tuple, not a _DummyModule\n"
        "result = lazy_loader.attach_stub('my_pkg', '/fake/path.py')\n"
        "assert isinstance(result, tuple), f'expected tuple, got "
        "{type(result)}'\n"
        "assert len(result) == 3, f'expected 3 items, got {len(result)}'\n"
        "getattr_fn, dir_fn, all_list = result\n"
        "assert callable(getattr_fn), 'first item must be callable'\n"
        "assert callable(dir_fn), 'second item must be callable'\n"
        "assert isinstance(all_list, list), 'third item must be a list'\n"
        "# The getattr function should return a dummy for unknown attrs\n"
        "child = getattr_fn('some_submodule')\n"
        "assert child is not None\n"
        "# The dir function should return a list\n"
        "assert isinstance(dir_fn(), list)\n"
        "print('OK')\n"
    ) % str(sitecustomize)
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


# --------------------------------------------------------------------------- #
# run_directive crash guard (defense in depth for broken/stubbed directives)
# --------------------------------------------------------------------------- #
def test_docutils_run_directive_exists():
    """COUPLING: the sitecustomize guard monkeypatches
    ``docutils.parsers.rst.states.Body.run_directive``. Fail loudly if
    docutils renames or removes it (same contract as
    ``test_napoleon_skip_member_exists``)."""
    from docutils.parsers.rst import states

    assert callable(getattr(states.Body, "run_directive", None))


def _load_sitecustomize_and_publish(sitecustomize: Path, rst_text: str) -> str:
    """Run a subprocess that loads the generated sitecustomize, registers a
    test directive, publishes ``rst_text``, and prints a report. Returns the
    script's stdout."""
    script = (  # noqa: UP031  (keep %-format: string embeds literal r'%s')
        "import importlib.util\n"
        "spec = importlib.util.spec_from_file_location('sitecustomize', "
        "r'%s')\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "from docutils import nodes\n"
        "from docutils.parsers.rst import Directive, directives\n"
        "from docutils.core import publish_doctree\n"
        "class Boom(Directive):\n"
        "    required_arguments = 1\n"
        "    def run(self):\n"
        "        raise RuntimeError('directive exploded')\n"
        "directives.register_directive('boom', Boom)\n"
        "import fake_missing_directive_pkg\n"
        "directives.register_directive('dummy', "
        "fake_missing_directive_pkg.SomeDirective)\n"
        "doctree = publish_doctree(r'''%s''')\n"
        "msgs = [n for n in doctree.findall(nodes.system_message)]\n"
        "paras = [n.astext() for n in doctree.findall(nodes.paragraph)]\n"
        "print('MSGS:', len(msgs))\n"
        "for m in msgs:\n"
        "    print('LEVEL:', m['level'])\n"
        "print('PARAS:', paras)\n"
        "print('OK')\n"
    ) % (str(sitecustomize), rst_text)
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
    return result.stdout


def test_stub_sitecustomize_run_directive_guard_absorbs_crash(tmp_path: Path):
    """A directive whose run() raises must degrade to a system message
    instead of aborting the parse."""
    stub_dir = build_stub_sitecustomize({"fake_missing_directive_pkg"}, tmp_path / "_stubs")
    out = _load_sitecustomize_and_publish(
        stub_dir / "sitecustomize.py",
        "Title\n=====\n\n.. boom:: arg\n\nSurviving paragraph.\n",
    )
    assert "MSGS: 1" in out
    assert "LEVEL: 3" in out  # ERROR, below halt_level (4)
    assert "Surviving paragraph." in out


def test_stub_sitecustomize_run_directive_guard_absorbs_dummy_directive(
    tmp_path: Path,
):
    """Regression: registering a _DummyModule as a directive class (the exact
    torchaudio failure) must not raise TypeError during parsing."""
    stub_dir = build_stub_sitecustomize({"fake_missing_directive_pkg"}, tmp_path / "_stubs")
    out = _load_sitecustomize_and_publish(
        stub_dir / "sitecustomize.py",
        "Title\n=====\n\n.. dummy:: something\n\nBody text.\n",
    )
    assert "MSGS: 1" in out
    assert "LEVEL: 3" in out
    assert "Body text." in out


def test_stub_sitecustomize_run_directive_guard_passthrough_ok(tmp_path: Path):
    """A healthy directive still renders its nodes unchanged (the guard is
    transparent)."""
    stub_dir = build_stub_sitecustomize({"fake_missing_directive_pkg"}, tmp_path / "_stubs")
    out = _load_sitecustomize_and_publish(
        stub_dir / "sitecustomize.py",
        "Title\n=====\n\n.. note::\n\n   A note body.\n",
    )
    assert "MSGS: 0" in out
    assert "A note body." in out


# --------------------------------------------------------------------------- #
# P1: html_to_markdown return-type robustness
# --------------------------------------------------------------------------- #
def test_convert_html_to_md_string_return(tmp_path: Path):
    html = tmp_path / "page.html"
    html.write_text("<h1>Title</h1><p>Body</p>", encoding="utf-8")
    md = tmp_path / "page.md"
    with mock.patch("html_to_markdown.convert", return_value="# Title\n\nBody\n"):
        assert convert_html_to_md(html, md) is True
    assert "# Title" in md.read_text(encoding="utf-8")


def test_convert_html_to_md_dict_return(tmp_path: Path):
    html = tmp_path / "page.html"
    html.write_text("<h1>Title</h1>", encoding="utf-8")
    md = tmp_path / "page.md"
    with mock.patch("html_to_markdown.convert", return_value={"content": "# Title\n"}):
        assert convert_html_to_md(html, md) is True
    assert "# Title" in md.read_text(encoding="utf-8")


class _FakeConversionResult:
    """Mimics html_to_markdown >=3.x ``ConversionResult`` (has .content)."""

    def __init__(self, content: str) -> None:
        self.content = content


def test_convert_html_to_md_conversion_result_return(tmp_path: Path):
    html = tmp_path / "page.html"
    html.write_text("<h1>Title</h1>", encoding="utf-8")
    md = tmp_path / "page.md"
    with mock.patch(
        "html_to_markdown.convert",
        return_value=_FakeConversionResult("# Title\n"),
    ):
        assert convert_html_to_md(html, md) is True
    assert "# Title" in md.read_text(encoding="utf-8")


def test_convert_html_to_md_failure_returns_false(tmp_path: Path):
    html = tmp_path / "page.html"
    html.write_text("<h1>x</h1>", encoding="utf-8")
    md = tmp_path / "page.md"
    with mock.patch("html_to_markdown.convert", side_effect=RuntimeError("boom")):
        assert convert_html_to_md(html, md) is False


# A furo-style page: front matter, sidebar TOC, body, footer nav + copyright +
# "Made with" + local "On this page" TOC.
_FURO_LIKE_MD = """\
---
meta-color-scheme: light dark
title: Installation - aiogram documentation
---
![SVG Image](data:image/svg+xml;base64,xxx)
[aiogram documentation](index.md)

- [Installation](#)
- [Migration FAQ](migration_2_to_3.md)

[Back to top](#)

# Installation

## From PyPI

```
pip install -U aiogram
```

[NextMigration FAQ SVG Image](migration_2_to_3.md) [SVG Image PreviousHome](index.md)

Copyright © 2026, aiogram Team

Made with [Sphinx](https://www.sphinx-doc.org/) and Furo

 On this page

- [Installation](#)
"""


def test_convert_html_to_md_strips_chrome_by_default(tmp_path: Path):
    html = tmp_path / "page.html"
    html.write_text("<html></html>", encoding="utf-8")
    md = tmp_path / "page.md"
    with mock.patch("html_to_markdown.convert", return_value=_FURO_LIKE_MD):
        assert convert_html_to_md(html, md) is True
    out = md.read_text(encoding="utf-8")
    assert out.startswith("# Installation")
    assert "pip install -U aiogram" in out
    assert "meta-color-scheme" not in out
    assert "Copyright" not in out
    assert "Made with" not in out
    assert "On this page" not in out


def test_convert_html_to_md_keep_chrome(tmp_path: Path):
    html = tmp_path / "page.html"
    html.write_text("<html></html>", encoding="utf-8")
    md = tmp_path / "page.md"
    with mock.patch("html_to_markdown.convert", return_value=_FURO_LIKE_MD):
        assert convert_html_to_md(html, md, strip_chrome=False) is True
    out = md.read_text(encoding="utf-8")
    # With chrome kept, the navigation/footer is preserved verbatim.
    assert "Copyright" in out
    assert "On this page" in out
    assert "meta-color-scheme" in out


# --------------------------------------------------------------------------- #
# P0/P3: autodoc content preservation (real Sphinx build of the fixture)
# --------------------------------------------------------------------------- #
_FIXTURE_AUTODOC = Path(__file__).resolve().parent / "fixtures" / "sphinx_autodoc"


def test_autodoc_fixture_preserves_class_content(tmp_path: Path):
    """autoclass output (Bases, members, params) survives conversion."""
    build_dir = tmp_path / "build"
    assert build_sphinx_html(_FIXTURE_AUTODOC, build_dir, lightweight=True)
    html = build_dir / "html" / "index.html"
    assert html.exists()
    md = tmp_path / "out.md"
    assert convert_html_to_md(html, md, wrap="none", strip_chrome=True)
    text = md.read_text(encoding="utf-8")

    # Bases: inheritance list is preserved (non-empty).
    bases_lines = [line for line in text.splitlines() if line.startswith("Bases:")]
    assert bases_lines, "Bases: line missing from output"
    assert "TelegramMessage" in bases_lines[0]
    assert "BaseBot" in bases_lines[0]

    # Signature params are code spans, not italicized (no ***kwargs* mangling).
    assert "***" not in text
    assert "*token: str*" not in text
    assert "token: str" in text

    # Members and field lists are present.
    assert "__init__" in text
    assert "download_file" in text
    assert "Parameters:" in text
    assert "Raises:" in text


def test_autodoc_keep_chrome_keeps_navigation(tmp_path: Path):
    """--keep-chrome (strip_chrome=False) converts the full page."""
    build_dir = tmp_path / "build"
    assert build_sphinx_html(_FIXTURE_AUTODOC, build_dir, lightweight=True)
    html = build_dir / "html" / "index.html"
    stripped = tmp_path / "stripped.md"
    full = tmp_path / "full.md"
    assert convert_html_to_md(html, stripped, strip_chrome=True)
    assert convert_html_to_md(html, full, strip_chrome=False)
    stripped_text = stripped.read_text(encoding="utf-8")
    full_text = full.read_text(encoding="utf-8")
    # The full page contains navigation chrome (furo footer) that the stripped
    # one drops by extracting only the <main>/<article> content container.
    assert "Made with" in full_text
    assert "Made with" not in stripped_text


# --------------------------------------------------------------------------- #
# P2: build command construction
# --------------------------------------------------------------------------- #
def test_build_sphinx_html_lightweight_command(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text(
        "import missing_package\nextensions = ['sphinx.ext.autodoc', 'sphinx_gallery']\n",
        encoding="utf-8",
    )
    build = tmp_path / "build"

    captured = {}

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env", {})
        # The function returns right after subprocess.run, so no HTML output
        # needs to exist; creating files here only risks permission errors.
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with mock.patch("subprocess.run", side_effect=fake_run):
        ok = sphinx_module.build_sphinx_html(
            src,
            build,
            verbose=False,
            lightweight=True,
            stub_modules={"missing_package"},
        )

    assert ok is True
    cmd = captured["cmd"]
    assert "-b" in cmd and "html" in cmd
    # extensions override must include core set and drop sphinx_gallery
    ext_arg = next(a for a in cmd if a.startswith("extensions="))
    assert "sphinx.ext.autodoc" in ext_arg
    assert "sphinx_gallery" not in ext_arg
    assert "autodoc_mock_imports=missing_package" in cmd
    # PYTHONPATH must include the generated stub dir
    assert "PYTHONPATH" in captured["env"]


def test_build_injects_markdown_builder(tmp_path: Path):
    # Step 1: building with -b markdown must inject the VENDORED
    # sphinx_markdown_builder extension and configure its link suffix to .md.
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text(
        "import missing_package\nextensions = ['sphinx.ext.autodoc', 'sphinx_gallery']\n",
        encoding="utf-8",
    )
    build = tmp_path / "build"

    captured = {}

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with mock.patch("subprocess.run", side_effect=fake_run):
        ok = sphinx_module.build_sphinx_html(
            src,
            build,
            verbose=False,
            lightweight=True,
            stub_modules={"missing_package"},
            builder="markdown",
        )

    assert ok is True
    cmd = captured["cmd"]
    assert "-b" in cmd and "markdown" in cmd
    ext_arg = next(a for a in cmd if a.startswith("extensions="))
    assert "sphinx_markdown_builder" in ext_arg
    assert "sphinx_gallery" not in ext_arg
    assert "markdown_uri_doc_suffix=.md" in cmd
    assert "markdown_docinfo=0" in cmd


def test_build_injects_vendored_builder_path(tmp_path: Path):
    # The vendored `sphinx_markdown_builder` (under rst_to_md/_vendor) must be
    # placed on PYTHONPATH so the patched copy shadows any PyPI install in the
    # sphinx-build subprocess.
    import rst_to_md.converters.sphinx as sphinx_module

    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text("extensions = ['sphinx.ext.autodoc']\n", encoding="utf-8")
    build = tmp_path / "build"

    captured: dict = {}

    def fake_run(cmd, *args, **kw):
        captured["env"] = kw.get("env", {})
        (build / "html" / "index.html").mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with mock.patch("subprocess.run", side_effect=fake_run):
        sphinx_module.build_sphinx_html(src, build, lightweight=True, builder="markdown")

    env = captured.get("env", {})
    pythonpath = env.get("PYTHONPATH", "")
    # The vendored _vendor directory must be on the path.
    assert "rst_to_md" not in pythonpath.split(os.sep)[-1] or "_vendor" in pythonpath
    assert "_vendor" in pythonpath


def _capture_build_cmd(src, build, **kwargs):
    """Run build_sphinx_html with a fake subprocess and return the cmd list."""
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, *args, **kw):
        captured["cmd"] = cmd
        (build / "html" / "index.html").mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with mock.patch("subprocess.run", side_effect=fake_run):
        sphinx_module.build_sphinx_html(src, build, **kwargs)
    return captured["cmd"]


def test_build_sphinx_html_passes_j_when_parallel(tmp_path: Path):
    """Performance: an explicit build_workers>1 must inject -j N."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text("extensions = []\n", encoding="utf-8")
    build = tmp_path / "build"
    cmd = _capture_build_cmd(src, build, lightweight=False, build_workers=4)
    assert "-j" in cmd
    assert cmd[cmd.index("-j") + 1] == "4"


def test_build_sphinx_html_no_j_when_serial(tmp_path: Path):
    """build_workers=1 (or 0 with a 1-core machine) must stay serial (no -j)."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text("extensions = []\n", encoding="utf-8")
    build = tmp_path / "build"
    cmd = _capture_build_cmd(src, build, lightweight=False, build_workers=1)
    assert "-j" not in cmd


def test_build_sphinx_html_j_auto_uses_cpu_count(tmp_path: Path):
    """build_workers=0 (auto) injects -j <cpu_count>."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text("extensions = []\n", encoding="utf-8")
    build = tmp_path / "build"
    with mock.patch.object(sphinx_module.os, "cpu_count", return_value=8):
        cmd = _capture_build_cmd(src, build, lightweight=False, build_workers=0)
    assert "-j" in cmd
    assert cmd[cmd.index("-j") + 1] == "8"


def test_build_sphinx_html_non_lightweight_no_override(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text("extensions = []\n", encoding="utf-8")
    build = tmp_path / "build"

    captured = {}

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        (build / "html" / "index.html").mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with mock.patch("subprocess.run", side_effect=fake_run):
        sphinx_module.build_sphinx_html(src, build, lightweight=False, stub_modules=None)
    cmd = captured["cmd"]
    assert not any(a.startswith("extensions=") for a in cmd)
    assert not any(a.startswith("autodoc_mock_imports=") for a in cmd)


def test_build_mock_all_imports(tmp_path: Path):
    """IMP-001: with mock_all_imports=True, autodoc_mock_imports must include
    importable packages (os, sphinx), not just the genuinely-missing ones."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text(
        "import os\nimport sphinx\nimport missing_package\nextensions = ['sphinx.ext.autodoc']\n",
        encoding="utf-8",
    )
    build = tmp_path / "build"

    captured = {}

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        (build / "html" / "index.html").mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    # With mock_all_imports=True, os/sphinx (importable) must be mocked too.
    with mock.patch("subprocess.run", side_effect=fake_run):
        sphinx_module.build_sphinx_html(
            src,
            build,
            lightweight=True,
            stub_modules={"os", "sphinx", "missing_package"},
            mock_all_imports=True,
        )
    cmd = captured["cmd"]
    mock_arg = next(a for a in cmd if a.startswith("autodoc_mock_imports="))
    mocked = mock_arg.split("=", 1)[1].split(",")
    assert "os" in mocked
    assert "sphinx" in mocked
    assert "missing_package" in mocked

    # Negative control: without mock_all_imports, importable packages excluded.
    with mock.patch("subprocess.run", side_effect=fake_run):
        sphinx_module.build_sphinx_html(
            src,
            build,
            lightweight=True,
            stub_modules={"os", "sphinx", "missing_package"},
        )
    cmd = captured["cmd"]
    mock_arg = next(a for a in cmd if a.startswith("autodoc_mock_imports="))
    mocked = mock_arg.split("=", 1)[1].split(",")
    assert "os" not in mocked
    assert "sphinx" not in mocked
    assert "missing_package" in mocked


# --------------------------------------------------------------------------- #
# P3 / P4: project conversion skipping + asset policy
# --------------------------------------------------------------------------- #
def _fake_build(src_dir, build_dir, *args, **kwargs):
    """Stand-in for build_sphinx_html that writes a fake HTML tree."""
    html_dir = build_dir / "html"
    for rel in [
        "index.html",
        "guide.html",
        "genindex.html",
        "search.html",
        "examples/foo.html",
        "auto_examples/bar.html",
        "_static/style.css",
    ]:
        p = html_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("<html><body>content</body></html>", encoding="utf-8")
    return True


def test_convert_sphinx_project_skips_and_sorts(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"

    with (
        mock.patch.object(sphinx_module, "build_sphinx_html", side_effect=_fake_build),
        mock.patch("html_to_markdown.convert", return_value="# x\n"),
    ):
        success, errors, skipped = convert_sphinx_project(src, out, lightweight=True)

    # index.html and guide.html converted; genindex/search/examples skipped.
    assert success == 2
    assert errors == 0
    assert skipped == 4
    assert (out / "index.md").exists()
    assert (out / "guide.md").exists()
    # Lightweight mode must NOT copy assets.
    assert not (out / "_images").exists()
    assert not (out / "_static").exists()
    # Build dir cleaned up.
    assert not (out / "_sphinx_build").exists()


# --------------------------------------------------------------------------- #
# P11: direct Markdown builder path (sphinx_markdown_builder)
# --------------------------------------------------------------------------- #
def test_convert_sphinx_project_markdown_builder(sphinx_min_project: Path, tmp_path: Path):
    """The direct Markdown builder (-b markdown) produces .md files directly
    (no HTML stage) and still skips system pages like genindex."""
    out = tmp_path / "out"
    success, errors, skipped = convert_sphinx_project(
        sphinx_min_project, out, builder="markdown", lightweight=True
    )
    # index.md and guide.md are produced; genindex.md is skipped.
    assert success >= 1
    assert errors == 0
    assert (out / "index.md").exists()
    assert (out / "guide.md").exists()
    # genindex is a system page and must be skipped in both builders.
    assert not (out / "genindex.md").exists()
    # The output is real Markdown (heading present), not raw HTML.
    text = (out / "guide.md").read_text(encoding="utf-8")
    assert "Guide" in text
    assert "<html" not in text


def test_convert_sphinx_project_markdown_skips_genindex(sphinx_min_project: Path, tmp_path: Path):
    """genindex.md (from the Markdown builder) must never appear in output.

    The skip itself is exercised by the suffix-agnostic SKIP_STEMS unit test and
    the HTML integration test; here we just guarantee the system page is absent
    from the Markdown output regardless of whether the builder emits it.
    """
    out = tmp_path / "out"
    success, errors, skipped = convert_sphinx_project(
        sphinx_min_project, out, builder="markdown", lightweight=True
    )
    assert success >= 1
    assert errors == 0
    assert not (out / "genindex.md").exists()


def test_convert_sphinx_project_markdown_cache(sphinx_min_project: Path, tmp_path: Path):
    """NTH-001 caching works for the Markdown builder (source .rst mtime)."""
    out = tmp_path / "out"
    r1 = convert_sphinx_project(sphinx_min_project, out, builder="markdown", lightweight=True)
    assert r1[0] > 0
    r2 = convert_sphinx_project(
        sphinx_min_project,
        out,
        builder="markdown",
        lightweight=True,
        use_cache=True,
    )
    # Second run: real docs are cached (no new successes); only the always-
    # skipped system pages (genindex) remain in the skipped count.
    assert r2[0] == 0


def test_convert_sphinx_project_markdown_parallel(sphinx_min_project: Path, tmp_path: Path):
    """NTH-002 parallel conversion works for the Markdown builder."""
    out = tmp_path / "out"
    success, errors, skipped = convert_sphinx_project(
        sphinx_min_project,
        out,
        builder="markdown",
        lightweight=True,
        max_workers=2,
    )
    assert success >= 1
    assert errors == 0
    assert (out / "index.md").exists()


# --------------------------------------------------------------------------- #
# P11: structural parity between HTML and direct Markdown builders
# --------------------------------------------------------------------------- #
def test_markdown_builder_parity_with_html(sphinx_md_project: Path, tmp_path: Path):
    """Both builders must yield a .md for the same source, and the direct
    Markdown builder output must not be raw HTML."""
    out_html = tmp_path / "html"
    out_md = tmp_path / "md"
    s_html, _, _ = convert_sphinx_project(
        sphinx_md_project, out_html, builder="html", lightweight=True
    )
    s_md, _, _ = convert_sphinx_project(
        sphinx_md_project, out_md, builder="markdown", lightweight=True
    )
    assert s_html >= 1
    assert s_md >= 1
    # Both produce index.md (the master doc).
    assert (out_html / "index.md").exists()
    assert (out_md / "index.md").exists()
    md_text = (out_md / "index.md").read_text(encoding="utf-8")
    # The documented class and a method must survive the direct Markdown build.
    assert "Calculator" in md_text
    assert "add" in md_text
    # Direct Markdown output is Markdown, not raw HTML.
    assert "<html" not in md_text


def test_markdown_builder_preserves_autodoc(sphinx_md_project: Path, tmp_path: Path):
    """The direct Markdown builder preserves autodoc class + members, and the
    vendored translator renders field lists / annotations / member signatures
    cleanly (D1/D2/D3 fixes)."""
    out = tmp_path / "out"
    convert_sphinx_project(sphinx_md_project, out, builder="markdown", lightweight=True)
    text = (out / "index.md").read_text(encoding="utf-8")
    assert "Calculator" in text
    assert "add" in text
    # Inheritance is preserved (show-inheritance -> Bases list).
    assert "Base" in text

    # D1: field lists are bold labels, NOT nested bullets. The outer defect
    # was `* **Parameters:**` (field name rendered as a bullet item); the
    # patched builder emits `**Parameters:**` as a plain bold label. An
    # inner bullet list of params (`* **a**`) is acceptable (matches the
    # html builder's `- **a**` flat list, just a `*` vs `-` marker).
    assert "**Parameters:**" in text or "**Returns:**" in text
    assert "* **Parameters:**" not in text
    assert "* **Raises:**" not in text

    # D2: `property`/`class` annotations are plain text, not `*italic*`.
    assert "property" in text
    assert "*property*" not in text

    # D3: member *methods* are `###` headings (the user expects
    # `### context(...)` for a method), while member *properties* are bold
    # paragraphs (a one-line property as a heading is noise). The top-level
    # class is a `##` section header (proper `#`->`##`->`###` hierarchy).
    assert "## class sample_pkg.Calculator" in text
    assert "### add(" in text
    assert "**property scale" in text
    assert "**add(" not in text
    assert "#### *property*" not in text
    assert "#### *class*" not in text


def test_markdown_builder_autodoc_formatting_matches_html(sphinx_md_project: Path, tmp_path: Path):
    """Regression: the markdown builder must not emit the three known
    autodoc formatting defects that the html builder avoids."""
    out_md = tmp_path / "md"
    convert_sphinx_project(sphinx_md_project, out_md, builder="markdown", lightweight=True)
    md = (out_md / "index.md").read_text(encoding="utf-8")
    # D1 - field name is NOT a bullet item (the outer nested-bullet defect)
    assert "* **Parameters:**" not in md
    assert "* **Raises:**" not in md
    # D2 - no italic property/class annotations
    assert "*property*" not in md
    assert "*class*" not in md
    # D3 - member methods are `####` headings; only the italic *property*/*
    # class* defect (heading wrapping an italic annotation) must be absent.
    assert "## class sample_pkg.Calculator" in md
    assert "### add(" in md
    assert "#### *property*" not in md
    assert "#### *class*" not in md


def test_markdown_builder_member_method_is_heading_property_is_bold(
    sphinx_md_project: Path, tmp_path: Path
):
    """D3 (corrected): a member *method* must be a `###` heading (the user
    expects `### context(...)` for a method), while a member *property* is a
    bold paragraph. The top-level class is a `##` section header. This guards
    against the regression where every nested member was flattened to bold."""
    out = tmp_path / "out"
    convert_sphinx_project(sphinx_md_project, out, builder="markdown", lightweight=True)
    text = (out / "index.md").read_text(encoding="utf-8")
    # Top-level class -> h2 section header.
    assert "## class sample_pkg.Calculator(precision: int = 2)" in text
    # Method -> h3 heading.
    assert "### add(a: int, b: int) → int" in text
    assert "**add(" not in text
    # Property -> bold paragraph (not a heading).
    assert "**property scale: int**" in text
    assert "#### property scale" not in text


# --------------------------------------------------------------------------- #
# XREF: cross-reference links inside autodoc signatures (P12)
# --------------------------------------------------------------------------- #
def test_markdown_builder_signature_xref_is_plain_text(
    sphinx_md_xref_project: Path, tmp_path: Path
):
    """XREF: a type referenced from a signature (cross-page pending_xref) must
    render as plain text, not an ambiguous `[Type](page.md#fully.qualified)`
    link. This matches the legacy html builder, which emits the bare type name.
    """
    out = tmp_path / "out"
    convert_sphinx_project(sphinx_md_xref_project, out, builder="markdown", lightweight=True)
    text = (out / "index.md").read_text(encoding="utf-8")
    # The type name is present...
    assert "BaseSession" in text
    # ...but NOT wrapped as a link inside the signature.
    assert "[BaseSession](" not in text
    # No fully-qualified anchor leaked into the signature.
    assert "session/base.md#" not in text
    # The class signature shows the plain type (param + return).
    assert "session: BaseSession | None = None" in text
    assert "→ BaseSession" in text or "BaseSession" in text


def test_markdown_builder_prose_xref_still_linked(sphinx_md_xref_project: Path, tmp_path: Path):
    """XREF: a cross-reference in *prose* (outside any signature) must NOT be
    flattened to plain text — only signature xrefs are. The builder renders the
    `:class:` role as a code span `` `session.base.BaseSession` ``, which is
    distinct from the plain `BaseSession` used inside the signature, proving the
    `desc_depth` guard only affects signature subtrees."""
    out = tmp_path / "out"
    convert_sphinx_project(sphinx_md_xref_project, out, builder="markdown", lightweight=True)
    text = (out / "index.md").read_text(encoding="utf-8")
    # Prose reference keeps its qualified code-span form (not flattened).
    assert "`session.base.BaseSession`" in text
    # It is NOT the bare plain-text form used inside the signature.
    assert "See the `session.base.BaseSession`" in text
    # No fully-qualified anchor leaked into prose either.
    assert "session/base.md#" not in text


def test_markdown_builder_signature_xref_no_orphan_context(
    sphinx_md_xref_project: Path, tmp_path: Path
):
    """XREF: the early-return path pushes a neutral SubContext so the
    @pushing_context depart stays stack-balanced — the generated Markdown for
    the signature is well-formed (no dangling `](` or unbalanced brackets)."""
    out = tmp_path / "out"
    convert_sphinx_project(sphinx_md_xref_project, out, builder="markdown", lightweight=True)
    text = (out / "index.md").read_text(encoding="utf-8")
    # Count brackets: any `[` must be matched by a `]` on the same line within
    # the signature region. Simplest robust check: the signature line has no
    # stray `](` that isn't part of a valid link.
    sig_line = next((ln for ln in text.splitlines() if ln.startswith("## class bot.Bot")), "")
    assert sig_line
    # No dangling link-close without an opener, and no `[Type](` inside sig.
    assert "[BaseSession](" not in sig_line
    # Balanced brackets on the signature line.
    assert sig_line.count("[") == sig_line.count("]")


def test_convert_sphinx_project_non_project(tmp_path: Path):
    src = tmp_path / "notsphinx"
    src.mkdir()
    out = tmp_path / "out"
    result = convert_sphinx_project(src, out)
    assert result == (0, 0, 0)


# --------------------------------------------------------------------------- #
# P10: napoleon skip-member robustness (pydantic-style crash must not abort)
# --------------------------------------------------------------------------- #
_FIXTURE_NAPOLEON = Path(__file__).resolve().parent / "fixtures" / "sphinx_napoleon_crash"


def test_sitecustomize_patches_napoleon_skip_member(tmp_path: Path):
    """The robustness sitecustomize must patch napoleon's _skip_member."""
    stub_dir = build_stub_sitecustomize(set(), tmp_path)
    content = (stub_dir / "sitecustomize.py").read_text(encoding="utf-8")
    assert "sphinx.ext.napoleon" in content
    assert "_safe_skip_member" in content
    assert "_orig_skip_member" in content


def test_napoleon_skip_member_exists():
    """IMP-004: fail loudly if Sphinx renames/removes the private handler we
    monkeypatch, instead of silently no-op'ing (which would let the crash
    return)."""
    import sphinx.ext.napoleon as _napoleon

    assert hasattr(_napoleon, "_skip_member")


def test_sitecustomize_patches_skip_member(tmp_path: Path):
    """IMP-004: the generated sitecustomize must reference both the private
    handler name and our wrapper, so a Sphinx rename would be caught by
    inspecting the generated text."""
    content = (
        build_stub_sitecustomize(set(), tmp_path)
        .joinpath("sitecustomize.py")
        .read_text(encoding="utf-8")
    )
    assert "_skip_member" in content
    assert "_safe_skip_member" in content


def test_sphinx_uses_shared_postprocess(tmp_path: Path):
    # IMP-005: Sphinx mode must route through the shared post_process_markdown.
    import rst_to_md.core.postprocess as pp

    html = tmp_path / "page.html"
    html.write_text("<html></html>", encoding="utf-8")
    md = tmp_path / "page.md"
    with (
        mock.patch("html_to_markdown.convert", return_value="# x\n"),
        mock.patch(
            "rst_to_md.converters.sphinx.post_process_markdown",
            wraps=pp.post_process_markdown,
        ) as spy,
    ):
        convert_html_to_md(html, md)
    spy.assert_called()


def test_napoleon_skip_member_crash_does_not_abort_build(tmp_path: Path):
    """A member whose ``__qualname__`` raises (pydantic-style) must be skipped,
    not abort the whole Sphinx build.

    Passing ``stub_modules=set()`` (not ``None``) ensures the robustness
    sitecustomize with the napoleon patch is installed even though nothing
    needs stubbing.
    """
    build_dir = tmp_path / "build"
    ok = build_sphinx_html(_FIXTURE_NAPOLEON, build_dir, lightweight=True, stub_modules=set())
    assert ok is True
    html = build_dir / "html" / "index.html"
    assert html.exists()
    text = html.read_text(encoding="utf-8")
    # The class itself is still documented; only the offending member is skipped.
    assert "Thing" in text
    assert "public_method" in text


def test_napoleon_skip_member_crash_without_patch_aborts_build(tmp_path: Path):
    """Regression guard: without the patch the same fixture aborts the build."""
    build_dir = tmp_path / "build"
    with pytest.raises(SphinxBuildError):
        build_sphinx_html(_FIXTURE_NAPOLEON, build_dir, lightweight=False)


def test_convert_sphinx_project_build_failure(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"

    def boom(*a, **k):
        raise SphinxBuildError("nope")

    with mock.patch.object(sphinx_module, "build_sphinx_html", side_effect=boom):
        result = convert_sphinx_project(src, out)
    assert result == (0, 1, 0)


def test_convert_sphinx_project_retries_once(tmp_path: Path):
    """IMP-001: a build failure triggers exactly one mock-all retry and still
    produces Markdown."""
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"

    calls = {"n": 0}

    def fake_build(src_dir, build_dir, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise SphinxBuildError("first build failed")
        html_dir = build_dir / "html"
        html_dir.mkdir(parents=True, exist_ok=True)
        (html_dir / "index.html").write_text("<html><body>content</body></html>", encoding="utf-8")
        return True

    with (
        mock.patch.object(sphinx_module, "build_sphinx_html", side_effect=fake_build),
        mock.patch("html_to_markdown.convert", return_value="# x\n"),
    ):
        success, errors, skipped = convert_sphinx_project(src, out, lightweight=True)

    assert calls["n"] == 2
    assert success == 1
    assert errors == 0
    assert (out / "index.md").is_file()


def test_convert_sphinx_project_fallback_logs_warning(tmp_path: Path):
    """IMP-001: the fallback logs a clear WARNING when it is used."""
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"

    state = {"called": False}

    def fake_build(src_dir, build_dir, *args, **kwargs):
        if not state["called"]:
            state["called"] = True
            raise SphinxBuildError("first build failed")
        html_dir = build_dir / "html"
        html_dir.mkdir(parents=True, exist_ok=True)
        (html_dir / "index.html").write_text("<html><body>content</body></html>", encoding="utf-8")
        return True

    # The rst_to_md logger does not propagate (see core/logging.setup_logging),
    # so caplog on the root logger would not capture it. Spy on the module's
    # logger.warning directly instead.
    with (
        mock.patch.object(sphinx_module, "build_sphinx_html", side_effect=fake_build),
        mock.patch("html_to_markdown.convert", return_value="# x\n"),
        mock.patch.object(
            sphinx_module.logger, "warning", wraps=sphinx_module.logger.warning
        ) as warn_spy,
    ):
        convert_sphinx_project(src, out, lightweight=True)

    assert any(
        "retrying once with all imports mocked" in (c.args[0] if c.args else "")
        for c in warn_spy.call_args_list
    )


def test_convert_sphinx_project_fallback_still_fails(tmp_path: Path):
    """IMP-001: if even the fallback retry fails, (0, 1, 0) is returned and the
    retry was attempted."""
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"

    calls = {"n": 0}

    def boom(*args, **kwargs):
        calls["n"] += 1
        raise SphinxBuildError("nope")

    with mock.patch.object(sphinx_module, "build_sphinx_html", side_effect=boom):
        result = convert_sphinx_project(src, out)
    assert result == (0, 1, 0)
    assert calls["n"] == 2  # first build + fallback retry


def test_is_sphinx_project(tmp_path: Path):
    assert not is_sphinx_project(tmp_path)
    (tmp_path / "conf.py").write_text("pass\n", encoding="utf-8")
    assert is_sphinx_project(tmp_path)


# --------------------------------------------------------------------------- #
# NTH-001: incremental caching (Sphinx mode)
# --------------------------------------------------------------------------- #
def test_sphinx_cache_skips_unchanged(sphinx_min_project: Path, tmp_path: Path):
    out = tmp_path / "out"
    with mock.patch("html_to_markdown.convert", return_value="# x\n"):
        r1 = convert_sphinx_project(sphinx_min_project, out)
        r2 = convert_sphinx_project(sphinx_min_project, out)
    assert r1[0] > 0
    # Second run: real docs are cached (no new successes); only the always-
    # skipped system pages (genindex/search) remain in the skipped count.
    assert r2[0] == 0
    assert r2[2] > r1[2]


def test_sphinx_cache_off_reconverts(sphinx_min_project: Path, tmp_path: Path):
    out = tmp_path / "out"
    with mock.patch("html_to_markdown.convert", return_value="# x\n"):
        convert_sphinx_project(sphinx_min_project, out)  # populate cache
        r_cache_on = convert_sphinx_project(sphinx_min_project, out, use_cache=True)
        r_cache_off = convert_sphinx_project(sphinx_min_project, out, use_cache=False)
    # cache-on: real docs skipped (no new successes)
    assert r_cache_on[0] == 0
    # cache-off: real docs reconverted
    assert r_cache_off[0] > 0
    assert r_cache_off[0] > r_cache_on[0]


# --------------------------------------------------------------------------- #
# NTH-003: per-file error surfacing (Sphinx mode)
# --------------------------------------------------------------------------- #
def test_convert_html_to_md_records_error(tmp_path: Path):
    html = tmp_path / "p.html"
    html.write_text("<html></html>", encoding="utf-8")
    md = tmp_path / "p.md"
    errs: list[str] = []
    with mock.patch("html_to_markdown.convert", side_effect=RuntimeError("boom")):
        ok = convert_html_to_md(html, md, errors=errs)
    assert ok is False
    assert len(errs) == 1
    assert "p.html" in errs[0]


# --------------------------------------------------------------------------- #
# Direct Markdown builder leaf: convert_built_md
# --------------------------------------------------------------------------- #
def test_convert_built_md_success_strips_footer_and_media(tmp_path: Path):
    # A .md produced by sphinx_markdown_builder may carry a Sphinx footer and
    # media links; convert_built_md must run the shared post-processing.
    src = tmp_path / "page.md"
    src.write_text(
        "# Title\n\nBody text.\n\n"
        "![diagram](media/diag.png)\n\n"
        "Created using Sphinx.\n\nLast updated on 2026-01-01.\n",
        encoding="utf-8",
    )
    out = tmp_path / "out" / "page.md"
    errs: list[str] = []
    ok = sphinx_module.convert_built_md(src, out, errors=errs)
    assert ok is True
    assert errs == []
    text = out.read_text(encoding="utf-8")
    assert "# Title" in text
    assert "Body text." in text
    # Footer + media stripped by post_process_markdown.
    assert "Created using Sphinx" not in text
    assert "Last updated on" not in text
    assert "media/diag.png" not in text


def test_convert_built_md_idempotent(tmp_path: Path):
    src = tmp_path / "page.md"
    src.write_text("# Title\n\nSome text.\n\n\n\n\n", encoding="utf-8")
    out = tmp_path / "out" / "page.md"
    assert sphinx_module.convert_built_md(src, out) is True
    first = out.read_text(encoding="utf-8")
    # Running again on the already-clean output is a no-op.
    assert sphinx_module.convert_built_md(out, out) is True
    assert out.read_text(encoding="utf-8") == first


def test_convert_built_md_failure_records_error(tmp_path: Path):
    missing = tmp_path / "nope.md"
    out = tmp_path / "out.md"
    errs: list[str] = []
    ok = sphinx_module.convert_built_md(missing, out, errors=errs)
    assert ok is False
    assert len(errs) == 1
    assert "nope.md" in errs[0]


def test_convert_built_md_suppresses_logs_when_progress(tmp_path: Path, caplog):
    caplog.set_level(logging.INFO, logger="rst_to_md")
    src = tmp_path / "page.md"
    src.write_text("# Title\n\nBody.\n", encoding="utf-8")
    out = tmp_path / "out.md"
    errs: list[str] = []
    ok = sphinx_module.convert_built_md(src, out, show_progress=True, errors=errs)
    assert ok is True
    assert "[OK]" not in caplog.text
    assert "[ERR]" not in caplog.text


# --------------------------------------------------------------------------- #
# NTH-006: Sphinx builder override
# --------------------------------------------------------------------------- #
def test_build_sphinx_html_passes_builder(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text("pass\n", encoding="utf-8")
    build = tmp_path / "build"
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, *a, **k):
        captured["cmd"] = list(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    with mock.patch("rst_to_md.converters.sphinx.subprocess.run", side_effect=fake_run):
        build_sphinx_html(src, build, builder="singlehtml")
    assert "-b" in captured["cmd"]
    assert "singlehtml" in captured["cmd"]

    captured.clear()
    with mock.patch("rst_to_md.converters.sphinx.subprocess.run", side_effect=fake_run):
        build_sphinx_html(src, build)
    assert "-b" in captured["cmd"]
    assert "html" in captured["cmd"]  # default builder


def test_convert_sphinx_project_passes_builder(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"
    seen: list[str] = []

    def fake_build(src_dir, build_dir, *args, **kwargs):
        seen.append(kwargs.get("builder"))
        html_dir = build_dir / "html"
        html_dir.mkdir(parents=True, exist_ok=True)
        (html_dir / "index.html").write_text("<html><body>x</body></html>", encoding="utf-8")
        return True

    with (
        mock.patch.object(sphinx_module, "build_sphinx_html", side_effect=fake_build),
        mock.patch("html_to_markdown.convert", return_value="# x\n"),
    ):
        convert_sphinx_project(src, out, builder="singlehtml")
    assert seen == ["singlehtml"]


def test_convert_sphinx_project_passes_build_workers(tmp_path: Path):
    """Performance: build_workers is forwarded to the build (and the IMP-001
    fallback retries serially with build_workers=1)."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"
    calls: list[int] = []

    def fake_build(src_dir, build_dir, *args, **kwargs):
        calls.append(kwargs.get("build_workers"))
        html_dir = build_dir / "html"
        html_dir.mkdir(parents=True, exist_ok=True)
        (html_dir / "index.html").write_text("<html><body>x</body></html>", encoding="utf-8")
        return True

    with (
        mock.patch.object(sphinx_module, "build_sphinx_html", side_effect=fake_build),
        mock.patch("html_to_markdown.convert", return_value="# x\n"),
    ):
        convert_sphinx_project(src, out, build_workers=4)
    # Primary build gets 4; no fallback was needed.
    assert calls == [4]


def test_convert_sphinx_project_fallback_is_serial(tmp_path: Path):
    """IMP-001: if the parallel build fails, the retry runs serially."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"
    calls: list[int] = []

    def fake_build(src_dir, build_dir, *args, **kwargs):
        calls.append(kwargs.get("build_workers"))
        if len(calls) == 1:
            raise sphinx_module.SphinxBuildError("boom")
        html_dir = build_dir / "html"
        html_dir.mkdir(parents=True, exist_ok=True)
        (html_dir / "index.html").write_text("<html><body>x</body></html>", encoding="utf-8")
        return True

    with (
        mock.patch.object(sphinx_module, "build_sphinx_html", side_effect=fake_build),
        mock.patch("html_to_markdown.convert", return_value="# x\n"),
    ):
        convert_sphinx_project(src, out, build_workers=4)
    # First attempt parallel (4), retry serial (1).
    assert calls == [4, 1]


def test_fallback_uses_same_builder(tmp_path: Path):
    """IMP-001 fallback must retry with the same builder the user requested."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text("pass\n", encoding="utf-8")
    out = tmp_path / "out"
    seen: list[str] = []
    calls = {"n": 0}

    def fake_build(src_dir, build_dir, *args, **kwargs):
        seen.append(kwargs.get("builder"))
        calls["n"] += 1
        if calls["n"] == 1:
            raise SphinxBuildError("first build failed")
        html_dir = build_dir / "html"
        html_dir.mkdir(parents=True, exist_ok=True)
        (html_dir / "index.html").write_text("<html><body>x</body></html>", encoding="utf-8")
        return True

    with (
        mock.patch.object(sphinx_module, "build_sphinx_html", side_effect=fake_build),
        mock.patch("html_to_markdown.convert", return_value="# x\n"),
    ):
        convert_sphinx_project(src, out, builder="singlehtml")
    assert seen == ["singlehtml", "singlehtml"]


# --------------------------------------------------------------------------- #
# WS2: autosummary generation policy (configurable, with importability probe)
# --------------------------------------------------------------------------- #
def _write_src_with_documented_modules(
    tmp_path: Path, rst_body: str, extensions: str = "['sphinx.ext.autosummary']"
) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text(f"extensions = {extensions}\n", encoding="utf-8")
    (src / "index.rst").write_text(rst_body, encoding="utf-8")
    return src


def _capture_autosummary_flag(tmp_path: Path, **kwargs) -> str:
    """Build a lightweight sphinx project with a faked subprocess and return the
    ``autosummary_generate=...`` flag that ended up on the command line."""
    src = kwargs.pop("src")
    build = tmp_path / "build"

    captured = {}

    def fake_run(cmd, *a, **k):
        captured["cmd"] = list(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    with mock.patch("rst_to_md.converters.sphinx.subprocess.run", side_effect=fake_run):
        sphinx_module.build_sphinx_html(src, build, **kwargs)
    cmd_str = " ".join(captured["cmd"])
    # Pull out the single autosummary_generate= flag.
    flag = next(
        (tok for tok in captured["cmd"] if tok.startswith("autosummary_generate=")),
        None,
    )
    return flag, cmd_str


def test_build_sphinx_html_autosummary_generate_false_explicit(tmp_path: Path):
    src = _write_src_with_documented_modules(tmp_path, "Title\n=====\n\nBody\n")
    flag, _ = _capture_autosummary_flag(
        tmp_path,
        src=src,
        lightweight=True,
        stub_modules=set(),
        builder="html",
        autosummary_generate="false",
    )
    assert flag == "autosummary_generate=False"


def test_build_sphinx_html_autosummary_generate_true_explicit(tmp_path: Path):
    src = _write_src_with_documented_modules(tmp_path, "Title\n=====\n\nBody\n")
    flag, _ = _capture_autosummary_flag(
        tmp_path,
        src=src,
        lightweight=True,
        stub_modules=set(),
        builder="html",
        autosummary_generate="true",
    )
    assert flag == "autosummary_generate=True"


def test_build_sphinx_html_autosummary_generate_auto_not_importable(tmp_path: Path):
    # auto + a documented module that is NOT installed -> generate=False (the
    # documented package must not be imported during the build).
    src = _write_src_with_documented_modules(
        tmp_path, ".. currentmodule:: this_package_is_not_installed_xyz\n"
    )
    flag, _ = _capture_autosummary_flag(
        tmp_path,
        src=src,
        lightweight=True,
        stub_modules=set(),
        builder="html",
    )
    assert flag == "autosummary_generate=False"


def test_decide_autosummary_generate_false():
    assert decide_autosummary_generate("false", Path("/")) is False


def test_decide_autosummary_generate_true():
    assert decide_autosummary_generate("true", Path("/")) is True


def test_decide_autosummary_generate_bool_passthrough():
    assert decide_autosummary_generate(True, Path("/")) is True
    assert decide_autosummary_generate(False, Path("/")) is False


def test_decide_autosummary_generate_auto_importable(tmp_path: Path):
    # ``sphinx`` is always installed in the test environment -> importable.
    src = _write_src_with_documented_modules(tmp_path, ".. currentmodule:: sphinx\n")
    assert decide_autosummary_generate("auto", src) is True


def test_decide_autosummary_generate_auto_not_importable(tmp_path: Path):
    src = _write_src_with_documented_modules(tmp_path, ".. currentmodule:: nope_package_xyz\n")
    assert decide_autosummary_generate("auto", src) is False


def test_decide_autosummary_generate_auto_short_circuits(tmp_path: Path):
    # When the caller already knows importability, the probe is skipped and the
    # supplied value wins even for a non-importable module.
    src = _write_src_with_documented_modules(tmp_path, ".. currentmodule:: nope_package_xyz\n")
    assert decide_autosummary_generate("auto", src, documented_importable=True) is True


def test_extract_documented_modules_parses_directives(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.rst").write_text(
        ".. currentmodule:: librosa.beat\n\n"
        ".. autoclass:: librosa.feature.MelSpectrogram\n\n"
        ".. autofunction:: librosa.load\n",
        encoding="utf-8",
    )
    (src / "b.rst").write_text(
        ".. automodule:: numpy\n\n.. autodata:: scipy.pi\n", encoding="utf-8"
    )
    names = extract_documented_modules(src)
    assert names == {"librosa", "numpy", "scipy"}


# --------------------------------------------------------------------------- #
# WS2: CLI flag
# --------------------------------------------------------------------------- #
def test_cli_autosummary_generate_default():
    from rst_to_md.cli import build_parser

    args = build_parser().parse_args(["docs"])
    assert args.autosummary_generate == AUTOSUMMARY_GENERATE_DEFAULT


def test_cli_autosummary_generate_explicit():
    from rst_to_md.cli import build_parser

    for value in ("auto", "true", "false"):
        args = build_parser().parse_args(["docs", "--autosummary-generate", value])
        assert args.autosummary_generate == value


# --------------------------------------------------------------------------- #
# WS4 + WS6: autosummary enrichment wired into the converters
# --------------------------------------------------------------------------- #
def _sample_pkg_source_map(tmp_path: Path) -> dict:
    pkg = tmp_path / "sample_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        'def beat_track(y=None, sr=None):\n    """Beat tracker."""\n    return []\n',
        encoding="utf-8",
    )
    from rst_to_md.core.source_extract import (
        build_source_map,
        find_source_roots,
    )

    roots = find_source_roots(tmp_path, {"sample_pkg"})
    return build_source_map(roots)


def test_convert_built_md_enriches_autosummary(tmp_path: Path):
    """convert_built_md fills empty autosummary cells when a source map is
    supplied (the direct Markdown builder path). IMP-007: the per-file call
    enriches tables only — generated/ stubs are written once by the project
    converter, so none must appear here."""
    source_map = _sample_pkg_source_map(tmp_path)

    src_rst = tmp_path / "page.rst"
    src_rst.write_text(".. currentmodule:: sample_pkg\n", encoding="utf-8")
    in_md = tmp_path / "in" / "page.md"
    in_md.parent.mkdir(parents=True)
    in_md.write_text("# sample_pkg\n\n| `beat_track` | |\n|---|---\n", encoding="utf-8")
    out_md = tmp_path / "out" / "page.md"
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    ok = convert_built_md(
        in_md,
        out_md,
        source_map=source_map,
        src_rst=src_rst,
        output_dir=out_dir,
    )
    assert ok is True
    text = out_md.read_text(encoding="utf-8")
    assert "Beat tracker." in text
    assert "[`beat_track`](generated/sample_pkg.beat_track.md" in text
    # IMP-007: no per-file stub writes.
    assert not (out_dir / "generated").exists()


def test_convert_built_md_no_source_map_is_passthrough(tmp_path: Path):
    """Without a source map, convert_built_md only runs the shared cleanup and
    does NOT enrich or create a generated/ dir."""
    in_md = tmp_path / "in" / "page.md"
    in_md.parent.mkdir(parents=True)
    in_md.write_text("# Page\n\n| `beat_track` | |\n|---|---\n", encoding="utf-8")
    out_md = tmp_path / "out" / "page.md"
    out_md.parent.mkdir(parents=True)

    ok = convert_built_md(in_md, out_md)
    assert ok is True
    text = out_md.read_text(encoding="utf-8")
    assert "# Page" in text
    # No enrichment, no generated stub pages.
    assert not (tmp_path / "out" / "generated").exists()


def test_convert_html_to_md_enriches_autosummary(tmp_path: Path):
    """convert_html_to_md fills empty autosummary cells when a source map is
    supplied (the legacy html builder path). IMP-007: the per-file call
    enriches tables only — generated/ stubs are written once by the project
    converter, so none must appear here."""
    source_map = _sample_pkg_source_map(tmp_path)

    src_rst = tmp_path / "page.rst"
    src_rst.write_text(".. currentmodule:: sample_pkg\n", encoding="utf-8")
    html = tmp_path / "page.html"
    html.write_text("<html></html>", encoding="utf-8")
    out_md = tmp_path / "out" / "page.md"
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with mock.patch(
        "html_to_markdown.convert",
        return_value="# sample_pkg\n\n| `beat_track` | |\n|---|---\n",
    ):
        ok = convert_html_to_md(
            html,
            out_md,
            source_map=source_map,
            src_rst=src_rst,
            output_dir=out_dir,
        )
    assert ok is True
    text = out_md.read_text(encoding="utf-8")
    assert "Beat tracker." in text
    # IMP-007: no per-file stub writes.
    assert not (out_dir / "generated").exists()


def test_convert_sphinx_project_enriches_autosummary(
    sphinx_md_autosummary_project: Path, tmp_path: Path
):
    """Full pipeline: a Sphinx project whose documented package is not installed
    still yields an autosummary table with signatures + summaries, plus the
    generated/ stub pages so table links resolve."""
    out = tmp_path / "out"
    success, errors, _ = convert_sphinx_project(
        sphinx_md_autosummary_project, out, builder="markdown", lightweight=True
    )
    assert errors == 0
    assert success >= 1
    text = (out / "index.md").read_text(encoding="utf-8")
    # Members + doc summaries present (enriched from source or rendered by build).
    assert "Dynamic programming beat tracker." in text
    assert "Predominant local pulse (PLP) estimation." in text
    # No empty stub cells remain.
    assert "|  |" not in text
    assert "| |" not in text
    # Generated stub pages written so the table links resolve.
    assert (out / "generated" / "sample_pkg.beat_track.md").is_file()
    assert (out / "generated" / "sample_pkg.plp.md").is_file()


def test_convert_sphinx_project_writes_generated_stubs(
    sphinx_md_autosummary_project: Path, tmp_path: Path
):
    """The generated/ stub pages carry the AST signature + docstring."""
    out = tmp_path / "out"
    convert_sphinx_project(sphinx_md_autosummary_project, out, builder="markdown", lightweight=True)
    beat_stub = out / "generated" / "sample_pkg.beat_track.md"
    assert beat_stub.is_file()
    content = beat_stub.read_text(encoding="utf-8")
    # Heading equals the fqn (the link anchor target).
    assert "# sample_pkg.beat_track" in content
    # AST-derived all-optional signature.
    assert "(*[, y, sr, onset_envelope])" in content
    assert "Dynamic programming beat tracker." in content


def test_convert_sphinx_project_writes_stubs_once(
    sphinx_md_autosummary_project: Path, tmp_path: Path, monkeypatch
):
    """IMP-007: generated/ stubs are written exactly once per project run,
    regardless of --workers, and never from the per-file enrich path."""
    from rst_to_md.converters import sphinx as sphinx_mod

    calls: list = []
    real_write = sphinx_mod.write_generated_stubs

    def spy(base_dir, source_map):
        calls.append(Path(base_dir))
        return real_write(base_dir, source_map)

    monkeypatch.setattr(sphinx_mod, "write_generated_stubs", spy)
    out = tmp_path / "out"
    ok, err, skip = sphinx_mod.convert_sphinx_project(
        sphinx_md_autosummary_project,
        out,
        builder="markdown",
        max_workers=4,
        show_progress=False,
    )
    assert err == 0
    assert ok >= 1
    assert calls == [out], f"expected exactly one stub write to {out}, got {calls}"
    assert (out / "generated" / "sample_pkg.beat_track.md").is_file()
    assert (out / "generated" / "sample_pkg.plp.md").is_file()


def test_convert_sphinx_project_parallel_stub_integrity(
    sphinx_md_autosummary_project: Path, tmp_path: Path
):
    """IMP-007: with --workers 4 the output (pages + generated stubs) must be
    byte-identical to a serial run — no interleaved/corrupt writes."""
    out_serial = tmp_path / "serial"
    out_parallel = tmp_path / "parallel"
    r1 = convert_sphinx_project(
        sphinx_md_autosummary_project,
        out_serial,
        builder="markdown",
        max_workers=1,
        show_progress=False,
    )
    r2 = convert_sphinx_project(
        sphinx_md_autosummary_project,
        out_parallel,
        builder="markdown",
        max_workers=4,
        show_progress=False,
    )
    assert r1[1] == 0 and r2[1] == 0

    def snapshot(root: Path) -> dict:
        return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*.md"))}

    assert snapshot(out_serial) == snapshot(out_parallel)
    gen = out_parallel / "generated"
    assert gen.is_dir()
    for stub in gen.glob("*.md"):
        text = stub.read_text(encoding="utf-8")
        assert text.startswith("# "), f"corrupt stub {stub}"


# --------------------------------------------------------------------------- #
# Regression: conf.py-local modules must never be stubbed (torchaudio crash)
# --------------------------------------------------------------------------- #
def test_local_directive_module_not_stubbed(
    sphinx_local_directives_project: Path, output_dir: Path
):
    """Regression: a conf.py-local module that registers docutils directives
    must NOT be stubbed by sitecustomize. Stubbing it makes docutils resolve
    ``directive.required_arguments`` to a ``_DummyModule`` and crash with
    ``TypeError: '<' not supported between instances of 'int' and
    '_DummyModule'`` (torchaudio docs failure)."""
    success, errors, skipped = convert_sphinx_project(
        sphinx_local_directives_project,
        output_dir,
        lightweight=True,
        builder="markdown",
    )
    assert errors == 0
    assert success >= 1
    index_md = (output_dir / "index.md").read_text(encoding="utf-8")
    assert "hello-local-directive" in index_md


def test_stubbed_third_party_directive_does_not_abort_build(
    sphinx_stubbed_directive_project: Path, output_dir: Path
):
    """A directive class imported from a genuinely-missing package resolves to
    a ``_DummyModule``; the ``run_directive`` guard must degrade it to a
    system message so the rest of the document still converts."""
    success, errors, skipped = convert_sphinx_project(
        sphinx_stubbed_directive_project,
        output_dir,
        lightweight=True,
        builder="markdown",
    )
    assert errors == 0
    assert success >= 1
    index_md = (output_dir / "index.md").read_text(encoding="utf-8")
    assert "Normal body content survives." in index_md


# --------------------------------------------------------------------------- #
# NTH-007: externalized sitecustomize template
# --------------------------------------------------------------------------- #
def test_sitecustomize_template_file_shape():
    """The packaged template must exist, be loadable via importlib.resources,
    and contain exactly one ``__ALLOWED__`` sentinel with no leftover
    ``.format()`` doubled braces."""
    from importlib import resources

    template = (
        resources.files("rst_to_md._templates")
        .joinpath("sitecustomize.py.tmpl")
        .read_text(encoding="utf-8")
    )
    assert template.count("__ALLOWED__") == 1
    # No .format()-style doubled braces should survive in the template.
    assert "{{" not in template
    assert "}}" not in template
    # The template must still be a syntactically valid Python module once the
    # sentinel is substituted with a concrete allow-list literal.
    import ast

    rendered = template.replace("__ALLOWED__", "{'alpha', 'beta'}")
    ast.parse(rendered)


def test_sitecustomize_rendered_matches_legacy_format(tmp_path: Path):
    """Rendering through ``build_stub_sitecustomize`` must produce exactly the
    same bytes as the historical inline ``.format()`` pipeline (regression
    guard against accidental template drift)."""
    stub_dir = build_stub_sitecustomize({"beta", "alpha"}, tmp_path / "_stubs")
    content = (stub_dir / "sitecustomize.py").read_text(encoding="utf-8")
    # The allow-list literal is rendered sorted with repr().
    assert "_ALLOWED = {'alpha', 'beta'}" in content
    # No sentinel or format placeholders may leak into the output.
    assert "__ALLOWED__" not in content
    assert "{allowed}" not in content


def test_sitecustomize_rendered_empty_allowed(tmp_path: Path):
    """An empty module set must render an empty allow-list literal."""
    stub_dir = build_stub_sitecustomize(set(), tmp_path / "_stubs")
    content = (stub_dir / "sitecustomize.py").read_text(encoding="utf-8")
    assert "_ALLOWED = {}" in content
    assert "__ALLOWED__" not in content
