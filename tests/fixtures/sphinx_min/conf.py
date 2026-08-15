"""Minimal Sphinx conf.py used by integration tests.

It intentionally imports a missing package (stubbed in lightweight mode) and
lists a denylisted extension (sphinx_gallery) that must be filtered out.
"""

project = "sphinx_min"
author = "Test Author"
copyright = "2024, Test Author"
version = "1.0"
release = "1.0.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_gallery",  # denylisted -> must be filtered out in lightweight mode
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
html_theme = "alabaster"
master_doc = "index"
