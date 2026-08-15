"""Incremental-build cache helpers (NTH-001).

Pure, side-effect-free predicates used to skip re-converting files whose
generated Markdown is already up to date relative to its source.
"""

from __future__ import annotations

from pathlib import Path


def is_up_to_date(source: Path, target: Path) -> bool:
    """Return ``True`` if ``target`` exists and is not older than ``source``.

    Used to skip re-converting a ``.rst``/``.html`` source when its output
    ``.md`` is already current. Equal mtimes count as up-to-date so the check
    is deterministic (no oscillation on filesystems with coarse mtime
    resolution).
    """
    if not target.exists():
        return False
    return target.stat().st_mtime >= source.stat().st_mtime
