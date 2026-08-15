import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
]
master_doc = "index"
html_theme = "alabaster"
project = "crashtest"
