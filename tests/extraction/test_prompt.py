"""Unit tests for apps.extraction.prompt."""
from __future__ import annotations

from apps.extraction.prompt import (
    ExtractionPrompt,
    build_extraction_prompt,
    build_locator_prompt,
)


# ---------------------------------------------------------------------- fixtures


SHIPPED_SCENARIO_SCHEMA = {
    "description": "Smoke-test extractor that pulls the German invoice number off a single-page PDF.",
    "fields": [
        {
            "kind": "field",
            "name": "Rechnungs Nummer",
            "label": "Rechnungs Nummer",
            "data_type": "string",
            "required": True,
            "description": "Die eindeutige Rechnungsnummer (the invoice number printed on the document, often labeled 'Rechnung-Nr.', 'Rechnungsnummer', or 'Rechnung').",
            "options": {},
        }
    ],
}


DEEP_SCHEMA = {
    "description": "Order document",
    "fields": [
        {
            "kind": "field",
            "name": "Order Number",
            "label": "Order Number",
            "data_type": "string",
            "required": True,
        },
        {
            "kind": "object",
            "name": "Buyer",
            "label": "Buyer",
            "fields": [
                {
                    "kind": "field",
                    "name": "Name",
                    "label": "Name",
                    "data_type": "name",
                    "required": True,
                },
                {
                    "kind": "field",
                    "name": "Country",
                    "label": "Country",
                    "data_type": "country",
                    "required": False,
                },
            ],
        },
        {
            "kind": "list",
            "name": "Order Lines",
            "label": "Order Lines",
            "item": {
                "kind": "object",
                "fields": [
                    {
                        "kind": "field",
                        "name": "qty",
                        "label": "Quantity",
                        "data_type": "quantity",
                        "required": True,
                    },
                    {
                        "kind": "field",
                        "name": "description",
                        "label": "Description",
                        "data_type": "string",
                        "required": False,
                    },
                ],
            },
        },
        {
            "kind": "field",
            "name": "Status",
            "label": "Status",
            "data_type": "enum",
            "required": True,
            "options": {
                "values": [
                    {"id": "open", "label": "Open"},
                    {"id": "closed", "label": "Closed"},
                ]
            },
        },
        {
            "kind": "field",
            "name": "Category",
            "label": "Category",
            "data_type": "open_enum",
            "options": {
                "values": [
                    {"id": "books", "label": "Books"},
                ]
            },
        },
    ],
}


# ---------------------------------------------------------------------- shipped scenario


def test_shipped_scenario_simple_string_field():
    prompt = build_extraction_prompt(
        SHIPPED_SCENARIO_SCHEMA,
        priming_prompt="This is a German invoice (Rechnung).",
        language_hint="de",
    )

    assert isinstance(prompt, ExtractionPrompt)

    schema = prompt.json_schema
    assert schema["type"] == "object"
    props = schema["properties"]

    # Slug name strategy: snake_case, deterministic.
    assert "rechnungs_nummer" in props
    assert props["rechnungs_nummer"]["type"] == "string"
    # The description should carry the human label.
    assert "Rechnungs Nummer" in props["rechnungs_nummer"]["description"]

    # required tracked at object level.
    assert "rechnungs_nummer" in schema["required"]

    # System prompt mentions priming prompt + language hint.
    assert "German invoice" in prompt.system
    assert "de" in prompt.system

    # User prompt mentions the field label.
    assert "Rechnungs Nummer" in prompt.user

    # Field index uses the slug as path.
    assert "rechnungs_nummer" in prompt.field_index
    fi = prompt.field_index["rechnungs_nummer"]
    assert fi["data_type"] == "string"
    assert fi["required"] is True
    assert fi["label"] == "Rechnungs Nummer"


# ---------------------------------------------------------------------- deep schema


def test_deep_schema_nested_object_and_list():
    prompt = build_extraction_prompt(DEEP_SCHEMA)

    schema = prompt.json_schema
    props = schema["properties"]

    # Top-level field
    assert props["order_number"]["type"] == "string"

    # Nested object
    buyer = props["buyer"]
    assert buyer["type"] == "object"
    assert buyer["properties"]["name"]["type"] == "string"
    assert buyer["properties"]["country"]["type"] == "string"
    # 'name' is required, 'country' is not.
    assert "name" in buyer.get("required", [])
    assert "country" not in buyer.get("required", [])

    # List of objects
    lines = props["order_lines"]
    assert lines["type"] == "array"
    assert lines["items"]["type"] == "object"
    assert lines["items"]["properties"]["qty"]["type"] == "string"
    assert lines["items"]["properties"]["description"]["type"] == "string"
    assert "qty" in lines["items"].get("required", [])

    # Enum description carries the id=label pairs.
    status_desc = props["status"]["description"]
    assert "open=Open" in status_desc
    assert "closed=Closed" in status_desc
    assert "Closed enum" in status_desc

    # Open enum carries the __new__ instruction.
    cat_desc = props["category"]["description"]
    assert "__new__" in cat_desc

    # Field index includes list-item paths with [].
    idx = prompt.field_index
    assert "order_number" in idx
    assert "buyer.name" in idx
    assert "buyer.country" in idx
    assert "order_lines[].qty" in idx
    assert "order_lines[].description" in idx
    assert idx["order_lines[].qty"]["data_type"] == "quantity"

    # Top-level required list contains nested-required keys at top level.
    assert "order_number" in schema["required"]
    assert "status" in schema["required"]


# ---------------------------------------------------------------------- locator


def test_build_locator_prompt_shape():
    sys_p, user_p = build_locator_prompt(
        field_path="buyer.name",
        field_label="Buyer Name",
        original_value="ACME GmbH",
        page_index=2,
    )

    assert isinstance(sys_p, str)
    assert isinstance(user_p, str)

    # System mentions the bbox shape and fractions [0,1].
    assert "bbox" in sys_p
    assert "[0, 1]" in sys_p or "0, 1]" in sys_p
    assert '"page"' in sys_p
    # null is allowed
    assert "null" in sys_p

    # User mentions the path/label/value/page.
    assert "buyer.name" in user_p
    assert "Buyer Name" in user_p
    assert "ACME GmbH" in user_p
    assert "2" in user_p
