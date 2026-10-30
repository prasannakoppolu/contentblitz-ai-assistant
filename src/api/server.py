"""FastAPI backend for the React UI.

Run (dev):   uvicorn src.api.server:app --reload --port 8000
Run (prod):  uvicorn src.api.server:app --host 0.0.0.0 --port 8000   (serves frontend/dist too)

Endpoints (all JSON unless noted):

    GET  /api/health
    GET  /api/config                                   detected keys (names only), defaults
    POST /api/threads                                  -> {thread_id}
    GET  /api/threads/{tid}/state                      UI-safe conversation state
    POST /api/threads/{tid}/chat                       Server-Sent Events: node / done / error
    PUT  /api/threads/{tid}/artifacts/blog             human edit -> re-score -> persist
    PUT  /api/threads/{tid}/artifacts/linkedin
    PUT  /api/threads/{tid}/brand-voice
    POST /api/brand-voice/learn                        derive a voice from samples
    POST /api/usage                                    usage/cost for the caller's provider config
    GET  /api/threads/{tid}/export/{artifact}/{fmt}    file download
    GET  /api/images/{filename}                        generated images
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.api.schemas import BlogEdit, BrandVoice, ChatRequest, ClientSettings, LearnVoiceRequest, LinkedInEdit
from src.core.config import PROJECT_ROOT, BrandVoiceConfig, Settings, load_settings
from src.core.workflow import ContentBlitzEngine
from src.workflow.langgraph_workflow import make_checkpointer
from src.utils.content_optimization import analyze_seo
from src.utils.export_tools import export_content, to_social_json, to_wordpress_wxr
from src.utils.quality_validation import learn_brand_voice, score_blog, score_linkedin

logger = logging.getLogger("contentblitz")

KEY_PROVIDERS = ["openai", "anthropic", "gemini", "serpapi", "perplexity", "tavily", "stability"]
EXPORT_MIME = {"md": "text/markdown", "html": "text/html", "txt": "text/plain", "pdf": "application/pdf",
               "wxr": "application/xml", "json": "application/json"}
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


# --------------------------------------------------------------------------- #
# Engine registry: one engine per provider configuration, shared memory
# --------------------------------------------------------------------------- #

class EngineRegistry:
    """Caches engines by settings signature. All engines share one checkpointer,
    so a conversation continues seamlessly when the user changes providers."""

    def __init__(self, base_overrides: Optional[Dict[str, Any]] = None, env: Optional[str] = None,
                 checkpointer: Any = None, max_engines: int = 8):
        self.base_overrides = base_overrides or {}
        self.env = env
        # CONTENTBLITZ_MEMORY=sqlite keeps conversations across restarts (needs langgraph-checkpoint-sqlite).
        self.checkpointer = checkpointer or make_checkpointer(
            os.getenv("CONTENTBLITZ_MEMORY", "memory"),
            os.getenv("CONTENTBLITZ_MEMORY_PATH", str(PROJECT_ROOT / "contentblitz_memory.sqlite")))
        self.max_engines = max_engines
        self._engines: "OrderedDict[str, ContentBlitzEngine]" = OrderedDict()
        self._lock = threading.Lock()
        self.base_settings: Settings = load_settings(env=env, overrides=self.base_overrides)
        self.default = self.get(ClientSettings())

    def overrides_for(self, cs: ClientSettings) -> Dict[str, Any]:
        keys = {k: v for k, v in cs.api_keys.items() if v and k in KEY_PROVIDERS}
        if keys.get("openai"):
            keys.setdefault("dalle3", keys["openai"])
            keys.setdefault("dalle2", keys["openai"])
        app: Dict[str, Any] = {}
        if cs.demo_mode is not None:
            app["use_mock"] = cs.demo_mode
        if cs.quality_threshold is not None:
            app["quality_threshold"] = cs.quality_threshold
        overrides: Dict[str, Any] = {"app": app, "api_keys": keys}
        chains: Dict[str, Any] = {}
        if cs.llm_primary:
            chains["llm"] = [cs.llm_primary] + [p for p in ("openai", "anthropic", "gemini") if p != cs.llm_primary]
        if cs.research_primary:
            chains["research"] = [cs.research_primary] + [p for p in ("serpapi", "perplexity", "tavily") if p != cs.research_primary]
        if chains:
            overrides["fallback_chains"] = chains
        return overrides

    @staticmethod
    def signature(overrides: Dict[str, Any]) -> str:
        # Hash so API keys never sit in memory as readable dict keys / logs.
        return hashlib.sha256(json.dumps(overrides, sort_keys=True).encode()).hexdigest()

    def get(self, cs: ClientSettings) -> ContentBlitzEngine:
        overrides = self.overrides_for(cs)
        sig = self.signature(overrides)
        with self._lock:
            engine = self._engines.get(sig)
            if engine is None:
                from src.core.config import deep_merge

                settings = load_settings(env=self.env, overrides=deep_merge(self.base_overrides, overrides))
                engine = ContentBlitzEngine(settings, checkpointer=self.checkpointer)
                self._engines[sig] = engine
                while len(self._engines) > self.max_engines:
                    self._engines.popitem(last=False)
            else:
                self._engines.move_to_end(sig)
            return engine


# --------------------------------------------------------------------------- #
# Serialisation helpers
# --------------------------------------------------------------------------- #

def _image_public(img: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not img:
        return img
    out = dict(img)
    if out.get("path"):
        out["src"] = f"/api/images/{Path(out['path']).name}"
    out.pop("path", None)  # never leak server paths to the browser
    return out


def public_state(state: Dict[str, Any], thread_id: str) -> Dict[str, Any]:
    fields = ["messages", "topic", "plan", "trace", "errors", "route", "research", "strategy_report", "content_brief",
              "blog", "blog_series", "linkedin", "history", "brand_voice", "needs_clarification", "response"]
    out = {k: state.get(k) for k in fields}
    out["image"] = _image_public(state.get("image"))
    out["thread_id"] = thread_id
    out["blog_series"] = out["blog_series"] or []
    out["messages"] = out["messages"] or []
    return json.loads(json.dumps(out, default=str))


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _voice(state: Dict[str, Any], engine: ContentBlitzEngine) -> BrandVoiceConfig:
    bv = state.get("brand_voice")
    if bv:
        return BrandVoiceConfig(**{k: v for k, v in bv.items() if k in BrandVoiceConfig.__dataclass_fields__})
    return engine.settings.brand_voice


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #

def create_app(base_overrides: Optional[Dict[str, Any]] = None, env: Optional[str] = None,
               serve_frontend: bool = True) -> FastAPI:
    registry = EngineRegistry(base_overrides, env)
    app = FastAPI(title="ContentBlitz API", version="2.0.0",
                  description="Multi-agent AI content marketing assistant (LangGraph).")
    app.state.registry = registry
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])

    def engine() -> ContentBlitzEngine:
        return registry.default

    def require_state(tid: str) -> Dict[str, Any]:
        state = engine().get_state(tid)
        if not state:
            raise HTTPException(404, "Unknown thread or no messages yet")
        return state

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        return {"status": "ok", "time": time.time()}

    @app.get("/api/config")
    def config() -> Dict[str, Any]:
        s = registry.base_settings
        detected = [p for p in KEY_PROVIDERS if s.has_key(p)]
        return {
            "detected_keys": detected,
            "default_demo_mode": s.use_mock or not detected,
            "quality_threshold": s.quality_threshold,
            "fallback_chains": {"llm": s.llm_order, "research": s.research_order, "image": s.image_order},
            "brand_voice": asdict(s.brand_voice),
            "key_providers": KEY_PROVIDERS,
            "env": s.env,
            "tracing": s.tracing,
        }

    @app.post("/api/threads")
    def new_thread() -> Dict[str, str]:
        return {"thread_id": ContentBlitzEngine.new_thread_id()}

    @app.get("/api/threads/{tid}/state")
    def get_state(tid: str) -> Dict[str, Any]:
        return public_state(engine().get_state(tid), tid)

    @app.post("/api/threads/{tid}/chat")
    def chat(tid: str, req: ChatRequest) -> StreamingResponse:
        eng = registry.get(req.settings)

        def events() -> Iterator[str]:
            yield _sse("start", {"thread_id": tid, "providers": eng.usage()["providers"],
                                 "offline": eng.services.is_offline})
            try:
                for node, update in eng.stream(req.message.strip(), tid):
                    trace = [t for t in (update.get("trace") or []) if t.get("agent") == node][-1:]
                    payload: Dict[str, Any] = {"node": node, "trace": trace[0] if trace else None}
                    if node == "query_handler":
                        payload["plan"] = update.get("plan") or []
                        payload["topic"] = update.get("topic") or ""
                    yield _sse("node", payload)
                yield _sse("done", public_state(eng.get_state(tid), tid))
            except Exception as exc:  # noqa: BLE001 - report to client instead of dropping the stream
                logger.exception("chat stream failed")
                yield _sse("error", {"message": f"{type(exc).__name__}: {exc}"})

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.put("/api/threads/{tid}/artifacts/blog")
    def edit_blog(tid: str, edit: BlogEdit) -> Dict[str, Any]:
        state = require_state(tid)
        blog = state.get("blog")
        if not blog:
            raise HTTPException(404, "No blog post in this conversation")
        q = score_blog(edit.markdown, blog["primary_keyword"], edit.meta_description, blog["secondary_keywords"],
                       _voice(state, engine()))
        updated = {**blog, "markdown": edit.markdown, "meta_description": edit.meta_description, "quality": q.to_dict(),
                   "seo": analyze_seo(edit.markdown, blog["primary_keyword"], edit.meta_description,
                                      blog["secondary_keywords"]).to_dict(),
                   "word_count": q.details["seo"]["word_count"], "revision": blog.get("revision", 1) + 1,
                   "edited_by_human": True}
        engine().update_artifact(tid, "blog", updated)
        return updated

    @app.put("/api/threads/{tid}/artifacts/linkedin")
    def edit_linkedin(tid: str, edit: LinkedInEdit) -> Dict[str, Any]:
        state = require_state(tid)
        li = state.get("linkedin")
        if not li:
            raise HTTPException(404, "No LinkedIn post in this conversation")
        q = score_linkedin(edit.text, _voice(state, engine()))
        updated = {**li, "text": edit.text, "char_count": len(edit.text), "quality": q.to_dict(),
                   "revision": li.get("revision", 1) + 1, "edited_by_human": True}
        engine().update_artifact(tid, "linkedin", updated)
        return updated

    @app.put("/api/threads/{tid}/brand-voice")
    def set_voice(tid: str, voice: BrandVoice) -> Dict[str, Any]:
        engine().set_brand_voice(tid, BrandVoiceConfig(**voice.model_dump()))
        return voice.model_dump()

    @app.post("/api/brand-voice/learn")
    def learn_voice(req: LearnVoiceRequest) -> Dict[str, Any]:
        base = BrandVoiceConfig(**req.base.model_dump()) if req.base else registry.base_settings.brand_voice
        return asdict(learn_brand_voice(req.samples, base))

    @app.post("/api/usage")
    def usage(cs: ClientSettings) -> Dict[str, Any]:
        eng = registry.get(cs)
        return {**eng.usage(), "offline": eng.services.is_offline}

    @app.get("/api/threads/{tid}/export/{artifact}/{fmt}")
    def export(tid: str, artifact: str, fmt: str) -> Response:
        state = require_state(tid)
        if fmt not in EXPORT_MIME:
            raise HTTPException(400, f"Unsupported format '{fmt}'")
        topic = state.get("topic") or "content"
        if artifact == "blog" and state.get("blog"):
            b = state["blog"]
            data, name = (_export(b["markdown"], fmt, b["title"], b["meta_description"]), b["slug"])
        elif artifact == "report" and state.get("strategy_report"):
            data, name = _export(state["strategy_report"], fmt, f"Research: {topic}", ""), "research-report"
        elif artifact == "series" and state.get("blog_series"):
            if fmt != "wxr":
                raise HTTPException(400, "Series export supports 'wxr' only")
            data = to_wordpress_wxr([{"title": p["title"], "markdown": p["markdown"], "meta_description": p["meta_description"],
                                      "tags": p["secondary_keywords"]} for p in state["blog_series"]]).encode()
            name = f"{state['blog_series'][0]['slug']}-series"
        elif artifact == "linkedin" and state.get("linkedin"):
            li = state["linkedin"]
            if fmt == "json":
                img = state.get("image") or {}
                data = to_social_json(li["text"], li["hashtags"], Path(img["path"]).name if img.get("path") else None).encode()
            elif fmt == "txt":
                data = li["text"].encode()
            else:
                raise HTTPException(400, "LinkedIn export supports 'txt' and 'json'")
            name = "linkedin-post"
        else:
            raise HTTPException(404, f"No '{artifact}' content to export")
        ext = "xml" if fmt == "wxr" else fmt
        return Response(data, media_type=EXPORT_MIME[fmt],
                        headers={"Content-Disposition": f'attachment; filename="{name}.{ext}"'})

    @app.get("/api/images/{filename}")
    def image(filename: str) -> FileResponse:
        images_dir = (Path(engine().settings.output_dir) / "images").resolve()
        path = (images_dir / filename).resolve()
        if path.parent != images_dir or not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise HTTPException(404, "Image not found")
        return FileResponse(path)

    if serve_frontend and FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> Response:
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            candidate = (FRONTEND_DIST / full_path).resolve()
            if full_path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


def _export(md: str, fmt: str, title: str, meta: str) -> bytes:
    if fmt == "json":
        raise HTTPException(400, "JSON export is available for LinkedIn posts only")
    try:
        return export_content(md, fmt, title, meta)
    except RuntimeError as exc:  # e.g. reportlab missing
        raise HTTPException(501, str(exc)) from exc


app = create_app()
