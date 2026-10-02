# Backend (FastAPI + Gemini)

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and paste your Gemini API key
```

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
