"""Sphinx-aware RST -> Markdown conversion.

This module builds a Sphinx HTML project, then converts the generated HTML to
Markdown using **html_to_markdown** (with a pandoc fallback). This is a
different backend from the simple RST mode in
[`rst_to_md/converters/rst.py`](rst_to_md/converters/rst.py:1), which converts
RST directly with **pypandoc**; both modes share the post-processing in
[`rst_to_md/core/postprocess.py`](rst_to_md/core/postprocess.py:176). In
*lightweight* mode it avoids requiring the documented package or
heavy extensions by:

  * stubbing missing top-level imports in ``conf.py`` (via a generated
    ``sitecustomize.py`` placed on ``PYTHONPATH``), and
  * mocking autodoc imports and filtering out plot/gallery/ipython extensions.

If the lightweight build still crashes in a way the napoleon patch does not
catch, :func:`convert_sphinx_project` retries **once** with every top-level
import from ``conf.py`` mocked (``autodoc_mock_imports`` = all imports). This
degraded fallback guarantees *some* Markdown is produced instead of zero output
for the whole project; the trade-off is that mocked modules may yield empty
``Bases:`` / member content.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ..config import (
    AUTOSUMMARY_GENERATE_DEFAULT,
    CORE_EXTENSIONS,
    EXTENSION_DENYLIST,
    SKIP_DIRS,
    SKIP_PATH_FRAGMENTS,
    SKIP_STEMS,
)
from ..core import is_up_to_date
from ..core.autosummary_enrich import enrich_file, write_generated_stubs
from ..core.html_clean import (
    clean_sphinx_html,
    normalize_autodoc_html,
)
from ..core.postprocess import post_process_markdown, strip_sphinx_chrome
from ..core.progress import ProgressTracker
from ..core.source_extract import build_source_map, find_source_roots
from ..exceptions import SphinxBuildError

logger = logging.getLogger("rst_to_md")


# --------------------------------------------------------------------------- #
# Inspection helpers (no Sphinx execution required)
# --------------------------------------------------------------------------- #
def is_sphinx_project(directory: Path) -> bool:
    """Return ``True`` if ``directory`` looks like a Sphinx project."""
    return (directory / "conf.py").exists()


def resolve_sphinx_project_dir(input_dir: Path) -> Path | None:
    """Return the directory containing ``conf.py`` for ``input_dir``.

    Many Sphinx repositories keep the actual project one level down (e.g.
    ``docs/source/conf.py``), so pointing the CLI at the repository's ``docs``
    folder would otherwise fail validation. Prefers ``input_dir`` itself;
    otherwise probes common one-level subdirectories (``source``, ``doc``,
    ``docs``) in that fixed order. Returns ``None`` when no ``conf.py`` is
    found. Deterministic: fixed probe order, no filesystem-order dependence.
    """
    if (input_dir / "conf.py").exists():
        return input_dir
    for sub in ("source", "doc", "docs"):
        candidate = input_dir / sub
        if (candidate / "conf.py").exists():
            return candidate
    return None


def check_sphinx_installed() -> bool:
    """Return ``True`` if the ``sphinx`` package is importable."""
    try:
        import sphinx  # noqa: F401

        return True
    except ImportError:
        return False


def _is_importable(module_name: str) -> bool:
    """Return ``True`` if ``module_name`` can be imported right now.

    Used to avoid mocking packages that are actually installed: mocking a
    present package would hide its real class hierarchies and signatures from
    autodoc.
    """
    import importlib

    try:
        importlib.import_module(module_name)
        return True
    except Exception:  # noqa: BLE001 - any failure means "not importable"
        return False


def extract_top_level_imports(conf_path: Path) -> set[str]:
    """Extract top-level module names imported by ``conf.py`` (via AST).

    The file is parsed, not executed, so missing dependencies do not matter.
    """
    if not conf_path.exists():
        return set()
    try:
        tree = ast.parse(conf_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        logger.warning("Could not parse %s; skipping import extraction", conf_path)
        return set()

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def extract_sys_path_dirs(conf_path: Path) -> list[Path]:
    """Extract directories that ``conf.py`` adds to ``sys.path`` (AST only).

    Recognizes ``sys.path.insert(<int>, <str>)`` and ``sys.path.append(<str>)``
    where the path argument is a string literal, optionally wrapped in
    ``os.path.abspath(...)``. Relative paths are resolved against the
    ``conf.py`` directory. Only existing directories are returned.
    Deterministic: sorted, de-duplicated, no execution of ``conf.py``.
    """
    if not conf_path.exists():
        return []
    try:
        tree = ast.parse(conf_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []

    base = conf_path.parent

    def _literal_path(node: ast.expr) -> Path | None:
        """Resolve a path argument to a ``Path``, or ``None`` if not literal."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return base / node.value
        # os.path.abspath("<literal>") / os.path.abspath('<literal>')
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "abspath"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            return base / node.args[0].value
        return None

    dirs: set[Path] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr in ("insert", "append")
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "path"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "sys"
        ):
            continue
        # insert(index, path) -> path is args[1]; append(path) -> args[0].
        path_arg = (
            node.args[1]
            if func.attr == "insert" and len(node.args) >= 2
            else node.args[0]
            if func.attr == "append" and len(node.args) >= 1
            else None
        )
        if path_arg is None:
            continue
        resolved = _literal_path(path_arg)
        if resolved is not None and resolved.is_dir():
            dirs.add(resolved.resolve())
    return sorted(dirs)


def find_local_modules(names: set[str], search_dirs: list[Path]) -> set[str]:
    """Return the subset of ``names`` that resolve to local Python modules.

    A name is local when any search dir contains ``<name>.py`` (module) or
    ``<name>/__init__.py`` (package). Such modules are importable inside the
    Sphinx subprocess — ``conf.py`` puts its own directory on ``sys.path`` —
    even though :func:`_is_importable` cannot see them from the parent
    process, so they must never be stubbed or mocked. Pure path checks only:
    no imports, no side effects, deterministic.
    """
    local: set[str] = set()
    for name in names:
        for d in search_dirs:
            if not d.is_dir():
                continue
            if (d / f"{name}.py").is_file() or (d / name / "__init__.py").is_file():
                local.add(name)
                break
    return local


def extract_package_imports(src_dir: Path) -> set[str]:
    """Extract top-level module names imported by the documented package.

    Scans all ``.py`` files in sibling directories of ``src_dir`` (the docs
    folder) for ``import`` / ``from ... import`` statements via AST.  This
    discovers transitive dependencies (e.g. ``lazy_loader`` imported by
    ``librosa/__init__.py``) that are NOT in ``conf.py`` but are needed for
    autodoc to import the documented package.

    Only scans directories that look like a Python package (contain
    ``__init__.py``), limited to the parent of ``src_dir`` to avoid scanning
    the entire filesystem.
    """
    names: set[str] = set()
    parent = src_dir.parent
    if not parent.is_dir():
        return names
    for sibling in parent.iterdir():
        if not sibling.is_dir() or sibling == src_dir:
            continue
        # Only scan directories that look like a Python package.
        if not (sibling / "__init__.py").exists():
            continue
        for py_file in sibling.rglob("*.py"):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        names.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0 and node.module:
                        names.add(node.module.split(".")[0])
    return names


def extract_documented_modules(src_dir: Path) -> set[str]:
    """Parse every ``.rst`` under ``src_dir`` for documented module names.

    Uses regex (no execution) to find ``.. currentmodule:: X``,
    ``.. automodule:: X``, ``.. autoclass:: X``, ``.. autofunction:: X`` and
    ``.. autodata:: X`` directives, returning the set of *top-level* module
    names (e.g. ``{"librosa"}``). Used to decide whether the documented package
    is importable for autosummary generation and to locate its source tree.
    """
    names: set[str] = set()
    if not src_dir.is_dir():
        return names
    for rst in src_dir.rglob("*.rst"):
        try:
            text = rst.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in re.finditer(
            r"^\s*\.\.\s+"
            r"(?:currentmodule|automodule|autoclass|autofunction|autodata)"
            r"::\s*(\S+)",
            text,
            re.MULTILINE,
        ):
            names.add(m.group(1).split(".", 1)[0])
    return names


def decide_autosummary_generate(
    mode: str,
    src_dir: Path,
    documented_importable: bool | None = None,
) -> bool:
    """Decide whether autosummary should generate stub pages for this build.

    * ``"false"`` -> ``False`` (always stub tables; enriched later from source).
    * ``"true"``  -> ``True`` (imports the documented package; may crash if the
      package or a dependency is missing).
    * ``"auto"``  -> ``True`` when the documented package is importable, else
      ``False``. If ``documented_importable`` is supplied it short-circuits the
      importability probe.

    A ``bool`` is also accepted (the runtime fallback ladder passes explicit
    ``True``/``False``) and is returned as-is.
    """
    if isinstance(mode, bool):
        return mode
    if mode == "false":
        return False
    if mode == "true":
        return True
    # mode == "auto"
    if documented_importable is not None:
        return documented_importable
    return any(_is_importable(m) for m in extract_documented_modules(src_dir))


def extract_extensions_from_conf(conf_path: Path) -> list[str]:
    """Extract the ``extensions`` list from ``conf.py`` using AST."""
    if not conf_path.exists():
        return []
    try:
        tree = ast.parse(conf_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "extensions":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        return [
                            elt.value
                            for elt in node.value.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        ]
    return []


def filter_extensions(extensions: list[str]) -> list[str]:
    """Drop extensions whose name contains a denylisted fragment.

    Also drops any extension that is not importable in the current
    environment.  In lightweight mode we only keep extensions that are
    actually installed so Sphinx does not crash trying to load a missing
    third-party extension (e.g. ``pydata_sphinx_theme``, ``myst_parser``).
    """
    result: list[str] = []
    for ext in extensions:
        if any(frag in ext for frag in EXTENSION_DENYLIST):
            continue
        if not _is_importable(ext):
            logger.debug("Filtering out unimportable extension: %s", ext)
            continue
        result.append(ext)
    return result


def build_extensions_list(conf_exts: list[str], builder: str) -> list[str]:
    """Compute the merged Sphinx extension list for a build.

    Starts from the project's ``conf.py`` extensions (filtered against the
    denylist), unions the core extensions always enabled in lightweight mode,
    and appends the **vendored** direct Markdown builder
    (``rst_to_md._vendor.sphinx_markdown_builder``) when ``builder == "markdown"``.
    The builder is vendored (not a PyPI dependency) so its ``MarkdownTranslator``
    can be patched for clean autodoc formatting. Pure and trivially testable.
    """
    merged = set(filter_extensions(conf_exts)) | CORE_EXTENSIONS
    if builder == "markdown":
        # The direct Markdown builder is VENDORED into
        # `rst_to_md/_vendor/sphinx_markdown_builder` (not a PyPI dependency) so
        # its translator can be patched for clean autodoc formatting. Its
        # internal imports use the bare `sphinx_markdown_builder` package name,
        # so we register it under that name and put `rst_to_md/_vendor` on the
        # subprocess PYTHONPATH (see build_sphinx_html) to shadow any PyPI copy.
        merged.add("sphinx_markdown_builder")
    return sorted(merged)


# --------------------------------------------------------------------------- #
# Import stubbing for lightweight builds
# --------------------------------------------------------------------------- #
_SITECUSTOMIZE_TEMPLATE_RESOURCE = "sitecustomize.py.tmpl"


def _load_sitecustomize_template() -> str:
    """Load the ``sitecustomize.py`` stub template from package data.

    The template lives in ``rst_to_md/_templates/sitecustomize.py.tmpl``
    and contains a single ``__ALLOWED__`` sentinel that is replaced with
    the rendered allow-list literal at build time.  Keeping the template
    as package data (instead of a ~300-line inline string constant) keeps
    ``sphinx.py`` focused on orchestration and lets the template evolve
    without touching converter code.
    """
    from importlib import resources

    return (
        resources.files("rst_to_md._templates")
        .joinpath(_SITECUSTOMIZE_TEMPLATE_RESOURCE)
        .read_text(encoding="utf-8")
    )


def build_stub_sitecustomize(module_names: set[str], dest_dir: Path) -> Path:
    """Write a ``sitecustomize.py`` that stubs the given missing modules.

    Returns the directory containing the file (to be prepended to PYTHONPATH).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    allowed = ", ".join(repr(m) for m in sorted(module_names)) or ""
    template = _load_sitecustomize_template()
    content = template.replace("__ALLOWED__", f"{{{allowed}}}")
    sitecustomize = dest_dir / "sitecustomize.py"
    sitecustomize.write_text(content, encoding="utf-8")
    return dest_dir


# --------------------------------------------------------------------------- #
# Sphinx build
# --------------------------------------------------------------------------- #
def build_sphinx_html(
    src_dir: Path,
    build_dir: Path,
    sphinx_opts: list[str] | None = None,
    verbose: bool = False,
    lightweight: bool = True,
    stub_modules: set[str] | None = None,
    mock_all_imports: bool = False,
    builder: str = "html",
    build_workers: int = 0,
    autosummary_generate: str = AUTOSUMMARY_GENERATE_DEFAULT,
) -> bool:
    """Build Sphinx documentation.

    Returns ``True`` on success. In lightweight mode, problematic extensions
    are disabled, autodoc imports are mocked, and (when ``stub_modules`` is
    provided) missing top-level imports in ``conf.py`` are stubbed.

    When ``mock_all_imports`` is ``True`` (the degraded fallback used by
    :func:`convert_sphinx_project`), *every* top-level import from ``conf.py``
    is added to ``autodoc_mock_imports`` (not just the genuinely-missing
    ones), so autodoc skips importing them and the build can still complete —
    at the cost of possibly-empty ``Bases:`` / member content.

    ``builder`` selects the Sphinx builder (default ``"html"``); other builders
    such as ``"singlehtml"`` are supported best-effort (NTH-006).
    """
    build_dir.mkdir(parents=True, exist_ok=True)
    html_dir = build_dir / "html"

    cmd: list[str] = [
        sys.executable,
        "-m",
        "sphinx.cmd.build",
        "-b",
        builder,
        "-d",
        str(build_dir / "doctrees"),
    ]

    env = os.environ.copy()

    if lightweight:
        cmd.extend(
            [
                "-D",
                "plot_html_show_source_link=0",
                "-D",
                "plot_formats=[]",
                "-D",
                "plot_include_source=False",
                "-D",
                "nb_execution_mode=off",
                "-D",
                "ipython_exe=",
                "-D",
                "matplotlib.backend=Agg",
                # Decide autosummary content generation.  autosummary's
                # generate step (process_generate_options at builder-inited)
                # imports the *actual* documented package to discover its
                # members.  If the package or any transitive dependency is
                # missing (e.g. librosa needs lazy_loader) the build crashes
                # before any output is produced.  autodoc_mock_imports does
                # NOT help because autosummary uses its own import path
                # (import_by_name -> _import_module) that bypasses the mock.
                # We therefore only enable generation when the documented
                # package is actually importable ("auto" probes that); otherwise
                # it stays False and autosummary renders stub tables that are
                # enriched from source after the build.  A literal "true"
                # forces generation (may crash if the package is missing); a
                # literal "false" always stubs.
                "-D",
                f"autosummary_generate={str(decide_autosummary_generate(autosummary_generate, src_dir))}",
            ]
        )

    # Extension list: compute it whenever we must inject (the direct Markdown
    # builder, or lightweight stubbing). In plain non-lightweight HTML mode we
    # leave the project's own conf.py extensions untouched.
    if builder == "markdown" or stub_modules is not None:
        conf_exts = extract_extensions_from_conf(src_dir / "conf.py")
        merged = build_extensions_list(conf_exts, builder)
        cmd.extend(["-D", "extensions=" + ",".join(merged)])

    if builder == "markdown":
        # Direct Markdown build: make internal cross-references point to .md
        # (not .html) and suppress the optional docinfo metadata block.
        cmd.extend(["-D", "markdown_uri_doc_suffix=.md"])
        cmd.extend(["-D", "markdown_docinfo=0"])
        # The `sphinx_markdown_builder` extension is VENDORED under
        # `rst_to_md/_vendor` (not a PyPI dependency) so its translator can be
        # patched. Its internal imports use the bare `sphinx_markdown_builder`
        # package name, so we prepend `rst_to_md/_vendor` to PYTHONPATH for the
        # sphinx-build subprocess, shadowing any PyPI install and ensuring the
        # patched copy is the one loaded.
        vendor_dir = Path(__file__).resolve().parent.parent / "_vendor"
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{vendor_dir}{os.pathsep}{existing}" if existing else str(vendor_dir)

    if stub_modules is not None:
        # Only stub modules that are genuinely missing. If a package is
        # actually importable we must NOT mock it, otherwise autodoc cannot
        # resolve real class hierarchies (the ``Bases:`` inheritance list)
        # or member signatures — the very content the user wants to keep.
        # The ``mock_all_imports`` fallback (used by convert_sphinx_project's
        # retry) overrides this so autodoc mocks EVERY top-level import,
        # trading fidelity for a build that completes.
        #
        # Local modules (files/packages inside the source dir, or in dirs that
        # conf.py adds to sys.path) are importable in the Sphinx subprocess
        # even though _is_importable() cannot see them from this process.
        # Stubbing them shadows the real file (sys.modules wins) and, when
        # conf.py registers their classes as docutils directives, docutils
        # crashes with: TypeError: '<' not supported between instances of
        # 'int' and '_DummyModule' (torchaudio custom_directives failure).
        # They must also stay out of autodoc_mock_imports for the same reason.
        conf_path = src_dir / "conf.py"
        search_dirs = [src_dir, *extract_sys_path_dirs(conf_path)]
        local = find_local_modules(stub_modules, search_dirs)
        missing = {m for m in stub_modules if not _is_importable(m)} - local
        mock_set = (stub_modules if mock_all_imports else missing) - local
        if mock_set:
            cmd.extend(["-D", "autodoc_mock_imports=" + ",".join(sorted(mock_set))])
        # Always install the robustness sitecustomize. It patches
        # napoleon's autodoc-skip-member handler to be exception-safe (some
        # third-party objects, e.g. pydantic models, raise on attribute
        # access during member gathering and would otherwise abort the whole
        # build) and stubs the missing modules above. This must run even when
        # stub_modules is empty, otherwise importable packages (e.g. aiogram)
        # would crash the build with no protection.
        stub_dir = build_stub_sitecustomize(missing, build_dir / "_stubs")
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{stub_dir}{os.pathsep}{existing}" if existing else str(stub_dir)

    # Filter out plot/gallery/example/ipython options from user opts.
    if sphinx_opts:
        filtered: list[str] = []
        skip_next = False
        for opt in sphinx_opts:
            if skip_next:
                skip_next = False
                continue
            if opt.startswith("-D") and any(
                k in opt for k in ("plot", "ipython", "gallery", "example")
            ):
                skip_next = True
                continue
            filtered.append(opt)
        cmd.extend(filtered)

    # Parallel build: -j N makes Sphinx read documents across N cores instead
    # of one, removing the single-core bottleneck for large doc sets. 0 => auto
    # (CPU count); 1 => serial. The IMP-001 fallback retry passes build_workers=1
    # so a parallel-incompatible extension still completes serially.
    if build_workers != 1:
        _n = build_workers if build_workers > 1 else (os.cpu_count() or 1)
        if _n > 1:
            cmd.extend(["-j", str(_n)])

    cmd.extend([str(src_dir), str(html_dir)])

    if verbose:
        logger.info("Running: %s", " ".join(cmd))

    _t0 = time.perf_counter()
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=not verbose,
            text=True,
            env=env,
        )
        _elapsed = time.perf_counter() - _t0
        if verbose:
            _cpus = os.cpu_count() or 1
            _j = next((cmd[i + 1] for i, a in enumerate(cmd) if a == "-j"), None)
            logger.info(
                "[DIAG] Sphinx build took %.1fs (build_workers=%s, total_cores=%d).",
                _elapsed,
                _j or 1,
                _cpus,
            )
        return True
    except subprocess.CalledProcessError as exc:
        logger.error("[ERR] Sphinx build failed:")
        if exc.stdout:
            logger.error(exc.stdout)
        if exc.stderr:
            logger.error(exc.stderr)
        raise SphinxBuildError(str(exc)) from exc


# --------------------------------------------------------------------------- #
# HTML -> Markdown
# --------------------------------------------------------------------------- #
def _html_to_markdown(html_content: str, wrap: str, md_path: Path) -> str:
    """Convert HTML text to Markdown, preferring ``html_to_markdown``."""
    html_convert: Callable[..., object] | None = None
    try:
        from html_to_markdown import convert as _html_convert

        html_convert = _html_convert
    except ImportError:
        html_convert = None

    if html_convert is not None:
        raw = html_convert(html_content)
        # The return type varies across html_to_markdown versions:
        #  * older versions return a plain ``str``
        #  * some return a ``dict`` with a "content" key
        #  * >=3.x returns a ``ConversionResult`` with a ``.content`` attribute
        # Normalise all of these to a markdown string.
        if isinstance(raw, str):
            return raw
        if hasattr(raw, "content"):
            content = raw.content
            return content if isinstance(content, str) else str(content)
        if isinstance(raw, dict):
            return raw.get("content", "")
        return str(raw)

    # Fallback to pandoc.
    import pypandoc

    return pypandoc.convert_text(
        html_content,
        "gfm",
        format="html",
        extra_args=[
            f"--wrap={wrap}",
            "--standalone",
            "--extract-media",
            str(md_path.parent / "media"),
        ],
    )


def convert_html_to_md(
    html_path: Path,
    md_path: Path,
    wrap: str = "none",
    strip_chrome: bool = True,
    errors: list[str] | None = None,
    show_progress: bool = False,
    source_map: dict | None = None,
    src_rst: Path | None = None,
    output_dir: Path | None = None,
) -> bool:
    """Convert a single HTML file to Markdown. Returns ``True`` on success.

    When ``strip_chrome`` is ``True`` (default) the Sphinx/theme navigation
    chrome (sidebar TOC, footer, "On this page" TOC, ...) is removed *before*
    conversion by extracting the document body (``<main>`` / ``<article>``) and
    normalizing autodoc markup, so the output contains only the documentation
    body (including autoclass/autofunction content such as class signatures,
    the ``Bases:`` inheritance list, members and parameter fields).

    After the shared post-processing, when ``source_map`` is provided the
    autosummary tables are enriched from source (:func:`enrich_file`) so empty
    stub cells gain signatures and summaries without importing the documented
    package. The ``generated/`` stub pages are NOT written here — the project
    converter writes them exactly once, outside the parallel loop (IMP-007).
    """
    try:
        html_content = html_path.read_text(encoding="utf-8", errors="ignore")
        # Chrome removal + autodoc repair happen on the HTML, which is far more
        # robust than regex post-processing on the final Markdown.
        if strip_chrome:
            html_content = clean_sphinx_html(html_content)
        else:
            # Even with chrome kept we still repair autodoc markup (e.g. keep
            # signature parameters as code spans instead of emphasis).
            html_content = normalize_autodoc_html(html_content)
        md_content = _html_to_markdown(html_content, wrap, md_path)
        if strip_chrome:
            md_content = strip_sphinx_chrome(md_content)
        md_content = post_process_markdown(md_content, strip_footer=strip_chrome)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")
        if source_map:
            # IMP-007: tables only — generated/ stubs are written once by
            # convert_sphinx_project, outside the parallel loop.
            enrich_file(md_path, src_rst, source_map, output_dir=output_dir, write_stubs=False)
        return True
    except Exception as exc:  # noqa: BLE001 - conversion failures are non-fatal
        if not show_progress:
            logger.error("[ERR] Error converting %s: %s", html_path, exc)
        if errors is not None:
            errors.append(f"{html_path}: {exc}")
        return False


def convert_built_md(
    md_path: Path,
    out_path: Path,
    strip_footer: bool = True,
    errors: list[str] | None = None,
    show_progress: bool = False,
    source_map: dict | None = None,
    src_rst: Path | None = None,
    output_dir: Path | None = None,
) -> bool:
    """Post-process a Markdown file already produced by a Sphinx build.

    Used by the direct Markdown builder path (``-b markdown``): the Sphinx
    ``sphinx_markdown_builder`` extension emits ``.md`` directly from the
    doctree, so there is no HTML stage, no chrome stripping and no
    HTML→Markdown conversion. We only run the shared deterministic
    :func:`post_process_markdown` cleanup (footer/media/link/blank-line
    normalization). Returns ``True`` on success, ``False`` on failure (the
    error is logged and, when ``errors`` is provided, appended for reporting).

    When ``source_map`` is provided, the autosummary tables are enriched from
    source (:func:`enrich_file`) so empty stub cells gain signatures and
    summaries without importing the documented package. The ``generated/``
    stub pages are NOT written here — the project converter writes them
    exactly once, outside the parallel loop (IMP-007).
    """
    try:
        content = md_path.read_text(encoding="utf-8")
        content = post_process_markdown(content, strip_footer=strip_footer)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        if not show_progress:
            logger.info("[OK] %s -> %s", md_path, out_path)
        if source_map:
            # IMP-007: tables only — generated/ stubs are written once by
            # convert_sphinx_project, outside the parallel loop.
            enrich_file(out_path, src_rst, source_map, output_dir=output_dir, write_stubs=False)
        return True
    except Exception as exc:  # noqa: BLE001 - conversion failures are non-fatal
        if not show_progress:
            logger.error("[ERR] Error post-processing %s: %s", md_path, exc)
        if errors is not None:
            errors.append(f"{md_path}: {exc}")
        return False


# --------------------------------------------------------------------------- #
# Asset handling
# --------------------------------------------------------------------------- #
def copy_assets(html_dir: Path, output_dir: Path) -> None:
    """Copy static assets (images, css) from the Sphinx build to output."""
    for asset_dir in ("_images", "_static"):
        src = html_dir / asset_dir
        dst = output_dir / asset_dir
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst, dirs_exist_ok=True)


# --------------------------------------------------------------------------- #
# Top-level project conversion
# --------------------------------------------------------------------------- #
def convert_sphinx_project(
    src_dir: Path,
    output_dir: Path,
    wrap: str = "none",
    sphinx_opts: list[str] | None = None,
    verbose: bool = False,
    clean_build: bool = True,
    lightweight: bool = True,
    strip_chrome: bool = True,
    use_cache: bool = True,
    max_workers: int | None = None,
    report_path: Path | None = None,
    dry_run: bool = False,
    builder: str = "html",
    show_progress: bool | None = None,
    build_workers: int = 0,
    autosummary_generate: str = AUTOSUMMARY_GENERATE_DEFAULT,
) -> tuple[int, int, int]:
    """Convert an entire Sphinx project to Markdown.

    Returns ``(success_count, error_count, skipped_count)``.

    When ``strip_chrome`` is ``True`` (default) Sphinx/theme navigation chrome
    is removed from every output file (see :func:`strip_sphinx_chrome`).

    If the lightweight build crashes in a way the napoleon patch does not
    catch, the build is retried **once** with every top-level import from
    ``conf.py`` mocked (``autodoc_mock_imports`` = all imports). This degraded
    fallback guarantees *some* Markdown is produced instead of zero output for
    the whole project; the trade-off is that mocked modules may yield empty
    ``Bases:`` / member content. If the retry also fails, ``(0, 1, 0)`` is
    returned.

    Additional features (see docs/plans/2026-07-13-nice-to-have-issues-plan.md):
      * ``use_cache`` — skip a ``.md`` whose source HTML is not newer (NTH-001).
      * ``max_workers`` — convert HTML files in parallel (NTH-002).
      * ``report_path`` — write a JSON summary + per-file results (NTH-003).
      * ``dry_run`` — list planned source docs without building (NTH-004).
       * ``builder`` — select the Sphinx builder (NTH-006, default ``"markdown"``).
       * ``build_workers`` — parallel Sphinx build workers (``-j N``); 0 = auto
         (CPU count), 1 = serial. This parallelizes the *build* itself (the
         dominant cost), unlike ``max_workers`` which only parallelizes the
         post-build conversion.
      * ``show_progress`` — live progress bar on TTY (auto when ``None``).

    Autosummary ``generated/`` stub pages are written exactly once, in the
    single-threaded section right after the source map is built and before the
    (possibly parallel) per-file conversion loop, so concurrent workers never
    race on the same paths (IMP-007).
    """
    show_progress = bool(show_progress)
    if not is_sphinx_project(src_dir):
        logger.error("[ERR] %s is not a Sphinx project (missing conf.py)", src_dir)
        return 0, 0, 0

    build_dir = output_dir / "_sphinx_build"
    if lightweight:
        # Merge conf.py imports with imports from the documented package
        # source (sibling directories).  This discovers transitive deps
        # (e.g. lazy_loader imported by librosa/__init__.py) that conf.py
        # does not import but autodoc needs to import the documented package.
        stub_modules = extract_top_level_imports(src_dir / "conf.py") | (
            extract_package_imports(src_dir)
        )
    else:
        stub_modules = None

    if verbose:
        logger.info("Building Sphinx documentation from %s", src_dir)
        logger.info("Build directory: %s", build_dir)

    # NTH-004: preview only — list planned source docs, build nothing.
    if dry_run:
        planned = 0
        for src in sorted(src_dir.rglob("*.rst")):
            rel = src.relative_to(src_dir)
            if rel.parent.name in SKIP_DIRS:
                continue
            if any(frag in part for part in map(str, rel.parts) for frag in SKIP_PATH_FRAGMENTS):
                continue
            md_path = output_dir / rel.with_suffix(".md")
            logger.info("Would convert: %s -> %s", src, md_path)
            planned += 1
        return planned, 0, 0

    if show_progress is not False and not verbose:
        logger.info("Building Sphinx %s (this may take a while)...", builder)

    _t_build0 = time.perf_counter()

    # Build the autosummary-generation fallback ladder. The intent is to produce
    # *real* autosummary tables whenever the documented package is importable,
    # and otherwise fall back to stub tables that are enriched from source after
    # the build (WS2 / WS4). We vary two dimensions:
    #   * autosummary_generate (True imports the package; False stubs), and
    #   * mock_all_imports (mock every top-level import, not just missing ones).
    # The ladder is (IMP-001 retry preserved):
    #   1. auto-decision (importable? True : False) / explicit value, mocking
    #      only the genuinely-missing imports;
    #   2. generate=False (stub tables) with ALL imports mocked — the degraded
    #      path that always completes.
    # A literal "false" always stubs (generate=False) on both rungs.
    if autosummary_generate == "false":
        _generate_ladder = [(False, False), (False, True)]
    else:
        _gen = decide_autosummary_generate(autosummary_generate, src_dir)
        _generate_ladder = [(_gen, False), (False, True)]

    built = False
    for _attempt, (_gen, _mock_all) in enumerate(_generate_ladder):
        try:
            build_sphinx_html(
                src_dir,
                build_dir,
                sphinx_opts,
                verbose,
                lightweight,
                stub_modules,
                mock_all_imports=_mock_all,
                builder=builder,
                build_workers=(build_workers if _attempt == 0 else 1),
                autosummary_generate=str(_gen),
            )
            built = True
            if verbose:
                logger.info(
                    "[DIAG] Build phase: %.1fs (parallel build workers=%s, "
                    "autosummary_generate=%s).",
                    time.perf_counter() - _t_build0,
                    build_workers or "auto",
                    _gen,
                )
            break
        except SphinxBuildError:
            # IMP-001 + WS2: escalate the fallback ladder. Warn on the first
            # escalation so the degraded path is visible; keep trying the next
            # rung, which may still complete and yield (possibly stub) output.
            if _attempt == 0:
                logger.warning(
                    "Sphinx build failed; retrying once with all imports mocked "
                    "(output may be incomplete)."
                )
            elif _attempt == 1:
                logger.warning(
                    "Sphinx build still failed; retrying with stub autosummary "
                    "tables (output may be incomplete)."
                )
            continue
    if not built:
        # Every rung of the ladder failed: signal failure via the error count.
        return 0, 1, 0

    # Build a source map (AST, no import) for autosummary enrichment + stub
    # pages. Cheap: it only parses the documented package's source tree.
    _documented = extract_documented_modules(src_dir)
    _roots = find_source_roots(src_dir, _documented)
    source_map: dict = build_source_map(_roots) if _roots else {}

    # IMP-007: write the generated/ autosummary stub pages exactly ONCE, here
    # in the single-threaded section, before the (possibly parallel) per-file
    # loop. Per-file enrich_file calls only fill tables (write_stubs=False),
    # so concurrent workers can no longer race on the same generated/*.md
    # paths, and the work is not duplicated N times. Writing before the loop
    # also guarantees the stubs exist even when every file is a cache hit.
    if source_map:
        write_generated_stubs(output_dir, source_map)

    is_md = builder == "markdown"
    html_dir = build_dir / "html"
    html_files = sorted(html_dir.rglob("*.md" if is_md else "*.html"))

    if verbose:
        logger.info("Found %d HTML files to convert", len(html_files))

    file_results: list[dict] = []
    success_count = error_count = skipped_count = 0

    def _convert_one(html_file: Path) -> tuple[str, str]:
        """Convert one HTML file; return (status, error_message)."""
        if html_file.stem in SKIP_STEMS:
            return "skipped", ""
        if html_file.parent.name in SKIP_DIRS:
            return "skipped", ""
        if any(frag in part for part in map(str, html_file.parts) for frag in SKIP_PATH_FRAGMENTS):
            return "skipped", ""
        rel_path = html_file.relative_to(html_dir)
        md_path = output_dir / rel_path.with_suffix(".md")
        # NTH-001: skip if the existing output is up to date relative to the
        # original .rst source. The generated .html is always rewritten by the
        # build, so comparing against it would never skip.
        source_for_cache = src_dir / rel_path.with_suffix(".rst")
        if not source_for_cache.exists():
            source_for_cache = html_file
        if use_cache and is_up_to_date(source_for_cache, md_path):
            return "skipped", ""
        errs: list[str] = []
        # Paired RST source (same relative path) used to recover the page's
        # module context for autosummary enrichment.
        src_rst = src_dir / rel_path.with_suffix(".rst")
        if is_md:
            # Direct Markdown builder: the file is already Markdown, so we only
            # run the shared post-processing cleanup (no HTML stage). When a
            # source map exists, autosummary tables are enriched from it.
            ok = convert_built_md(
                html_file,
                md_path,
                strip_footer=strip_chrome,
                errors=errs,
                show_progress=show_progress,
                source_map=source_map or None,
                src_rst=src_rst if src_rst.exists() else None,
                output_dir=output_dir,
            )
        else:
            ok = convert_html_to_md(
                html_file,
                md_path,
                wrap,
                strip_chrome=strip_chrome,
                errors=errs,
                show_progress=show_progress,
                source_map=source_map or None,
                src_rst=src_rst if src_rst.exists() else None,
                output_dir=output_dir,
            )
        if ok:
            return "ok", ""
        return "error", (errs[0] if errs else "unknown error")

    def _record(html_file: Path, status: str, msg: str) -> None:
        nonlocal success_count, error_count, skipped_count
        file_results.append({"path": str(html_file), "status": status, "error": msg})
        if status == "ok":
            success_count += 1
        elif status == "error":
            error_count += 1
        else:  # skipped (system file or cache hit)
            skipped_count += 1

    tracker = ProgressTracker(
        total=len(html_files),
        enabled=show_progress,
        desc="Converting MD" if is_md else "Converting HTML",
    )
    tracker.start()

    # NTH-002: parallel path. Distinct output paths => no write races.
    # as_completed drives the progress bar live as each file finishes.
    if max_workers not in (None, 1):
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_convert_one, hf): hf for hf in html_files}
            for fut in as_completed(futures):
                html_file = futures[fut]
                status, msg = fut.result()
                _record(html_file, status, msg)
                tracker.update(status, msg)
    else:
        for html_file in html_files:
            status, msg = _convert_one(html_file)
            _record(html_file, status, msg)
            tracker.update(status, msg)

    tracker.finish()

    # In lightweight mode media references are stripped, so copying assets
    # would only create orphans; only copy when not lightweight.
    if not lightweight:
        copy_assets(html_dir, output_dir)

    if clean_build:
        shutil.rmtree(build_dir, ignore_errors=True)
        if verbose:
            logger.info("Cleaned up build directory %s", build_dir)

    # NTH-003: emit a machine-readable report if requested.
    if report_path is not None:
        report = {
            "summary": {
                "success": success_count,
                "errors": error_count,
                "skipped": skipped_count,
            },
            "files": file_results,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return success_count, error_count, skipped_count
