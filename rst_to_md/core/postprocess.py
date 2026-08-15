"""Markdown post-processing for Sphinx-generated HTML.

All functions here are pure (no I/O) so they are trivially testable and can be
run repeatedly without changing an already-clean result (idempotent).
"""

from __future__ import annotations

import re

# Maximum number of consecutive newlines allowed in the final output.
_MAX_BLANK_NEWLINE_RUN = 2


def normalize_line_endings(text: str) -> str:
    """Normalize ``\\r\\r\\n``, ``\\r\\n`` and ``\\r`` to ``\\n``."""
    return re.sub(r"\r\r\n|\r\n|\r", "\n", text)


def strip_navigation(text: str) -> str:
    """Remove Sphinx navigation elements (Next/Previous/Index, menu)."""
    text = re.sub(
        r"\[Navigation menu\].*?(?=\n\n# |\Z)",
        "",
        text,
        flags=re.DOTALL,
    )
    for label in ("Next", "Previous", "Index", "Module Index", "Search Page"):
        text = re.sub(rf"\[{label}\].*?\n", "", text)
    return text


def strip_media(text: str) -> str:
    """Remove image/audio placeholders and broken media links."""
    text = re.sub(r"!\[.*?\]\(media/.*?\)\n?", "", text)
    text = re.sub(r"!\[.*?\]\(_images/.*?\)\n?", "", text)
    text = re.sub(r"<img.*?>", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"<audio.*?>.*?</audio>", "", text, flags=re.IGNORECASE | re.DOTALL
    )
    text = re.sub(r"\(plot_.*?\.py\)", "", text)
    text = re.sub(r"\(.*?\.ipynb\)", "", text)
    return text


def strip_empty_links(text: str) -> str:
    """Remove empty links and figure captions."""
    text = re.sub(r"\[\]\(.*?\)\n?", "", text)
    text = re.sub(r"\*Figure.*?\*:?\s*\n", "", text)
    return text


def rewrite_links(text: str) -> str:
    """Rewrite ``.html`` references to ``.md`` preserving anchors/queries.

    Handles:
      - ``[text](target.html)``            -> ``[text](target.md)``
      - ``[text](target.html#frag)``       -> ``[text](target.md#frag)``
      - ``[text](target.html?x=1#frag)``   -> ``[text](target.md?x=1#frag)``
      - ``[text](.html#frag)``             -> ``[text](#frag)``
      - absolute URLs (``http://...``) are left untouched.
    """
    # Current-page links must run FIRST, otherwise the general rule below would
    # turn (.html#frag) into (.md#frag). Capture only the fragment (no leading
    # '#') so the replacement can prepend a single '#'.
    text = re.sub(r"\[([^\]]+)\]\(\.html#([^)]*)\)", r"[\1](#\2)", text)
    # Bare current-page link (.html) -> (#).
    text = re.sub(r"\[([^\]]+)\]\(\.html\)", r"[\1](#)", text)
    # Full links with a non-empty target and optional query/anchor.
    text = re.sub(
        r"\[([^\]]+)\]\((?!https?://)([^)]+?)\.html((?:[?#][^)]*)?)\)",
        lambda m: f"[{m.group(1)}]({m.group(2)}.md{m.group(3)})",
        text,
    )
    return text


def strip_sphinx_footer(text: str) -> str:
    """Remove Sphinx footer lines and build timestamps."""
    # Match the copyright line in either ordering (``© Copyright`` or
    # ``Copyright ©``), anchored to the start of a line.
    text = re.sub(r"^\s*©?\s*Copyright.*?(?=\n\n|$)", "", text, flags=re.MULTILINE | re.DOTALL)
    text = re.sub(r"Created using Sphinx.*?(\n\n|$)", "", text)
    text = re.sub(r"Last updated on .*?(\n|\Z)", "", text)
    text = re.sub(r"Built with Sphinx.*?(\n|\Z)", "", text)
    return text


# Unambiguous markers that identify the *start* of Sphinx/theme trailing chrome
# (footer navigation, the local "On this page" table of contents, theme
# attribution). These are anchored to the start of a line and never occur in
# authored documentation content, so matching them cannot clip real text.
# Copyright / "Created using" / "Built with" are handled separately by
# :func:`strip_sphinx_footer` (which already runs in the pipeline) so we do not
# need a generic "Copyright" match that could accidentally clip a License page.
_CHROME_TRAILING_RE = re.compile(
    r"^(?:"
    r"#\s*On this page"  # local TOC heading
    r"|Made with"  # "Made with Sphinx and Furo"
    r"|Back to top"  # back-to-top link
    r"|View this page"  # "View this page" source link
    r"|\[(?:(?:Next|Previous))"  # footer nav labels: [Next...] / [Previous...]
    r")",
    re.IGNORECASE,
)
# Footer navigation rendered as two adjacent .md links on one line.
_CHROME_FOOTER_NAV_RE = re.compile(r"^\[.*\]\(.*\.md\)\s+\[.*\]\(.*\.md\)")


def strip_sphinx_chrome(text: str) -> str:
    """Remove Sphinx/theme navigation chrome from converted Markdown.

    Sphinx HTML themes (furo, alabaster, ...) wrap the authored document body
    with navigation chrome that is not part of the documentation:

      * a YAML front matter block (furo),
      * a global sidebar table of contents,
      * theme icons / logo,
      * "Back to top" / "View this page" links,
      * a footer navigation (Previous / Next),
      * a copyright line, and
      * a local "On this page" table of contents.

    The document body always begins with the page's level-1 heading
    (``# Title``), which Sphinx renders inside ``<main>``; everything before it
    is chrome. The trailing chrome always follows the body. Stripping both
    yields clean Markdown containing only the documentation content.

    This function is pure and idempotent.
    """
    # 1. Drop the YAML front matter (furo emits one at the very top).
    text = re.sub(r"^\s*---\n.*?\n---\n?", "", text, flags=re.DOTALL)

    lines = text.split("\n")

    # 2. Keep only content from the first level-1 heading (the page title).
    #    The global sidebar TOC, theme icons and back-to-top links all render
    #    before <main>, so they are discarded. If no H1 exists we keep the
    #    whole document rather than risk deleting authored content.
    start = 0
    for i, line in enumerate(lines):
        if re.match(r"^#\s+\S", line):
            start = i
            break
    body = lines[start:]

    # 3. Cut the trailing chrome (footer nav, local TOC, theme attribution).
    #    These markers only ever appear *after* the document body, so we scan
    #    the whole body and cut from the *first* marker encountered. Cutting
    #    at the first (earliest) marker removes all subsequent chrome in one
    #    pass, and scanning the entire body (rather than a bounded tail
    #    window) also handles pathological cases where the "On this page" TOC
    #    itself is huge (e.g. a changelog listing hundreds of versions).
    end = len(body)
    for i, line in enumerate(body):
        if _CHROME_TRAILING_RE.match(line) or _CHROME_FOOTER_NAV_RE.match(line):
            end = i
            break
    body = body[:end]

    return "\n".join(body).strip()


def clean_code_blocks(text: str) -> str:
    """Normalize pandoc source-code fence annotations to plain language tags."""
    text = re.sub(r"``` \{\.sourceCode \.python\}", "```python", text)
    text = re.sub(r"``` \{\.sourceCode \.([^}]+)\}", r"```\1", text)
    return text


# Empty named anchors like ``<a id="beat"></a>`` with no inner content and no
# ``href``. The vendored markdown builder emits these for ``.. _label:`` targets;
# they carry no navigation value in plain Markdown and must be stripped. Anchors
# that wrap content (``<a id="x">visible</a>``) or carry an ``href``
# (``<a href="u">t</a>``) are left untouched.
_EMPTY_ANCHOR_RE = re.compile(r'<a\s+id="[^"]*"\s*>\s*</a>')


def strip_empty_anchors(text: str) -> str:
    """Remove empty named anchors like ``<a id="beat"></a>``.

    These are emitted by the vendored markdown builder for ``.. _label:``
    targets and carry no navigation value in plain Markdown. Only *empty*
    anchors (no inner text) are removed; anchors that wrap content or carry an
    ``href`` are left untouched. Idempotent.
    """
    return _EMPTY_ANCHOR_RE.sub("", text)


def collapse_blank_lines(text: str, max_run: int = _MAX_BLANK_NEWLINE_RUN) -> str:
    """Collapse runs of more than ``max_run`` newlines down to ``max_run``."""
    return re.sub("\n" * (max_run + 1) + "+", "\n" * max_run, text)


def post_process_markdown(content: str, strip_footer: bool = True) -> str:
    """Run the full deterministic, idempotent cleanup pipeline.

    When ``strip_footer`` is ``False`` the Sphinx footer lines (copyright,
    "Created using Sphinx", ...) are left in place. This is used together with
    ``strip_chrome=False`` to preserve all Sphinx-generated output.
    """
    content = normalize_line_endings(content)
    # Strip leftover empty named anchors (``<a id="..."></a>``) emitted by the
    # vendored markdown builder for ``.. _label:`` targets. Doing this early
    # (before blank-line collapsing) keeps the cleanup deterministic and lets
    # the following steps treat the surrounding blank lines as ordinary spacing.
    content = strip_empty_anchors(content)
    # Strip the pilcrow (¶) *before* the link/empty-link cleanup so that
    # Sphinx/furo permalink anchors like ``[¶](#anchor "Link to this
    # heading")`` become empty links ``[](#anchor ...)`` and are removed by
    # :func:`strip_empty_links`. Doing this last would leave dangling empty
    # links behind.
    content = content.replace("¶", "")
    content = strip_navigation(content)
    content = strip_media(content)
    content = strip_empty_links(content)
    content = rewrite_links(content)
    if strip_footer:
        content = strip_sphinx_footer(content)
    content = clean_code_blocks(content)
    content = collapse_blank_lines(content)
    return content.strip()
