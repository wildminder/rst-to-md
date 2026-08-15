"""Sphinx config for the autodoc fixture (P0).

Uses the furo theme (same as the aiogram docs that exhibited the bug) and the
autodoc extension, so the generated HTML reproduces the exact markup that
caused the `Bases:` inheritance list and signature mangling.
"""

import os
import sys

sys.path.insert(0, os.path.abspath("."))

project = "sphinx_autodoc"
author = "test"
version = "1.0.0"
release = "1.0.0"

extensions = [
    "sphinx.ext.autodoc",
]

html_theme = "furo"
master_doc = "index"
exclude_patterns = ["_build"]
