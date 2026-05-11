"""Tests for apps.files.services ingest pipeline."""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.accounts.models import User
from apps.accounts.services import create_personal_account
from apps.files.models import PageImage, StoredFile
from apps.files.services import (
    absolute_blob_path,
    absolute_page_path,
    ensure_page_images,
    ingest_upload,
    page_image_bytes,
)

PDF_FIXTURE = Path(__file__).resolve().parent.parent / "data" / "Rechnung 240010439.pdf"


@pytest.fixture
def pdf_bytes() -> bytes:
    return PDF_FIXTURE.read_bytes()


@pytest.fixture
def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (24, 16), color=(10, 200, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _make_user_and_account(email: str, name: str):
    user = User.objects.create_user(username=email, email=email, password="testpw123")
    account = create_personal_account(user, base_name=name)
    return user, account


@pytest.mark.django_db
def test_ingest_pdf_creates_stored_file(pdf_bytes):
    _, account = _make_user_and_account("alice@example.com", "Alice")

    upload = SimpleUploadedFile(
        "Rechnung 240010439.pdf", pdf_bytes, content_type="application/pdf"
    )
    stored = ingest_upload(account, upload)

    assert isinstance(stored, StoredFile)
    assert stored.account_id == account.id
    assert stored.sha256 and len(stored.sha256) == 64
    assert stored.size == len(pdf_bytes)
    assert stored.page_count > 0
    assert stored.mime == "application/pdf"
    blob = absolute_blob_path(stored)
    assert blob.is_file()
    assert blob.read_bytes() == pdf_bytes
    # Path must live under MEDIA_ROOT/<slug>/<sha2>/<sha>/<sha>.pdf
    rel = Path(stored.blob_path)
    parts = rel.parts
    assert parts[0] == account.slug
    assert parts[1] == stored.sha256[:2]
    assert parts[2] == stored.sha256
    assert parts[3] == f"{stored.sha256}.pdf"


@pytest.mark.django_db
def test_reingest_same_bytes_same_account_dedups(pdf_bytes):
    _, account = _make_user_and_account("bob@example.com", "Bob")

    first = ingest_upload(
        account,
        SimpleUploadedFile("doc.pdf", pdf_bytes, content_type="application/pdf"),
    )
    blob_path = absolute_blob_path(first)
    mtime_before = blob_path.stat().st_mtime_ns

    second = ingest_upload(
        account,
        SimpleUploadedFile("doc-renamed.pdf", pdf_bytes, content_type="application/pdf"),
    )

    assert second.pk == first.pk
    assert StoredFile.objects.filter(account=account, sha256=first.sha256).count() == 1
    # Blob should not have been rewritten.
    assert blob_path.stat().st_mtime_ns == mtime_before


@pytest.mark.django_db
def test_per_account_dedup_independent(pdf_bytes):
    _, acc1 = _make_user_and_account("c1@example.com", "Acc One")
    _, acc2 = _make_user_and_account("c2@example.com", "Acc Two")

    s1 = ingest_upload(acc1, pdf_bytes, original_name="doc.pdf")
    s2 = ingest_upload(acc2, pdf_bytes, original_name="doc.pdf")

    assert s1.pk != s2.pk
    assert s1.sha256 == s2.sha256
    assert s1.account_id == acc1.id
    assert s2.account_id == acc2.id
    # Two different blob locations.
    assert absolute_blob_path(s1) != absolute_blob_path(s2)
    assert absolute_blob_path(s1).is_file()
    assert absolute_blob_path(s2).is_file()


@pytest.mark.django_db
def test_ensure_page_images_idempotent(pdf_bytes):
    _, account = _make_user_and_account("d@example.com", "D")
    stored = ingest_upload(account, pdf_bytes, original_name="r.pdf")

    pages_first = ensure_page_images(stored)
    assert len(pages_first) == stored.page_count
    assert all(isinstance(p, PageImage) for p in pages_first)
    for idx, page in enumerate(pages_first):
        assert page.index == idx
        path = absolute_page_path(page)
        assert path.is_file()
        assert path.suffix == ".png"
        assert path.name == f"{idx:04d}.png"
        assert page.width > 0 and page.height > 0
        # Sanity-check the bytes are a real PNG.
        data = page_image_bytes(page)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    # Capture mtimes; second call must not rewrite.
    mtimes = {p.id: absolute_page_path(p).stat().st_mtime_ns for p in pages_first}
    pages_second = ensure_page_images(stored)
    assert [p.id for p in pages_second] == [p.id for p in pages_first]
    for p in pages_second:
        assert absolute_page_path(p).stat().st_mtime_ns == mtimes[p.id]


@pytest.mark.django_db
def test_ingest_png_yields_single_page(png_bytes):
    _, account = _make_user_and_account("e@example.com", "E")

    stored = ingest_upload(account, png_bytes, original_name="pic.png")
    assert stored.mime == "image/png"
    assert stored.page_count == 1
    assert absolute_blob_path(stored).is_file()

    pages = ensure_page_images(stored)
    assert len(pages) == 1
    page = pages[0]
    assert page.index == 0
    assert page.width == 24
    assert page.height == 16
    assert absolute_page_path(page).is_file()
    assert page_image_bytes(page)[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.django_db
def test_unsupported_mime_rejected():
    _, account = _make_user_and_account("f@example.com", "F")
    with pytest.raises(ValueError, match="unsupported_mime"):
        ingest_upload(account, b"hello", original_name="notes.txt")
