"""Post-locate decoders that run AFTER the LLM has identified and located
a field, refining the field value using pixel-level local code.

Architecture
------------
The extractor pipeline has three passes:
  1. Extract  - LLM reads the page image and returns structured JSON values.
  2. Locate   - LLM returns a bbox per field, indicating where on the page
                it found the value.
  3. Decode   - For field data_types that have a registered decoder, crop
                the page image at the located bbox and run a purpose-built
                local decoder. Today only qr_code is wired up; the registry
                is the extension point for future barcode/MRZ/signature
                decoders.

Each decoder takes raw page PNG bytes plus a normalized [0,1] bbox and
returns either a string (the decoded value) or None (decoder did not
recognize anything — caller may fall back or surface as an error).

Decoders deliberately receive bytes, not Django model instances, so they
are trivially unit-testable: synthesize a known image with segno, hand
the bytes to the decoder, assert the round-trip.
"""
from __future__ import annotations

import io
from typing import Callable

from PIL import Image


def _decode_qr_from_bytes(img_bytes: bytes, bbox_norm: tuple | None = None) -> str | None:
    """Decode a QR code from a PNG image, optionally cropping to bbox first.

    The bbox is normalized (0..1) in image coordinates. We pad the crop a
    little because the LLM-provided bbox tends to hug the QR tightly and
    QRCodeDetector needs the quiet zone to be present. If the cropped
    region doesn't decode, we fall back to running detection on the full
    image — useful when the bbox is wrong or absent.
    """
    # Deferred import keeps Django apps that don't run extraction (admin
    # commands, tests) from paying the cv2 import cost.
    import cv2
    import numpy as np

    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = img.size

    full_arr = np.array(img)
    detector = cv2.QRCodeDetector()

    if bbox_norm and len(bbox_norm) == 4:
        x0, y0, x1, y1 = bbox_norm
        # Snap to pixel coords; add ~5% padding on each side so the QR's
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
            data, _points, _straight = detector.detectAndDecode(crop_arr)
            if data:
                return data

    # Whole-page fallback. Slower because the detector scans more area,
    # but catches cases where the locator pass gave us the wrong region
    # (or no region at all).
    data, _points, _straight = detector.detectAndDecode(full_arr)
    return data or None


# data_type -> decoder. Returning None from a decoder means "I didn't
# find a value"; the orchestrator keeps the LLM's original_value as a
# marker plus surfaces an error. To add a new field-type decoder, write
# a function with this signature and register it here.
Decoder = Callable[[bytes, tuple | None], "str | None"]

_DECODER_REGISTRY: dict[str, Decoder] = {
    "qr_code": _decode_qr_from_bytes,
}


def get_decoder(data_type: str) -> Decoder | None:
    return _DECODER_REGISTRY.get(data_type)
