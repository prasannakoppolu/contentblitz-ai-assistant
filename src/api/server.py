"""FastAPI backend for the React UI.

Run (dev):   uvicorn src.api.server:app --reload --port 8000
Run (prod):  uvicorn src.api.server:app --host 0.0.0.0 --port 8000   (serves frontend/dist too)

Endpoints (JSON unless noted). Everything except health, config and /api/auth/*
needs a signed-in session (HttpOnly ``cb_session`` cookie); /api/admin/* also
needs an email listed in ``ADMIN_EMAILS``.

    GET  /api/health
    GET  /api/config                                   customer-safe defaults (brand voice)
    POST /api/auth/login/start     {email}             404 not_registered | code sent
    POST /api/auth/signup/start    {email, name}       409 already_registered | code sent
    POST /api/auth/verify          {email, code, purpose}  -> user, sets the session cookie
    POST /api/auth/logout
    GET  /api/auth/me                                  current user or 401
    GET  /api/threads                                  the caller's conversations
    POST /api/threads                                  -> {thread_id}
    PATCH/DELETE /api/threads/{tid}                    rename / remove from the list
    GET  /api/threads/{tid}/state                      UI-safe conversation state
    POST /api/threads/{tid}/chat                       Server-Sent Events: start / node / done / error
    PUT  /api/threads/{tid}/artifacts/blog             human edit -> re-score -> persist
    PUT  /api/threads/{tid}/artifacts/linkedin
    PUT  /api/threads/{tid}/brand-voice
    POST /api/brand-voice/learn                        derive a voice from samples
    GET  /api/threads/{tid}/export/{artifact}/{fmt}    file download
    GET  /api/images/{filename}                        generated images
    GET  /api/admin/overview                           settings, providers, usage, users (admin)
    PUT  /api/admin/settings                           offline mode, provider priority, quality bar (admin)
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

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.api.schemas import (
    BlogEdit,
    BrandVoice,
    ChatRequest,
    ClientSettings,
    LearnVoiceRequest,
    LinkedInEdit,
    LoginStart,
    ServerSettings,
    SignupStart,
    ThreadRename,
    VerifyCode,
)
from src.auth import AuthError, AuthService, AuthStore, mailer_from_env, parse_admins
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

SESSION_COOKIE = "cb_session"
SETTINGS_KEY = "server_settings"


def _truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _title_from(message: str) -> str:
    title = " ".join(message.split())
    return title if len(title) <= 60 else title[:57].rstrip() + "…"


def create_app(base_overrides: Optional[Dict[str, Any]] = None, env: Optional[str] = None,
               serve_frontend: bool = True, auth: Optional[AuthService] = None) -> FastAPI:
    registry = EngineRegistry(base_overrides, env)
    if auth is None:
        db_path = os.getenv("CONTENTBLITZ_AUTH_DB", str(PROJECT_ROOT / "data" / "contentblitz_auth.sqlite"))
        auth = AuthService(AuthStore(db_path), mailer_from_env(), parse_admins(os.getenv("ADMIN_EMAILS", "")),
                           expose_dev_codes=_truthy(os.getenv("CONTENTBLITZ_AUTH_DEV_CODES")))
    if auth.mailer.delivery == "console":
        logger.warning("SMTP_HOST is not set: sign-in codes are printed to this log instead of emailed.")
    secure_cookie = _truthy(os.getenv("CONTENTBLITZ_COOKIE_SECURE"))

    app = FastAPI(title="ContentBlitz API", version="2.1.0",
                  description="Multi-agent AI content marketing assistant (LangGraph).")
    app.state.registry = registry
    app.state.auth = auth
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

    @app.exception_handler(AuthError)
    def _auth_error(_req: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse({"detail": exc.message, "code": exc.code, **exc.extra}, status_code=exc.status)

    # ----------------------------------------------------------- settings
    def server_settings() -> ServerSettings:
        return ServerSettings(**auth.store.get_json(SETTINGS_KEY, {}))

    def detected_keys() -> list:
        return [p for p in KEY_PROVIDERS if registry.base_settings.has_key(p)]

    def effective(ss: Optional[ServerSettings] = None) -> ClientSettings:
        ss = ss or server_settings()
        base = registry.base_settings
        return ClientSettings(
            demo_mode=ss.demo_mode if ss.demo_mode is not None else (base.use_mock or not detected_keys()),
            llm_primary=ss.llm_primary, research_primary=ss.research_primary,
            quality_threshold=ss.quality_threshold)

    def engine() -> ContentBlitzEngine:
        return registry.get(effective())

    # ------------------------------------------------------- dependencies
    def current_user(request: Request) -> Dict[str, Any]:
        user = auth.user_for_token(request.cookies.get(SESSION_COOKIE))
        if not user:
            raise AuthError(401, "not_signed_in", "Please sign in to continue.")
        return user

    def admin_user(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
        if not auth.is_admin(user):
            raise AuthError(403, "admin_only", "This page is for ContentBlitz administrators.")
        return user

    def owned(tid: str, user: Dict[str, Any], claim: bool = False) -> None:
        """404 unless the caller owns the thread. With ``claim``, an unowned id becomes theirs."""
        owner = auth.store.thread_owner(tid)
        if owner == user["id"]:
            return
        if owner is None and claim:
            auth.store.claim_thread(tid, user["id"])
            return
        raise HTTPException(404, "Unknown conversation")

    def require_state(tid: str, user: Dict[str, Any]) -> Dict[str, Any]:
        owned(tid, user)
        state = engine().get_state(tid)
        if not state:
            raise HTTPException(404, "Unknown thread or no messages yet")
        return state

    # ------------------------------------------------------------- public
    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        return {"status": "ok", "time": time.time()}

    @app.get("/api/config")
    def config() -> Dict[str, Any]:
        s = registry.base_settings
        return {"brand_voice": asdict(s.brand_voice), "env": s.env, "email_delivery": auth.mailer.delivery}

    # --------------------------------------------------------------- auth
    def _set_session(resp: Response, token: str) -> None:
        resp.set_cookie(SESSION_COOKIE, token, max_age=auth.session_ttl_s, httponly=True, samesite="lax",
                        secure=secure_cookie, path="/")

    @app.post("/api/auth/login/start")
    def login_start(req: LoginStart) -> Dict[str, Any]:
        return auth.start_login(req.email)

    @app.post("/api/auth/signup/start")
    def signup_start(req: SignupStart) -> Dict[str, Any]:
        return auth.start_signup(req.email, req.name)

    @app.post("/api/auth/verify")
    def verify(req: VerifyCode, response: Response) -> Dict[str, Any]:
        user, token = auth.verify(req.email, req.code, req.purpose)
        _set_session(response, token)
        return {"user": auth.public_user(user)}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response) -> Dict[str, bool]:
        auth.logout(request.cookies.get(SESSION_COOKIE))
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/auth/me")
    def me(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
        return {"user": auth.public_user(user)}

    # ------------------------------------------------------------ threads
    @app.get("/api/threads")
    def list_threads(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
        return {"threads": auth.store.threads_for(user["id"])}

    @app.post("/api/threads")
    def new_thread(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, str]:
        tid = ContentBlitzEngine.new_thread_id()
        auth.store.claim_thread(tid, user["id"])
        return {"thread_id": tid}

    @app.patch("/api/threads/{tid}")
    def rename_thread(tid: str, req: ThreadRename, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, str]:
        owned(tid, user)
        auth.store.rename_thread(tid, req.title.strip())
        return {"thread_id": tid, "title": req.title.strip()}

    @app.delete("/api/threads/{tid}")
    def delete_thread(tid: str, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, bool]:
        owned(tid, user)
        auth.store.delete_thread(tid)
        return {"ok": True}

    @app.get("/api/threads/{tid}/state")
    def get_state(tid: str, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
        owned(tid, user)
        return public_state(engine().get_state(tid), tid)

    @app.post("/api/threads/{tid}/chat")
    def chat(tid: str, req: ChatRequest, user: Dict[str, Any] = Depends(current_user)) -> StreamingResponse:
        owned(tid, user, claim=True)
        message = req.message.strip()
        auth.store.touch_thread(tid, _title_from(message))
        eng = engine()

        def events() -> Iterator[str]:
            yield _sse("start", {"thread_id": tid})
            try:
                for node, update in eng.stream(message, tid):
                    trace = [t for t in (update.get("trace") or []) if t.get("agent") == node][-1:]
                    payload: Dict[str, Any] = {"node": node, "trace": trace[0] if trace else None}
                    if node == "query_handler":
                        payload["plan"] = update.get("plan") or []
                        payload["topic"] = update.get("topic") or ""
                    yield _sse("node", payload)
                auth.store.touch_thread(tid)
                yield _sse("done", public_state(eng.get_state(tid), tid))
            except Exception:  # noqa: BLE001 - report to client instead of dropping the stream
                logger.exception("chat stream failed")
                yield _sse("error", {"message": "Something went wrong while the agents were working"})

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.put("/api/threads/{tid}/artifacts/blog")
    def edit_blog(tid: str, edit: BlogEdit, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
        state = require_state(tid, user)
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
    def edit_linkedin(tid: str, edit: LinkedInEdit, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
        state = require_state(tid, user)
        li = state.get("linkedin")
        if not li:
            raise HTTPException(404, "No LinkedIn post in this conversation")
        q = score_linkedin(edit.text, _voice(state, engine()))
        updated = {**li, "text": edit.text, "char_count": len(edit.text), "quality": q.to_dict(),
                   "revision": li.get("revision", 1) + 1, "edited_by_human": True}
        engine().update_artifact(tid, "linkedin", updated)
        return updated

    @app.put("/api/threads/{tid}/brand-voice")
    def set_voice(tid: str, voice: BrandVoice, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
        owned(tid, user, claim=True)
        engine().set_brand_voice(tid, BrandVoiceConfig(**voice.model_dump()))
        return voice.model_dump()

    @app.post("/api/brand-voice/learn")
    def learn_voice(req: LearnVoiceRequest, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
        base = BrandVoiceConfig(**req.base.model_dump()) if req.base else registry.base_settings.brand_voice
        return asdict(learn_brand_voice(req.samples, base))

    @app.get("/api/threads/{tid}/export/{artifact}/{fmt}")
    def export(tid: str, artifact: str, fmt: str, user: Dict[str, Any] = Depends(current_user)) -> Response:
        state = require_state(tid, user)
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
    def image(filename: str, user: Dict[str, Any] = Depends(current_user)) -> FileResponse:
        images_dir = (Path(engine().settings.output_dir) / "images").resolve()
        path = (images_dir / filename).resolve()
        if path.parent != images_dir or not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise HTTPException(404, "Image not found")
        return FileResponse(path)

    # -------------------------------------------------------------- admin
    @app.get("/api/admin/overview")
    def admin_overview(_admin: Dict[str, Any] = Depends(admin_user)) -> Dict[str, Any]:
        ss = server_settings()
        eff = effective(ss)
        eng = registry.get(eff)
        s = eng.settings
        users = auth.store.list_users()
        return {
            "settings": ss.model_dump(),
            "effective": {"demo_mode": eff.demo_mode, "llm_primary": s.llm_order[0] if s.llm_order else None,
                          "research_primary": s.research_order[0] if s.research_order else None,
                          "quality_threshold": s.quality_threshold},
            "detected_keys": detected_keys(),
            "key_providers": KEY_PROVIDERS,
            "fallback_chains": {"llm": s.llm_order, "research": s.research_order, "image": s.image_order},
            "usage": {**eng.usage(), "offline": eng.services.is_offline},
            "tracing": s.tracing,
            "email_delivery": auth.mailer.delivery,
            "env": s.env,
            "users": [{**{k: u[k] for k in ("email", "name", "created_at", "last_login", "conversations")},
                       "is_admin": auth.is_admin(u)} for u in users],
            "totals": {"users": len(users), "conversations": auth.store.count_threads()},
        }

    @app.put("/api/admin/settings")
    def admin_settings(ss: ServerSettings, _admin: Dict[str, Any] = Depends(admin_user)) -> Dict[str, Any]:
        auth.store.set_json(SETTINGS_KEY, ss.model_dump())
        return {"settings": ss.model_dump()}

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
