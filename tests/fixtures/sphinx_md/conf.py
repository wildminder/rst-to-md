"""Sphinx config for the direct Markdown builder parity fixture (P11).

Mirrors the autodoc fixture but is used to compare the HTML builder and the
direct Markdown builder (sphinx_markdown_builder) on the *same* source so we
can assert structural parity (class + members survive both pipelines).
"""

import os
import sys

sys.path.insert(0, os.path.abspath("."))

project = "sphinx_md"
author = "test"
version = "1.0.0"
release = "1.0.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
]

html_theme = "alabaster"
master_doc = "index"
exclude_patterns = ["_build"]
