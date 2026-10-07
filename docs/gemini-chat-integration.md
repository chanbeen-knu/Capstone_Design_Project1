# Gemini 채팅 연동 — 진행상황 및 실행 가이드

업데이트: 2026-10-02

## 요약

ChatPanel의 더미(mock) 응답을 실제 Google Gemini API 응답으로 교체했습니다. 프론트엔드가 Gemini를 직접 호출하지 않고, 새로 만든 경량 FastAPI 백엔드를 거치도록 구성했습니다 (API 키를 브라우저에 노출하지 않기 위함).

```
React (Vite :5173) --fetch('/api/chat')--> Vite proxy --> FastAPI (:8000) --> Gemini API
```

- Vite dev server의 `server.proxy`가 `/api/*` 요청을 `http://127.0.0.1:8000`으로 포워딩합니다. 브라우저 입장에서는 same-origin이라 CORS 문제가 없습니다.
- API 키는 `backend/.env`에만 존재하고 git에 올라가지 않습니다 (`.gitignore`에 이미 `.env`, `.env.*` 패턴이 있어 `backend/` 하위에도 적용됩니다).

## Git 브랜치 현황

- `main` — `front-end` 브랜치를 fast-forward 머지해서 최신 프론트엔드 상태로 업데이트됨.
- `backend/gemini-chat-api` — 이번 작업 브랜치. FastAPI 백엔드 신규 생성 + ChatPanel을 실제 API 호출로 교체.
- 브랜치 네이밍 컨벤션: `<영역>/<작업 설명>` 형태 (예: `backend/gemini-chat-api`, `frontend/graph-filter`). 브랜치 이름만 보고 어떤 영역의 어떤 작업인지 알 수 있게 합니다.
- 전략: `main`은 항상 동작하는 상태로 유지하고, 기능 단위로 짧은 브랜치를 파서 작업 후 `main`에 머지하는 단순 feature-branch 방식을 씁니다 (git-flow 같은 복잡한 체계는 쓰지 않음).

## 변경된 파일

| 파일 | 내용 |
| --- | --- |
| `backend/main.py` (신규) | FastAPI 앱. `POST /api/chat`, `GET /api/health` 엔드포인트. `google-genai` SDK로 Gemini 호출 |
| `backend/requirements.txt` (신규) | `fastapi`, `uvicorn[standard]`, `google-genai`, `python-dotenv` |
| `backend/.env.example` (신규) | `GEMINI_API_KEY`, `GEMINI_MODEL` 환경변수 템플릿 |
| `backend/README.md` (신규) | 백엔드 단독 실행/검증 커맨드 |
| `vite.config.js` (수정) | `/api` → `http://127.0.0.1:8000` 프록시 추가 |
| `src/components/ChatPanel.jsx` (수정) | mock 응답 제거, 실제 `fetch('/api/chat')` 호출로 교체. 로딩 표시, 에러 메시지, 멀티턴 history 전송 추가 |
| `src/data/mockData.js` (수정) | `createMockReply` 함수 삭제 (그래프 관련 데이터는 그대로 유지) |

## 실행 방법 (macOS/zsh)

### 1. 백엔드

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env 파일을 열어 GEMINI_API_KEY=<자신의 Gemini API 키>로 수정
```

Gemini API 키는 [Google AI Studio](https://aistudio.google.com/app/apikey)에서 발급받습니다.

백엔드 실행:

```bash
uvicorn main:app --reload --port 8000
```

단독 검증:

```bash
curl http://127.0.0.1:8000/api/health
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "크레인과 연결된 위험요인은?", "history": []}'
```

### 2. 프론트엔드

새 터미널에서:

```bash
npm install   # 최초 1회
npm run dev
```

브라우저에서 `http://localhost:5173` (포트가 사용 중이면 Vite가 자동으로 다음 포트를 사용) 접속 후 채팅 테스트.

## 모델 선택 관련 참고사항

구현 중 다음 사항을 발견했습니다 (팀원이 같은 이슈를 겪을 수 있어 기록):

- `gemini-2.5-flash`는 신규 API 키에 더 이상 제공되지 않습니다 (404 NOT_FOUND).
- `gemini-3.8-flash` 같은 최신 모델은 간헐적으로 503(과부하)이 발생합니다.
- 현재 기본값은 **`gemini-3.1-flash-lite`**로 설정했습니다 — 응답이 안정적이고 품질도 충분합니다. `.env`의 `GEMINI_MODEL` 값으로 언제든 변경 가능합니다.
- API 키 자체가 403 `PERMISSION_DENIED`를 반환하면 모델 문제가 아니라 Google Cloud 프로젝트의 결제/API 활성화 설정 문제일 수 있습니다. [AI Studio](https://aistudio.google.com/app/apikey)에서 키를 재발급받아보세요.

## 검증 완료 항목

- 백엔드 단독 기동 및 `/api/health`, `/api/chat` curl 테스트 통과
- Vite 프록시를 통한 `/api/chat` 호출 정상 동작 확인
- 멀티턴 대화 컨텍스트(이전 답변 참조 질문) 정상 반영 확인
- 백엔드 중단 시 프론트엔드에서 에러 메시지가 정상적으로 표시되는지 확인
- `npm run build`, `npm run lint` 통과

## 다음 작업 후보

- `requirements.txt` 버전 고정 (현재는 미고정)
- 전역 CSS 정리 (가로 스크롤, 다크모드 대비 — `docs/development-review.md` 참고)
- 메뉴 전환 시 채팅 상태 유지
- FastAPI에 Neo4j / Knowledge Graph 연동 추가
