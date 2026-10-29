"""End-to-end: CLI, full content pipelines with export, and the Streamlit UI."""
from __future__ import annotations

from pathlib import Path

import pytest

from src import cli
from src.utils.export_tools import export_content, to_wordpress_wxr

APP = Path(__file__).resolve().parents[2] / "src" / "web_app" / "streamlit_app.py"


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


@pytest.fixture
def app(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("CONTENTBLITZ_MOCK", "1")
    monkeypatch.setenv("CONTENTBLITZ_OUTPUT_DIR", str(tmp_path))
    at = AppTest.from_file(str(APP), default_timeout=90)
    at.run()
    return at


def test_streamlit_renders_and_runs_campaign(app):
    assert not app.exception
    assert any("ContentBlitz" in m.value for m in app.markdown)
    app.chat_input[0].set_value("Create a campaign about urban beekeeping").run()
    assert not app.exception
    assert len(app.chat_message) == 2
    assert "Research on urban beekeeping" in app.chat_message[1].markdown[0].value
    labels = [b.label for b in app.get("download_button")]
    assert "PDF" in labels and "WordPress XML" in labels


def test_streamlit_example_button_and_followup(app):
    app.button(key="ex1").click().run()
    assert not app.exception and len(app.chat_message) == 2
    app.chat_input[0].set_value("make it shorter").run()
    assert not app.exception and len(app.chat_message) == 4
    assert "revised the **blog**" in app.chat_message[3].markdown[0].value
