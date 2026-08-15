import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import crashpkg  # noqa: F401  (intentionally imported so autodoc documents it)

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
]
master_doc = "index"
html_theme = "alabaster"
project = "fallbacktest"
