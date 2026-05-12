"""Smoke tests for scanner copy / delete / read-only schema viewer."""
from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.services import create_personal_account
from apps.scanners.models import Scanner


@pytest.fixture
def client_user_account(db):
    user = User.objects.create_user(
        username="action-tester@example.com",
        email="action-tester@example.com",
        password="x" * 12,
    )
    account = create_personal_account(user, base_name="Action Tester")
    c = Client()
    c.force_login(user)
    return c, user, account


def test_scanner_detail_renders_hierarchical_schema_not_raw_json(client_user_account):
    """The detail page should render the schema via the recursive node template,
    not as a raw <pre> JSON dump."""
    c, _user, account = client_user_account
    # create_personal_account seeded an Invoice template; use it.
    scanner = Scanner.objects.get(account=account, slug="invoice")
    resp = c.get(
        reverse(
            "web:scanner_detail",
            kwargs={"account_slug": account.slug, "scanner_slug": scanner.slug},
        )
    )
    assert resp.status_code == 200
    body = resp.content.decode()
    # Hierarchical viewer markers
    assert 'class="kind-badge kind-field"' in body
    # Field names appear as identifiers
    assert "invoice_number" in body
    assert "gross_amount" in body
    # currency_amount data type shown
    assert "currency_amount" in body
    # No raw JSON dump
    assert '"fields":' not in body or '<pre' not in body


def test_scanner_copy_creates_duplicate_and_redirects_to_edit(client_user_account):
    c, _user, account = client_user_account
    src = Scanner.objects.get(account=account, slug="invoice")
    url = reverse(
        "web:scanner_copy",
        kwargs={"account_slug": account.slug, "scanner_slug": src.slug},
    )
    resp = c.post(url)
    assert resp.status_code in (302, 303), resp.content[:400]
    # New scanner exists with "(copy)" in the name.
    copy = Scanner.objects.exclude(pk=src.pk).get(account=account, name__icontains="(copy)")
    assert copy.schema_json == src.schema_json
    assert copy.priming_prompt == src.priming_prompt
    assert copy.slug != src.slug
    # Redirected to the *edit* page of the copy.
    assert resp.url == reverse(
        "web:scanner_edit",
        kwargs={"account_slug": account.slug, "scanner_slug": copy.slug},
    )


def test_scanner_copy_requires_post(client_user_account):
    c, _user, account = client_user_account
    src = Scanner.objects.get(account=account, slug="invoice")
    url = reverse(
        "web:scanner_copy",
        kwargs={"account_slug": account.slug, "scanner_slug": src.slug},
    )
    # GET should redirect to detail without creating a copy.
    resp = c.get(url)
    assert resp.status_code in (302, 303)
    assert Scanner.objects.filter(account=account).count() == 1


def test_scanner_delete_removes_row_and_redirects_to_list(client_user_account):
    c, _user, account = client_user_account
    src = Scanner.objects.get(account=account, slug="invoice")
    url = reverse(
        "web:scanner_delete",
        kwargs={"account_slug": account.slug, "scanner_slug": src.slug},
    )
    resp = c.post(url)
    assert resp.status_code in (302, 303)
    assert resp.url == reverse("web:scanner_list", kwargs={"account_slug": account.slug})
    assert not Scanner.objects.filter(pk=src.pk).exists()


def test_scanner_delete_requires_post(client_user_account):
    c, _user, account = client_user_account
    src = Scanner.objects.get(account=account, slug="invoice")
    url = reverse(
        "web:scanner_delete",
        kwargs={"account_slug": account.slug, "scanner_slug": src.slug},
    )
    resp = c.get(url)
    # GET must NOT delete.
    assert resp.status_code in (302, 303)
    assert Scanner.objects.filter(pk=src.pk).exists()


def test_scanner_detail_shows_raw_json_pre_block(client_user_account):
    """The Raw-JSON toggle should embed the schema as pretty-printed JSON in a
    <pre> for copy-out, alongside the hierarchical viewer."""
    c, _user, account = client_user_account
    scanner = Scanner.objects.get(account=account, slug="invoice")
    resp = c.get(
        reverse("web:scanner_detail", kwargs={"account_slug": account.slug, "scanner_slug": scanner.slug})
    )
    body = resp.content.decode()
    # The raw-JSON section uses our specific pre class for styling.
    assert 'class="mono raw-json"' in body
    # Django auto-escapes the JSON output inside the <pre>: '"' → '&quot;'.
    # Check for the escaped form of a top-level key.
    assert "&quot;fields&quot;:" in body
    # Plain ASCII identifiers appear as-is inside the escaped JSON.
    assert "invoice_number" in body
    assert "currency_amount" in body


def test_scanner_create_from_json(client_user_account):
    """POSTing a valid raw JSON schema to scanner_create_from_json must save
    the scanner exactly as posted (no editor round-trip in between)."""
    import json as _json

    c, _user, account = client_user_account
    schema = {
        "fields": [
            {"kind": "field", "name": "po_number", "label": "PO Number",
             "data_type": "string", "required": True, "description": "", "options": {}},
        ]
    }
    resp = c.post(
        reverse("web:scanner_create_from_json", kwargs={"account_slug": account.slug}),
        data={
            "name": "PO scanner",
            "description": "",
            "priming_prompt": "",
            "schema_json_text": _json.dumps(schema),
        },
    )
    assert resp.status_code in (302, 303), resp.content[:500]
    saved = Scanner.objects.get(account=account, name="PO scanner")
    assert saved.schema_json["fields"][0]["name"] == "po_number"


def test_scanner_create_from_json_rejects_malformed(client_user_account):
    c, _user, account = client_user_account
    resp = c.post(
        reverse("web:scanner_create_from_json", kwargs={"account_slug": account.slug}),
        data={"name": "Bad", "schema_json_text": "{not valid json"},
    )
    assert resp.status_code == 200
    assert b"Schema JSON parse error" in resp.content
    assert not Scanner.objects.filter(account=account, name="Bad").exists()
