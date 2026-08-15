"""Enrich empty autosummary tables from package source (no import needed).

These functions are pure post-processors that operate on *already-built*
Markdown (the same shape for both the ``markdown`` and ``html`` Sphinx
builders). They fill stub autosummary table rows — a name with an empty
description/signature cell — using a :class:`~rst_to_md.core.source_extract.ObjectInfo`
map built by AST-parsing the documented package's source tree. They also emit
``generated/<fqn>.md`` stub pages so the rewritten table links resolve.

Everything here is import-free (the documented package is never imported) and
deterministic, so it is trivially unit-testable and safe to re-run.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..config import AUTOSUMMARY_LINK_PREFIX, GENERATED_DIR_NAME
from .source_extract import ObjectInfo, build_source_map, find_source_roots

# A table-cell first column holding a backtick-wrapped identifier, e.g.
# `` `beat_track` `` (the markdown-builder stub form).
_NAME_BACKTICK_RE = re.compile(r"^`([^`]+)`")
# A table-cell first column holding a link, e.g. `` [beat_track](generated/...) ``
# (the html-builder / already-linked form).
_NAME_LINK_RE = re.compile(r"^\[([^\]]+)\]\(([^)]+)\)")

# RST directives that name a module/object; used to recover the module context
# of an output page so bare autosummary names can be resolved to fqns.
_MODULE_CTX_RE = re.compile(
    r"^\s*\.\.\s+"
    r"(currentmodule|automodule|autoclass|autofunction|autodata)::\s*(\S+)"
)


def extract_module_context(rst_path) -> str | None:
    """Return the module fqn for the page paired with ``rst_path``.

    Parses the RST (regex, not execution) for the last ``.. currentmodule:: X``
    directive and any ``.. automodule:: X`` / ``.. autoclass/autofunction:: X``
    directive. The last ``currentmodule`` wins; other directives only supply a
    fallback. Returns ``None`` when no directive is present (callers then treat
    bare autosummary names as top-level fqns).
    """
    p = Path(rst_path) if rst_path else None
    if p is None or not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    return _module_from_rst(text)


def _module_from_rst(text: str) -> str | None:
    module: str | None = None
    for line in text.splitlines():
        m = _MODULE_CTX_RE.match(line)
        if not m:
            continue
        kind = m.group(1)
        name = m.group(2)
        if kind == "currentmodule":
            # The last currentmodule wins (explicit page context).
            module = name
        elif kind == "automodule":
            # automodule names the module directly — it IS the context.
            module = name
        elif module is None:
            # autoclass/autofunction/autodata name a member, so use the parent
            # module as the context for bare autosummary names.
            module = name.rsplit(".", 1)[0] if "." in name else name
    return module


def enrich_autosummary_table(
    md_text: str,
    module_fqn: str | None,
    source_map: dict[str, ObjectInfo],
    link_prefix: str = AUTOSUMMARY_LINK_PREFIX,
) -> str:
    """Fill empty autosummary table cells from ``source_map``.

    For every Markdown table row whose first cell is a backtick-wrapped name
    (`` `name` ``) or a link (`` [name](generated/...) ``) and whose second cell
    is empty (a stub row), look up the member's fqn (``module_fqn + "." + name``,
    or the link target's stem) and, if present in ``source_map``, rewrite the
    first cell to a link with the autosummary signature and set the second cell
    to the docstring summary.

    Rows that are already populated, that name an unknown member, or that are
    ordinary data tables are left unchanged. The function is idempotent: on a
    second pass the second cells are non-empty, so nothing changes.
    """
    lines = md_text.split("\n")
    out: list[str] = []
    for line in lines:
        new_line = _enrich_row(line, module_fqn, source_map, link_prefix)
        out.append(new_line if new_line is not None else line)
    return "\n".join(out)


def _parse_name_cell(cell: str, link_prefix: str):
    """Return ``(bare_name, is_link, target)`` or ``None`` for a first cell."""
    m = _NAME_BACKTICK_RE.match(cell)
    if m:
        return (m.group(1).strip(), False, None)
    m = _NAME_LINK_RE.match(cell)
    if m:
        return (m.group(1).strip(), True, m.group(2).strip())
    return None


def _fqn_from_link(target: str, link_prefix: str, bare: str, module_fqn: str | None) -> str:
    stem = target.split("#", 1)[0]
    if stem.endswith(".md"):
        stem = stem[: -len(".md")]
    if stem.startswith(link_prefix):
        stem = stem[len(link_prefix) :]
    if stem:
        return stem
    return (module_fqn + "." + bare) if module_fqn else bare


def _enrich_row(
    line: str,
    module_fqn: str | None,
    source_map: dict[str, ObjectInfo],
    link_prefix: str,
) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    cells = line.split("|")
    # Drop the empty fragments produced by the outer ``|`` delimiters.
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    if len(cells) < 2:
        return None

    cell1 = cells[0].strip()
    cell2 = cells[1].strip()

    parsed = _parse_name_cell(cell1, link_prefix)
    if parsed is None:
        return None
    bare, is_link, target = parsed

    if is_link and target:
        fqn = _fqn_from_link(target, link_prefix, bare, module_fqn)
    else:
        fqn = (module_fqn + "." + bare) if module_fqn else bare

    if fqn not in source_map:
        return None
    # Already populated -> idempotent no-op (and the normal-data-table guard).
    if cell2 != "":
        return None

    info = source_map[fqn]
    cells[0] = f'[`{bare}`]({link_prefix}{fqn}.md#{fqn} "{fqn}"){info.signature}'
    cells[1] = info.summary
    return "|" + "|".join(f" {c} " for c in cells) + "|"


def write_generated_stubs(base_dir, source_map: dict[str, ObjectInfo]) -> list[Path]:
    """Write ``<base_dir>/generated/<fqn>.md`` stub pages for every member.

    Each stub page begins with ``# <fqn>`` (the in-page anchor the enriched
    table links target, ``generated/<fqn>.md#<fqn>``), followed by the signature
    and full docstring. Writes are deterministic (sorted by fqn, idempotent
    overwrite) and confined to the ``generated/`` subdirectory. Returns the list
    of written file paths.
    """
    gen_dir = Path(base_dir) / GENERATED_DIR_NAME
    gen_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for fqn in sorted(source_map):
        info = source_map[fqn]
        page = gen_dir / (fqn + ".md")
        page.write_text(_generated_stub_content(fqn, info), encoding="utf-8")
        written.append(page)
    return written


def _generated_stub_content(fqn: str, info: ObjectInfo) -> str:
    lines = [f"# {fqn}", "", f"`{info.signature}`", ""]
    if info.full_docstring:
        lines.append(info.full_docstring)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def enrich_file(
    md_path,
    src_rst,
    source_map: dict[str, ObjectInfo],
    output_dir=None,
) -> str:
    """Enrich one built Markdown file's autosummary tables and write stubs.

    Reads ``md_path``, derives the page's module context from the paired
    ``src_rst`` (same relative path, ``.rst`` extension), fills any empty
    autosummary cells, rewrites the file, and writes the ``generated/`` stub
    pages next to the markdown file so the rewritten links resolve. When
    ``source_map`` is empty this is a deterministic passthrough. Returns the new
    text.
    """
    md_path = Path(md_path)
    text = md_path.read_text(encoding="utf-8")
    module_fqn = extract_module_context(src_rst)
    new_text = enrich_autosummary_table(text, module_fqn, source_map)
    if new_text != text:
        md_path.write_text(new_text, encoding="utf-8")
    # Stub pages live beside the markdown file so the relative ``generated/...``
    # links emitted above resolve from any output subdirectory.
    gen_base = Path(output_dir) if output_dir else md_path.parent
    write_generated_stubs(gen_base, source_map)
    return new_text


__all__ = [
    "extract_module_context",
    "enrich_autosummary_table",
    "write_generated_stubs",
    "enrich_file",
    "build_source_map",
    "find_source_roots",
]
