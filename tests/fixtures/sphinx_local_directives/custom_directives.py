"""Local helper module registering a docutils directive (torchaudio pattern).

This module is only importable when the fixture directory is on ``sys.path``
(as ``conf.py`` arranges inside the Sphinx subprocess). It must never be
stubbed by the lightweight-mode sitecustomize.
"""

from docutils import nodes
from docutils.parsers.rst import Directive


class Echo(Directive):
    """Render its single required argument as a paragraph."""

    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = True
    has_content = False

    def run(self):
        return [nodes.paragraph("", self.arguments[0])]
