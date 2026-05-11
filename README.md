# Docer

LLM/Vision document scanning and structured data extraction. Multi-tenant. Web + REST API. Local Ollama for inference.

See `REQUIREMENTS.md` for the contract and `IMPLEMENTATION_PLAN.md` for architecture.

## Quick start

Prerequisites:
- Python 3.13+ (project uses 3.14)
- `uv` (https://docs.astral.sh/uv/)
- Local Ollama with a vision model installed. Default: `gemma4:31b`. Configure with `OLLAMA_HOST` and `DOCER_DEFAULT_MODEL` env vars.

```powershell
# Install deps
uv sync

# Migrate + create a superuser (optional)
uv run python manage.py migrate
uv run python manage.py createsuperuser

# Run the dev server
uv run python manage.py runserver

# In a second terminal, run the Huey worker
uv run python manage.py run_huey
```

Sign up at <http://localhost:8000/auth/signup>; you'll land on your account dashboard.

## E2E tests

```powershell
uv run pytest tests/e2e -q
```

Drops a PDF into `tests/data/` and adds a row to `tests/data/scenarios.json` to add a regression test.
The e2e suite hard-fails if Ollama or the configured model are unreachable.

## REST API

Authenticate with a Bearer API key issued from the account's API-keys page.

```bash
curl -H "Authorization: Bearer dk_..." \
     -F "file=@invoice.pdf" \
     http://localhost:8000/api/v1/<account>/scanners/<scanner>/scan
```
