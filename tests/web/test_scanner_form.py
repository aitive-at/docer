"""Smoke tests for the scanner form (graphical editor + hidden language fields)."""
from __future__ import annotations

import json

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.services import create_personal_account
from apps.scanners.models import Scanner


@pytest.fixture
def client_user_account(db):
    user = User.objects.create_user(
        username="form-tester@example.com",
        email="form-tester@example.com",
        password="x" * 12,
    )
    account = create_personal_account(user, base_name="Form Tester")
    c = Client()
    c.force_login(user)
    return c, user, account


def test_scanner_create_form_has_no_language_or_model_inputs(client_user_account):
    c, _user, account = client_user_account
    resp = c.get(reverse("web:scanner_create", kwargs={"account_slug": account.slug}))
    assert resp.status_code == 200, resp.content[:500]
    body = resp.content.decode()
    assert 'name="language_hint"' not in body
    assert 'name="model_override"' not in body
    # Editor wiring should be present.
    assert 'id="docer-initial-schema"' in body
    assert 'name="schema_json_text"' in body


def test_scanner_create_post_with_editor_json(client_user_account):
    c, _user, account = client_user_account
    schema = {
        "fields": [
            {"kind": "field", "name": "invoice_number", "label": "Invoice Number",
             "data_type": "string", "required": True, "description": "the no.", "options": {}},
        ]
    }
    resp = c.post(
        reverse("web:scanner_create", kwargs={"account_slug": account.slug}),
        data={
            "name": "Test scanner",
            "description": "x",
            "priming_prompt": "y",
            "schema_json_text": json.dumps(schema),
        },
    )
    assert resp.status_code in (302, 303), resp.content[:500]
    scanner = Scanner.objects.get(account=account, name="Test scanner")
    assert scanner.schema_json["fields"][0]["name"] == "invoice_number"


def test_scanner_create_post_with_deeply_nested_schema(client_user_account):
    """Recursive editor must round-trip schemas of arbitrary depth (>= 3 levels)."""
    c, _user, account = client_user_account
    schema = {
        "fields": [
            {"kind": "object", "name": "buyer", "label": "Buyer", "required": True, "fields": [
                {"kind": "field", "name": "name", "label": "Name",
                 "data_type": "name", "required": True, "description": "", "options": {}},
                {"kind": "object", "name": "address", "label": "Address", "required": False, "fields": [
                    {"kind": "field", "name": "street", "label": "Street",
                     "data_type": "street", "required": False, "description": "", "options": {}},
                    {"kind": "field", "name": "city", "label": "City",
                     "data_type": "city", "required": False, "description": "", "options": {}},
                ]},
            ]},
            {"kind": "list", "name": "order_lines", "label": "Order Lines",
             "options": {"min_items": 1},
             "item": {"kind": "object", "fields": [
                {"kind": "field", "name": "qty", "label": "Quantity",
                 "data_type": "int", "required": True, "description": "", "options": {}},
             ]}},
        ]
    }
    resp = c.post(
        reverse("web:scanner_create", kwargs={"account_slug": account.slug}),
        data={
            "name": "Deep schema",
            "description": "",
            "priming_prompt": "",
            "schema_json_text": json.dumps(schema),
        },
    )
    assert resp.status_code in (302, 303), resp.content[:500]
    scanner = Scanner.objects.get(account=account, name="Deep schema")
    saved = scanner.schema_json
    assert saved["fields"][0]["fields"][1]["fields"][0]["name"] == "street"
    assert saved["fields"][1]["options"]["min_items"] == 1


def test_editor_node_factory_defaults_field_required_to_true(client_user_account):
    """The editor's JS nodeFactory must default new fields to required:true.
    Verified by inspecting the rendered create form's embedded JS — saves us
    from needing a headless browser for a one-line invariant."""
    c, _user, account = client_user_account
    resp = c.get(reverse("web:scanner_create", kwargs={"account_slug": account.slug}))
    assert resp.status_code == 200
    body = resp.content.decode()
    # Field default
    assert "kind: 'field'" in body
    assert "required: true" in body, "new fields must default to required:true"
    # Make sure we didn't accidentally leave the old default in place.
    assert "required: false" not in body


def test_scanner_form_renders_required_checkbox_for_existing_field(client_user_account):
    """An existing field with required:true must render a checked checkbox.
    Alpine's x-model binding on a checkbox is reactive — if our schema's
    `required` property changes, the input toggles accordingly. This guard
    catches accidental removal of the x-model binding."""
    scanner = Scanner.objects.create(
        account=client_user_account[2],
        name="Required edit",
        slug="required-edit",
        schema_json={
            "fields": [
                {"kind": "field", "name": "must_have", "label": "Must Have",
                 "data_type": "string", "required": True, "description": "", "options": {}},
            ]
        },
    )
    c = client_user_account[0]
    resp = c.get(
        reverse(
            "web:scanner_edit",
            kwargs={"account_slug": client_user_account[2].slug, "scanner_slug": scanner.slug},
        )
    )
    body = resp.content.decode()
    # The x-model binding on the required checkbox is the contract.
    assert 'x-model="node.required"' in body
    # Initial schema is in the JSON-script tag for Alpine to read.
    assert '"required": true' in body or '"required":true' in body


def test_scanner_edit_round_trip_preserves_schema(client_user_account):
    c, _user, account = client_user_account
    scanner = Scanner.objects.create(
        account=account,
        name="Round trip",
        slug="round-trip",
        schema_json={"fields": [{"kind": "field", "name": "a", "label": "A",
                                 "data_type": "string", "required": False, "description": "", "options": {}}]},
    )
    resp = c.get(
        reverse("web:scanner_edit", kwargs={"account_slug": account.slug, "scanner_slug": scanner.slug})
    )
    assert resp.status_code == 200
    body = resp.content.decode()
    # The schema is embedded as JSON in a json_script tag for Alpine to read.
    assert '"name": "a"' in body or '"name":"a"' in body
    assert 'id="docer-initial-schema"' in body


def test_edit_page_has_no_leaked_template_comment_markers(client_user_account):
    """Multi-line {# ... #} comments don't get stripped by Django and leak as
    raw text into the page (regression: previously rendered the rationale
    block above the field-type dropdown). Use {% comment %} for multi-line."""
    c, _user, account = client_user_account
    scanner = Scanner.objects.create(
        account=account,
        name="Comment guard",
        slug="comment-guard",
        schema_json={"fields": [{"kind": "field", "name": "a", "label": "A",
                                 "data_type": "currency_amount", "required": False,
                                 "description": "", "options": {}}]},
    )
    resp = c.get(
        reverse("web:scanner_edit", kwargs={"account_slug": account.slug, "scanner_slug": scanner.slug})
    )
    body = resp.content.decode()
    assert "{#" not in body
    assert "#}" not in body
