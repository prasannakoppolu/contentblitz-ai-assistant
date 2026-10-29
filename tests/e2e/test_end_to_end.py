"""End-to-end: CLI and full content pipelines with export. Browser tests live in test_web_ui.py."""
from __future__ import annotations

from pathlib import Path

from src import cli
from src.utils.export_tools import export_content, to_wordpress_wxr



def test_research_to_multiformat_to_export(engine, tmp_path):
    engine.run("Research the state of B2B podcast marketing", "p")
    engine.run("Write a 3-part blog series about it", "p")
    s = engine.run("Now a LinkedIn post to promote it, with an image", "p")
    assert len(s["blog_series"]) == 3
    assert s["linkedin"] and Path(s["image"]["path"]).exists()
    html = export_content(s["blog"]["markdown"], "html", s["blog"]["title"], s["blog"]["meta_description"]).decode()
    assert s["blog"]["meta_description"] in html
    wxr = to_wordpress_wxr([{"title": p["title"], "markdown": p["markdown"]} for p in s["blog_series"]])
    assert wxr.count("<item>") == 3


def test_cli_single_query(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("CONTENTBLITZ_OUTPUT_DIR", str(tmp_path))
    assert cli.main(["--mock", "Write a LinkedIn post about hybrid work"]) == 0
    out = capsys.readouterr().out
    assert "LinkedIn post" in out and "query_handler" in out


def test_cli_requires_query(capsys):
    assert cli.main(["--mock"]) == 1
