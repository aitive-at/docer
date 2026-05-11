# Docer — Implementation Plan

Companion to `REQUIREMENTS.md`. Describes architecture, repo layout, the data model, module responsibilities, and the build sequence (including which pieces are parallelized across agents).

## 1. Architecture overview

```
                    ┌─────────────┐
   browser <─HTMX──▶│  Django     │◀── REST ──▶  programmatic
                    │  (web+api)  │
                    └─────┬───────┘
                          │ enqueue
                    ┌─────▼───────┐    ┌────────────┐
                    │  Huey       │───▶│  Ollama    │
                    │  worker     │    │  HTTP API  │
                    └─────┬───────┘    └────────────┘
                          │
                    ┌─────▼───────┐
                    │  SQLite +   │
                    │  media dir  │
                    └─────────────┘
```

A single Django process serves both the web UI and the REST API. Scan jobs run in a Huey worker process (or thread, in tests) backed by the same SQLite DB. The worker calls Ollama over HTTP.

## 2. Repo layout

```
docer/
├── pyproject.toml              # uv-managed
├── manage.py
├── docer/                      # Django project (settings, urls, wsgi, huey config)
│   ├── settings.py
│   ├── urls.py
│   └── huey_config.py
├── apps/
│   ├── accounts/               # User, Account, Membership, ApiKey
│   ├── files/                  # File model, dedup, PDF→image
│   ├── scanners/               # Scanner, FieldNode, EnumValue
│   ├── scans/                  # Scan, ScanFieldResult, ScanError
│   ├── extraction/             # Ollama client, prompt build, orchestrator
│   ├── canonicalize/           # Per-type canonicalizers
│   ├── web/                    # HTMX views + templates
│   └── api/                    # DRF views, serializers, auth
├── templates/
│   ├── base.html
│   └── ...
├── static/
│   └── css/theme.css           # aitivedata-styled
├── media/                      # uploaded files (gitignored)
└── tests/
    ├── conftest.py
    ├── e2e/test_scenarios.py
    └── data/                   # scenarios.json + PDFs
```

## 3. Dependencies (uv)

- `django>=6.0,<6.1`
- `djangorestframework`
- `huey` (SQLite backend, in-built)
- `pypdfium2` — lightweight PDF rasterizer, no system deps, Windows-friendly
- `Pillow` — image work
- `httpx` — Ollama HTTP client
- `python-stdnum` — IBAN, VAT, EAN validation/canonicalization
- `phonenumbers` — phone E.164
- `email-validator` — email canonicalization
- `python-dateutil` + `babel` — multilingual date/number parsing
- `python-slugify` — slug generation
- `pytest`, `pytest-django`, `pytest-xdist` — test runners

## 4. Data model (concrete)

```python
# accounts
class User(AbstractUser): pass    # email login

class Account(Model):
    kind = CharField(choices=[("personal","personal"),("organization","organization")], default="personal")
    name = CharField(max_length=120)
    slug = SlugField(unique=True)
    created_at = DateTimeField(auto_now_add=True)
    pages_scanned_total = PositiveIntegerField(default=0)
    documents_scanned_total = PositiveIntegerField(default=0)

class Membership(Model):
    account = FK(Account)
    user = FK(User)
    role = CharField(choices=["owner","admin","member"])
    class Meta: unique_together = [("account","user")]

class ApiKey(Model):
    account = FK(Account, related_name="api_keys")
    user = FK(User)                     # who created it
    name = CharField(max_length=80)
    key_prefix = CharField(max_length=12, db_index=True)   # first 8 chars for lookup
    key_hash = CharField(max_length=128)                   # sha256 of full key
    created_at = DateTimeField(auto_now_add=True)
    revoked_at = DateTimeField(null=True)

# files
class StoredFile(Model):
    account = FK(Account)
    sha256 = CharField(max_length=64, db_index=True)
    mime = CharField(max_length=80)
    size = PositiveBigIntegerField()
    blob_path = CharField(max_length=500)                  # under MEDIA_ROOT/<account>/<sha2>/
    original_name = CharField(max_length=255)
    page_count = PositiveSmallIntegerField(default=0)
    class Meta: unique_together = [("account","sha256")]   # per-account dedup

class PageImage(Model):
    stored_file = FK(StoredFile, related_name="pages")
    index = PositiveSmallIntegerField()                    # 0-based
    width = PositiveIntegerField()
    height = PositiveIntegerField()
    image_path = CharField(max_length=500)                 # cached PNG

# scanners
class Scanner(Model):
    account = FK(Account, related_name="scanners")
    name = CharField(max_length=120)
    slug = SlugField()
    description = TextField(blank=True)
    priming_prompt = TextField(blank=True)
    language_hint = CharField(max_length=10, blank=True)   # e.g., "de"
    model_override = CharField(max_length=120, blank=True) # ollama model name override
    schema_json = JSONField(default=dict)                  # the field tree (see below)
    class Meta: unique_together = [("account","slug")]

# Field schema is stored as JSON inside Scanner.schema_json:
# {
#   "fields": [
#     {"kind":"field","name":"invoice_number","label":"Rechnungs Nummer",
#      "data_type":"string","required":true,"description":"...","options":{}},
#     {"kind":"object","name":"buyer","label":"Buyer",
#      "fields":[{"kind":"field","name":"name","data_type":"name", ...}]},
#     {"kind":"list","name":"order_lines","label":"Order Lines",
#      "item":{"kind":"object","fields":[...]}}
#   ]
# }
# Open enums mutate this JSON on the scanner when new ids are added.

# scans
class Scan(Model):
    account = FK(Account, related_name="scans")
    scanner = FK(Scanner, related_name="scans")
    file = FK(StoredFile)
    status = CharField(choices=["queued","preparing","extracting","locating","completed","failed","partial"], default="queued")
    progress_pct = PositiveSmallIntegerField(default=0)
    progress_message = CharField(max_length=200, blank=True)
    started_at = DateTimeField(null=True)
    finished_at = DateTimeField(null=True)
    extracted_json = JSONField(null=True)        # mirror of canonicalized result tree
    error_message = TextField(blank=True)
    pages_processed = PositiveSmallIntegerField(default=0)

class ScanFieldResult(Model):
    scan = FK(Scan, related_name="field_results")
    path = CharField(max_length=400)             # dotted+index path: "buyer.name", "order_lines[2].qty"
    data_type = CharField(max_length=40)
    original_value = TextField(blank=True)
    canonical_value = JSONField(null=True)        # JSON: scalar or {amount,currency} etc.
    confidence = FloatField(null=True)
    page_index = PositiveSmallIntegerField(null=True)
    bbox = JSONField(null=True)                  # [x0,y0,x1,y1] in image pixels, optional
    attempts = JSONField(default=list)            # list of {prompt, raw, error}
    error = TextField(blank=True)
```

All tenant-owned models inherit from a `TenantModel` mixin that requires `account` and provides a `for_account(account)` manager helper. Views obtain `request.account` from URL kwarg → middleware → assert membership.

## 5. Module responsibilities

### apps/canonicalize
- `canonicalize(data_type, raw, *, language=None, options=None) -> CanonicalResult`
- Pure functions, no Django imports, fully unit-testable.
- One file per type (`names.py`, `iban.py`, `currency.py`, ...) plus a registry `__init__.py`.
- Returns `CanonicalResult(original=raw, canonical=<json>, errors=[...])`.

### apps/extraction
- `OllamaClient` — thin httpx wrapper: `chat(messages, images=[...], format="json")`.
- `prompt.py` — translates a scanner's field tree into:
  - a system prompt that includes the priming prompt and language hint
  - a JSON-schema description of the desired output
  - per-field hints inlined
- `extractor.py` — `run_extraction(scan)`: stages a Scan through preparing → extracting → locating, writes `ScanFieldResult` rows, updates `extracted_json`, increments account counters.
- `locator.py` — per-field "where is this value on the page" call returning a normalized bbox (or None).

### apps/scans (Huey tasks)
- `tasks.run_scan(scan_id)` — pulls the Scan, calls `extraction.run_extraction`, handles errors, marks final status.

### apps/web
- HTMX views; templates extend `base.html` with the aitivedata theme.
- Live progress endpoint: simple polling first (`hx-get` every 1s while not terminal). SSE is a stretch.

### apps/api
- DRF; permission class checks API key → resolves account → asserts URL `<account>` matches.

## 6. URL design

```
/                                     # marketing/landing redirect to login or dashboard
/auth/signup, /auth/login, /auth/logout
/<account>/                           # dashboard
/<account>/scanners/
/<account>/scanners/<slug>/
/<account>/scanners/<slug>/scan       # upload form
/<account>/scans/<id>/                # progress + result
/<account>/scans/<id>/page/<n>.png    # page render w/ optional overlay
/<account>/settings/api-keys
/api/v1/<account>/...                 # REST mirror
/htmx/<account>/scans/<id>/progress   # HTMX poll fragment
```

## 7. Build sequence and parallelization

**Phase 1 — Foundation (sequential, main agent):**
1. Bootstrap project (`uv init`-style, `pyproject.toml`, deps, Django settings, base templates).
2. Domain models + migrations.
3. Auth (signup/login/logout) + per-account routing middleware.

**Phase 2 — Parallelizable specialists:**
- **Agent A** — `apps/canonicalize/`: implement all canonicalizers + unit tests.
- **Agent B** — `apps/files/`: upload, SHA-256 dedup, PDF rasterization, page caching.
- **Agent C** — `apps/extraction/ollama_client.py` + `prompt.py`: Ollama wrapper + prompt builder. Stub `run_extraction` so it can be wired by main agent.
- **Agent D** — `static/css/theme.css` + `templates/base.html` + auth/dashboard templates: visual identity from aitivedata.com.

**Phase 3 — Wire-up (sequential, main agent):**
4. Extraction orchestrator (`extractor.py` + `locator.py`) using Phase-2 outputs.
5. Huey wiring + scan task; live progress endpoint.

**Phase 4 — UI + API (parallel):**
- **Agent E** — `apps/web/` views + templates for scanner CRUD, schema editor, scan submission, scan result with image overlay.
- **Agent F** — `apps/api/` DRF endpoints + API key auth + serializers.

**Phase 5 — E2E (main agent):**
6. E2E harness (`tests/e2e/test_scenarios.py`) walks `scenarios.json`. Run with real Ollama. Iterate prompt/canonicalization until green.

## 8. Risk register

| Risk | Mitigation |
|------|------------|
| Vision LLM returns malformed JSON | Use Ollama `format=json` + strict prompt + retry with error message in attempts array |
| Bbox locate-pass unreliable | Treat as best-effort; never block extraction; log to `attempts` |
| Account scoping leak | `TenantModel` base + middleware that sets `request.account`; tests assert cross-account 404 |
| Django 6 / Python 3.14 ecosystem gaps | If a dep fails on 3.14, swap to nearest pure-Python alternative |
| Slow gemma4:31b inference | E2E may be slow; document expected wall-clock; allow per-test override of model via env var |
| File path on Windows (case, separators) | Use `pathlib` everywhere; never string-concat paths |

## 9. Definition of done for v1

- `uv run pytest tests/e2e -k Rechnungsnummer` passes on a machine with Ollama + `gemma4:31b`.
- Dropping a new PDF into `tests/data/` and adding a scenario row makes that scan run as a regression test with no code changes.
- Web UI: a freshly signed-up user can create a scanner, upload a PDF, watch progress, see canonical results, and copy an API key that works against the REST API.
