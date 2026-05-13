"""Build LLM prompts (and JSON schemas) from a Scanner.schema_json tree.

This module is pure Python over a JSON dict - it does not import Django models.
The orchestrator owns the actual Scanner row; here we only deal with its
already-loaded `schema_json`.

Schema shape (see IMPLEMENTATION_PLAN.md sec 4):

    {
      "fields": [
        {"kind":"field","name":"invoice_number","label":"Rechnungs Nummer",
         "data_type":"string","required":true,"description":"...","options":{}},
        {"kind":"object","name":"buyer","label":"Buyer",
         "fields":[ ...field nodes... ]},
        {"kind":"list","name":"order_lines","label":"Order Lines",
         "item":{"kind":"object","fields":[ ... ]}}
      ]
    }
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from slugify import slugify


@dataclass
class ExtractionPrompt:
    system: str
    user: str
    json_schema: dict
    field_index: dict[str, dict] = field(default_factory=dict)


# ---------------------------------------------------------------------- helpers


def _slug(name: str) -> str:
    """Deterministic snake_case slug for use as a JSON key."""
    s = slugify(name or "", separator="_", lowercase=True) or "field"
    # JSON keys can technically be anything but we keep things ASCII/clean.
    return s


def _is_field(node: dict) -> bool:
    return (node.get("kind") or "field") == "field"


def _describe_field(node: dict) -> str:
    """Build the JSON-Schema 'description' string for a leaf field."""
    bits: list[str] = []
    label = node.get("label") or node.get("name") or ""
    data_type = node.get("data_type", "string")
    if label:
        bits.append(f"Label: {label}")
    bits.append(f"Data type: {data_type}")
    if node.get("required"):
        bits.append("Required.")
    desc = (node.get("description") or "").strip()
    if desc:
        bits.append(f"Hint: {desc}")

    options = node.get("options") or {}

    if data_type in ("enum", "open_enum"):
        values = options.get("values") or []
        pairs = []
        for v in values:
            if isinstance(v, dict) and "id" in v:
                pairs.append(f"{v['id']}={v.get('label', v['id'])}")
        if pairs:
            bits.append("Allowed ids (id=label): " + "; ".join(pairs))
        if data_type == "open_enum":
            bits.append(
                "Open enum: if no listed id matches, you MAY return "
                'id="__new__:<short_label_in_snake_case>".'
            )
        else:
            bits.append("Closed enum: only the listed ids are valid.")

    if data_type == "currency_amount":
        cur = options.get("default_currency")
        if cur:
            bits.append(f"Default currency when truly absent on the document: {cur}.")
        bits.append(
            "Return the AMOUNT and its CURRENCY together as a single string. "
            "The currency code or symbol may NOT appear next to the amount itself - "
            "look at the WHOLE document (header, totals row, footer, an adjacent column, "
            "the invoice metadata) and include whatever currency the document is denominated in. "
            'Preserve every printed separator exactly (e.g. "1.234,56 EUR", "$1,234.56", '
            '"12,34 €", "JPY 1234"). Do not strip thousand separators or decimal commas/dots - '
            "downstream code parses them and converts the value to integer minor units "
            "(e.g. euro cents) plus a normalized ISO-4217 currency code."
        )

    if data_type == "date" or data_type == "datetime":
        bits.append(
            "Return the value exactly as printed (do not reformat). If the format is "
            "ambiguous (e.g. '03/04/2024' could be DMY or MDY), use the document's "
            "language and country to disambiguate; downstream code parses the locale."
        )

    if data_type == "country":
        bits.append(
            "If the country is not printed next to the address, infer it from "
            "the document's letterhead, language, currency code, IBAN country prefix, "
            "VAT-ID prefix, postal-code format, or phone country code, and return that. "
            "Prefer the ISO-3166 alpha-2 code (e.g. 'DE', 'AT', 'US') when one is printed; "
            "otherwise return whatever country name is printed."
        )

    if data_type == "phone":
        region = options.get("default_region")
        if region:
            bits.append(f"Default region when no country code is present: {region}.")
        bits.append(
            "If the leading '+' or country code is missing, infer the country from "
            "the document's letterhead, address, IBAN/VAT-ID country prefix, or other "
            "locale signals, and include the country dial code (e.g. '+49 30 1234567')."
        )

    if data_type == "vat_id" or data_type == "uid":
        bits.append(
            "EU VAT IDs start with a country prefix (e.g. 'DE', 'ATU', 'FR'). "
            "If a printed value is missing the country prefix, infer the country "
            "from the document's letterhead/address and prepend the correct prefix."
        )

    if data_type in ("int", "float", "decimal"):
        bits.append(
            "Do NOT strip thousand separators or change the decimal mark. Return the "
            "number exactly as printed. If separators are ambiguous (e.g. '1,234' may "
            "be 1234 or 1.234 depending on locale), the document's language settles it; "
            "downstream code parses the locale."
        )

    if data_type == "quantity":
        bits.append(
            "If the unit is not printed next to the value, look at the column header, "
            "row label, or document context (e.g. 'Quantity (kg)', 'Stk.', 'pcs') and "
            "include it in the returned string (e.g. '12 kg', '3 pcs')."
        )

    if data_type in ("street", "city", "zip"):
        bits.append(
            "If the country isn't printed with the address, the document's letterhead, "
            "language, currency, postal-code format, or VAT-ID/IBAN country prefix tells "
            "you which country the address is in - that determines how the field should "
            "be read. Return the value as printed."
        )

    if data_type == "boolean":
        bits.append('Return literal text such as "yes"/"no", "ja"/"nein", "true"/"false".')

    if data_type == "qr_code":
        bits.append(
            "Return the literal string 'QR_PRESENT' if a QR code matching "
            "this field's description is visible anywhere on the page, "
            "otherwise return ''. Do NOT attempt to decode the QR's pixels "
            "yourself — the actual contents will be decoded automatically "
            "by a downstream pass using a purpose-built QR library. Your "
            "job is only to confirm presence here; the locator pass will "
            "ask you for the QR's bounding box separately."
        )

    bits.append('Return "" (empty string) if the value is genuinely absent.')
    return " ".join(bits)


def _node_to_schema(node: dict) -> dict:
    """Convert a single schema node to a JSON-Schema fragment."""
    kind = node.get("kind") or "field"
    if kind == "field":
        return {
            "type": "string",
            "description": _describe_field(node),
        }
    if kind == "object":
        return _object_schema(node.get("fields") or [], label=node.get("label"))
    if kind == "list":
        item = node.get("item") or {}
        # item is documented as kind=object; tolerate kind=field too.
        item_schema = _node_to_schema(
            item if item.get("kind") in ("object", "field") else {"kind": "object", "fields": item.get("fields", [])}
        )
        out: dict[str, Any] = {
            "type": "array",
            "items": item_schema,
        }
        if node.get("label"):
            out["description"] = f"List of {node['label']}"
        return out
    raise ValueError(f"Unknown schema node kind: {kind!r}")


def _object_schema(fields: list[dict], *, label: str | None = None) -> dict:
    properties: dict[str, dict] = {}
    required: list[str] = []
    for child in fields:
        key = _slug(child.get("name") or child.get("label") or "field")
        properties[key] = _node_to_schema(child)
        if _is_field(child) and child.get("required"):
            required.append(key)
    out: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        out["required"] = required
    if label:
        out["description"] = label
    return out


def _index_node(node: dict, path: str, out: dict[str, dict]) -> None:
    """Walk the schema and populate path -> field metadata."""
    kind = node.get("kind") or "field"
    if kind == "field":
        out[path] = {
            "data_type": node.get("data_type", "string"),
            "options": dict(node.get("options") or {}),
            "required": bool(node.get("required")),
            "label": node.get("label") or node.get("name") or path,
            "description": node.get("description") or "",
        }
        return
    if kind == "object":
        for child in node.get("fields") or []:
            child_key = _slug(child.get("name") or child.get("label") or "field")
            _index_node(child, f"{path}.{child_key}" if path else child_key, out)
        return
    if kind == "list":
        item = node.get("item") or {}
        item_kind = item.get("kind") or "object"
        item_path = f"{path}[]"
        if item_kind == "field":
            out[item_path] = {
                "data_type": item.get("data_type", "string"),
                "options": dict(item.get("options") or {}),
                "required": bool(item.get("required")),
                "label": item.get("label") or item.get("name") or item_path,
                "description": item.get("description") or "",
            }
            return
        for child in item.get("fields") or []:
            child_key = _slug(child.get("name") or child.get("label") or "field")
            _index_node(child, f"{item_path}.{child_key}", out)
        return
    raise ValueError(f"Unknown schema node kind: {kind!r}")


def _build_field_index(scanner_schema: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for child in scanner_schema.get("fields") or []:
        key = _slug(child.get("name") or child.get("label") or "field")
        _index_node(child, key, out)
    return out


# ---------------------------------------------------------------------- prompts


_SYSTEM_PREAMBLE = (
    "You are a precise document-data extractor. You will receive one or more "
    "rendered page images of a document, plus a JSON schema describing the "
    "fields the user wants. Your job is to read the document and output a "
    "single JSON object that strictly matches the requested schema. "
    "Follow these rules:\n"
    "  1. Output JSON ONLY - no prose, no markdown fences.\n"
    "  2. Use the EXACT printed text for each value (do not normalize, "
    "translate, or reformat). Downstream code canonicalizes locale-specific "
    "values (dates, numbers, currencies, etc.).\n"
    "  3. READ THE WHOLE DOCUMENT before extracting any single field. Many "
    "fields are interpreted in the document's overall context: the country "
    "and language of the document determine how dates, numbers, currencies, "
    "addresses, phone numbers, postal codes, and tax-IDs are formatted. The "
    "currency, country, language hint, and other locale signals may appear "
    "in the letterhead, totals row, footer, an adjacent column, or in another "
    "field's value (e.g. an IBAN's country code or a VAT-ID's prefix). When a "
    "field's interpretation needs context that is not at the value's exact "
    "location, USE THAT WIDER CONTEXT.\n"
    "  4. If a field is genuinely absent on the page, emit \"\" (empty string) "
    "for scalars and an empty array for lists. Optional fields may also be "
    "omitted entirely.\n"
    "  5. For fields whose description lists allowed enum ids, return one of "
    "those ids verbatim. For open enums you MAY return "
    "\"__new__:<short_label_in_snake_case>\" if nothing fits.\n"
    "  6. Do not invent values. If unsure, leave the field empty rather than "
    "guess."
)


def build_extraction_prompt(
    scanner_schema: dict,
    *,
    priming_prompt: str = "",
    language_hint: str = "",
) -> ExtractionPrompt:
    fields = scanner_schema.get("fields") or []
    json_schema = _object_schema(fields)
    index = _build_field_index(scanner_schema)

    system_parts: list[str] = [_SYSTEM_PREAMBLE]
    if priming_prompt.strip():
        system_parts.append("Document context (priming prompt from the operator):")
        system_parts.append(priming_prompt.strip())
    if language_hint.strip():
        system_parts.append(
            f"The document is primarily in language: {language_hint.strip()}."
        )
    system = "\n\n".join(system_parts)

    description = (scanner_schema.get("description") or "").strip()

    user_lines: list[str] = [
        "Extract the following fields from the attached page image(s).",
    ]
    if description:
        user_lines.append("")
        user_lines.append(description)
    if language_hint.strip():
        user_lines.append("")
        user_lines.append(f"Language hint: {language_hint.strip()}.")

    field_summary = _summarize_fields_for_user(fields)
    if field_summary:
        user_lines.append("")
        user_lines.append("Fields requested:")
        user_lines.extend(field_summary)

    user_lines.append("")
    user_lines.append("Return a single JSON object that matches this schema:")
    import json as _json  # local alias to avoid leaking name in module top

    user_lines.append(_json.dumps(json_schema, indent=2, ensure_ascii=False))

    user = "\n".join(user_lines)

    return ExtractionPrompt(
        system=system,
        user=user,
        json_schema=json_schema,
        field_index=index,
    )


def _summarize_fields_for_user(fields: list[dict], indent: str = "  ") -> list[str]:
    """One bullet line per top-level entry, recursing one level for context."""
    lines: list[str] = []
    for node in fields:
        kind = node.get("kind") or "field"
        label = node.get("label") or node.get("name") or "(unnamed)"
        if kind == "field":
            dt = node.get("data_type", "string")
            req = " [required]" if node.get("required") else ""
            hint = (node.get("description") or "").strip()
            line = f"{indent}- {label} ({dt}){req}"
            if hint:
                line += f" - {hint}"
            lines.append(line)
        elif kind == "object":
            lines.append(f"{indent}- {label} (object):")
            lines.extend(_summarize_fields_for_user(node.get("fields") or [], indent + "  "))
        elif kind == "list":
            lines.append(f"{indent}- {label} (list of objects):")
            item = node.get("item") or {}
            lines.extend(_summarize_fields_for_user(item.get("fields") or [], indent + "  "))
    return lines


# ---------------------------------------------------------------------- locator


def build_locator_prompt(
    field_path: str,
    field_label: str,
    original_value: str,
    page_index: int,
) -> tuple[str, str]:
    """Prompt for the locator pass.

    The model is asked to return JSON of the form:

        {"bbox": [x0, y0, x1, y1] | null, "page": <int>}

    where coordinates are fractions in [0, 1] of the image width/height.
    The caller scales to pixels.
    """
    system = (
        "You are a precise visual locator for already-extracted document fields. "
        "You will be shown a single rendered page image and told the value that "
        "was previously extracted. Your job is to point at where on the image "
        "that value appears.\n\n"
        "Output JSON ONLY in this exact shape:\n"
        '  {"bbox": [x0, y0, x1, y1], "page": <integer>}\n'
        "Coordinates must be fractions in [0, 1] of the image width and height "
        "(x0/x1 are widths, y0/y1 are heights), measured from the top-left "
        "corner. (0,0) is top-left, (1,1) is bottom-right.\n"
        'If you cannot find the value on this page, return {"bbox": null, '
        '"page": <integer>}. Never invent a box.'
    )
    user = (
        f"Field path: {field_path}\n"
        f"Field label: {field_label}\n"
        f"Extracted value: {original_value!r}\n"
        f"Current page index: {page_index}\n\n"
        "Locate this value on the attached page image and return the JSON "
        "described above."
    )
    return system, user
