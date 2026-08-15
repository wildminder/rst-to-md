"""Simple RST -> Markdown conversion (no Sphinx build).

This "simple" mode converts each ``.rst`` file directly with **pypandoc**
(RST -> Markdown). It is a separate pipeline from the Sphinx mode in
[`rst_to_md/converters/sphinx.py`](rst_to_md/converters/sphinx.py:1), which
builds Sphinx HTML and converts that HTML to Markdown with **html_to_markdown**
(pandoc as fallback). The two modes intentionally use different HTML/Markdown
backends; they share the same post-processing in
[`rst_to_md/core/postprocess.py`](rst_to_md/core/postprocess.py:176).

Features (see docs/plans/2026-07-13-nice-to-have-issues-plan.md):
  * NTH-001 incremental caching (``use_cache`` / ``--no-cache``)
  * NTH-002 parallel conversion (``max_workers`` / ``--workers``)
  * NTH-003 JSON report (``report_path`` / ``--report``)
  * NTH-004 dry-run preview (``dry_run`` / ``--dry-run``)
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ..core import is_up_to_date
from ..core.postprocess import post_process_markdown
from ..core.progress import ProgressTracker

logger = logging.getLogger("rst_to_md")


def _pandoc_convert(content: str, fmt: str, wrap: str) -> str:
    """Convert RST text to Markdown using pypandoc."""
    import pypandoc

    return pypandoc.convert_text(
        content,
        fmt,
        format="rst",
        extra_args=[f"--wrap={wrap}"],
    )


def convert_rst_to_md(
    rst_path: Path,
    md_path: Path,
    wrap: str = "none",
    fmt: str = "gfm",
    errors: list[str] | None = None,
    show_progress: bool = False,
) -> bool:
    """Convert a single RST file to Markdown.

    Returns ``True`` on success, ``False`` on failure (the error is logged).
    The output parent directory is created if it does not exist. If ``errors``
    is a list, a ``"path: message"`` string is appended on failure so callers
    can build a per-file error report (NTH-003).
    """
    try:
        content = rst_path.read_text(encoding="utf-8")
        md_content = _pandoc_convert(content, fmt, wrap)
        md_content = post_process_markdown(md_content)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding="utf-8")
        if not show_progress:
            logger.info("[OK] %s -> %s", rst_path, md_path)
        return True
    except Exception as exc:  # noqa: BLE001 - conversion failures are non-fatal
        if not show_progress:
            logger.error("[ERR] Error converting %s: %s", rst_path, exc)
        if errors is not None:
            errors.append(f"{rst_path}: {exc}")
        return False


def convert_directory(
    input_dir: Path,
    output_dir: Path,
    wrap: str = "none",
    fmt: str = "gfm",
    verbose: bool = False,
    use_cache: bool = True,
    max_workers: int | None = None,
    report_path: Path | None = None,
    dry_run: bool = False,
    show_progress: bool | None = None,
) -> tuple[int, int, int]:
    """Convert all ``.rst`` files under ``input_dir`` to Markdown.

    Files are processed in sorted (deterministic) order. Returns a
    ``(success_count, error_count, skipped_count)`` tuple; simple mode never
    skips system files, but ``skipped_count`` counts cache hits when
    ``use_cache`` is enabled (NTH-001).

    Features:
      * ``use_cache`` — skip a ``.md`` whose source is not newer (NTH-001).
      * ``max_workers`` — convert in parallel via ``ThreadPoolExecutor`` when
        greater than 1 (NTH-002).
      * ``report_path`` — write a JSON summary + per-file results (NTH-003).
      * ``dry_run`` — log the planned ``src -> dst`` map and convert nothing
        (NTH-004).
      * ``show_progress`` — live progress bar on TTY (auto when ``None``).
    """
    show_progress = bool(show_progress)
    if verbose:
        logger.info("Format: %s, Wrap: %s", fmt, wrap)

    rst_files = sorted(input_dir.rglob("*.rst"))
    if not rst_files:
        logger.warning("No RST files found in %s", input_dir)
        return 0, 0, 0

    if verbose:
        logger.info("Found %d RST files to convert", len(rst_files))

    # NTH-004: preview only — list planned work, write nothing.
    if dry_run:
        planned = 0
        for rst_file in rst_files:
            rel_path = rst_file.relative_to(input_dir)
            md_path = output_dir / rel_path.with_suffix(".md")
            logger.info("Would convert: %s -> %s", rst_file, md_path)
            planned += 1
        return planned, 0, 0

    file_results: list[dict] = []
    success_count = error_count = skipped_count = 0

    def _convert_one(rst_file: Path) -> tuple[str, str]:
        """Convert one file; return (status, error_message)."""
        rel_path = rst_file.relative_to(input_dir)
        md_path = output_dir / rel_path.with_suffix(".md")
        # NTH-001: skip if the existing output is up to date.
        if use_cache and is_up_to_date(rst_file, md_path):
            return "skipped", ""
        errs: list[str] = []
        ok = convert_rst_to_md(
            rst_file, md_path, wrap, fmt, errors=errs, show_progress=show_progress
        )
        if ok:
            return "ok", ""
        return "error", (errs[0] if errs else "unknown error")

    def _record(rst_file: Path, status: str, msg: str) -> None:
        nonlocal success_count, error_count, skipped_count
        entry = {"path": str(rst_file), "status": status, "error": msg}
        file_results.append(entry)
        if status == "ok":
            success_count += 1
        elif status == "error":
            error_count += 1
        else:  # skipped (cache hit)
            skipped_count += 1

    tracker = ProgressTracker(total=len(rst_files), enabled=show_progress, desc="Converting RST")
    tracker.start()

    # NTH-002: parallel path. Distinct output paths => no write races.
    # as_completed drives the progress bar live as each file finishes.
    if max_workers not in (None, 1):
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_convert_one, rf): rf for rf in rst_files}
            for fut in as_completed(futures):
                rst_file = futures[fut]
                status, msg = fut.result()
                _record(rst_file, status, msg)
                tracker.update(status, msg)
    else:
        for rst_file in rst_files:
            status, msg = _convert_one(rst_file)
            _record(rst_file, status, msg)
            tracker.update(status, msg)

    tracker.finish()

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
