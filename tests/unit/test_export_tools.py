import json

import pytest

from src.utils.export_tools import (
    export_content,
    markdown_to_html,
    to_html_document,
    to_plain_text,
    to_social_json,
    to_wordpress_wxr,
)

MD = """# Title & More

Intro with **bold** and a [link](https://example.com).

## Section

- one
- two

1. first
2. second

| A | B |
|---|---|
| 1 | 2 |

> quote
"""


def test_markdown_to_html():
    html = markdown_to_html(MD)
    for tag in ("<h1>Title &amp; More</h1>", "<strong>bold</strong>", '<a href="https://example.com">link</a>',
                "<ul>", "<ol>", "<table>", "<th>A</th>", "<td>2</td>", "<blockquote>"):
        assert tag in html


def test_html_document_has_meta():
    doc = to_html_document(MD, "T", "desc")
    assert '<meta name="description" content="desc">' in doc and doc.startswith("<!doctype html>")


def test_plain_text():
    txt = to_plain_text(MD)
    assert "#" not in txt.splitlines()[0] and "link (https://example.com)" in txt


def test_pdf_export():
    pytest.importorskip("reportlab")
    data = export_content(MD + "\n🚀 emoji line", "pdf", "T")
    assert data.startswith(b"%PDF")


def test_wordpress_wxr():
    xml = to_wordpress_wxr([{"title": "Post A", "markdown": MD, "meta_description": "m", "tags": ["SEO Tips"]}])
    assert "<wp:post_name>post-a</wp:post_name>" in xml and 'nicename="seo-tips"' in xml
    assert "<wp:status>draft</wp:status>" in xml


def test_social_json():
    payload = json.loads(to_social_json("hello", ["#a"], "/tmp/x.png"))
    assert payload["platform"] == "linkedin" and payload["media"] == ["/tmp/x.png"]


@pytest.mark.parametrize("fmt", ["md", "html", "txt", "wxr"])
def test_export_content_formats(fmt):
    assert export_content(MD, fmt, "T")


def test_export_unknown_format():
    with pytest.raises(ValueError):
        export_content(MD, "docx")
