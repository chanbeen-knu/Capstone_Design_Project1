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

Get an API key from the [Upstage Console](https://console.upstage.ai).

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

If `/api/chat` returns a 502 mentioning an invalid or unsupported model, your
`UPSTAGE_MODEL` value in `.env` may not be valid for your key — try another
candidate (e.g. `solar-pro3`, `solar-mini`) and re-test.
