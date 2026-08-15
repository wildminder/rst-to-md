"""Sphinx config for the local-directive regression fixture.

Mirrors the torchaudio pattern: ``conf.py`` puts its own directory on
``sys.path``, imports a LOCAL helper module (``custom_directives``), and
registers one of its classes as a docutils directive. The local module is NOT
importable from the parent rst-to-md process, which is exactly what used to
make the stubbing machinery misclassify it as "missing" and shadow it with a
``_DummyModule`` — crashing docutils with ``TypeError: '<' not supported
between instances of 'int' and '_DummyModule'``.
"""

import os
import sys

sys.path.insert(0, os.path.abspath("."))

project = "sphinx_local_directives"
author = "test"
version = "1.0.0"
release = "1.0.0"

extensions = ["sphinx.ext.autodoc"]
html_theme = "alabaster"
master_doc = "index"
exclude_patterns = ["_build"]

from custom_directives import Echo  # noqa: E402
from docutils.parsers import rst  # noqa: E402

rst.directives.register_directive("echo", Echo)
