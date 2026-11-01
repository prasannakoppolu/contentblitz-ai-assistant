"""FastAPI backend: SSE chat, state, edits, brand voice, exports, images, security.

Every client here is signed in (see ``signed_in`` in tests/integration/auth_helpers.py)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.api.schemas import ClientSettings
from src.api.server import EngineRegistry, create_app
from tests.integration.auth_helpers import make_auth, signed_in

MOCK = {"demo_mode": True}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTENTBLITZ_OUTPUT_DIR", str(tmp_path))
    app = create_app(base_overrides={"app": {"use_mock": True, "max_retries": 0}}, env="test", serve_frontend=False,
                     auth=make_auth())
    return signed_in(TestClient(app))


def parse_sse(text: str):
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def chat(client, tid, message):
    r = client.post(f"/api/threads/{tid}/chat", json={"message": message})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    return parse_sse(r.text)


def test_health_and_config(client):
    assert client.get("/api/health").json()["status"] == "ok"
    cfg = client.get("/api/config").json()
    assert cfg["brand_voice"]["name"] == "ContentBlitz"
    # Customers never see provider keys, offline mode or usage: those live on /api/admin.
    assert not {"key_providers", "detected_keys", "default_demo_mode", "tracing"} & set(cfg)


def test_chat_streams_agent_progress_and_final_state(client):
    tid = client.post("/api/threads").json()["thread_id"]
    events = chat(client, tid, "Create a campaign about urban beekeeping")
    kinds = [e for e, _ in events]
    assert kinds[0] == "start" and kinds[-1] == "done"
    nodes = [d["node"] for e, d in events if e == "node"]
    assert nodes == ["query_handler", "research", "strategist", "blog", "linkedin", "image", "finalize"]
    final = events[-1][1]
    assert final["blog"]["title"] and final["linkedin"]["hashtags"]
    assert final["image"]["src"].startswith("/api/images/") and "path" not in final["image"]
    assert final["messages"][-1]["role"] == "assistant"


def test_state_persists_and_followups_use_memory(client):
    chat(client, "t1", "Research sustainable packaging")
    events = chat(client, "t1", "Now write an SEO blog post about it")
    assert [d["node"] for e, d in events if e == "node"] == ["query_handler", "blog", "finalize"]
    state = client.get("/api/threads/t1/state").json()
    assert state["topic"] == "sustainable packaging" and len(state["messages"]) == 4
    assert client.get("/api/threads/unknown/state").status_code == 404
    fresh = client.post("/api/threads").json()["thread_id"]
    assert client.get(f"/api/threads/{fresh}/state").json()["messages"] == []
    listed = client.get("/api/threads").json()["threads"]
    assert {t["thread_id"]: t["title"] for t in listed} == {fresh: "", "t1": "Research sustainable packaging"}


def test_blog_and_linkedin_edits_rescore(client):
    chat(client, "e", "Write a blog post and a LinkedIn post about hybrid work")
    blog = client.get("/api/threads/e/state").json()["blog"]
    r = client.put("/api/threads/e/artifacts/blog", json={"markdown": "# Short\n\nTiny.", "meta_description": "x"})
    assert r.status_code == 200
    edited = r.json()
    assert edited["edited_by_human"] and edited["revision"] == blog["revision"] + 1
    assert edited["quality"]["score"] < blog["quality"]["score"]
    li = client.put("/api/threads/e/artifacts/linkedin", json={"text": "New post? #A"}).json()
    assert li["char_count"] == len("New post? #A")
    assert client.get("/api/threads/e/state").json()["blog"]["markdown"] == "# Short\n\nTiny."


def test_edit_missing_artifact_404(client):
    assert client.put("/api/threads/none/artifacts/blog", json={"markdown": "x"}).status_code == 404
    chat(client, "r", "Research edge AI")
    assert client.put("/api/threads/r/artifacts/linkedin", json={"text": "x"}).status_code == 404


def test_brand_voice_set_and_learn(client):
    chat(client, "v", "hello")
    voice = {"name": "Acme", "tone": "playful", "audience": "devs", "banned_phrases": ["synergy"]}
    assert client.put("/api/threads/v/brand-voice", json=voice).status_code == 200
    assert client.get("/api/threads/v/state").json()["brand_voice"]["name"] == "Acme"
    learned = client.post("/api/brand-voice/learn", json={"samples": ["Short. Punchy. You'll love it! 🚀🚀🚀"]}).json()
    assert "conversational" in learned["tone"]


@pytest.mark.parametrize("artifact,fmt,mime", [
    ("blog", "md", "text/markdown"), ("blog", "html", "text/html"), ("blog", "txt", "text/plain"),
    ("blog", "pdf", "application/pdf"), ("blog", "wxr", "application/xml"),
    ("report", "md", "text/markdown"), ("linkedin", "txt", "text/plain"), ("linkedin", "json", "application/json"),
])
def test_exports(client, artifact, fmt, mime):
    chat(client, "x", "Create a campaign about plant-based snacks")
    r = client.get(f"/api/threads/x/export/{artifact}/{fmt}")
    assert r.status_code == 200 and r.headers["content-type"].startswith(mime)
    assert "attachment" in r.headers["content-disposition"]


def test_series_export_and_bad_requests(client):
    chat(client, "s", "Write a 3-part blog series about B2B podcast marketing")
    r = client.get("/api/threads/s/export/series/wxr")
    assert r.status_code == 200 and r.text.count("<item>") == 3
    assert client.get("/api/threads/s/export/series/md").status_code == 400
    assert client.get("/api/threads/s/export/blog/docx").status_code == 400
    assert client.get("/api/threads/s/export/linkedin/txt").status_code == 404
    assert client.get("/api/threads/s/export/blog/json").status_code == 400


def test_images_served_and_traversal_blocked(client):
    final = chat(client, "i", "Generate an image of a mountain sunrise")[-1][1]
    r = client.get(final["image"]["src"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get("/api/images/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/api/images/missing.png").status_code == 404


def test_chat_validation(client):
    assert client.post("/api/threads/v/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/threads/v/chat", json={"message": "x" * 4001}).status_code == 422


def test_chat_stream_reports_errors(client, monkeypatch):
    eng = client.app.state.registry.get(ClientSettings(**MOCK))  # the engine an offline server uses

    def boom(*a, **k):
        raise RuntimeError("graph exploded")
        yield  # pragma: no cover

    monkeypatch.setattr(eng, "stream", boom)
    events = chat(client, "z", "Research anything")
    assert events[-1][0] == "error" and "went wrong" in events[-1][1]["message"]
    assert "graph exploded" not in events[-1][1]["message"]  # internals stay in the server log


def test_registry_builds_engine_per_settings_and_shares_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTENTBLITZ_OUTPUT_DIR", str(tmp_path))
    reg = EngineRegistry({"app": {"use_mock": True}}, env="test", max_engines=2)
    a = reg.get(ClientSettings(demo_mode=True))
    assert reg.get(ClientSettings(demo_mode=True)) is a
    b = reg.get(ClientSettings(demo_mode=False, api_keys={"openai": "sk-x"}, llm_primary="anthropic"))
    assert b is not a and b.settings.llm_order[0] == "anthropic" and b.settings.has_key("dalle3")
    a.run("Research hybrid work", "shared")
    assert b.get_state("shared")["topic"] == "hybrid work"  # same checkpointer
    reg.get(ClientSettings(quality_threshold=90))
    assert len(reg._engines) == 2  # LRU eviction


def test_spa_fallback_serves_index(tmp_path, monkeypatch):
    import src.api.server as server

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id=root></div>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setattr(server, "FRONTEND_DIST", dist)
    c = TestClient(server.create_app({"app": {"use_mock": True}}, env="test", auth=make_auth()))
    assert c.get("/").text == "<div id=root></div>"
    assert c.get("/dashboard/blog").text == "<div id=root></div>"
    assert c.get("/assets/app.js").status_code == 200
    assert c.get("/api/nope").status_code == 404


def test_sqlite_memory_survives_restart(tmp_path, monkeypatch):
    pytest.importorskip("langgraph.checkpoint.sqlite")
    monkeypatch.setenv("CONTENTBLITZ_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CONTENTBLITZ_MEMORY", "sqlite")
    monkeypatch.setenv("CONTENTBLITZ_MEMORY_PATH", str(tmp_path / "mem.sqlite"))
    auth = make_auth()
    first = signed_in(TestClient(create_app({"app": {"use_mock": True}}, env="test", serve_frontend=False, auth=auth)))
    chat(first, "keep", "Research hybrid work")
    restarted = TestClient(create_app({"app": {"use_mock": True}}, env="test", serve_frontend=False, auth=auth))
    restarted.cookies.update(first.cookies)
    assert restarted.get("/api/threads/keep/state").json()["topic"] == "hybrid work"


def test_memory_falls_back_to_in_process_when_sqlite_missing(monkeypatch):
    import builtins

    from langgraph.checkpoint.memory import MemorySaver

    from src.workflow.langgraph_workflow import make_checkpointer

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("langgraph.checkpoint.sqlite"):
            raise ImportError(name)
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert isinstance(make_checkpointer("sqlite", ":memory:"), MemorySaver)
