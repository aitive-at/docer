"""Pytest configuration shared across all test suites."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Force Huey into immediate mode so enqueue runs the task in-process.
os.environ.setdefault("DOCER_HUEY_IMMEDIATE", "1")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "docer.settings")


@pytest.fixture(autouse=True)
def _isolated_media(tmp_path_factory, settings):
    """Each test gets its own MEDIA_ROOT so blobs don't leak across tests."""
    media_dir = tmp_path_factory.mktemp("media")
    settings.MEDIA_ROOT = str(media_dir)
    return Path(media_dir)


@pytest.fixture
def ollama_required():
    """Skip if Ollama is unreachable. Use sparingly — e2e prefers hard-fail."""
    import httpx
    from django.conf import settings

    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.get(f"{settings.OLLAMA_HOST}/api/tags")
            r.raise_for_status()
    except Exception as e:
        pytest.skip(f"Ollama not reachable at {settings.OLLAMA_HOST}: {e}")
