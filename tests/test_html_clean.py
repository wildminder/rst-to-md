"""Tests for rst_to_md.core.html_clean (HTML-level chrome removal + autodoc repair)."""

from __future__ import annotations

from rst_to_md.core.html_clean import (
    clean_sphinx_html,
    extract_content_html,
    normalize_autodoc_html,
)


# --------------------------------------------------------------------------- #
# extract_content_html
# --------------------------------------------------------------------------- #
def test_extract_main_drops_sidebar_and_footer():
    html = (
        "<nav class='sidebar'>NAVIGATION</nav>"
        "<main><h1>Title</h1><p>Body content.</p></main>"
        "<footer>FOOTER</footer>"
    )
    out = extract_content_html(html)
    assert "NAVIGATION" not in out
    assert "FOOTER" not in out
    assert "Title" in out
    assert "Body content." in out


def test_extract_article_selector():
    html = "<div><article><h1>A</h1><p>keep</p></article><aside>drop</aside></div>"
    out = extract_content_html(html)
    assert "keep" in out
    assert "drop" not in out


def test_extract_falls_back_to_full_html_when_no_container():
    html = "<div><p>only content</p></div>"
    assert extract_content_html(html) == html


def test_extract_idempotent():
    html = "<nav>x</nav><main><h1>T</h1><p>body</p></main><footer>y</footer>"
    once = extract_content_html(html)
    assert extract_content_html(once) == once


# --------------------------------------------------------------------------- #
# normalize_autodoc_html
# --------------------------------------------------------------------------- #
def test_normalize_sig_param_becomes_code_not_italic():
    html = '<em class="sig-param"><span class="pre">**kwargs</span></em>'
    out = normalize_autodoc_html(html)
    assert "<code" in out
    assert "**kwargs" in out
    assert "<em" not in out


def test_normalize_removes_headerlinks():
    html = '<a class="headerlink" href="#x" title="Link">\u00b6</a><p>doc</p>'
    out = normalize_autodoc_html(html)
    assert "headerlink" not in out
    assert "doc" in out


def test_normalize_keeps_bases_code_links():
    # The Bases: inheritance list renders as <code> (or <a>) which must survive.
    html = (
        "<p>Bases: <code class=\"xref py py-class docutils literal notranslate\">"
        "<span class=\"pre\">TelegramMessage</span></code>, "
        "<code class=\"xref py py-class docutils literal notranslate\">"
        "<span class=\"pre\">BaseBot</span></code></p>"
    )
    out = normalize_autodoc_html(html)
    assert "TelegramMessage" in out
    assert "BaseBot" in out


def test_normalize_idempotent():
    html = (
        '<em class="sig-param"><span class="pre">**x</span></em>'
        '<a class="headerlink" href="#y">\u00b6</a>'
    )
    once = normalize_autodoc_html(html)
    assert normalize_autodoc_html(once) == once


# --------------------------------------------------------------------------- #
# clean_sphinx_html (combined)
# --------------------------------------------------------------------------- #
def test_clean_sphinx_html_idempotent():
    html = (
        "<nav>nav</nav>"
        "<main>"
        "<h1>T</h1>"
        '<p>Bases: <code class="xref py py-class"><span class="pre">Base</span></code></p>'
        '<em class="sig-param"><span class="pre">**kw</span></em>'
        '<a class="headerlink" href="#z">\u00b6</a>'
        "</main>"
        "<footer>foot</footer>"
    )
    once = clean_sphinx_html(html)
    assert clean_sphinx_html(once) == once
    # chrome gone, content + autodoc repair applied
    assert "nav" not in once
    assert "foot" not in once
    assert "Base" in once
    assert "<code" in once
    assert "**kw" in once
    assert "headerlink" not in once


def test_front_matter_re_removed():
    # IMP-002: the dead _FRONT_MATTER_RE regex must be gone; front matter is
    # stripped later in postprocess.strip_sphinx_chrome instead.
    import rst_to_md.core.html_clean as hc

    assert not hasattr(hc, "_FRONT_MATTER_RE")


def test_clean_sphinx_html_unchanged_by_dead_regex_removal():
    # Regression: removing _FRONT_MATTER_RE must not change clean_sphinx_html
    # output. A representative Sphinx body (no front matter in HTML) is returned
    # with chrome stripped and autodoc repair applied.
    html = (
        "<nav>nav</nav>"
        "<main>"
        "<h1>T</h1>"
        '<p>Bases: <code class="xref py py-class"><span class="pre">Base</span></code></p>'
        '<em class="sig-param"><span class="pre">**kw</span></em>'
        '<a class="headerlink" href="#z">\u00b6</a>'
        "</main>"
        "<footer>foot</footer>"
    )
    out = clean_sphinx_html(html)
    assert "nav" not in out
    assert "foot" not in out
    assert "Base" in out
    assert "<code" in out
    assert "**kw" in out
    assert "headerlink" not in out
