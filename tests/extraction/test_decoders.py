"""Unit tests for post-locate decoders (apps/extraction/decoders.py).

These exercise the decoder functions in isolation from Django models —
synthesize a known image, hand the bytes to the decoder, assert the
round-trip. The orchestration that wires decoders into the Scan pipeline
is exercised by integration tests elsewhere.
"""
from __future__ import annotations

import io

import segno

from apps.extraction.decoders import _decode_qr_from_bytes, get_decoder


def _make_qr_png(text: str, *, scale: int = 8, border: int = 4) -> bytes:
    """Render `text` as a QR code and return the PNG bytes."""
    qr = segno.make(text, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=scale, border=border)
    return buf.getvalue()


def test_qr_decoder_round_trip_full_image():
    """Decoding a freshly-generated QR with no bbox must recover the payload."""
    payload = "https://example.com/pay?inv=12345"
    img_bytes = _make_qr_png(payload)
    assert _decode_qr_from_bytes(img_bytes, bbox_norm=None) == payload


def test_qr_decoder_round_trip_with_full_bbox():
    """When the bbox covers the entire image, decode still succeeds."""
    payload = "BEGIN:VCARD\nVERSION:3.0\nFN:Alice\nEND:VCARD"
    img_bytes = _make_qr_png(payload)
    assert _decode_qr_from_bytes(img_bytes, bbox_norm=(0.0, 0.0, 1.0, 1.0)) == payload


def test_qr_decoder_falls_back_to_whole_page_when_bbox_misses():
    """If the bbox points at a region with no QR, the decoder should retry
    on the full image. Otherwise a bad bbox would permanently lose the QR."""
    payload = "https://example.com/fallback?test=1"
    img_bytes = _make_qr_png(payload)
    # bbox points at top-left 5% — the QR is centered, so cropped region has no QR.
    bad_bbox = (0.0, 0.0, 0.05, 0.05)
    assert _decode_qr_from_bytes(img_bytes, bbox_norm=bad_bbox) == payload


def test_qr_decoder_returns_none_when_no_qr_present():
    """A solid-color image with no QR must return None — caller surfaces a
    soft error rather than getting a misleading false-positive string."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), color="white").save(buf, format="PNG")
    assert _decode_qr_from_bytes(buf.getvalue(), bbox_norm=None) is None


def test_registry_routes_qr_code_to_decoder():
    """The qr_code data_type must resolve to a decoder; unknown types resolve
    to None (caller skips them)."""
    assert get_decoder("qr_code") is _decode_qr_from_bytes
    assert get_decoder("string") is None
    assert get_decoder("currency_amount") is None
