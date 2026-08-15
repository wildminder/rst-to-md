"""Tests for the pure Markdown post-processing pipeline (P3, P4)."""

from __future__ import annotations

import pytest

from rst_to_md.core.postprocess import (
    collapse_blank_lines,
    normalize_line_endings,
    post_process_markdown,
    rewrite_links,
    strip_empty_anchors,
    strip_media,
    strip_sphinx_chrome,
    strip_sphinx_footer,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("a\r\nb", "a\nb"),
        ("a\rb", "a\nb"),
        ("a\r\r\nb", "a\nb"),
    ],
)
def test_normalize_line_endings(raw, expected):
    assert normalize_line_endings(raw) == expected


# --------------------------------------------------------------------------- #
# WS1: strip_empty_anchors — left-over named anchors from the vendored markdown
# builder (e.g. ``<a id="beat"></a>``) carry no navigation value in plain
# Markdown and must be stripped.
# --------------------------------------------------------------------------- #
def test_strip_empty_anchors_removes_empty_id_anchor():
    assert strip_empty_anchors('<a id="beat"></a>') == ""


def test_strip_empty_anchors_handles_spacing():
    # Optional whitespace before ``>`` must not block the match.
    assert strip_empty_anchors('<a id="beat" ></a>') == ""


def test_strip_empty_anchors_keeps_anchored_content():
    # Anchors that wrap real content are left untouched (they carry text).
    assert strip_empty_anchors('<a id="x">visible</a>') == '<a id="x">visible</a>'


def test_strip_empty_anchors_keeps_href_links():
    # Anchors with an href (real links) are left untouched.
    assert strip_empty_anchors('<a href="u">t</a>') == '<a href="u">t</a>'


def test_strip_empty_anchors_preserves_surrounding_text():
    text = 'intro\n\n<a id="beat"></a>\n\nbody\n'
    out = strip_empty_anchors(text)
    assert "intro" in out
    assert "body" in out
    assert "beat" not in out


def test_strip_empty_anchors_idempotent():
    once = strip_empty_anchors('<a id="beat"></a>')
    assert strip_empty_anchors(once) == once


def test_post_process_markdown_strips_beat_anchor():
    # The shared pipeline must strip ``<a id="..."></a>`` anchors coming from
    # the vendored markdown builder (the user-visible beat.md defect).
    text = '# librosa.beat\n\n<a id="beat"></a>\n\nBeat tracking functions.\n'
    out = post_process_markdown(text)
    assert "<a id=" not in out
    assert "# librosa.beat" in out
    assert "Beat tracking functions." in out


def test_collapse_blank_lines():
    assert collapse_blank_lines("a\n\n\n\nb") == "a\n\nb"
    assert collapse_blank_lines("a\n\nb") == "a\n\nb"


def test_strip_media_removes_image_links():
    text = "![alt](_images/foo.png)\n\n![alt](media/bar.jpg)\n\nKeep me"
    out = strip_media(text)
    assert "_images/" not in out
    assert "media/" not in out
    assert "Keep me" in out


def test_strip_sphinx_footer():
    text = "Body\n\n© Copyright 2024 Someone\n\nCreated using Sphinx 9.1.0\n"
    out = strip_sphinx_footer(text)
    assert "Copyright" not in out
    assert "Created using Sphinx" not in out
    assert "Body" in out


def test_strip_sphinx_footer_reversed_copyright_order():
    # Some themes emit "Copyright (c) YEAR, Author" (Copyright before the
    # copyright symbol); both orderings must be stripped.
    text = "Body\n\nCopyright © 2026, aiogram Team\n\nNext line\n"
    out = strip_sphinx_footer(text)
    assert "Copyright" not in out
    assert "aiogram Team" not in out
    assert "Body" in out
    assert "Next line" in out


def test_strip_sphinx_chrome_large_on_this_page_toc():
    # A pathological page whose "On this page" TOC is itself huge (e.g. a
    # changelog listing hundreds of versions). The trailing chrome must still
    # be cut even though the marker is far from the end of the file.
    toc_entries = "\n".join(f"  * [v{i}](#id{i})" for i in range(300))
    text = f"# Changelog\n\nSome intro text.\n\n# On this page\n\n{toc_entries}\n"
    out = strip_sphinx_chrome(text)
    assert out.startswith("# Changelog")
    assert "Some intro text." in out
    assert "On this page" not in out
    assert "v299" not in out


# A realistic furo-style page: YAML front matter, theme icons, a global sidebar
# TOC, back-to-top link, the document body, then footer nav + copyright +
# "Made with" attribution + a local "On this page" TOC.
_FURO_LIKE = """\
---
meta-color-scheme: light dark
meta-viewport: width=device-width, initial-scale=1
title: Installation - aiogram 0.0.0 documentation
---
![SVG Image](data:image/svg+xml;base64,PHN2Zw==)
[aiogram 0.0.0 documentation](index.md)

- [Installation](#)
- [Migration FAQ (2.x -> 3.0)](migration_2_to_3.md)
  * [Bot](api/bot.md)
- [Changelog](changelog.md)

[![SVG Image] Back to top](#)

# Installation

## From PyPI

```
pip install -U aiogram
```

[NextMigration FAQ (2.x -> 3.0) SVG Image](migration_2_to_3.md) [SVG Image PreviousHome](index.md)

Copyright © 2026, aiogram Team

Made with [Sphinx](https://www.sphinx-doc.org/) and Furo

 On this page

- [Installation](#)
  * [From PyPI](#from-pypi)
"""


def test_strip_sphinx_chrome_removes_navigation_and_footer():
    out = strip_sphinx_chrome(_FURO_LIKE)
    # Document body is preserved.
    assert out.startswith("# Installation")
    assert "pip install -U aiogram" in out
    assert "## From PyPI" in out
    # All chrome is gone.
    assert "meta-color-scheme" not in out
    assert "aiogram 0.0.0 documentation" not in out
    assert "data:image/svg" not in out
    assert "Back to top" not in out
    assert "Migration FAQ" not in out
    assert "Changelog" not in out
    assert "Copyright" not in out
    assert "Made with" not in out
    assert "On this page" not in out


def test_strip_sphinx_chrome_idempotent():
    once = strip_sphinx_chrome(_FURO_LIKE)
    twice = strip_sphinx_chrome(once)
    assert once == twice


def test_strip_sphinx_chrome_keeps_license_content_with_copyright():
    # A License page that legitimately mentions "Copyright" must not be clipped.
    license_page = (
        "# License\n\n"
        "Copyright © 2024 The Authors. All rights reserved.\n\n"
        "Some licensing terms here.\n"
    )
    out = strip_sphinx_chrome(license_page)
    assert "Copyright © 2024 The Authors" in out
    assert "Some licensing terms here." in out
    assert out.startswith("# License")


def test_strip_sphinx_chrome_removes_front_matter():
    # IMP-002: front matter (furo YAML block) is stripped here, not in
    # html_clean. The surviving single source of truth must keep working.
    text = (
        "---\n"
        "meta-color-scheme: light dark\n"
        "title: Installation\n"
        "---\n"
        "# Installation\n\n"
        "Body text.\n"
    )
    out = strip_sphinx_chrome(text)
    assert out.startswith("# Installation")
    assert "meta-color-scheme" not in out
    assert "title: Installation" not in out
    assert "---" not in out
    assert "Body text." in out


def test_strip_sphinx_chrome_no_h1_keeps_content():
    # If there is no level-1 heading we must not delete the whole document.
    text = "Just a paragraph.\n\nCopyright © 2024 Someone\n"
    out = strip_sphinx_chrome(text)
    assert "Just a paragraph." in out


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("[Guide](guide.html)", "[Guide](guide.md)"),
        ("[Guide](guide.html#section)", "[Guide](guide.md#section)"),
        ("[Guide](guide.html?x=1#frag)", "[Guide](guide.md?x=1#frag)"),
        ("[Top](.html#top)", "[Top](#top)"),
        (
            "[Ext](https://example.com/page.html)",
            "[Ext](https://example.com/page.html)",
        ),
    ],
)
def test_rewrite_links(raw, expected):
    assert rewrite_links(raw) == expected


def test_post_process_idempotent():
    messy = (
        "Title\r\n\r\n"
        "![x](_images/a.png)\n"
        "[Next](next.html)\n"
        "Body text.\n\n\n\n"
        "© Copyright 2024\n"
        "Created using Sphinx 9.1.0¶\n"
    )
    once = post_process_markdown(messy)
    twice = post_process_markdown(once)
    assert once == twice


def test_post_process_deterministic():
    inputs = [
        "A\n\n\n\nB [Link](p.html#x) ![i](media/x.png)",
        "A\n\n\n\nB [Link](p.html#x) ![i](media/x.png)",
    ]
    results = [post_process_markdown(i) for i in inputs]
    assert results[0] == results[1]
    assert "p.md#x" in results[0]
    assert "media/" not in results[0]


def test_post_process_strips_pilcrow_permalink():
    # Sphinx/furo emit heading permalinks as ``[¶](#anchor "Link to this
    # heading")``. The pilcrow must be stripped *before* empty-link cleanup so
    # the anchor becomes an empty link and is removed.
    text = '# Installation[¶](#installation "Link to this heading")\n\nBody\n'
    out = post_process_markdown(text)
    assert "Link to this heading" not in out
    assert "#installation" not in out
    assert out.startswith("# Installation")
    assert "Body" in out


def test_postprocess_identical_for_both_backends():
    # IMP-005: both modes share the SAME post_process_markdown, so a given
    # Markdown fragment is normalized identically regardless of which backend
    # (pypandoc RST->MD or html_to_markdown HTML->MD) produced it.
    fragment = (
        "Title\r\n\r\n![x](_images/a.png)\n[Next](next.html)\nBody. \n\n\n\n© Copyright 2024\n"
    )
    out1 = post_process_markdown(fragment)
    out2 = post_process_markdown(fragment)
    # Deterministic: identical input yields identical output.
    assert out1 == out2
    # Idempotent: running the pipeline again does not change the result.
    assert post_process_markdown(out1) == out1
    # Shared normalization behaviors are present in the result.
    assert "Title" in out1
    assert "Body." in out1
    assert "_images/" not in out1
    assert "Copyright" not in out1
