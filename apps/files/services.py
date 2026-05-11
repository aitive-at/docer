"""File ingest pipeline: per-account dedup, blob storage, page rasterization."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import IO

import pypdfium2
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from PIL import Image

from apps.accounts.models import Account
from apps.files.models import PageImage, StoredFile

logger = logging.getLogger(__name__)

_EXT_TO_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}

_MIME_TO_EXT = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/tiff": "tiff",
}

_SUPPORTED_MIMES = frozenset(_MIME_TO_EXT.keys())


def _media_root() -> Path:
    return Path(settings.MEDIA_ROOT)


def _read_bytes(source: UploadedFile | bytes | IO[bytes]) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, UploadedFile):
        source.seek(0)
        data = source.read()
        source.seek(0)
        return data
    if hasattr(source, "read"):
        if hasattr(source, "seek"):
            try:
                source.seek(0)
            except (OSError, ValueError):
                pass
        data = source.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
        return data
    raise TypeError(f"unsupported_source_type: {type(source)!r}")


def _detect_mime(original_name: str | None, explicit: str | None) -> str:
    if explicit:
        mime = explicit.lower()
        if mime not in _SUPPORTED_MIMES:
            raise ValueError(f"unsupported_mime: {explicit}")
        return mime
    if not original_name:
        raise ValueError("unsupported_mime: missing name and mime")
    ext = Path(original_name).suffix.lower()
    mime = _EXT_TO_MIME.get(ext)
    if not mime:
        raise ValueError(f"unsupported_mime: {ext or original_name!r}")
    return mime


def _account_dir(account: Account, sha256: str) -> Path:
    return _media_root() / account.slug / sha256[:2] / sha256


def _blob_filename(sha256: str, mime: str) -> str:
    ext = _MIME_TO_EXT[mime]
    return f"{sha256}.{ext}"


def absolute_blob_path(stored: StoredFile) -> Path:
    return _media_root() / Path(stored.blob_path)


def absolute_page_path(page: PageImage) -> Path:
    return _media_root() / Path(page.image_path)


def page_image_bytes(page: PageImage) -> bytes:
    return absolute_page_path(page).read_bytes()


def _pdf_page_count(blob: Path) -> int:
    pdf = pypdfium2.PdfDocument(str(blob))
    try:
        return len(pdf)
    finally:
        pdf.close()


def _resolve_source_name(source: UploadedFile | bytes | IO[bytes], explicit: str | None) -> str:
    if explicit:
        return explicit
    if isinstance(source, UploadedFile) and source.name:
        return source.name
    name = getattr(source, "name", None)
    if isinstance(name, str) and name:
        return Path(name).name
    return ""


@transaction.atomic
def ingest_upload(
    account: Account,
    uploaded: UploadedFile | bytes | IO[bytes],
    *,
    original_name: str | None = None,
    mime: str | None = None,
) -> StoredFile:
    name = _resolve_source_name(uploaded, original_name)
    resolved_mime = _detect_mime(name, mime)
    data = _read_bytes(uploaded)
    if not data:
        raise ValueError("empty_upload")

    sha256 = hashlib.sha256(data).hexdigest()

    existing = StoredFile.objects.filter(account=account, sha256=sha256).first()
    if existing is not None:
        logger.debug("ingest_upload: dedup hit account=%s sha256=%s", account.slug, sha256)
        return existing

    target_dir = _account_dir(account, sha256)
    target_dir.mkdir(parents=True, exist_ok=True)
    blob_name = _blob_filename(sha256, resolved_mime)
    blob_abs = target_dir / blob_name
    if not blob_abs.exists():
        blob_abs.write_bytes(data)

    page_count = 0
    if resolved_mime == "application/pdf":
        page_count = _pdf_page_count(blob_abs)
    else:
        page_count = 1

    rel_blob = blob_abs.relative_to(_media_root())
    stored = StoredFile.objects.create(
        account=account,
        sha256=sha256,
        mime=resolved_mime,
        size=len(data),
        blob_path=str(rel_blob),
        original_name=(name or blob_name)[:255],
        page_count=page_count,
    )
    logger.info(
        "ingest_upload: stored account=%s sha256=%s pages=%d mime=%s",
        account.slug,
        sha256,
        page_count,
        resolved_mime,
    )
    return stored


def _pages_dir_for(stored: StoredFile) -> Path:
    blob_abs = absolute_blob_path(stored)
    return blob_abs.parent / "pages"


def _render_pdf_pages(stored: StoredFile, pages_dir: Path, dpi: int) -> list[tuple[int, int, int, Path]]:
    blob_abs = absolute_blob_path(stored)
    pdf = pypdfium2.PdfDocument(str(blob_abs))
    results: list[tuple[int, int, int, Path]] = []
    try:
        scale = dpi / 72.0
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                pil = page.render(scale=scale).to_pil()
            finally:
                page.close()
            out_path = pages_dir / f"{index:04d}.png"
            pil.save(out_path, format="PNG")
            results.append((index, pil.width, pil.height, out_path))
    finally:
        pdf.close()
    return results


def _render_image_page(stored: StoredFile, pages_dir: Path) -> list[tuple[int, int, int, Path]]:
    blob_abs = absolute_blob_path(stored)
    with Image.open(blob_abs) as im:
        im.load()
        rgb = im.convert("RGBA") if im.mode in ("P", "LA") else im
        out_path = pages_dir / "0000.png"
        rgb.save(out_path, format="PNG")
        return [(0, rgb.width, rgb.height, out_path)]


def ensure_page_images(stored: StoredFile) -> list[PageImage]:
    existing = list(stored.pages.all())
    if stored.page_count > 0 and len(existing) == stored.page_count:
        return existing

    pages_dir = _pages_dir_for(stored)
    pages_dir.mkdir(parents=True, exist_ok=True)

    dpi = int(getattr(settings, "DOCER_PDF_RENDER_DPI", 180))

    if stored.mime == "application/pdf":
        rendered = _render_pdf_pages(stored, pages_dir, dpi)
    elif stored.mime in _SUPPORTED_MIMES:
        rendered = _render_image_page(stored, pages_dir)
    else:
        raise ValueError(f"unsupported_mime: {stored.mime}")

    media_root = _media_root()
    with transaction.atomic():
        stored.pages.all().delete()
        objs = [
            PageImage(
                stored_file=stored,
                index=index,
                width=width,
                height=height,
                image_path=str(path.relative_to(media_root)),
            )
            for (index, width, height, path) in rendered
        ]
        PageImage.objects.bulk_create(objs)
        if stored.page_count != len(rendered):
            stored.page_count = len(rendered)
            stored.save(update_fields=["page_count"])

    return list(stored.pages.all())
