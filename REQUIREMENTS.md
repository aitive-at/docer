# Docer — Requirements

Derived from `HUMAN_SPEC.md` + clarifying Q&A. This document is the contract; `IMPLEMENTATION_PLAN.md` describes how we satisfy it.

## 1. Product summary

Docer is a multi-tenant document-scanning and structured data-extraction platform that runs both on-prem and in the cloud. It accepts PDFs and common image formats, uses a vision-capable LLM (via Ollama) to extract user-defined structured fields, canonicalizes those values for downstream comparison, and exposes the workflow through both a web UI (HTMX) and a REST API.

## 2. Stakeholders & use cases

- **Account owner** — signs up, configures scanners, uploads documents, reviews extraction results, manages API keys.
- **Programmatic consumer** — submits documents and reads results via REST API using account-scoped API keys.
- **Operator (on-prem)** — runs the same code without cloud features; uses local Ollama.

## 3. Functional requirements

### 3.1 Accounts & isolation

- **R-A1** Anyone can sign up with email + password. No email confirmation in v1.
- **R-A2** On signup, a personal `Account` is automatically created and the user becomes its sole owner.
- **R-A3** Schema must support organizational accounts (kind = `personal` | `organization`), but only personal accounts can be created in v1. The `Membership` table exists from day one.
- **R-A4** Multi-tenant isolation is **soft**: every tenant-owned row carries `account_id`; the ORM/manager layer enforces that querysets are scoped to the current account.
- **R-A5** All web URLs are scoped under `/<account-slug>/...`. The slug is derived from the account name and is unique.
- **R-A6** Each account has a dashboard showing pages-scanned counts (for billing later) and recent scans.
- **R-A7** Each account can mint API keys; keys are hashed at rest and shown in plaintext only at creation time.

### 3.2 Scanners

- **R-S1** Each account may create multiple scanners. Scanners are isolated per account.
- **R-S2** A scanner has: name, slug (unique within account), description, **priming prompt** (free-form, helps the LLM understand the document type), language hint(s), default model override (optional).
- **R-S3** A scanner has a hierarchical **field schema** with these node kinds:
  - **Field** — leaf with a data type, hints, required flag, canonicalization config.
  - **Object** — single nested record with its own fields.
  - **List of Objects** — repeated nested records (e.g., order lines).
- **R-S4** Each Field has:
  - `name` (machine key) and `label` (display)
  - `data_type` (one of the typed canonicalizers below)
  - `required` flag
  - `description` / `hints` (free text shown to the LLM)
  - type-specific options (e.g., enum values, currency code, decimal places)
- **R-S5** Supported data types (must canonicalize to a normal form **and** preserve the original raw value):
  - `string` (free text)
  - `name` (person, fold to canonical comparable form)
  - `street` (address line)
  - `city`, `zip`, `country` (ISO-3166 alpha-2 for country)
  - `email`
  - `phone` (E.164)
  - `iban`
  - `vat_id` / `uid` (EU VAT format with country prefix)
  - `int`, `float`, `decimal` (decimal with explicit precision)
  - `currency_amount` — pair of (amount, currency ISO-4217)
  - `quantity` — pair of (number, unit)
  - `date` (ISO-8601 date)
  - `datetime` (ISO-8601 datetime)
  - `boolean`
  - `enum` (closed) — user-defined `(id, label)` pairs; scanner must return the `id`. Match is fuzzy via LLM if direct match fails.
  - `open_enum` — like `enum` but the LLM may propose a new `(id, label)` if no existing entry matches; new ids get added to the scanner config.
- **R-S6** Scanners are CRUD-able from web UI and API.

### 3.3 Document upload & file storage

- **R-F1** Accepted inputs: PDF, PNG, JPEG, WEBP, TIFF.
- **R-F2** Files are deduplicated **per account** by SHA-256. Re-uploading the same bytes for the same account points to the existing blob (does not produce a second blob).
- **R-F3** PDFs are rasterized into per-page images at scan time.
- **R-F4** Original bytes are kept; rasterized page images are cached on disk.

### 3.4 Scanning pipeline

- **R-P1** Submitting a document for a scanner enqueues an async job; the request returns immediately with a `Scan` id.
- **R-P2** Scan lifecycle: `queued → preparing → extracting → locating → completed | failed | partial`.
- **R-P3** Live progress is reported to the UI (HTMX-friendly: SSE or short polling) including: current stage, page n/N, per-field status.
- **R-P4** Extraction is **two-pass**:
  1. **Extract pass** — vision LLM is given priming prompt + the field schema (translated into a JSON schema) + page image(s). It returns structured JSON.
  2. **Locate pass** — for each successfully-extracted field, a separate LLM call asks "where on this page is this value?" and returns a bounding box. Failures here do **not** fail the scan.
- **R-P5** For each field, the result records: `original_value`, `canonical_value`, `confidence` (if available), list of `attempts` and `errors`. Required fields that fail to extract surface as scan-level errors.
- **R-P6** Categorical (enum / open_enum) matching uses the LLM as the fuzzy matcher; never substring matching alone.
- **R-P7** All textual interaction with the LLM is multilingual. Priming prompt and field hints can be in any language; canonicalizers are language-aware where applicable (e.g., dates, numbers).
- **R-P8** Per-account counters track total documents and total **pages** scanned (rolling and per-period) for billing later.

### 3.5 Visual feedback

- **R-V1** The scan result page shows each rendered page next to extracted fields.
- **R-V2** When the locate pass returned a bounding box for a field, draw the overlay on the page image.
- **R-V3** No bounding box → field is shown without overlay; UI must not crash.

### 3.6 REST API

- **R-API1** Authentication: bearer token = an account-scoped API key.
- **R-API2** Endpoints (account-scoped):
  - `GET/POST /api/v1/<account>/scanners`, `GET/PATCH/DELETE /api/v1/<account>/scanners/<slug>`
  - `POST /api/v1/<account>/scanners/<slug>/scan` (multipart upload → 202 + scan id)
  - `GET /api/v1/<account>/scans/<id>` (status + result when complete)
  - `GET /api/v1/<account>/scans/<id>/pages/<n>.png` (rendered page, optionally with overlay)
- **R-API3** All web functionality is also reachable through the API; the web UI builds on the same primitives.

### 3.7 Web UI

- **R-W1** Visual identity matches `aitivedata.com`: dark theme, Libre Baskerville headings, Outfit body, JetBrains Mono labels, accent `#D64B6A` on bg `#0E0F11`, generous radius (16–24px), subtle borders, blurred glass cards.
- **R-W2** HTMX powers interactivity, especially live scan progress.
- **R-W3** Pages: signup, login, account dashboard, scanner list, scanner editor (schema designer), scan submission, scan progress, scan result, account settings (API keys, members placeholder).

## 4. Non-functional requirements

- **R-N1** Stack: Django 6.0, SQLite for local dev, Python ≥ 3.14.
- **R-N2** Tooling: `uv` for everything Python (deps, run, test). No `pip`/`poetry`/`pipx` in instructions.
- **R-N3** Async queue: **Huey** with SQLite broker.
- **R-N4** Inference: Ollama HTTP API; default model `gemma4:31b` (configurable via `DOCER_DEFAULT_MODEL` / `OLLAMA_HOST`). Real Ollama is required at e2e time — the test fails hard if Ollama or the model is unreachable.
- **R-N5** All sensitive secrets (Django `SECRET_KEY`, Ollama host) come from environment / `.env`.
- **R-N6** No emojis in UI or code unless requested.

## 5. Testing requirements

- **R-T1** A pytest e2e harness boots Django + Huey worker in-process, then for each scenario in `tests/data/scenarios.json`:
  1. Creates a fresh user + account
  2. Creates the scanner with the configured fields
  3. Uploads the bundled PDF
  4. Polls the scan to completion
  5. Asserts canonical extracted values match `expected`
- **R-T2** Adding a regression test must require only:
  - Drop a PDF into `tests/data/`
  - Add an entry to `tests/data/scenarios.json`
- **R-T3** The shipped scenario (`Rechnung 240010439.pdf`, expecting `"Rechnungs Nummer": "240010439"`) must pass on the developer's machine with Ollama reachable.

## 6. Out of scope for v1 (explicit non-goals)

- Email confirmation flow, password reset emails.
- Org account creation UI, invitations, role management (schema is ready; UI is not).
- Billing / payment integration.
- File-content cross-tenant deduplication (we explicitly chose per-account dedup).
- Embedding-based fuzzy matching (LLM is the fuzzy matcher).
- Production deployment (Docker, k8s) — local-dev focus for now.
