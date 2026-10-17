# Backend (FastAPI + Upstage Solar)

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and paste your Upstage API key
```

The ontology endpoints can run without an Upstage key; `/api/chat` returns 503 until one is configured.

## Frontend integration follow-up

This branch switches `/api/health` from `gemini_configured` to `upstage_configured`.
The current `src/components/SettingsPanel.jsx` still reads `gemini_configured` and
labels the provider Gemini, so its service status will be incorrect even when
Upstage is configured. PR #5 is already in `main`; when that updated frontend is
merged into this branch, update the resolved panel to read `upstage_configured`
and show Upstage in its labels.
Also update the Gemini descriptions in `src/components/AboutPanel.jsx` and the
feature documentation. Verify the Settings page with an Upstage key configured
and with the key absent.

## Run

```bash
uvicorn main:app --reload --port 8000
```

## Verify

```bash
curl http://127.0.0.1:8000/api/health

curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "크레인과 연결된 위험요인은?", "history": []}'
```
