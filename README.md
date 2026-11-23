# Capstone_Design_Project1
ontology_safety_ai_agent

## 온톨로지 통합 (2026-10-16)

엑셀 → Neo4j 적재 파이프라인은 `ontology/`, 탐색 API는 `backend/ontology_api.py` 변경사항은 `docs/ontology-integration.md`

## 논문 검증용 최소 LLM 연결 계획 (2026-10-30)

- [최소 연결 계획](docs/graph-chat-template-design.md): 건설업의 사례 조회·계층 집계·대책 종합을 4개 Cypher 템플릿으로 연결하는 설계.
- [최소 실행 검증 계획](docs/graph-chat-evaluation-plan.md): 논문용 실행 결과 3건의 검증 기준과 기록 방식.
- [실제 Neo4j 타당성 점검](docs/graph-chat-feasibility-check.md): 읽기 전용으로 확인한 스키마·적재 현황과 직접 조회 결과. LLM 종단 실행은 아직 미검증.
