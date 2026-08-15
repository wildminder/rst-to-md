"""Extract member signatures and docstring summaries from package source (AST).

This module builds a map from fully-qualified object name (e.g.
``librosa.beat.beat_track``) to a small :class:`ObjectInfo` record that holds the
autosummary-style signature and the first docstring sentence. It uses **only**
``ast`` parsing — the documented package is never imported — so it works in the
tool's lightweight mode where the documented package (e.g. ``librosa``) is not
installed.

The map is consumed by
:mod:`rst_to_md.core.autosummary_enrich` to populate otherwise-empty autosummary
table cells and by ``write_generated_stubs`` to emit stub pages.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("rst_to_md")


@dataclass(frozen=True)
class ObjectInfo:
    """Information about a single documented object extracted from source.

    Attributes:
        fqn: Fully-qualified name, e.g. ``librosa.beat.beat_track``.
        kind: ``"function"`` | ``"class"`` | ``"method"``.
        signature: Autosummary-style signature, e.g. ``"(*[, y, sr, ...])"``.
        summary: First sentence of the docstring (``""`` if none).
        full_docstring: Whole docstring (``""`` if none).
        lineno: Line number of the object definition in its source file.
    """

    fqn: str
    kind: str
    signature: str
    summary: str
    full_docstring: str
    lineno: int


def _render_default(node: ast.AST) -> str:
    """Render a default-value AST node back to source text.

    Uses :func:`ast.unparse` when available (deterministic); falls back to a
    stable placeholder on any failure so the function never raises.
    """
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001 - many node shapes; never crash the map
        return "..."


def format_autosummary_signature(args: ast.arguments) -> str:
    """Render an autosummary-style signature from an ``ast.arguments`` node.

    Replicates the ``(*[, a, b, ...])`` all-optional form used by autosummary
    when a function has no required positional-or-keyword parameters, and the
    ``(a, b=1)`` form otherwise:

    * all-optional (every positional-or-keyword argument has a default, plus any
      keyword-only arguments) -> ``(*[, a, b])`` (names only, no ``=default``);
    * mixed required + optional -> ``(a, b=1)`` (required bare, optional as
      ``name=default``);
    * ``*args`` / ``**kwargs`` are rendered verbatim.
    """
    # Positional-only + positional-or-keyword arguments, in order.
    posargs: list[ast.arg] = list(getattr(args, "posonlyargs", [])) + list(args.args)
    defaults: list[ast.expr] = list(args.defaults)
    n_defaults = len(defaults)
    split = len(posargs) - n_defaults
    required = posargs[:split]
    optional = posargs[split:]

    kwonly: list[ast.arg] = list(args.kwonlyargs)
    kw_defaults: list[ast.expr | None] = list(args.kw_defaults)

    if not required and args.vararg is None and args.kwarg is None:
        # All-optional form (no required positional-or-keyword params and no
        # *args/**kwargs): list names only (matching autosummary's
        # ``(*[, a, b])`` shape). Keyword-only names are included bare too.
        names: list[str] = [a.arg for a in optional]
        names += [a.arg for a in kwonly]
        return "(*[, " + ", ".join(names) + "])"

    # Mixed form: required bare, optional as name=default.
    parts: list[str] = [a.arg for a in required]
    for a in optional:
        parts.append(f"{a.arg}={_render_default(defaults.pop(0))}")
    if args.vararg is not None:
        parts.append(f"*{args.vararg.arg}")
    for a, dflt in zip(kwonly, kw_defaults, strict=True):
        if dflt is None:
            parts.append(a.arg)
        else:
            parts.append(f"{a.arg}={_render_default(dflt)}")
    if args.kwarg is not None:
        parts.append(f"**{args.kwarg.arg}")
    return "(" + ", ".join(parts) + ")"


def _first_sentence(docstring: str) -> str:
    """Return the first sentence of ``docstring`` (whitespace-normalized).

    A sentence ends at the first ``". "`` (period + space) or at the end of the
    string. The trailing period is kept so summaries read naturally.
    """
    text = " ".join(docstring.split())
    idx = text.find(". ")
    if idx == -1:
        return text.strip()
    return text[: idx + 1].strip()


def _module_fqn_for(py_file: Path, root: Path) -> str | None:
    """Compute the module fqn for ``py_file`` relative to package root ``root``.

    ``root/librosa/beat.py`` -> ``librosa.beat``; ``root/librosa/__init__.py``
    -> ``librosa``; ``root/foo.py`` -> ``foo``.
    """
    try:
        rel = py_file.relative_to(root)
    except ValueError:
        return None
    parts = list(rel.with_suffix("").parts)
    if not parts:
        return None
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _should_skip(name: str) -> bool:
    """Skip dunder/private members.

    ``__init__`` is kept (its signature is the class initializer); every other
    name beginning with ``_`` (``__str__``, ``_helper``, ``__private``) is
    skipped. Public names are kept.
    """
    return name.startswith("_") and name != "__init__"


def build_source_map(source_roots: list[Path]) -> dict[str, ObjectInfo]:
    """Build a ``fqn -> ObjectInfo`` map by AST-parsing every ``.py`` file.

    Scans each root (recursively) for Python source. Records module-level
    functions/classes and class methods (including ``__init__``). Parse errors
    and undecodable files are skipped (never raised), so a single broken file
    does not abort the whole map.
    """
    source_map: dict[str, ObjectInfo] = {}
    for root in source_roots:
        if not root.is_dir():
            continue
        for py_file in sorted(root.rglob("*.py")):
            module_fqn = _module_fqn_for(py_file, root)
            if not module_fqn:
                # A root that IS a package directory scanned directly yields an
                # empty fqn for its __init__.py; skip to avoid bogus keys.
                continue
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                logger.debug("Skipping unparsable source file: %s", py_file)
                continue

            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if _should_skip(node.name):
                        continue
                    source_map[_join(module_fqn, node.name)] = _info_from_function(
                        _join(module_fqn, node.name), node
                    )
                elif isinstance(node, ast.ClassDef):
                    if _should_skip(node.name):
                        continue
                    source_map[_join(module_fqn, node.name)] = _info_from_class(
                        _join(module_fqn, node.name), node
                    )
                    # Methods (incl. __init__) nested directly in the class.
                    for child in node.body:
                        if isinstance(
                            child, (ast.FunctionDef, ast.AsyncFunctionDef)
                        ) and not _should_skip(child.name):
                            method_fqn = _join(module_fqn, node.name, child.name)
                            source_map[method_fqn] = _info_from_function(
                                method_fqn, child, kind="method"
                            )
    return source_map


def _join(*parts: str) -> str:
    return ".".join(p for p in parts if p)


def _info_from_function(
    fqn: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    kind: str = "function",
) -> ObjectInfo:
    func = node  # type: ignore[assignment]
    doc = ast.get_docstring(func) or ""
    sig = format_autosummary_signature(func.args) if hasattr(func, "args") else "()"
    return ObjectInfo(
        fqn=fqn,
        kind=kind,
        signature=sig,
        summary=_first_sentence(doc),
        full_docstring=doc,
        lineno=getattr(func, "lineno", 0),
    )


def _info_from_class(fqn: str, node: ast.ClassDef) -> ObjectInfo:
    doc = ast.get_docstring(node) or ""
    # Use __init__'s signature when present so the class row shows its
    # constructor signature (matching autosummary's class-table behavior).
    signature = "()"
    for child in node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
            child.name == "__init__"
        ):
            signature = format_autosummary_signature(child.args)
            break
    return ObjectInfo(
        fqn=fqn,
        kind="class",
        signature=signature,
        summary=_first_sentence(doc),
        full_docstring=doc,
        lineno=node.lineno,
    )


def _find_package_root(start: Path, mod: str) -> Path | None:
    """Return the directory ``D`` such that ``D/mod`` is a package/module.

    Walks upward from ``start`` (bounded) looking for ``D/mod/__init__.py`` or
    ``D/mod.py``. This is the directory that, when used as a scan root, makes
    AST fqns keep the documented module name (``librosa.beat`` rather than just
    ``beat``).
    """
    d = start
    for _ in range(6):
        if (d / mod / "__init__.py").is_file() or (d / (mod + ".py")).is_file():
            return d
        parent = d.parent
        if parent == d:
            break
        d = parent
    return None


def find_source_roots(src_dir: Path, documented_modules: set[str]) -> list[Path]:
    """Return candidate directories to scan for the documented package source.

    The documented package is typically *not* installed, so we discover its
    source tree without importing it:

    * ``src_dir`` itself (covers a package living *inside* the docs tree, e.g.
      the ``sample_pkg`` test fixture at ``sphinx_md/sample_pkg``);
    * for each documented top-level module, the directory ``D`` that directly
      contains the package (``D/mod/__init__.py`` or ``D/mod.py``), found by
      walking up from ``src_dir``'s parent. This yields correct fqns even when
      the package lives beside ``src_dir`` (e.g. ``librosa`` beside
      ``librosa/docs`` in production) — the key is that ``D`` is the package's
      parent, so scanning it produces ``librosa.beat`` not just ``beat``.

    Results are de-duplicated, only existing directories are kept, and the list
    is sorted for deterministic ordering.
    """
    roots: set[Path] = {src_dir}
    for mod in documented_modules:
        pkg_root = _find_package_root(src_dir.parent, mod)
        if pkg_root is not None:
            roots.add(pkg_root)
    return sorted(r for r in roots if r.is_dir())
