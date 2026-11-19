# APEX AI Gaming — Research Foundation v0.1

**Prototype only:** synthetic driving simulation, not GTA 6, streaming, or production-ready.

APEX provides a bounded deterministic driving simulation, baseline autonomous controller, disclosed AI-character commentary, protected FastAPI endpoints, tests, Docker, and a Google Cloud deployment runbook.

## Run locally
```bash
cp .env.example .env
# Replace APEX_API_KEY with a long random secret.
docker compose up --build -d
curl http://127.0.0.1:8080/health
set -a; . ./.env; set +a
curl -X POST http://127.0.0.1:8080/episodes -H "X-Apex-Key: $APEX_API_KEY" -H 'Content-Type: application/json' -d '{"seed":7}'
```

## Test
```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
ruff check app tests
pytest -q
```

See docs/BUZZ_HANDOFF.md and docs/DEPLOY_GOOGLE_CLOUD.md. Never deploy to the OwnerEasy production VM. No license is granted for redistribution.