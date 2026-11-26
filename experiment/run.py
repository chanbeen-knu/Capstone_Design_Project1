"""온톨로지 챗봇 평가: experiment/questions.csv를 실제 LLM + Neo4j로 실행하고 세 층으로 채점한다.

  ① 질문 이해  — intent가 허용 목록에 있고, 필수 조건(노드 ID)이 모두 연결됐는가
  ② 조회 정확도 — 기대 사실(숫자·이름)과 근거 사례가 답변·블록에 있는가 (기대값은 독립 Cypher로 계산)
  ③ 숫자 근거   — 답변 문장의 숫자·사례 번호가 모두 조회 결과에 있는가 (LLM 환각 검사)

답변 문장 형식은 채점하지 않는다. 사실만 비교하므로 답변 템플릿을 바꿔도 그대로 쓸 수 있다.
실행: backend/.venv/Scripts/python experiment/run.py [--ids Q01,Q08] [--repeat 3]
"""
import argparse
import csv
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'backend'))

import logging  # noqa: E402

import main  # noqa: E402  (backend/.env 로드, LLM 클라이언트)
import ontology_chat  # noqa: E402

logging.getLogger('neo4j.notifications').setLevel(logging.ERROR)  # 전문 검색 deprecation 경고 숨김
NUMBER = re.compile(r'SIF-C-\d{4}|\d[\d,]*(?:\.\d+)?')


def plain(value):
    return re.sub(r'[\s,]', '', str(value))


def split(value, sep='|'):
    return [v.strip() for v in value.split(sep) if v.strip()]


def grade(q, r):
    """질문 한 줄과 챗봇 응답 → 층별 통과 여부와 실패 이유."""
    reasons = []
    intents = split(q['intents'])
    understand = r.get('intent') in intents
    if not understand:
        reasons.append(f"유형 {r.get('intent')} (허용 {'/'.join(intents)})")
    got = r.get('conditions') or {}
    allowed = defaultdict(set)
    for cond in split(q['conditions'], ';'):
        dim, nodes = cond.split('=', 1)  # 'HB:2m 미만|HB:저고소(2m 미만)' = 둘 중 하나면 정답
        allowed[dim] |= set(split(nodes))
        if not set(split(nodes)) & set(got.get(dim, [])):
            understand = False
            reasons.append(f'조건 없음 {cond}')
    # 필수 축에 허용하지 않은 노드가 섞이면 실패 (예: 2m 미만을 물었는데 고소까지 함께 조회). 허용 노드의 하위 노드는 괜찮음
    for dim, ok in allowed.items():
        extra = [n['name'] for n in ontology_chat.names_of(got.get(dim, []))
                 if n['id'] not in ok and not ok & set(n['parents'])]
        if extra:
            understand = False
            reasons.append(f"조건 과다 {dim}: {', '.join(extra)}")
    if q['intents'] == 'unsupported':
        return dict(understand=understand, retrieve=understand, grounded=True, reasons=reasons)

    found = {k: r.get(k) for k in ('block', 'evidence', 'mapping', 'relaxed', 'conditions')}
    haystack = plain(r.get('answer', '') + json.dumps(found, ensure_ascii=False))
    retrieve = True
    for fact in split(q['facts']):
        if plain(fact) not in haystack:
            retrieve = False
            reasons.append(f'사실 없음 {fact}')
    for code in split(q['gold_cases']):
        if code not in haystack:
            retrieve = False
            reasons.append(f'근거 없음 {code}')

    # ③ 문장 속 숫자는 조회 결과(블록·근거·조건)에 있어야 한다. '3가지' 같은 개수 표현은 제외
    source = json.dumps(found, ensure_ascii=False)
    values = {float(plain(n)) for n in NUMBER.findall(source) if not n.startswith('SIF')}
    text = re.sub(r'\d+가지', '', r.get('answer', ''))
    # 숫자는 값으로 비교 (문장 '60.00%' = 데이터 60.0), 사례 번호는 글자로
    stray = [n for n in NUMBER.findall(text)
             if (n not in source if n.startswith('SIF') else float(plain(n)) not in values)]
    for n in stray:
        reasons.append(f'근거 없는 숫자 {n}')
    return dict(understand=understand, retrieve=retrieve, grounded=not stray, reasons=reasons)


def run(questions, repeat):
    if main.client is None:
        sys.exit('backend/.env에 생성 API 키가 없습니다.')
    rows = []
    for q in questions:
        for attempt in range(1, repeat + 1):
            started = time.perf_counter()
            try:
                r = ontology_chat.answer(main.client, main.MODEL_NAME, q['question'], [])
                error = None
            except Exception as exc:  # 한 문항 실패가 전체 실행을 멈추지 않게
                r, error = {}, f'{type(exc).__name__}: {exc}'
            ms = round((time.perf_counter() - started) * 1000)
            g = grade(q, r) if not error else dict(understand=False, retrieve=False, grounded=False, reasons=[error])
            rows.append(dict(id=q['id'], attempt=attempt, persona=q['persona'], category=q['category'],
                             question=q['question'], intent=r.get('intent'), conditions=r.get('conditions'), summary_terms=r.get('summary_terms'),
                             answer=r.get('answer'), block=(r.get('block') or {}).get('kind'),
                             heading=(r.get('block') or {}).get('heading'), latency_ms=ms, error=error, **g))
            mark = '✓' if g['understand'] and g['retrieve'] and g['grounded'] else '✗'
            print(f"{mark} {q['id']}#{attempt} {ms:>5}ms {q['question']}  {'; '.join(g['reasons'])}")
    return rows


def summary(rows, path):
    def rate(items, key):
        return f"{sum(r[key] for r in items)}/{len(items)}"

    lines = [f'# 온톨로지 챗봇 평가 ({path.stem})', '',
             '| 범주 | 문항 | ① 질문 이해 | ② 조회 정확도 | ③ 숫자 근거 |', '|---|---|---|---|---|']
    groups = defaultdict(list)
    for r in rows:
        groups[r['category']].append(r)
    for name, items in groups.items():
        lines.append(f"| {name} | {len(items)} | {rate(items, 'understand')} | {rate(items, 'retrieve')} | {rate(items, 'grounded')} |")
    lines.append(f"| **전체** | {len(rows)} | {rate(rows, 'understand')} | {rate(rows, 'retrieve')} | {rate(rows, 'grounded')} |")
    times = sorted(r['latency_ms'] for r in rows)
    lines += ['', f'응답 시간: 중앙값 {times[len(times) // 2]}ms, 90퍼센타일 {times[int(len(times) * 0.9) - 1]}ms', '']
    if any(r['attempt'] > 1 for r in rows):
        by_id = defaultdict(set)
        for r in rows:
            by_id[r['id']].add(json.dumps([r['intent'], r['conditions'], r.get('summary_terms')], ensure_ascii=False, sort_keys=True))
        stable = sum(len(v) == 1 for v in by_id.values())
        lines += [f'안정성(반복 시 같은 유형·조건·개요 조건): {stable}/{len(by_id)}', '']
    failed = [r for r in rows if not (r['understand'] and r['retrieve'] and r['grounded'])]
    lines += ['## 실패 문항', ''] + [f"- {r['id']}#{r['attempt']} {r['question']} → {'; '.join(r['reasons'])}" for r in failed]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return '\n'.join(lines)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--ids', help='쉼표로 구분한 문항 ID (기본: 전체)')
    ap.add_argument('--repeat', type=int, default=1, help='같은 질문 반복 횟수 (안정성)')
    ap.add_argument('--file', default='questions.csv', help='질문 파일 (예: questions_holdout.csv)')
    args = ap.parse_args()
    with open(ROOT / args.file, encoding='utf-8-sig', newline='') as f:
        questions = list(csv.DictReader(f))
    if args.ids:
        wanted = set(args.ids.split(','))
        questions = [q for q in questions if q['id'] in wanted]
    rows = run(questions, args.repeat)
    out = ROOT / 'results'
    out.mkdir(exist_ok=True)
    stamp = Path(args.file).stem.replace('questions', 'ontology') + datetime.now().strftime('_%Y%m%d_%H%M')
    with open(out / f'{stamp}.jsonl', 'w', encoding='utf-8') as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + '\n' for r in rows)
    print('\n' + summary(rows, out / f'summary_{stamp}.md'))
