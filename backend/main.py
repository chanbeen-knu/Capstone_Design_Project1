import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from pydantic import BaseModel

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set. Copy backend/.env.example to backend/.env "
        "and add your key."
    )

client = genai.Client(api_key=API_KEY)

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

    contents = []
    for turn in request.history:
        gemini_role = "model" if turn.role == "assistant" else "user"
        contents.append({"role": gemini_role, "parts": [{"text": turn.content}]})
    contents.append({"role": "user", "parts": [{"text": question}]})

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Gemini request failed: {exc}"
        ) from exc

    answer = getattr(response, "text", None)
    if not answer:
        raise HTTPException(status_code=502, detail="Gemini returned an empty response")

    return ChatResponse(answer=answer)


@app.get("/api/health")
def health():
    return {"status": "ok", "model": MODEL_NAME}
