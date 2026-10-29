"""Image generation providers beyond DALL-E: Stability AI and a local
placeholder renderer (the final fallback, which never fails)."""
from __future__ import annotations

import hashlib
import io
import textwrap
from typing import Tuple

from src.core.resilience import ProviderError
from src.integrations.base import HTTPProviderMixin, ImageProvider, ImageResponse


class StabilityProvider(HTTPProviderMixin, ImageProvider):
    name = "stability"
    model = "stability"

    def __init__(self, api_key: str, timeout: int = 90, max_retries: int = 2, retry_base_delay: float = 1.0):
        self.api_key = api_key
        self.timeout, self.max_retries, self.retry_base_delay = timeout, max_retries, retry_base_delay

    def generate_image(self, prompt: str, size: str = "1024x1024", style: str = "vivid") -> ImageResponse:
        w, h = _parse_size(size)
        aspect = "1:1" if w == h else ("16:9" if w > h else "9:16")
        resp = self._request(
            "POST", "https://api.stability.ai/v2beta/stable-image/generate/core",
            headers={"Authorization": f"Bearer {self.api_key}", "Accept": "image/*"},
            files={"none": ("", "")},
            data={"prompt": prompt[:2000], "aspect_ratio": aspect, "output_format": "png"},
        )
        if not resp.content:
            raise ProviderError(self.name, "empty image body")
        return ImageResponse(self.name, self.model, image_bytes=resp.content, size=size)


class PlaceholderImageProvider(ImageProvider):
    """Renders a branded gradient card with the prompt's headline locally.

    Used as the last fallback so the workflow always returns a usable visual.
    """

    name = "placeholder"
    model = "local-placeholder"

    def __init__(self, brand_colors: Tuple[str, str] = ("#4F46E5", "#06B6D4")):
        self.brand_colors = brand_colors

    def generate_image(self, prompt: str, size: str = "1024x1024", style: str = "vivid") -> ImageResponse:
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError as exc:  # pragma: no cover - Pillow ships with streamlit
            raise ProviderError(self.name, "Pillow not installed", retryable=False) from exc

        w, h = _parse_size(size)
        # Derive a deterministic hue shift from the prompt so different images look different.
        seed = int(hashlib.md5(prompt.encode()).hexdigest()[:6], 16)
        c1 = _hex_to_rgb(self.brand_colors[0])
        c2 = _hex_to_rgb(self.brand_colors[1])
        shift = seed % 60 - 30
        c2 = tuple(max(0, min(255, c + shift)) for c in c2)

        img = Image.new("RGB", (w, h), c1)
        draw = ImageDraw.Draw(img)
        for y in range(h):
            t = y / max(1, h - 1)
            draw.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)))
        # Decorative circles
        for i in range(5):
            r = (seed >> i) % (w // 4) + w // 10
            cx = (seed * (i + 3)) % w
            cy = (seed * (i + 7)) % h
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255), width=2)

        headline = prompt.split(".")[0][:90]
        try:
            font = ImageFont.load_default(size=max(18, w // 22))
        except TypeError:  # older Pillow
            font = ImageFont.load_default()
        lines = textwrap.wrap(headline, width=26)[:4]
        y0 = h // 2 - len(lines) * (w // 20) // 2
        for i, line in enumerate(lines):
            draw.text((w // 12, y0 + i * (w // 18)), line, fill=(255, 255, 255), font=font)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return ImageResponse(self.name, self.model, image_bytes=buf.getvalue(), size=f"{w}x{h}",
                             revised_prompt=prompt)


def _parse_size(size: str) -> Tuple[int, int]:
    try:
        w, h = (int(x) for x in size.lower().split("x"))
        return w, h
    except ValueError:
        return 1024, 1024


def _hex_to_rgb(color: str) -> Tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
