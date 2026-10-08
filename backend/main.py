import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from pydantic import BaseModel

import graph

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set. Copy backend/.env.example to backend/.env "
        "and add your key."
    )

client = genai.Client(api_key=API_KEY)
last_chat_success = None

app = FastAPI(title="Safety Agent Chat API")

# The Vite dev-server proxy (see vite.config.js) is the primary mechanism that
# keeps the browser same-origin, so this middleware only matters for direct
# calls (e.g. the /docs page) or if the proxy config ever gets removed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
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
    global last_chat_success
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
            status_code=502, detail="Gemini request failed."
        ) from exc

    answer = getattr(response, "text", None)
    if not answer:
        raise HTTPException(status_code=502, detail="Gemini returned an empty response")

    last_chat_success = datetime.now(timezone.utc).isoformat()
    return ChatResponse(answer=answer)


@app.get("/api/health")
def health():
    return {"status": "ok", "model": MODEL_NAME, "gemini_configured": bool(API_KEY),
            "last_chat_success": last_chat_success}


# ---------------------------------------------------------------------------
#새로 추가한  Neo4j 지식그래프 API
# ---------------------------------------------------------------------------

def _neo4j_call(fn, *args):
    """Neo4j가 꺼져 있거나 비밀번호가 틀리면 503으로 알려주기."""
    try:
        return fn(*args)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {exc}") from exc


@app.get("/api/graph/health")
def graph_health():
    _neo4j_call(graph.ping)
    return {"status": "ok", "neo4j": "connected"}


@app.get("/api/objects")
def objects():
    """왼쪽/툴바 선택용 기인물 목록 (사례 수 많은 순)."""
    return _neo4j_call(graph.object_list)


@app.get("/api/graph/object/{name}")
def object_graph(name: str, per_type: int = 6):
    """기인물 중심 그래프 {nodes, links}."""
    result = _neo4j_call(graph.object_graph, name, per_type)
    if result is None:
        raise HTTPException(status_code=404, detail=f"'{name}' 기인물을 찾을 수 없습니다")
    return result


@app.get("/api/cases/{case_id}")
def case_detail(case_id: str):
    result = _neo4j_call(graph.case_detail, case_id)
    if result is None:
        raise HTTPException(status_code=404, detail="사례를 찾을 수 없습니다")
    return result
