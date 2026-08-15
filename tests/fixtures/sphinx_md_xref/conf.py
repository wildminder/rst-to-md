"""Sphinx config for the cross-page autodoc signature xref fixture (P12).

Mirrors the autodoc fixture but documents a type on its own page so that a
reference to it from another class's signature becomes a cross-page
`pending_xref` -> `reference` node (the case that produced ambiguous
`[Type](page.md#fully.qualified.anchor)` links inside signatures).
"""

import os
import sys

sys.path.insert(0, os.path.abspath("."))

project = "sphinx_md_xref"
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
