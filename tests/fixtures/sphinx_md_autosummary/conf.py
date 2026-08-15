"""Sphinx config for the autosummary source-enrichment fixture.

Mirrors ``sphinx_md`` but enables ``sphinx.ext.autosummary`` so the page
exercises autosummary table generation. ``sample_pkg`` lives inside this docs
tree and is added to ``sys.path`` so it is importable inside the Sphinx build;
the ``auto`` ladder therefore generates real autosummary tables. The post-build
AST source map (built without importing the package) still drives the
``generated/`` stub pages so the table links resolve. The autosummary
enrichment that fills *empty* stub cells (the librosa / not-installed scenario)
is covered directly by the unit tests on ``enrich_autosummary_table`` and
``convert_built_md``; this fixture exercises the full build -> enrich -> write
pipeline end to end.
"""

import os
import sys

sys.path.insert(0, os.path.abspath("."))

project = "sphinx_md_autosummary"
author = "test"
version = "1.0.0"
release = "1.0.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
]

html_theme = "alabaster"
master_doc = "index"
exclude_patterns = ["_build"]
