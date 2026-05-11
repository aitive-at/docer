"""Live smoke test against a local Ollama server.

Skipped automatically if Ollama is unreachable. Marked `live_ollama` so it can
be excluded with `-m "not live_ollama"`.
"""
from __future__ import annotations

import io

import pytest
from django.conf import settings

from apps.extraction.ollama_client import (
    OllamaClient,
    OllamaError,
    encode_image_b64,
)


pytestmark = pytest.mark.live_ollama


def _make_white_png_bytes() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (32, 32), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_ollama_chat_round_trip_with_image():
    client = OllamaClient()
    try:
        client.health()
    except OllamaError as e:
        pytest.skip(f"Ollama not reachable at {settings.OLLAMA_HOST}: {e}")

    model = settings.DOCER_DEFAULT_MODEL
    if not client.has_model(model):
        pytest.skip(f"Configured model {model!r} not installed in Ollama")

    image_b64 = encode_image_b64(_make_white_png_bytes())

    result = client.chat(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a precise vision describer. Output JSON ONLY of the form "
                    '{"answer": "<one word describing the dominant color of the image>"}. '
                    "No prose, no markdown."
                ),
            },
            {
                "role": "user",
                "content": (
                    "What is the dominant color of this image? Respond with the JSON "
                    'object {"answer": "<one word>"}.'
                ),
                "images": [image_b64],
            },
        ],
        format="json",
        options={"temperature": 0.0},
    )

    assert result.raw, "Ollama returned empty content"
    assert isinstance(result.json, dict), (
        f"Ollama did not return a JSON object; raw={result.raw!r}"
    )
    assert "answer" in result.json, f"Missing 'answer' key in {result.json!r}"
    assert isinstance(result.json["answer"], str)
    assert result.json["answer"].strip(), "answer was empty"
    # We don't assert the exact word - small models occasionally call white
    # 'gray' or 'blank'. The shape is what we're testing.
