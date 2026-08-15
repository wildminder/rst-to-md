"""Sphinx config for the stubbed-directive regression fixture.

Imports a directive class from a guaranteed-missing third-party package and
registers it. The stubbing machinery must keep the import working (via a
``_DummyModule``) while the ``run_directive`` guard degrades the unusable
directive to a system message instead of aborting the build with
``TypeError: '<' not supported between instances of 'int' and '_DummyModule'``.
"""

project = "sphinx_stubbed_directive"
author = "test"
version = "1.0.0"
release = "1.0.0"

extensions = ["sphinx.ext.autodoc"]
html_theme = "alabaster"
master_doc = "index"
exclude_patterns = ["_build"]

from definitely_missing_directive_pkg import FancyDirective  # noqa: E402
from docutils.parsers import rst  # noqa: E402

rst.directives.register_directive("fancy", FancyDirective)
