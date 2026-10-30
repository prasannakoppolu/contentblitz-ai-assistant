"""Image Generation Agent: prompt enhancement, multi-provider generation with
fallbacks (DALL-E 3 -> DALL-E 2 -> Stability -> local placeholder), download,
validation, local storage and metadata management.

Subgraph::

    START → enhance → generate → store ─┬─(image valid)──────────────→ END
                                        └─(download/decode failed)→ placeholder → END

``enhance`` is a LangChain prompt chain; ``generate`` walks the image provider chain.
"""
from __future__ import annotations

import base64
import io
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

import requests
from langgraph.graph import END, START, StateGraph

from src.agents.base import BaseAgent
from src.agents.prompts import IMAGE_PROMPT
from src.integrations.base import ImageResponse
from src.integrations.image_clients import PlaceholderImageProvider
from src.utils.content_optimization import slugify
from src.utils.quality_validation import score_image
from src.utils.templates import IMAGE_STYLES
from src.workflow.state_management import trace_entry

NEGATIVE_SUFFIX = "No text, no letters, no logos, no watermarks."
SIZES = {"blog": "1792x1024", "linkedin": "1024x1024", "default": "1024x1024"}


class ImageState(TypedDict, total=False):
    subject: str
    platform: str
    request: str
    feedback: Optional[str]
    prompt: str
    response: Any
    attempts: List[Dict[str, Any]]
    meta: Dict[str, Any]


class ImageGenerationAgent(BaseAgent):
    name = "image"
    description = "Enhances prompts and generates on-brand visuals with provider fallbacks and local storage."

    def build_graph(self):
        g = StateGraph(ImageState)
        g.add_node("enhance", lambda s: {"prompt": self.enhance_prompt(s["subject"], s["platform"], s.get("request", ""),
                                                                         s.get("feedback"))})
        g.add_node("generate", self._generate)
        g.add_node("store", lambda s: {"meta": self.store(s["response"], s["prompt"], s["subject"], s["platform"])})
        g.add_node("placeholder", self._placeholder)
        g.add_edge(START, "enhance")
        g.add_edge("enhance", "generate")
        g.add_edge("generate", "store")
        g.add_conditional_edges("store", lambda s: "placeholder" if not s["meta"].get("path") else END,
                                ["placeholder", END])
        g.add_edge("placeholder", END)
        return g.compile()

    def _generate(self, s: ImageState) -> Dict[str, Any]:
        size = SIZES.get(s["platform"], SIZES["default"])
        response = self.services.image.generate_image(s["prompt"], size=size, style="vivid")
        return {"response": response, "attempts": list(self.services.image.attempts)}

    def _placeholder(self, s: ImageState) -> Dict[str, Any]:
        """The provider returned something we couldn't download or decode: render locally instead."""
        failed = s["response"].provider
        response = PlaceholderImageProvider().generate_image(s["prompt"], size=SIZES.get(s["platform"], SIZES["default"]))
        attempts = s.get("attempts", []) + [{"provider": failed, "ok": False, "error": "image download or validation failed"},
                                            {"provider": "placeholder", "ok": True}]
        return {"meta": self.store(response, s["prompt"], s["subject"], s["platform"]), "attempts": attempts}

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        started = time.time()
        blog = self.blog_for(state)
        platform = self._platform(state)
        out = self.invoke_graph({
            "subject": state.get("topic", "") or blog.get("title") or "content marketing", "platform": platform,
            "request": state.get("user_query", ""),
            "feedback": state.get("feedback") if state.get("refine_target") == "image" else None})
        meta = dict(out["meta"])
        attempts = out.get("attempts", [])
        meta.update(original_request=state.get("user_query", ""), attempts=attempts)
        meta["quality"] = score_image(meta).to_dict()
        fell_back = any(not a["ok"] for a in attempts)
        detail = f"{meta['provider']} {meta['width']}x{meta['height']}" + (" (after fallback)" if fell_back else "")
        return {"image": meta, "trace": state.get("trace", []) + [trace_entry(self.name, "ok", detail, meta["provider"], started)]}

    # ------------------------------------------------------------------ steps
    def _platform(self, state: Dict[str, Any]) -> str:
        q = (state.get("user_query") or "").lower()
        if "linkedin" in q:
            return "linkedin"
        if "blog" in q or "hero" in q or "header" in q or "blog" in (state.get("plan") or []):
            return "blog"
        return "linkedin" if "linkedin" in (state.get("plan") or []) else "default"

    def enhance_prompt(self, subject: str, platform: str, original: str = "", feedback: Optional[str] = None) -> str:
        voice = self.settings.brand_voice
        style = IMAGE_STYLES.get(platform, IMAGE_STYLES["default"])
        try:
            result = self.ask(IMAGE_PROMPT, {"subject": subject, "platform": platform, "style": style, "brand": voice.name,
                                             "tone": voice.tone, "request": original,
                                             "feedback": f"\nRevision feedback: {feedback}" if feedback else ""},
                              task="image_prompt", tier="fast", temperature=0.8, max_tokens=300,
                              context={"subject": subject, "style": style, "platform": platform})
            prompt = re.sub(r"\s+", " ", result.text).strip().strip('"')
        except Exception:  # noqa: BLE001
            prompt = f"{subject}. {style}, professional, clean composition, brand colours indigo and teal, soft lighting."
        if "no text" not in prompt.lower():
            prompt = f"{prompt} {NEGATIVE_SUFFIX}"
        return prompt[:1500]

    def store(self, response: ImageResponse, prompt: str, subject: str, platform: str) -> Dict[str, Any]:
        out_dir = Path(self.settings.output_dir) / "images"
        out_dir.mkdir(parents=True, exist_ok=True)
        data = self._image_bytes(response)
        width = height = 0
        fmt = None
        if data:
            try:
                from PIL import Image

                with Image.open(io.BytesIO(data)) as img:
                    img.verify()
                with Image.open(io.BytesIO(data)) as img:
                    width, height, fmt = img.width, img.height, img.format
            except Exception:  # noqa: BLE001 - invalid image
                data = None
        stem = f"{slugify(subject)[:50] or 'image'}-{int(time.time())}"
        path = None
        if data:
            ext = {"JPEG": "jpg", "WEBP": "webp"}.get(fmt or "", "png")
            path = out_dir / f"{stem}.{ext}"
            path.write_bytes(data)
        meta = {
            "provider": response.provider, "model": response.model, "url": response.url,
            "path": str(path) if path else None, "width": width, "height": height, "format": fmt,
            "size_requested": response.size, "enhanced_prompt": prompt, "revised_prompt": response.revised_prompt,
            "subject": subject, "platform": platform, "alt_text": f"Illustration: {subject}", "created_at": time.time(),
        }
        (out_dir / f"{stem}.json").write_text(json.dumps(meta, indent=2, default=str))
        return meta

    def _image_bytes(self, response: ImageResponse) -> Optional[bytes]:
        if response.image_bytes:
            return response.image_bytes
        if response.b64_data:
            return base64.b64decode(response.b64_data)
        if response.url:
            try:
                r = requests.get(response.url, timeout=60)
                r.raise_for_status()
                return r.content
            except requests.RequestException:
                return None
        return None
