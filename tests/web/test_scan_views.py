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


def test_scan_progress_polling_response_emits_oob_with_286_when_terminal(client_user_account):
    """When the scan reaches a terminal state, the polling response must:
    (a) return HTTP 286 so htmx stops the polling timer, and
    (b) include an OOB block so the result panel updates without page reload.
    """
    c, _user, account = client_user_account
    scanner = Scanner.objects.get(account=account, slug="invoice")
    scan = _make_scan(account, scanner, status=Scan.COMPLETED)
    resp = c.get(
        reverse("web:scan_progress", kwargs={"account_slug": account.slug, "scan_id": scan.id})
    )
    assert resp.status_code == 286, "htmx convention: 286 stops polling"
    body = resp.content.decode()
    assert 'hx-swap-oob="outerHTML"' in body
    assert 'id="scan-result-panel"' in body


def test_scan_progress_polling_response_returns_card_only_while_running(client_user_account):
    """While the scan is still running, the polling response is just the card
    (no wrapper, no OOB, no hx-swap-oob), with HTTP 200 so polling continues."""
    c, _user, account = client_user_account
    scanner = Scanner.objects.get(account=account, slug="invoice")
    scan = _make_scan(account, scanner, status=Scan.EXTRACTING)
    resp = c.get(
        reverse("web:scan_progress", kwargs={"account_slug": account.slug, "scan_id": scan.id})
    )
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "hx-swap-oob" not in body
    assert 'id="scan-progress-card"' in body
    # The stable poller wrapper is NOT part of the swap response — it stays
    # in the page across polls.
    assert 'id="scan-poller"' not in body


def test_qr_code_field_renders_as_inline_svg_image(client_user_account):
    """A qr_code field with an extracted value must render an <img> whose src
    is a data: URI carrying an SVG QR code, and whose title is the decoded
    text (hover-to-show)."""
    from apps.scans.models import ScanFieldResult

    c, _user, account = client_user_account
    scanner = Scanner.objects.get(account=account, slug="invoice")
    scan = _make_scan(account, scanner, status=Scan.COMPLETED)
    ScanFieldResult.objects.create(
        scan=scan,
        path="payment_qr",
        data_type="qr_code",
        original_value="https://example.com/pay?inv=42",
    )
    resp = c.get(
        reverse("web:scan_detail", kwargs={"account_slug": account.slug, "scan_id": scan.id})
    )
    body = resp.content.decode()
    assert 'class="qr-preview"' in body
    assert "data:image/svg+xml" in body
    # Hover-to-show: title attribute carries the decoded text.
    assert "https://example.com/pay?inv=42" in body


def test_scan_detail_initial_render_has_stable_poller_with_every_trigger(client_user_account):
    """The initial page render wraps the progress card in #scan-poller with an
    every-2s trigger. This is what survives single-poll failures."""
    c, _user, account = client_user_account
    scanner = Scanner.objects.get(account=account, slug="invoice")
    scan = _make_scan(account, scanner, status=Scan.EXTRACTING)
    resp = c.get(
        reverse("web:scan_detail", kwargs={"account_slug": account.slug, "scan_id": scan.id})
    )
    body = resp.content.decode()
    assert 'id="scan-poller"' in body
    assert 'hx-trigger="every 2s"' in body
    # No chained-load trigger — that was the broken pattern.
    assert "load delay:1s" not in body
