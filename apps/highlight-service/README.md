# Highlight Service

FastAPI backend for short-drama highlight cutting and promo video generation.

This service is intentionally independent from the frontend. It exposes only HTTP APIs and stores its own runtime files under this directory:

- `inputs/`
- `outputs/`
- `work/`
- `data/`

## Start

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
```

Health check:

```bash
curl http://127.0.0.1:8765/api/health
```

API docs:

```text
http://127.0.0.1:8765/docs
```
