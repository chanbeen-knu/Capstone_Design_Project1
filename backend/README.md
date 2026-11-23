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

## Legacy graph-chat verification

`legacy_main.py`는 이전 API 검증을 위한 보관본입니다. 아래 테스트와 검증 스크립트는 이 보관본을 대상으로 하며 현재 `main.py`의 RAG API를 검증하지 않습니다.
조회 범위는 건설업으로 고정하며 다음 세 기능만 지원합니다.

- 단위작업 하나 또는 기인물 하나의 사고사례 조회.
- 공종·작업·단위작업 범위의 전체 사고 건수·비율 집계.
- 단위작업과 기인물을 함께 지정한 예방대책 빈도·근거 조회.

`chat_templates.py`의 T01~T04는 사례 조회·계층 집계·대책 종합·근거 상세의 고정 읽기 쿼리입니다.
집계는 DB가 전체 사례에 대해 계산하고, LLM에는 확정 결과와 최대 10건의 설명용 사례를 제공합니다.
수치와 원본 번호는 백엔드가 표시합니다. 생성 설명의 사례번호·숫자가 검증되지 않으면 DB 근거만 표시합니다.
LLM은 현재 `UPSTAGE_MODEL` 설정을 사용합니다.

제조업·기간·재해종류 필터·자유서술 상황 검색·사고 패턴은 지원하지 않습니다.
모호하거나 조건이 부족한 질문은 안내 문구를 반환합니다. DB 오류는 503, 모델 호출 오류는 502이며 근거 없는 답변으로 대체하지 않습니다.

### 단위 검증

저장소 루트에서 실행합니다. 실제 API·DB를 호출하지 않습니다.

```bash
backend/.venv/bin/python -m unittest discover -s tests -p 'test_graph_chat.py' -v
```

### 실제 종단 실행 기록

저장소 루트에서 실행합니다. **실제 Neo4j와 Upstage API를 호출하므로 모델 사용량이 발생합니다.**

```bash
backend/.venv/bin/python scripts/verify_graph_chat.py --live
```

세 질문을 FastAPI의 실제 `/api/chat` 핸들러에 POST하고, 독립적인 원본 JSON 계산과 사례·대책 연결을 대조합니다.
전송 후보의 텍스트·식별자를 공개 SIF 원본과 먼저 비교하며, 내용이 달라지면 모델에 전송하지 않고 중단합니다.
검증 기록은 `docs/verification/`에 JSON과 Markdown으로 남습니다. 실패 기록도 보존하며,
자동 검사 통과 후에는 `pending_review`로 저장합니다. 실제 설명의 의미·출처를 검토한 뒤에만 `verified`로 변경해야 합니다.
