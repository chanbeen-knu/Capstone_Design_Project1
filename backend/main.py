import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

API_KEY = os.getenv("UPSTAGE_API_KEY")
MODEL_NAME = os.getenv("UPSTAGE_MODEL", "solar-pro2")

if not API_KEY:
    raise RuntimeError(
        "UPSTAGE_API_KEY is not set. Copy backend/.env.example to backend/.env "
        "and add your key."
    )

client = OpenAI(api_key=API_KEY, base_url="https://api.upstage.ai/v1")

app = FastAPI(title="Safety Agent Chat API")

# The Vite dev-server proxy (see vite.config.js) is the primary mechanism that
# keeps the browser same-origin, so this middleware only matters for direct
# calls (e.g. the /docs page) or if the proxy config ever gets removed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    answer: str


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    question = request.message.strip()
    if not question:
        raise HTTPException(status_code=400, detail="message is required")

    messages = [{"role": turn.role, "content": turn.content} for turn in request.history]
    messages.append({"role": "user", "content": question})

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Upstage request failed: {exc}"
        ) from exc

    answer = response.choices[0].message.content if response.choices else None
    if not answer:
        raise HTTPException(status_code=502, detail="Upstage returned an empty response")

    return ChatResponse(answer=answer)


@app.get("/api/health")
def health():
    return {"status": "ok", "model": MODEL_NAME}
