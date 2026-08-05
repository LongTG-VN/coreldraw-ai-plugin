"""Pluggable image-generation adapters for CorelDRAW template image slots.

The default provider is disabled. Set IMAGE_API_BASE_URL, IMAGE_API_TOKEN, and
IMAGE_MODEL to enable a TikNow-compatible HTTP contract without hard-coding a
third-party service into the CorelDRAW automation layer.
"""

from __future__ import annotations

import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4


class ImageProviderError(RuntimeError):
    """Raised when the configured image provider cannot finish a generation."""


class ImageGenerationProvider(Protocol):
    @property
    def status(self) -> dict[str, Any]: ...

    def generate(
        self,
        prompt: str,
        output_dir: Path,
        *,
        model: str | None = None,
        aspect_ratio: str = "1:1",
    ) -> Path: ...


class DisabledImageProvider:
    @property
    def status(self) -> dict[str, Any]:
        return {
            "enabled": False,
            "provider": "disabled",
            "detail": (
                "Set IMAGE_API_BASE_URL, IMAGE_API_TOKEN and IMAGE_MODEL to "
                "enable remote image generation."
            ),
        }

    def generate(
        self,
        prompt: str,
        output_dir: Path,
        *,
        model: str | None = None,
        aspect_ratio: str = "1:1",
    ) -> Path:
        raise ImageProviderError(
            "Image generation is disabled. Supply image_path or configure the provider."
        )


class TikNowCompatibleImageProvider:
    """Adapter for the public submit/status flow used by TikNow-style plugins."""

    def __init__(
        self,
        base_url: str,
        token: str,
        default_model: str,
        *,
        timeout_seconds: int = 180,
        poll_interval_seconds: float = 3.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds

    @property
    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "provider": "tiknow-compatible",
            "base_url": self.base_url,
            "default_model": self.default_model,
            "timeout_seconds": self.timeout_seconds,
        }

    def _json_request(
        self, path: str, *, method: str = "GET", body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = Request(
            f"{self.base_url}/api{path}",
            data=payload,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - user config
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ImageProviderError(f"Image API request failed: {exc}") from exc

    @staticmethod
    def _first_result_url(value: Any) -> str:
        if isinstance(value, list):
            return str(value[0]) if value else ""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list) and parsed:
                        return str(parsed[0])
                except json.JSONDecodeError:
                    pass
            return stripped
        return ""

    @staticmethod
    def _download(url: str, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            suffix = mimetypes.guess_extension("image/png") or ".png"
        path = output_dir / f"generated_{uuid4().hex[:12]}{suffix}"
        try:
            with urlopen(url, timeout=60) as response, path.open("wb") as target:  # noqa: S310
                target.write(response.read())
        except Exception as exc:
            raise ImageProviderError(f"Cannot download generated image: {exc}") from exc
        if path.stat().st_size <= 0:
            raise ImageProviderError("Generated image download is empty")
        return path

    def generate(
        self,
        prompt: str,
        output_dir: Path,
        *,
        model: str | None = None,
        aspect_ratio: str = "1:1",
    ) -> Path:
        selected_model = model or self.default_model
        if not selected_model:
            raise ImageProviderError("No image model is configured")

        submitted = self._json_request(
            "/generate/submit",
            method="POST",
            body={
                "type": "image",
                "model": selected_model,
                "prompt": prompt,
                "aspectRatio": aspect_ratio,
                "mode": "CorelDRAW template plugin",
            },
        )
        task_id = str((submitted.get("data") or {}).get("taskId") or "")
        if submitted.get("code") != 0 or not task_id:
            raise ImageProviderError(
                str(submitted.get("message") or "Image generation submit failed")
            )

        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            status = self._json_request(f"/generate/status/{task_id}")
            data = status.get("data") or {}
            state = data.get("status")
            if status.get("code") == 0 and state == "succeeded":
                result_url = self._first_result_url(data.get("resultUrl"))
                if not result_url:
                    raise ImageProviderError("Provider returned no result URL")
                return self._download(result_url, output_dir)
            if state == "failed":
                raise ImageProviderError(
                    str(data.get("failureReason") or "Image generation failed")
                )
            time.sleep(self.poll_interval_seconds)

        raise ImageProviderError(
            f"Image generation timed out after {self.timeout_seconds} seconds"
        )


def build_image_provider() -> ImageGenerationProvider:
    base_url = os.getenv("IMAGE_API_BASE_URL", "").strip()
    token = os.getenv("IMAGE_API_TOKEN", "").strip()
    model = os.getenv("IMAGE_MODEL", "").strip()
    if not base_url or not token or not model:
        return DisabledImageProvider()
    timeout = int(os.getenv("IMAGE_TIMEOUT_SECONDS", "180"))
    poll = float(os.getenv("IMAGE_POLL_INTERVAL_SECONDS", "3"))
    return TikNowCompatibleImageProvider(
        base_url,
        token,
        model,
        timeout_seconds=timeout,
        poll_interval_seconds=poll,
    )
