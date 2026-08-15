"""HTML-level cleaning for Sphinx-generated pages.

Operating on the HTML (instead of the final Markdown) is far more robust than
regex post-processing on Markdown:

* Chrome removal becomes "convert only the content container" (``<main>`` /
  ``<article>`` / ``[role="main"]``), which structurally guarantees that all
  autodoc-rendered documentation (class signatures, the ``Bases:`` inheritance
  list, members, parameter/raises/return fields) is preserved while the
  sidebar, global TOC, nav and footer are dropped *before* conversion.
* A small normalizer repairs Sphinx/autodoc-specific markup that generic
  HTML→Markdown converters mangle (e.g. ``html_to_markdown`` italicizes
  ``<em class="sig-param">``, turning ``**kwargs`` into ``***kwargs*``).

All functions are pure (no I/O) and idempotent.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

# Selectors tried in priority order to locate the document body. Sphinx themes
# put the authored content inside one of these; everything outside (sidebar,
# nav, footer, "On this page" TOC, copyright) is chrome.
_CONTENT_SELECTORS = [
    "main",
    "[role='main']",
    "article",
    "div.body",
    "div.document",
    "div.content",
]


def extract_content_html(html: str) -> str:
    """Return only the document-body HTML, dropping all navigation chrome.

    Finds the first content container via :data:`_CONTENT_SELECTORS` and returns
    its *inner* HTML. If no container is found the original HTML is returned
    unchanged (safe fallback — we never delete content we cannot locate).
    """
    soup = BeautifulSoup(html, "html.parser")
    container = None
    for selector in _CONTENT_SELECTORS:
        container = soup.select_one(selector)
        if container is not None:
            break
    if container is None:
        return html
    return container.decode_contents()


def normalize_autodoc_html(html: str) -> str:
    """Repair Sphinx/autodoc markup so generic converters emit faithful MD.

    * ``<em class="sig-param">…</em>`` (signature parameters) is rewritten to
      ``<code>…</code>`` so ``**`` / ``*`` are not interpreted as Markdown
      emphasis (``**kwargs`` would otherwise become ``***kwargs*``).
    * ``<a class="headerlink">`` permalink anchors (the ``¶``) are removed at
      the source, which is cleaner than stripping the pilcrow afterwards.
    """
    soup = BeautifulSoup(html, "html.parser")

    for em in soup.select("em.sig-param"):
        em.name = "code"

    for headerlink in soup.select("a.headerlink"):
        headerlink.decompose()

    return str(soup)


def clean_sphinx_html(html: str) -> str:
    """Run the full HTML-level cleanup: extract body then normalize autodoc.

    Pure and idempotent. Intended to run immediately before the HTML→Markdown
    converter.
    """
    html = extract_content_html(html)
    html = normalize_autodoc_html(html)
    return html
