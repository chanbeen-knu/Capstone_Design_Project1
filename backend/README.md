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

## Frontend integration

The frontend uses `/api/health` → `upstage_configured` for provider status.
Conversation history and the sidebar from PR #5 are integrated with the ontology explorer.

## Run

```bash
uvicorn main:app --reload --port 8000
```

## Verify

```bash
curl http://127.0.0.1:8000/api/health

curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "단위작업 2.3.1 철근 반입의 사고사례를 보여줘.", "history": []}'
```

## SIF RAG chatbot

현재 `main.py`의 `/api/chat`은 `agent: "ontology"` 또는 `"vector"`를 받습니다.
화면에서 두 에이전트를 나란히 비교할 수 있으며, 응답에는 근거 사례·통계·호출 메타데이터가 포함됩니다.
온톨로지 답변은 실제 Neo4j 관계를 그래프로 표시합니다.

저장소 루트에서 의존성을 설치하세요.

```bash
backend/.venv/bin/python -m pip install -r backend/requirements.txt -r ontology/requirements.txt
```

기존 `backend/.env`는 유지합니다. 생성 키는 `GENERATION_API_KEY`를 우선 사용하고
없으면 `UPSTAGE_API_KEY`를 사용합니다. 생성 모델은 `GENERATION_API_MODEL` 또는
`UPSTAGE_MODEL`로 정합니다. 벡터 검색을 사용하려면 `EMBEDDING_API_KEY`를 추가하세요.
원본 레포의 비밀키는 복사하지 않았습니다. 기존 Neo4j 접속 설정도 그대로 사용합니다.

벡터 인덱스는 원본과 동일한 SIF 워크북으로 만든 `local-db/sif-construction.npz`를 복사했습니다.
이 디렉터리는 Git에서 제외합니다. 워크북 또는 임베딩 모델을 바꾸거나 새로 체크아웃했다면 재구축하세요.

```bash
backend/.venv/bin/python backend/vector_index.py
```

벡터 에이전트는 전체 건수·비율 집계 대신 검색 한계와 관련 사례를 표시합니다.
전체 집계는 온톨로지 에이전트를 사용하세요. 생성 JSON이 유효하지 않으면 검증 오류를 전달해
한 번 재시도하며, 오류는 서버 로그에 남깁니다.

```bash
(cd backend && .venv/bin/python -m unittest -v test_rag)
backend/.venv/bin/python -m unittest discover -s tests -p 'test_rag_api.py' -v
node --test tests/conversation-search.test.js
npm run build
```
