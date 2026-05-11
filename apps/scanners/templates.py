"""Pre-built Scanner templates that can be auto-attached to new accounts.

Used by apps.accounts.services.create_personal_account to seed a useful starter
scanner so users can try the product without first authoring a schema.

Templates intentionally use empty language_hint so the LLM is free to detect
the document's actual language from visual cues; the priming_prompt and field
descriptions enumerate label vocabulary in several common languages.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .models import Scanner

if TYPE_CHECKING:
    from apps.accounts.models import Account


INVOICE_TEMPLATE: dict = {
    "name": "Invoice",
    "description": (
        "Extract the invoice number and gross total amount from invoices in "
        "any language."
    ),
    "priming_prompt": (
        "You are analyzing an invoice document. Invoices may be in any "
        "language (German, English, French, Italian, Spanish, Dutch, etc.) "
        "and from any country. Your job is to identify the invoice number "
        "(the document's own identifier) and the gross total amount due "
        "(including any VAT / sales tax). The amount and its currency may "
        "appear in different places on the page - inspect headers, totals "
        "rows, footers, and any 'amount due' boxes to find both."
    ),
    "language_hint": "",
    "schema_json": {
        "fields": [
            {
                "kind": "field",
                "name": "invoice_number",
                "label": "Invoice Number",
                "data_type": "string",
                "required": True,
                "description": (
                    "The invoice's own document number, printed somewhere "
                    "near the top of the page. Common labels in different "
                    "languages: 'Invoice No.', 'Invoice #', 'Invoice Number', "
                    "'Rechnungsnummer', 'Rechnungs-Nr.', 'Rg.-Nr.', "
                    "'Belegnummer', 'Facture N°', 'N° de facture', "
                    "'N° Factura', 'Factura Nº', 'Fattura N.', "
                    "'Numero fattura', 'Faktuurnummer', 'Nr. faktury'. "
                    "Return the value exactly as printed, including any "
                    "prefix, suffix, or separators (e.g. 'INV-2024-0042', "
                    "'RE 12345/24', '2024/0042')."
                ),
                "options": {},
            },
            {
                "kind": "field",
                "name": "gross_amount",
                "label": "Gross Amount",
                "data_type": "currency_amount",
                "required": True,
                "description": (
                    "The total gross amount due (the final figure that "
                    "includes VAT / sales tax / IVA / MwSt.). This is "
                    "typically the largest amount at the bottom of the "
                    "invoice, often emphasized in bold or in a separate "
                    "box. Common labels in different languages: 'Total', "
                    "'Grand Total', 'Total Due', 'Amount Due', "
                    "'Gesamtbetrag', 'Bruttobetrag', 'Gesamt brutto', "
                    "'Rechnungsbetrag', 'Total TTC', 'Montant total', "
                    "'Importe Total', 'Total a pagar', 'Totale', "
                    "'Totale lordo', 'Totaal', 'Te betalen'. If both a "
                    "net and a gross total are shown, return the GROSS "
                    "(VAT-inclusive) figure."
                ),
                "options": {},
            },
        ],
    },
}


DEFAULT_TEMPLATES: tuple[dict, ...] = (INVOICE_TEMPLATE,)


def seed_default_scanners(account: "Account") -> list[Scanner]:
    """Create starter Scanner rows for a freshly-created account.

    Idempotent: skips templates whose slug already exists on the account, so
    re-running for an existing account doesn't create duplicates.
    """
    created: list[Scanner] = []
    for tmpl in DEFAULT_TEMPLATES:
        scanner = Scanner(
            account=account,
            name=tmpl["name"],
            description=tmpl["description"],
            priming_prompt=tmpl["priming_prompt"],
            language_hint=tmpl["language_hint"],
            schema_json=tmpl["schema_json"],
        )
        scanner.slug = scanner.make_unique_slug(tmpl["name"])
        if Scanner.objects.filter(account=account, slug=scanner.slug).exists():
            continue
        scanner.save()
        created.append(scanner)
    return created
