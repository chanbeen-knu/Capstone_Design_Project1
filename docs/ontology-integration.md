# 온톨로지 통합 (2026-10-16)

SafeGori 프로젝트에 온톨로지 적재 파이프라인을 합치고, 10/13 멘토 회의 항목 일부를 반영했습니다.
기존 화면 구성·디자인·채팅(Gemini)·사고 사례 JSON은 그대로 두었습니다.

## 범위: 건설업만 (2026-10-17)

팀 결정에 따라 건설업 사례 3,459건만 다룹니다.

- `ontology/config/scope.yaml`의 `sectors: [C]`로 적재 범위를 정합니다. 제조업 등까지 넣으려면 `[C, M]`.
- 이미 제조업 사례까지 적재했다면 `python ingest.py prune`으로 범위 밖 사례를 지우고 파생 관계·패턴·용어를 다시 계산합니다 (DB를 비울 필요 없음).
- `public/data/cases.json`도 건설업만 담도록 다시 만들었습니다 (`scripts/import_cases.py`, `--all`이면 두 시트). ID(`sif-2-5` 형식)는 그대로입니다.
- 화면: 업종 토글·자료 구분 필터는 업종이 하나일 때 숨깁니다(`src/sif/api.ts`의 `SECTORS`). T-Box에서 제조업 전용 클래스(업종, 고위험작업·상황)도 숨깁니다. 탐색기 기본 사례는 SIF-C-1357.
- 용어 사전 중 제조업에만 있는 기인물을 가리키는 7개는 `aliases_제조업.csv`로 분리했습니다.

## 바뀐 것 요약

| 구분 | 파일 | 내용 |
| --- | --- | --- |
| 신규 | `ontology/` | 엑셀 → Neo4j 적재 파이프라인 (`ingest.py`, 분류 규칙 `config/`) |
| 수정 | `backend/graph.py` | 새 스키마로 질의 교체. `/api/objects`, `/api/graph/object/{name}`, `/api/cases/{id}` 응답 모양은 유지 |
| 신규 | `backend/ontology_api.py` | 온톨로지 탐색 API 라우터 (`/api/patterns`, `/api/case`, `/api/tbox`, `/api/taxonomy`, `/api/search` 등) |
| 수정 | `backend/main.py` | 라우터 연결. Gemini 키가 없어도 서버가 뜨고 `/api/chat`만 503 |
| 수정 | `src/components/GraphPanel.jsx` | 흐름 배치(작업 → 기인물 → 유발요인 → 재해종류 → 예방대책), 경로 강조, 그래프 전체보기 |
| 수정 | `src/components/CasesPanel.jsx` | 카드 한 줄 3개, "사고 패턴" 탭(대표 사례·원인·대책) |
| 신규 | `src/sif/` (`SifExplorer.tsx`, `SifGraph.tsx`, `api.ts`) | 온톨로지 탐색기. 기인물 흐름·T-Box·사례 그래프·사고 패턴·재해종류·공종·업종·유발요인·연도·시기·추락 높이 9개 탭 |
| 수정 | `src/App.jsx` | 온톨로지 전체 탐색 = 탐색기. 기존 GraphPanel은 첫 탭 "기인물 흐름". 보조 채팅 제거 |
| 수정 | `src/data/mockData.js`, `src/api/graph.js`, `src/App.css` | 노드 유형 이름(설비 → 기인물, 위험요인 → 유발요인), 패턴 API 호출, 스타일 |

## 온톨로지 전체 탐색 화면 구성

왼쪽 탭에서 보기를 고릅니다. 사례 찾기(용어 사전 적용: "포크레인", "2021 크레인")와 보는 사람 선택은 모든 탭에 공통입니다.

| 탭 | 내용 |
| --- | --- |
| 기인물 흐름 | 기존 화면. 기인물 하나 기준 작업 → 기인물 → 유발요인 → 재해종류 → 예방대책 |
| T-Box로 보기 | 클래스·관계 구조 위에 지금 사례의 값 표시 |
| 사례 그래프 | 멘토님 A-Box 형식. "흐름 보기"로 단계별 배치 전환, "전체보기" 팝업 |
| 사고 패턴 | 패턴 카드(3열) + 대표 사례·원인·대책 |
| 재해종류 / 공종·업종 / 유발요인 / 연도·시기 / 추락 높이 | 분류 트리. 노드를 누르면 오른쪽에 분포와 사례 목록, 연도 범위 필터 |

`src/sif/`는 TypeScript 파일이지만 Vite가 그대로 빌드하므로 따로 설정할 것은 없습니다. 같은 주소의 `/api`로 요청하고, `vite.config.js`의 프록시가 8000번 백엔드로 넘깁니다.

## 회의 항목 반영 현황

| 회의 항목 | 상태 |
| --- | --- |
| 사고사례 카드 축소, 한 줄에 3개 | 반영 (`.case-grid`, 좁은 화면은 2개·1개) |
| 그래프 전체보기 팝업 | 반영 (툴바 "그래프 전체보기", Esc로 닫기) |
| 온톨로지 전체 탐색 화면에서 채팅 제거 | 반영 |
| 마우스로 노드·관계 탐색, 흐름이 한눈에 (o→o→o) | 반영. 노드에 마우스를 올리거나 누르면 앞뒤로 이어진 경로 전체가 강조되고 입자가 흐름 |
| 중복·유사 사고 그룹화 검토 | 반영 ("사고 패턴": 기인물+재해종류+유발요인, 5건 이상, 대표 사례 2건) |
| 대표 사례·원인·대책 중심 답변 | 패턴 상세 화면에 반영. 채팅 답변 쪽은 아직 |
| 동의어 사전 | 반영 (`ontology/config/aliases.csv` 78개, 패턴 검색에 적용. 예: 포크레인 → 굴착기) |
| 최근 대화·새 채팅·관리자 메뉴 | 미반영 |
| 온톨로지 기반 채팅, Cypher 템플릿 | 미반영 (`/api/chat`은 아직 Gemini 단독) |

## 실행 순서

1. **Neo4j 적재** (처음 한 번, 자료가 늘면 다시)
   ```bash
   cd ontology
   pip install -r requirements.txt
   cp .env.example .env            # backend/.env와 같은 Neo4j 정보
   python ingest.py check
   python ingest.py load "붙임1. 사망사고 고위험요인(SIF) 아카이브(제조업 등, 건설업).xlsx" --dry-run   # 미리보기
   python ingest.py load "붙임1. 사망사고 고위험요인(SIF) 아카이브(제조업 등, 건설업).xlsx"
   ```
2. **백엔드**: `cd backend && pip install -r requirements.txt && uvicorn main:app --reload --port 8000`
3. **프런트**: `npm run dev`

## 주의: Neo4j 스키마가 바뀝니다

기존 `graph.py`가 읽던 스키마(`PreventiveMeasure`, `DURING`, `RESULTED_IN`, `HAS_HAZARD`, 기인물→재해종류 `LEADS_TO`, `MITIGATED_BY`)는 이 저장소에 적재 코드가 없었습니다. 새 스키마는 `ontology/ingest.py`가 만듭니다.

- 같은 DB에 두 스키마를 섞지 마세요. 특히 `LEADS_TO`는 기존에는 기인물→재해종류, 새 스키마에서는 유발요인→재해종류라 뜻이 다릅니다.
- 기존 DB를 남겨 두려면 Neo4j Desktop에서 새 데이터베이스를 만들고 `.env`의 `NEO4J_DATABASE`에 이름을 적으세요. 아니면 기존 데이터를 지운 뒤 적재합니다: `MATCH (n) DETACH DELETE n`.
- 사례 ID는 기존 `public/data/cases.json`과 같은 `sif-1-7` 형식을 `legacyId`로 함께 저장합니다(6,032건 전부 일치 확인). `/api/cases/{id}`는 `sif-1-7`, `SIF-M-0004` 둘 다 받습니다.

## 검증한 것

- 프런트: `npm run lint` 오류 없음, `npm run build` 성공.
- 백엔드: FastAPI 앱을 그대로 띄우고, Neo4j 자리에 실제 6,032건 변환 결과로 응답하는 테스트용 대역을 넣어 모든 수정 엔드포인트를 호출.
- 브라우저: 온톨로지 전체 탐색의 9개 탭 전부, 사례 목록 3열, 사고 패턴 검색·상세·원문 이동을 실제로 눌러 확인. 콘솔 오류 없음.
- **실제 Neo4j에 적재·조회는 아직 확인하지 못했습니다.** 처음에는 `ingest.py check` → `load --dry-run` → `load` 순서로 진행하고, 오류가 나면 메시지를 공유해 주세요.
