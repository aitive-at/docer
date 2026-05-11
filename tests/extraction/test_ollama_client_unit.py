"""Offline unit tests for OllamaClient behaviors that don't require a live server."""
from __future__ import annotations

from unittest.mock import patch

from apps.extraction.ollama_client import OllamaClient


def _fake_tags(*names: str) -> dict:
    return {"models": [{"name": n} for n in names]}


def test_has_model_exact_match():
    client = OllamaClient(host="http://example", timeout=1.0)
    with patch.object(client, "health", return_value=_fake_tags("gemma4:31b", "llama3:8b")):
        assert client.has_model("gemma4:31b") is True
        assert client.has_model("does-not-exist") is False


def test_has_model_strips_cloud_suffix_for_ollama_cloud():
    """Ollama Cloud's /api/tags lists 'gemma4:31b' but /api/chat needs
    'gemma4:31b-cloud'. has_model() must treat them as the same model."""
    client = OllamaClient(host="https://ollama.com", timeout=1.0, api_key="fake")
    with patch.object(client, "health", return_value=_fake_tags("gemma4:31b", "gpt-oss:120b")):
        assert client.has_model("gemma4:31b-cloud") is True
        assert client.has_model("gpt-oss:120b-cloud") is True
        # Still rejects models that genuinely aren't in the catalog.
        assert client.has_model("nonexistent:1b-cloud") is False


def test_has_model_returns_false_when_health_fails():
    from apps.extraction.ollama_client import OllamaUnavailable

    client = OllamaClient(host="http://example", timeout=1.0)
    with patch.object(client, "health", side_effect=OllamaUnavailable("connection refused")):
        assert client.has_model("anything") is False
