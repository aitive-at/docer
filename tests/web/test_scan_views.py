"""Tests for scan_detail rendering and scan_progress polling responses.

Specifically guards against the duplicate-OOB-result-panel regression
where _scan_progress.html emitted its hx-swap-oob block during initial
page render of a terminal scan, producing two #scan-result-panel divs.
"""
from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from PIL import Image

from apps.accounts.models import User
from apps.accounts.services import create_personal_account
from apps.files.services import ingest_upload
from apps.scanners.models import Scanner
from apps.scans.models import Scan


def _make_scan(account, scanner, status: str) -> Scan:
    """Build a real Scan with a small PNG file behind it."""
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color="white").save(buf, format="PNG")
    upload = SimpleUploadedFile("page.png", buf.getvalue(), content_type="image/png")
    stored = ingest_upload(account, upload)
    return Scan.objects.create(account=account, scanner=scanner, file=stored, status=status, progress_pct=100)


@pytest.fixture
def client_user_account(db):
    user = User.objects.create_user(
        username="scan-tester@example.com",
        email="scan-tester@example.com",
        password="x" * 12,
    )
    account = create_personal_account(user, base_name="Scan Tester")
    c = Client()
    c.force_login(user)
    return c, user, account


def test_scan_detail_for_completed_scan_does_not_duplicate_result_panel(client_user_account):
    """Refreshing a finished scan must NOT emit an hx-swap-oob result-panel
    inline alongside the real one (regression: caused duplicate UI sections)."""
    c, _user, account = client_user_account
    scanner = Scanner.objects.get(account=account, slug="invoice")
    scan = _make_scan(account, scanner, status=Scan.COMPLETED)
    resp = c.get(
        reverse("web:scan_detail", kwargs={"account_slug": account.slug, "scan_id": scan.id})
    )
    body = resp.content.decode()
    # Out-of-band swap markup is only valid in htmx response context.
    assert "hx-swap-oob" not in body
    # The real #scan-result-panel still exists exactly once.
    assert body.count('id="scan-result-panel"') == 1


def test_scan_progress_polling_response_emits_oob_when_terminal(client_user_account):
    """When the scan reaches a terminal state, the polling response must
    include the OOB block so the result panel updates without page reload."""
    c, _user, account = client_user_account
    scanner = Scanner.objects.get(account=account, slug="invoice")
    scan = _make_scan(account, scanner, status=Scan.COMPLETED)
    resp = c.get(
        reverse("web:scan_progress", kwargs={"account_slug": account.slug, "scan_id": scan.id})
    )
    body = resp.content.decode()
    assert 'hx-swap-oob="outerHTML"' in body
    assert 'id="scan-result-panel"' in body


def test_scan_progress_polling_response_omits_oob_while_running(client_user_account):
    """While the scan is still running, the polling response must NOT include
    the OOB block — only the updated progress card."""
    c, _user, account = client_user_account
    scanner = Scanner.objects.get(account=account, slug="invoice")
    scan = _make_scan(account, scanner, status=Scan.EXTRACTING)
    resp = c.get(
        reverse("web:scan_progress", kwargs={"account_slug": account.slug, "scan_id": scan.id})
    )
    body = resp.content.decode()
    assert "hx-swap-oob" not in body
    # But the progress div with the next-poll trigger IS present.
    assert 'id="scan-progress"' in body
    assert 'hx-trigger="load delay:1s"' in body
