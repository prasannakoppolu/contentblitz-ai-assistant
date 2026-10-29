"""Image Generation Agent: prompt enhancement, multi-provider generation with
fallbacks (DALL-E 3 -> DALL-E 2 -> Stability -> local placeholder), download,
validation, local storage and metadata management."""
from __future__ import annotations

import base64
import io
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from src.agents.base import BaseAgent
from src.integrations.base import ImageResponse
from src.utils.content_optimization import slugify
from src.utils.quality_validation import score_image
from src.utils.templates import IMAGE_STYLES
from src.workflow.state_management import trace_entry

PROMPT_SYSTEM = """You are an expert art director writing prompts for DALL-E 3. Expand the brief into a single
vivid prompt (60-120 words) specifying: subject, composition, style/medium, colour palette, lighting, mood and
camera/perspective. Marketing-safe, inclusive, no real brands or people, and explicitly 'no text, no logos,
no watermarks'. Return only the prompt."""

NEGATIVE_SUFFIX = "No text, no letters, no logos, no watermarks."
SIZES = {"blog": "1792x1024", "linkedin": "1024x1024", "default": "1024x1024"}


class ImageGenerationAgent(BaseAgent):
    name = "image"
    description = "Enhances prompts and generates on-brand visuals with provider fallbacks and local storage."

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        started = time.time()
        topic = state.get("topic", "")
        platform = self._platform(state)
        blog = self.blog_for(state)
        feedback = state.get("feedback") if state.get("refine_target") == "image" else None
        subject = topic or blog.get("title") or "content marketing"
        original = state.get("user_query", "")

        enhanced = self.enhance_prompt(subject, platform, original, feedback)
        size = SIZES.get(platform, SIZES["default"])
        response = self.services.image.generate_image(enhanced, size=size, style="vivid")
        attempts = list(self.services.image.attempts)
        meta = self.store(response, enhanced, subject, platform)
        meta["original_request"] = original
        meta["attempts"] = attempts
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
        brief = (f"Subject: {subject}\nPlatform: {platform} ({style})\nBrand: {voice.name}, tone {voice.tone}\n"
                 f"User request: {original}" + (f"\nRevision feedback: {feedback}" if feedback else ""))
        try:
            resp = self.llm(brief, PROMPT_SYSTEM, task="image_prompt", tier="fast", temperature=0.8, max_tokens=300,
                            context={"subject": subject, "style": style, "platform": platform})
            prompt = re.sub(r"\s+", " ", resp.text).strip().strip('"')
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
