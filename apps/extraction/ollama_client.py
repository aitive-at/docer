"""Thin httpx wrapper around the local Ollama HTTP API.

Spec contract: see REQUIREMENTS.md sec 3.4 + IMPLEMENTATION_PLAN.md sec 5
("apps/extraction"). This module is intentionally pure Python over HTTP - it
does not import Django models. Settings (host/timeout/default-model) are read
lazily from `django.conf.settings` so the client may also be constructed with
explicit overrides for tests.
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class OllamaResult:
    """Outcome of a single /api/chat call."""

    raw: str
    json: dict | list | None
    model: str
    duration_ms: int


class OllamaError(Exception):
    """Base class for Ollama-related failures."""


class OllamaUnavailable(OllamaError):
    """Could not reach the configured Ollama host (DNS / connection refused)."""


class OllamaModelMissing(OllamaError):
    """Ollama responded with 404 or 'model not found' for the requested model."""


class OllamaTimeout(OllamaError):
    """Request exceeded the configured timeout."""


def encode_image_b64(path_or_bytes: str | Path | bytes) -> str:
    """Return base64-encoded raw bytes (no data: prefix), as Ollama wants."""
    if isinstance(path_or_bytes, (str, Path)):
        data = Path(path_or_bytes).read_bytes()
    elif isinstance(path_or_bytes, (bytes, bytearray, memoryview)):
        data = bytes(path_or_bytes)
    else:
        raise TypeError(
            f"encode_image_b64: expected path or bytes, got {type(path_or_bytes).__name__}"
        )
    return base64.b64encode(data).decode("ascii")


class OllamaClient:
    """Small synchronous Ollama HTTP client."""

    def __init__(
        self,
        host: str | None = None,
        timeout: float | None = None,
        api_key: str | None = None,
    ):
        self._host = host
        self._timeout = timeout
        self._api_key = api_key

    @property
    def host(self) -> str:
        if self._host is not None:
            return self._host
        from django.conf import settings

        return settings.OLLAMA_HOST

    @property
    def timeout(self) -> float:
        if self._timeout is not None:
            return self._timeout
        from django.conf import settings

        return float(settings.DOCER_OLLAMA_TIMEOUT)

    @property
    def api_key(self) -> str | None:
        if self._api_key is not None:
            return self._api_key or None
        from django.conf import settings

        return getattr(settings, "OLLAMA_API_KEY", "") or None

    # ------------------------------------------------------------------ helpers

    def _client(self) -> httpx.Client:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return httpx.Client(
            base_url=self.host.rstrip("/"),
            timeout=self.timeout,
            headers=headers or None,
        )

    @staticmethod
    def _is_unavailable(exc: Exception) -> bool:
        return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError))

    # ------------------------------------------------------------------ api

    def health(self) -> dict:
        """Return /api/tags response or raise OllamaUnavailable."""
        try:
            with self._client() as c:
                r = c.get("/api/tags")
                r.raise_for_status()
                return r.json()
        except httpx.TimeoutException as e:
            raise OllamaTimeout(f"timeout fetching /api/tags from {self.host}: {e}") from e
        except httpx.HTTPError as e:
            raise OllamaUnavailable(f"cannot reach Ollama at {self.host}: {e}") from e

    def has_model(self, model: str) -> bool:
        try:
            tags = self.health()
        except OllamaError:
            return False
        names = {m.get("name") for m in tags.get("models", [])}
        if model in names:
            return True
        # Ollama Cloud quirk: /api/chat requires the "-cloud" routing suffix
        # (e.g. "gemma4:31b-cloud") but /api/tags lists canonical names
        # ("gemma4:31b"). Treat the suffix as an alias for the base tag.
        if model.endswith("-cloud") and model.removesuffix("-cloud") in names:
            return True
        return False

    def chat(
        self,
        *,
        model: str,
        messages: list[dict],
        format: str | dict | None = "json",
        options: dict | None = None,
    ) -> OllamaResult:
        """POST /api/chat with stream=False.

        Each message may contain an `images` list whose entries are base64
        strings (use `encode_image_b64`). When `format == "json"` (or a JSON
        schema dict) we attempt to parse the assistant content as JSON and
        return it via `OllamaResult.json`; on parse failure `json` is None
        and the raw text is preserved on the result.
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if format is not None:
            payload["format"] = format
        if options:
            payload["options"] = options

        started = time.monotonic()
        try:
            with self._client() as c:
                r = c.post("/api/chat", json=payload)
        except httpx.TimeoutException as e:
            raise OllamaTimeout(
                f"timeout calling /api/chat on {self.host} (timeout={self.timeout}s): {e}"
            ) from e
        except httpx.HTTPError as e:
            if self._is_unavailable(e):
                raise OllamaUnavailable(f"cannot reach Ollama at {self.host}: {e}") from e
            raise OllamaError(f"transport error talking to Ollama: {e}") from e

        duration_ms = int((time.monotonic() - started) * 1000)

        if r.status_code == 404:
            raise OllamaModelMissing(
                f"Ollama returned 404 for model={model!r}: {r.text[:200]}"
            )
        if r.status_code >= 400:
            text = r.text or ""
            if "model" in text.lower() and "not found" in text.lower():
                raise OllamaModelMissing(
                    f"Ollama reports model {model!r} not found: {text[:200]}"
                )
            raise OllamaError(f"Ollama HTTP {r.status_code}: {text[:500]}")

        try:
            body = r.json()
        except json.JSONDecodeError as e:
            raise OllamaError(f"Ollama response was not JSON: {e}: {r.text[:200]}") from e

        message = body.get("message") or {}
        content = message.get("content", "") or ""

        # Tool calls fall back to a JSON dump of their arguments so callers
        # always see something on `raw` even when content is empty.
        tool_calls = message.get("tool_calls") or []
        if not content and tool_calls:
            try:
                content = json.dumps(tool_calls[0].get("function", {}).get("arguments", {}))
            except (TypeError, ValueError):
                content = ""

        parsed: dict | list | None = None
        if format is not None and content:
            try:
                loaded = json.loads(content)
                if isinstance(loaded, (dict, list)):
                    parsed = loaded
            except json.JSONDecodeError:
                parsed = None

        return OllamaResult(
            raw=content,
            json=parsed,
            model=body.get("model", model),
            duration_ms=duration_ms,
        )
