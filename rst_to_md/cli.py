"""Command-line interface for rst_to_md.

This module only parses arguments and dispatches to the converter functions;
all conversion logic lives in :mod:`rst_to_md.converters`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .config import AUTOSUMMARY_GENERATE_DEFAULT
from .converters.rst import convert_directory
from .converters.sphinx import (
    check_sphinx_installed,
    convert_sphinx_project,
    resolve_sphinx_project_dir,
)
from .core.logging import setup_logging

logger = logging.getLogger("rst_to_md")


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(
        prog="rst-to-md",
        description="Convert reStructuredText (.rst) files to Markdown (.md).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s docs                          Convert docs/ to md_docs/\n"
            "  %(prog)s docs output                   Convert docs/ to output/\n"
            "  %(prog)s docs output --sphinx          Convert a Sphinx project\n"
            "  %(prog)s docs output --wrap auto       Use pandoc's auto-wrap\n"
        ),
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Directory containing RST files (or a Sphinx project with conf.py)",
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        nargs="?",
        default=None,
        help="Directory to write Markdown files (default: <input_dir>_md)",
    )
    parser.add_argument(
        "-w",
        "--wrap",
        choices=["none", "auto", "preserve"],
        default="none",
        help="Pandoc wrap option (default: none)",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["gfm", "markdown", "markdown_strict"],
        default="gfm",
        help="Output format for simple mode (default: gfm)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show verbose output",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    # Sphinx options
    parser.add_argument(
        "--sphinx",
        action="store_true",
        help="Use Sphinx-aware conversion for Sphinx projects",
    )
    parser.add_argument(
        "--sphinx-opts",
        nargs="*",
        default=[],
        help="Additional options to pass to sphinx-build",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Keep Sphinx build directory after conversion",
    )
    parser.add_argument(
        "--lightweight",
        action="store_true",
        default=True,
        help="Lightweight mode: disable plotting/examples/ipython (default: ON)",
    )
    parser.add_argument(
        "--no-lightweight",
        action="store_false",
        dest="lightweight",
        help="Disable lightweight mode (full sphinx build with all features)",
    )
    parser.add_argument(
        "--keep-chrome",
        action="store_true",
        default=False,
        help=(
            "Keep Sphinx/theme navigation chrome (sidebar TOC, footer, "
            "'On this page' TOC). Default: strip it for clean Markdown."
        ),
    )

    # Nice-to-have features (NTH-001..NTH-006)
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable incremental caching (reconvert every file).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel conversion workers (default: 1 = serial).",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write a JSON summary + per-file results to this path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be converted without writing anything.",
    )
    parser.add_argument(
        "-b",
        "--builder",
        default="markdown",
        help="Sphinx builder to use (default: markdown; use 'html' for the "
        "legacy rst->html->markdown pipeline).",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable the live progress bar (auto-enabled when output is a TTY).",
    )
    parser.add_argument(
        "--build-workers",
        type=int,
        default=0,
        help="Parallel Sphinx build workers (passed as -j N). 0 = auto (CPU "
        "count), 1 = serial. Parallelizes the build itself, unlike --workers "
        "which only parallelizes post-build conversion.",
    )
    parser.add_argument(
        "--autosummary-generate",
        choices=["auto", "true", "false"],
        default=AUTOSUMMARY_GENERATE_DEFAULT,
        help="Autosummary stub-page generation: auto (generate when the "
        "documented package is importable), true (always; may crash if the "
        "package is missing), false (never; tables enriched from source). "
        "Default: auto.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(args.verbose)

    if not args.input_dir.is_dir():
        logger.error("Error: '%s' is not a valid directory", args.input_dir)
        return 2

    if args.output_dir is None:
        args.output_dir = Path(f"{args.input_dir}_md")

    if args.verbose:
        logger.info("Input directory: %s", args.input_dir.absolute())
        logger.info("Output directory: %s", args.output_dir.absolute())

    if args.sphinx:
        if not check_sphinx_installed():
            logger.error(
                "[ERR] Sphinx is not installed. Install with: pip install sphinx"
            )
            return 1
        # Many repositories keep the Sphinx project one level down (e.g.
        # docs/source/conf.py); resolve it so pointing at docs/ works too.
        project_dir = resolve_sphinx_project_dir(args.input_dir)
        if project_dir is None:
            logger.error(
                "[ERR] %s is not a Sphinx project (no conf.py found in it or "
                "in source/, doc/, docs/)",
                args.input_dir,
            )
            return 2
        if project_dir != args.input_dir:
            logger.info("Using Sphinx project directory: %s", project_dir)

        success, errors, skipped = convert_sphinx_project(
            project_dir,
            args.output_dir,
            args.wrap,
            args.sphinx_opts,
            args.verbose,
            clean_build=not args.no_clean,
            lightweight=args.lightweight,
            strip_chrome=not args.keep_chrome,
            use_cache=not args.no_cache,
            max_workers=args.workers,
            report_path=args.report,
            dry_run=args.dry_run,
            builder=args.builder,
            show_progress=not args.no_progress,
            build_workers=args.build_workers,
            autosummary_generate=args.autosummary_generate,
        )
        logger.info("Sphinx conversion complete!")
        logger.info("  Success: %d files", success)
        if skipped > 0:
            logger.info("  Skipped: %d system files", skipped)
        if errors > 0:
            logger.info("  Errors: %d files", errors)
        logger.info("  Output: %s", args.output_dir.absolute())
        return 0 if errors == 0 else 1

    success, errors, _ = convert_directory(
        args.input_dir,
        args.output_dir,
        args.wrap,
        args.format,
        args.verbose,
        use_cache=not args.no_cache,
        max_workers=args.workers,
        report_path=args.report,
        dry_run=args.dry_run,
        show_progress=not args.no_progress,
    )
    logger.info("Conversion complete!")
    logger.info("  Success: %d files", success)
    if errors > 0:
        logger.info("  Errors: %d files", errors)
    logger.info("  Output: %s", args.output_dir.absolute())
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
