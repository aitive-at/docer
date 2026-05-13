"""Post-locate decoders that run AFTER the LLM has identified and located
a field, refining the field value using pixel-level local code.

Architecture
------------
The extractor pipeline has three passes:
  1. Extract  - LLM reads the page image and returns structured JSON values.
  2. Locate   - LLM returns a bbox per field (only for fields with values).
  3. Decode   - For field data_types that have a registered decoder, run the
                decoder against the page image. The decoder is the AUTHORITY
                for what the value is — the LLM is a hint at most.

Each decoder takes raw page PNG bytes plus an optional normalized [0,1]
bbox and returns either a string (the decoded value) or None (decoder did
not recognize anything).

Decoders deliberately receive bytes, not Django model instances, so they
are trivially unit-testable: synthesize a known image with segno, hand
the bytes to the decoder, assert the round-trip.
"""
from __future__ import annotations

import io
from typing import Callable, Iterator

from PIL import Image


def _image_variants(arr) -> Iterator:
    """Yield processed variants of an image to give the QR detector more
    chances. Order: raw → gray → Otsu-binarized → upscaled. cv2's QR
    detector benefits enormously from binarization on scanned-PDF input
    where contrast is washed out.
    """
    import cv2
    import numpy as np  # noqa: F401  (cv2 needs numpy available)

    yield arr  # raw RGB

    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    yield cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)

    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    yield cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)

    h, w = arr.shape[:2]
    if max(h, w) < 800:
        scale = 800.0 / max(h, w)
        upscaled = cv2.resize(
            arr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC
        )
        yield upscaled


def _detectors():
    """Yield available cv2 QR detectors. QRCodeDetectorAruco (opencv 4.7+)
    is significantly more accurate than the legacy QRCodeDetector — but
    its failure modes are different, so we run both and take the first
    non-empty result."""
    import cv2

    if hasattr(cv2, "QRCodeDetectorAruco"):
        yield cv2.QRCodeDetectorAruco()
    yield cv2.QRCodeDetector()


def _decode_qr_from_bytes(img_bytes: bytes, bbox_norm: tuple | None = None) -> str | None:
    """Decode a QR from PNG bytes, optionally cropping to bbox first.

    Strategy: try the (padded) cropped region first if a bbox is given,
    then the whole page. For each region, try several image variants
    (raw, grayscale, Otsu-binarized, upscaled) against every available
    detector. First non-empty match wins.
    """
    import cv2
    import numpy as np

    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = img.size
    full_arr = np.array(img)

    regions: list = []
    if bbox_norm and len(bbox_norm) == 4:
        x0, y0, x1, y1 = bbox_norm
        # Coerce normalized [0,1] to pixel coords; pad ~8% so the QR's
        # required quiet zone is included.
        px0 = max(0, int(x0 * w))
        py0 = max(0, int(y0 * h))
        px1 = min(w, int(x1 * w))
        py1 = min(h, int(y1 * h))
        pad_x = max(8, (px1 - px0) // 12)
        pad_y = max(8, (py1 - py0) // 12)
        cx0 = max(0, px0 - pad_x)
        cy0 = max(0, py0 - pad_y)
        cx1 = min(w, px1 + pad_x)
        cy1 = min(h, py1 + pad_y)
        crop_arr = full_arr[cy0:cy1, cx0:cx1]
        if crop_arr.size:
            regions.append(crop_arr)
    regions.append(full_arr)

    for region in regions:
        for variant in _image_variants(region):
            for detector in _detectors():
                try:
                    data, _points, _straight = detector.detectAndDecode(variant)
                except cv2.error:
                    continue
                if data:
                    return data
    return None


Decoder = Callable[[bytes, tuple | None], "str | None"]

# data_type -> decoder. Returning None from a decoder means "I didn't
# find a value"; the orchestrator clears any LLM marker. To add a new
# field-type decoder, write a function with this signature and register
# it here.
_DECODER_REGISTRY: dict[str, Decoder] = {
    "qr_code": _decode_qr_from_bytes,
}


def get_decoder(data_type: str) -> Decoder | None:
    return _DECODER_REGISTRY.get(data_type)
