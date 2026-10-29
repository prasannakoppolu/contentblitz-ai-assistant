"""Export generated content to Markdown, HTML, plain text, PDF, WordPress WXR
and platform-ready social formats."""
from __future__ import annotations

import html
import io
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape as xml_escape

from src.utils.content_optimization import slugify, strip_markdown


def markdown_to_html(md: str) -> str:
    """Small, dependency-free Markdown -> HTML converter covering the syntax our agents emit."""
    out: List[str] = []
    in_ul = in_ol = in_table = False
    table_rows: List[List[str]] = []

    def inline(text: str) -> str:
        text = html.escape(text)
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<em>\1</em>", text)
        text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
        text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)
        return text

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def flush_table() -> None:
        nonlocal in_table, table_rows
        if in_table:
            rows = [r for r in table_rows if not all(re.fullmatch(r":?-+:?", c.strip()) for c in r)]
            if rows:
                out.append("<table>")
                out.append("<thead><tr>" + "".join(f"<th>{inline(c.strip())}</th>" for c in rows[0]) + "</tr></thead>")
                out.append("<tbody>" + "".join("<tr>" + "".join(f"<td>{inline(c.strip())}</td>" for c in r) + "</tr>"
                                               for r in rows[1:]) + "</tbody></table>")
            in_table, table_rows = False, []

    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            close_lists()
            in_table = True
            table_rows.append(stripped.strip("|").split("|"))
            continue
        flush_table()
        if not stripped:
            close_lists()
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            close_lists()
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
        elif re.match(r"^[-*]\s+", stripped):
            if in_ol:
                close_lists()
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            item = re.sub(r"^[-*]\s+", "", stripped)
            out.append(f"<li>{inline(item)}</li>")
        elif re.match(r"^\d+\.\s+", stripped):
            if in_ul:
                close_lists()
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            item = re.sub(r"^\d+\.\s+", "", stripped)
            out.append(f"<li>{inline(item)}</li>")
        elif stripped.startswith(">"):
            close_lists()
            out.append(f"<blockquote>{inline(stripped.lstrip('> '))}</blockquote>")
        else:
            close_lists()
            out.append(f"<p>{inline(stripped)}</p>")
    close_lists()
    flush_table()
    return "\n".join(out)


def to_html_document(md: str, title: str = "ContentBlitz Export", meta_description: str = "",
                     image_path: Optional[str] = None) -> str:
    body = markdown_to_html(md)
    img = f'<img src="{html.escape(image_path)}" alt="{html.escape(title)}" style="max-width:100%"/>' if image_path else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(meta_description)}">
<style>body{{font-family:Georgia,serif;max-width:760px;margin:2rem auto;padding:0 1rem;line-height:1.65;color:#1f2937}}
h1,h2,h3{{font-family:system-ui,sans-serif;line-height:1.25}}table{{border-collapse:collapse}}td,th{{border:1px solid #ddd;padding:.4rem}}</style>
</head><body>{img}
{body}
</body></html>"""


def to_plain_text(md: str) -> str:
    text = re.sub(r"^#{1,6}\s*", "", md, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    return text.strip() + "\n"


def to_pdf_bytes(md: str, title: str = "ContentBlitz Export") -> bytes:
    """Render Markdown to a simple PDF with ReportLab."""
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PDF export requires 'reportlab' (pip install reportlab)") from exc

    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, title=title, leftMargin=54, rightMargin=54)
    story: List[Any] = []
    bullets: List[Any] = []

    def esc(t: str) -> str:
        t = html.escape(t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        return re.sub(r"[\U0001F300-\U0001FAFF☀-➿️]", "", t)

    def flush() -> None:
        nonlocal bullets
        if bullets:
            story.append(ListFlowable([ListItem(Paragraph(esc(b), styles["BodyText"])) for b in bullets], bulletType="bullet"))
            bullets = []

    for line in md.splitlines():
        s = line.strip()
        if not s:
            flush()
            continue
        m = re.match(r"^(#{1,3})\s+(.*)", s)
        if m:
            flush()
            story.append(Paragraph(esc(m.group(2)), styles[{1: "Title", 2: "Heading2", 3: "Heading3"}[len(m.group(1))]]))
        elif re.match(r"^([-*]|\d+\.)\s+", s):
            bullets.append(re.sub(r"^([-*]|\d+\.)\s+", "", s))
        else:
            flush()
            story.append(Paragraph(esc(s), styles["BodyText"]))
            story.append(Spacer(1, 4))
    flush()
    doc.build(story)
    return buf.getvalue()


def to_wordpress_wxr(posts: List[Dict[str, Any]], site_title: str = "ContentBlitz") -> str:
    """WordPress eXtended RSS (WXR 1.2) for Tools -> Import -> WordPress."""
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    items = []
    for i, post in enumerate(posts, 1):
        title = post.get("title", f"Post {i}")
        content = markdown_to_html(post.get("markdown", ""))
        tags = "".join(f'<category domain="post_tag" nicename="{slugify(t)}"><![CDATA[{t}]]></category>'
                       for t in post.get("tags", []))
        items.append(f"""
  <item>
    <title>{xml_escape(title)}</title>
    <pubDate>{now}</pubDate>
    <dc:creator><![CDATA[contentblitz]]></dc:creator>
    <description>{xml_escape(post.get('meta_description', ''))}</description>
    <content:encoded><![CDATA[{content}]]></content:encoded>
    <excerpt:encoded><![CDATA[{post.get('meta_description', '')}]]></excerpt:encoded>
    <wp:post_id>{i}</wp:post_id>
    <wp:post_name>{slugify(title)}</wp:post_name>
    <wp:status>draft</wp:status>
    <wp:post_type>post</wp:post_type>
    {tags}
  </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"
  xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:wp="http://wordpress.org/export/1.2/">
<channel>
  <title>{xml_escape(site_title)}</title>
  <wp:wxr_version>1.2</wp:wxr_version>{''.join(items)}
</channel>
</rss>
"""


def to_social_json(linkedin_post: str, hashtags: List[str], image_path: Optional[str] = None) -> str:
    """Scheduler-friendly payload (Buffer / Hootsuite style)."""
    return json.dumps({"platform": "linkedin", "text": linkedin_post, "hashtags": hashtags,
                       "media": [image_path] if image_path else [], "character_count": len(linkedin_post)}, indent=2)


def export_content(md: str, fmt: str, title: str = "ContentBlitz Export", meta_description: str = "") -> bytes:
    fmt = fmt.lower()
    if fmt in {"md", "markdown"}:
        return md.encode()
    if fmt == "html":
        return to_html_document(md, title, meta_description).encode()
    if fmt in {"txt", "text"}:
        return to_plain_text(md).encode()
    if fmt == "pdf":
        return to_pdf_bytes(md, title)
    if fmt in {"wxr", "wordpress"}:
        return to_wordpress_wxr([{"title": title, "markdown": md, "meta_description": meta_description}]).encode()
    raise ValueError(f"Unsupported export format: {fmt}")


EXPORT_FORMATS = {"Markdown": ("md", "text/markdown"), "HTML": ("html", "text/html"),
                  "Plain text": ("txt", "text/plain"), "PDF": ("pdf", "application/pdf"),
                  "WordPress XML": ("wxr", "application/xml")}

__all__ = ["markdown_to_html", "to_html_document", "to_plain_text", "to_pdf_bytes", "to_wordpress_wxr",
           "to_social_json", "export_content", "EXPORT_FORMATS", "strip_markdown"]
