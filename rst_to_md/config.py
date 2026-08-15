"""Configuration constants for rst_to_md.

These values control which Sphinx-generated artifacts are skipped and which
extensions are enabled/disabled in lightweight mode. Keeping them in one place
makes the conversion policy explicit and easy to test.
"""

from __future__ import annotations

# HTML files that should never be converted to Markdown.
SKIP_FILES: frozenset[str] = frozenset(
    {
        "genindex.html",
        "search.html",
        "py-modindex.html",
        "examples.html",
    }
)

# Suffix-agnostic stems derived from SKIP_FILES so the same system pages are
# skipped regardless of builder output extension (e.g. genindex.md from the
# direct Markdown builder, or genindex.html from the HTML builder).
SKIP_STEMS: frozenset[str] = frozenset(f.rsplit(".", 1)[0] for f in SKIP_FILES)

# Directory names whose contents are never converted.
SKIP_DIRS: frozenset[str] = frozenset(
    {
        "_static",
        "_sources",
        "_modules",
        "auto_examples",
        "examples",
        "gallery",
        "plots",
    }
)

# Path fragments that indicate example/plot/gallery content to skip anywhere
# in the tree (substring match against each path component).
SKIP_PATH_FRAGMENTS: frozenset[str] = frozenset(
    {
        "examples",
        "auto_examples",
        "gallery",
        "plots",
        "plot_",
    }
)

# Core Sphinx extensions always enabled in lightweight mode.
CORE_EXTENSIONS: frozenset[str] = frozenset(
    {
        "sphinx.ext.autodoc",
        "sphinx.ext.autosummary",
        "sphinx.ext.viewcode",
        "sphinx.ext.napoleon",
        "sphinx.ext.intersphinx",
    }
)

# Extension name fragments disabled in lightweight mode (substring match).
EXTENSION_DENYLIST: frozenset[str] = frozenset(
    {
        "plot",
        "gallery",
        "nbsphinx",
        "ipython",
        "numpydoc",
    }
)

# Autosummary generation policy for the Sphinx build.
#   "auto"  -> generate=True only if the documented package is importable
#   "true"  -> always generate=True (imports the package; may crash if missing)
#   "false" -> always generate=False (stub tables, enriched later from source)
AUTOSUMMARY_GENERATE_DEFAULT: str = "auto"

# Directory (relative to the output root, and used as the autosummary link
# prefix) where generated stub pages for documented members are written so the
# enriched autosummary table links resolve.
GENERATED_DIR_NAME: str = "generated"

# Link prefix prepended to generated stub page paths inside the enriched
# autosummary table (e.g. ``generated/librosa.beat.beat_track.md#...``).
AUTOSUMMARY_LINK_PREFIX: str = "generated/"
