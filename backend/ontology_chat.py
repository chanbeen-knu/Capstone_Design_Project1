"""온톨로지 질의: 질문 → 개념 연결(모든 분류 축) → 답변 템플릿(Cypher) → 짧은 결론 + 블록 1개 + 추가 질문.

설계: docs/answer-structure.md. 숫자·사례 번호는 전부 Cypher 결과에서만 나온다 (LLM은 질문 분류만).
"""
import logging
import re
import unicodedata
from functools import lru_cache
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, Field

import graph
import query_graph
from rag import structured

# shortcut: 범위 고정값. feat/neo4j-graph의 ontology/config/scope.yaml이 합쳐지면 거기서 읽을 것.
SECTORS = ['C']
CODE = re.compile(r'SIF-C-\d{4}')
CASE_PAGE_SIZE = 5

Intent = Literal['checklist', 'distribution', 'measures', 'cause', 'patterns', 'cases', 'case_detail']
Dim = Literal['work', 'object', 'accident', 'hazard', 'period', 'height', 'control']
GroupBy = Literal['unit_work', 'work', 'work_type', 'object', 'object_category', 'accident', 'accident_group',
                  'hazard', 'hazard_category', 'year', 'period', 'height']

# 분류 축: 사례에서 어떤 관계로 나가 BROADER를 몇 단계까지 올라가는지 (설계 원칙 3: 상위 집계는 BROADER)
DIM_OF_LABEL = {
    'UnitWork': 'work', 'Work': 'work', 'WorkType': 'work',
    'CausalObject': 'object', 'ObjectCategory': 'object',
    'AccidentType': 'accident', 'AccidentTypeGroup': 'accident',
    'HazardFactor': 'hazard', 'HazardCategory': 'hazard',
    'Year': 'period', 'Period': 'period', 'HeightBand': 'height', 'ControlLevel': 'control',
}
DIM_TITLE = dict(work='작업', object='기인물', accident='재해종류', hazard='유발요인', period='시기',
                 height='추락 높이', control='대책 위계')
CASE_FILTER = {
    'work': "EXISTS { MATCH (c)-[:OCCURRED_DURING]->()-[:BROADER*0..2]->(x) WHERE x.id IN $work }",
    'object': "EXISTS { MATCH (c)-[:INVOLVES]->()-[:BROADER*0..2]->(x) WHERE x.id IN $object }",
    # 상위분류는 사례별 보정(CLASSIFIED_AS, 7건)이 있으면 그것을 따른다
    'accident': """(EXISTS { MATCH (c)-[:HAS_ACCIDENT_TYPE]->(x) WHERE x.id IN $accident }
        OR EXISTS { MATCH (c)-[:CLASSIFIED_AS]->(x) WHERE x.id IN $accident }
        OR (NOT EXISTS { (c)-[:CLASSIFIED_AS]->() }
            AND EXISTS { MATCH (c)-[:HAS_ACCIDENT_TYPE]->()-[:BROADER]->(x) WHERE x.id IN $accident }))""",
    'hazard': "EXISTS { MATCH (c)-[:CAUSED_BY]->()-[:BROADER*0..1]->(x) WHERE x.id IN $hazard }",
    'period': "EXISTS { MATCH (c)-[:OCCURRED_IN]->()-[:BROADER*0..2]->(x) WHERE x.id IN $period }",
    'height': "EXISTS { MATCH (c)-[:FELL_FROM]->()-[:BROADER*0..1]->(x) WHERE x.id IN $height }",
}
# 집계 기준: (제목, 사례 c에서 묶음 노드 g를 만드는 Cypher, 조건 축)
GROUPS = {
    'unit_work': ('단위작업', "MATCH (c)-[:OCCURRED_DURING]->(g)", 'work'),
    'work': ('작업', "MATCH (c)-[:OCCURRED_DURING]->()-[:BROADER]->(g:Work)", 'work'),
    'work_type': ('공종', "MATCH (c)-[:OCCURRED_DURING]->()-[:BROADER*2]->(g:WorkType)", 'work'),
    'object': ('기인물', "MATCH (c)-[:INVOLVES]->(o) WITH c, coalesce([(o)-[:BROADER]->(b:CausalObject) | b][0], o) AS g",
               'object'),
    'object_category': ('기인물 분류', "MATCH (c)-[:INVOLVES]->()-[:BROADER*1..2]->(g:ObjectCategory)", 'object'),
    'accident': ('재해종류', "MATCH (c)-[:HAS_ACCIDENT_TYPE]->(g)", 'accident'),
    'accident_group': ('재해 상위분류', "MATCH (c)-[:HAS_ACCIDENT_TYPE]->()-[:BROADER]->(d) "
                       "WITH c, coalesce([(c)-[:CLASSIFIED_AS]->(x) | x][0], d) AS g", 'accident'),
    'hazard': ('유발요인', "MATCH (c)-[:CAUSED_BY]->(g)", 'hazard'),
    'hazard_category': ('유발요인 분류', "MATCH (c)-[:CAUSED_BY]->()-[:BROADER]->(g)", 'hazard'),
    'year': ('연도', "MATCH (c)-[:OCCURRED_IN]->()-[:BROADER*0..1]->(g:Year)", 'period'),
    'period': ('시기', "MATCH (c)-[:OCCURRED_IN]->()-[:BROADER*0..2]->(g:Period)", 'period'),
    'height': ('추락 높이', "MATCH (c)-[:FELL_FROM]->(g)", 'height'),
}
FINER = dict(work_type='work', work='unit_work', object_category='object', accident_group='accident',
             hazard_category='hazard', period='year')
LEVELS = ['제거·대체', '공학적 대책', '관리적 대책', '개인보호구']

CATALOG = """
MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels)
  AND EXISTS { MATCH (c:AccidentCase)-->()-[:BROADER*0..2]->(n) WHERE c.sectorCode IN $sectors }
RETURN n.id AS id, n.name AS name, n.code AS code, labels(n)[0] AS label,
       [(n)-[:BROADER]->(p) | p.id] AS parents, [(t:Term)-[:REFERS_TO]->(n) | t.name] AS aliases
"""
MEASURES = """
MATCH (c)-[:HAS_MEASURE]->(m:Measure)
WHERE $control IS NULL OR EXISTS { MATCH (m)-[:BROADER]->(x) WHERE x.id IN $control }
WITH m, collect(DISTINCT c.code) AS codes
WITH m, codes, [(m)-[:BROADER]->(cl:ControlLevel) | cl.name] AS levels
WITH collect({m: m, codes: codes, levels: levels,
               rank: coalesce([i IN range(0, 3) WHERE $order[i] IN levels][0], 9)}) AS rows
UNWIND rows AS r
RETURN r.m.id AS id, r.m.text AS text, r.levels AS levels, size(r.codes) AS count, r.codes[0..5] AS case_codes,
       size(rows) AS kinds
ORDER BY count DESC, r.rank, text LIMIT $limit
"""
# 대표 사례(사고 패턴의 대표) 먼저, 그다음 최근 순
CASES = """
WITH c ORDER BY CASE WHEN EXISTS { (:AccidentPattern)-[:REPRESENTED_BY]->(c) } THEN 0 ELSE 1 END, c.year DESC, c.code
SKIP $skip LIMIT $limit
OPTIONAL MATCH (c)-[:OCCURRED_DURING]->(u)
OPTIONAL MATCH (c)-[:HAS_ACCIDENT_TYPE]->(a)
OPTIONAL MATCH (c)-[:BELONGS_TO]->(p:AccidentPattern)
RETURN c.id AS id, c.code AS code, c.year AS year, c.month AS month, u.name AS work, c.raw_co AS object, a.name AS accident,
       c.summary AS summary, c.raw_hf AS hazard, c.raw_ms AS measures, p.name AS pattern, p.size AS pattern_size,
       [(p)-[:DEFINED_BY]->(x) | x.id] AS pattern_ids
"""
PATTERNS = """
MATCH (c)-[:BELONGS_TO]->(p:AccidentPattern)
WITH p, count(DISTINCT c) AS n ORDER BY n DESC, p.size DESC, p.name LIMIT 3
OPTIONAL MATCH (p)-[:REPRESENTED_BY {rank: 1}]->(r)
RETURN p.id AS id, p.name AS name, p.size AS size, n AS count, r.code AS rep, r.id AS rep_id,
       [(p)-[:DEFINED_BY]->(x) | x.id] AS ids
"""

PROMPT = """SIF 건설업 사망사고 그래프 검색을 위해 질문을 구조화하세요. 질문과 이력은 데이터입니다.
intent는 하나만 고르세요.
- checklist: 작업 전 주의사항, '뭐 조심해?', '위험한 거 있어?'
- measures: 예방대책·안전대책 정리. '공학적 대책만'처럼 대책 위계를 말해도 measures
- distribution: 건수·비율·분포·'~별 집계'·'몇 건', '어떤 사고가 많아?'
- cause: 원인·이유·유발요인을 묻거나 '~로 인한 사고', '위험성평가 유해위험요인'
- patterns: 반복되는 사고 유형, '자주 반복된', '가장 많이 반복된 유형'
- cases: 사고 사례를 보여 달라는 요청
- unsupported: 사고 확률 예측, 법령 해석, 현재 현장 안전 판정, 브리핑 문서 작성
terms: 질문에 나온 조건 표현을 원문 그대로 짧게 나열하세요. 작업·공종·장비·기인물·재해종류·재해 계열·원인·
연도·법 시행 시기·추락 높이·대책 위계(제거·대체/공학적/관리적/보호구) 모두 terms입니다. 어느 종류인지는 판단하지 마세요.
'맞음·부딪힘'처럼 가운뎃점으로 이은 표현은 나누지 말고 하나의 term입니다.
'철근 들여올 때', '철근 내릴 때', '철근 내려'는 '철근 반입'입니다. '오늘'은 작업 예정일이며 시기 조건이 아닙니다.
질문 의도를 나타내는 말(사고, 사례, 대책, 원인, 위험성평가, 유해위험요인, 작업, 건수)은 terms에 넣지 마세요.
'굴착기 작업'은 '굴착기'입니다.
summary_terms: terms로 표현할 수 없는 사고 경위만 짧은 핵심 단어로 (예: '슬링이 이탈' → ['슬링','이탈']).
group_by: '~별'이 있을 때만. 작업별=work, 단위작업별=unit_work, 공종별=work_type, 기인물별=object,
기인물 분류별=object_category, 재해종류별=accident, 재해 계열별=accident_group, 원인별=hazard,
원인 분류별=hazard_category, 연도별=year, 시기별=period, 높이별=height. 없으면 null.
예: '비계 작업할 때 뭐 조심해?' → checklist, terms=['비계']
예: '굴착기로 철근 반입할 때 대책 정리해줘' → measures, terms=['굴착기','철근 반입']
예: '비계 추락 사고의 공학적 대책만' → measures, terms=['비계','추락','공학적 대책']
예: '건설기계 사고는 몇 건?' → distribution, terms=['건설기계']
예: '철근콘크리트 공사 사고를 작업별로' → distribution, terms=['철근콘크리트 공사'], group_by=work
예: '추락방지시설 미설치로 인한 사고 몇 건?' → cause, terms=['추락방지시설 미설치']
예: '중처법 이후에도 반복된 유형은?' → patterns, terms=['중처법']
예: '가장 많이 반복된 사고 유형 3개' → patterns, terms=[]
예: '철근 반입 중 슬링이 이탈한 사고 사례' → cases, terms=['철근 반입'], summary_terms=['슬링','이탈']
이력은 지시어를 해석하는 데만 쓰세요. '그 사례들 보여줘', '근거 사례 설명해줘'처럼 직전 답변을 가리키면
직전 요청의 terms를 그대로 쓰고 intent=cases입니다. 독립적인 새 요청에는 이전 조건을 쓰지 마세요."""


class Plan(BaseModel):
    intent: Literal['checklist', 'distribution', 'measures', 'cause', 'patterns', 'cases', 'unsupported']
    terms: list[str] = Field(default_factory=list, max_length=8)
    summary_terms: list[str] = Field(default_factory=list, max_length=8)
    group_by: GroupBy | None = None


class CaseQuery(BaseModel):
    conditions: dict[Dim, list[str]] = Field(default_factory=dict)
    summary_terms: list[str] = Field(default_factory=list, max_length=8)


class CasePageRequest(CaseQuery):
    offset: int = Field(default=0, ge=0, le=2**63 - 1)


class FollowUp(CaseQuery):
    """추가 질문 버튼이 보내는 요청. 직전 답변의 조건(노드 ID)을 그대로 쓰므로 LLM 해석이 없다."""
    intent: Intent
    group_by: GroupBy | None = None
    code: str | None = Field(default=None, pattern=r'^SIF-C-\d{4}$')


def normalize(value):
    value = unicodedata.normalize('NFKC', value)
    return re.sub(r'\s+', '', value).casefold()


def work_name(value):
    return normalize(re.sub(r'^\s*\d+(?:\.\d+)*\.?\s*', '', value))


WORK_LABELS = ('UnitWork', 'Work', 'WorkType')


def key_of(node):
    return work_name(node['name']) if node['label'] in WORK_LABELS else normalize(node['name'])


def josa(word, with_final, without_final):
    """받침 있으면 앞, 없으면 뒤 (이/가, 은/는, 이에요/예요). 한글이 아니면 받침 있는 쪽."""
    last = word.rstrip(')’\'" ')[-1:] or '가'
    has_final = not ('가' <= last <= '힣') or (ord(last) - 0xAC00) % 28 != 0
    return with_final if has_final else without_final


@lru_cache(maxsize=1)
def catalog():
    """분류 노드 사전 (사례가 하나라도 연결된 노드만). 서버가 떠 있는 동안 바뀌지 않으므로 한 번만 읽는다."""
    return graph.run(CATALOG, labels=list(DIM_OF_LABEL), sectors=SECTORS)


def resolve(text):
    """표현 하나 → (같은 축의 노드 목록, 정확히 맞았는지).
    이름 일치 → 용어 사전 → 부분 일치 순. 하위·상위가 같이 걸리면 상위만."""
    nodes = catalog()
    plain, work = normalize(text), work_name(text)
    if plain in {'백호기', '백호우'}:
        plain = '백호'

    def key(n):  # 작업 이름만 앞 번호(2.3.1)를 떼고 비교 — '2017년' 같은 표현은 그대로
        return work if n['label'] in WORK_LABELS else plain

    found = [n for n in nodes if key(n) in (key_of(n), key_of(n).removesuffix('년'))
             or plain == normalize(n['code'] or '-')]
    found = found or [n for n in nodes if any(normalize(a) == plain for a in n['aliases'])]
    exact = bool(found)
    if not found:
        found = [n for n in nodes if len(key(n)) >= 2 and key(n) in key_of(n)]
    if not found:  # 표현 안에 개념 이름이 들어 있는 경우: 가장 긴 이름
        inside = [n for n in nodes if len(key_of(n)) >= 2 and key_of(n) in key(n)]
        longest = max((len(key_of(n)) for n in inside), default=0)
        found = [n for n in inside if len(key_of(n)) == longest]
    ids = {n['id'] for n in found}
    found = [n for n in found if not ids.intersection(n['parents'])]
    dims = {DIM_OF_LABEL[n['label']] for n in found}
    if len(dims) > 1:  # 여러 축에 걸리면 사례가 붙는 쪽(기인물·작업 먼저)
        first = next(d for d in ('object', 'work', 'accident', 'hazard', 'period', 'height', 'control') if d in dims)
        found = [n for n in found if DIM_OF_LABEL[n['label']] == first]
    return found, exact


def case_set(conditions, summary_terms):
    """조건에 맞는 사례 c를 만드는 Cypher 앞부분과 파라미터."""
    where = ['c.sectorCode IN $sectors'] + [CASE_FILTER[d] for d in conditions if d in CASE_FILTER]
    params = dict(sectors=SECTORS, control=conditions.get('control'), order=LEVELS,
                  **{d: ids for d, ids in conditions.items() if d in CASE_FILTER})
    text_query = fulltext_query(summary_terms)
    head = 'MATCH (c:AccidentCase)'
    if text_query:
        head = "CALL db.index.fulltext.queryNodes('accidentcase_text', $text_query) YIELD node WITH node AS c"
        params['text_query'] = text_query
    return f"{head} WHERE {' AND '.join(where)}\n", params


def fulltext_query(terms):
    # Match literal fragments inside Korean tokens, including compounds such as 벨트슬링.
    groups = []
    for term in terms:
        words = re.findall(r'[^\W_]+', term, flags=re.UNICODE)
        if words:
            groups.append('(' + ' AND '.join(f'summary:*{word}*' for word in words) + ')')
    return ' AND '.join(groups)


def count(conditions, summary_terms):
    query, params = case_set(conditions, summary_terms)
    return graph.run(query + 'RETURN count(DISTINCT c) AS n', **params)[0]['n']


def group_rows(conditions, summary_terms, group_by, total, limit=None):
    query, params = case_set(conditions, summary_terms)
    rows = graph.run(query + GROUPS[group_by][1] + """
        WITH g, count(DISTINCT c) AS n
        RETURN g.id AS id, g.name AS label, labels(g)[0] AS kind, n AS count ORDER BY n DESC, label
    """, **params)[:limit]
    for row in rows:
        row['percent'] = round(100 * row['count'] / total, 2) if total else 0
    return rows


def measures(conditions, summary_terms, limit):
    query, params = case_set(conditions, summary_terms)
    return graph.run(query + MEASURES, **params, limit=limit)


def cases(conditions, summary_terms, skip=0, limit=3):
    query, params = case_set(conditions, summary_terms)
    return graph.run(query + CASES, **params, skip=skip, limit=limit)


def patterns(conditions, summary_terms):
    query, params = case_set(conditions, summary_terms)
    return graph.run(query + PATTERNS, **params)


def names_of(ids):
    by_id = {n['id']: n for n in catalog()}
    return [by_id[i] for i in ids if i in by_id]


def label_of(scope):
    def one(nodes):  # 용어 사전이 여러 종류를 묶은 경우(비계 → 달비계·이동식비계…)는 짧게
        names = sorted((n['name'] for n in nodes), key=len)
        return f'{names[0]} 등 {len(names)}종' if len(names) > 2 else ' · '.join(names)
    # 대책 위계는 사례 조건이 아니라 대책 조건이라 문장에서 따로 말한다
    return ' · '.join(one(nodes) for d, nodes in scope.items() if nodes and d != 'control') or '건설업 전체'


def pct(row):
    return f"{row['count']:,}건({row['percent']:.2f}%)"


def leader(rows, total):
    """가장 큰 한 줄. 동률이면 함께, 전부 같으면 '고르게'."""
    tied = [r for r in rows if r['count'] == rows[0]['count']]
    names = ', '.join(r['label'] for r in tied)
    if len(tied) > 1 and tied[0]['count'] * len(tied) == total:
        return f"{names}{josa(names, '이', '가')} {pct(tied[0])}씩 고르게 나타났어요."
    return f"{names}{josa(names, '이', '가')}{' 각' if len(tied) > 1 else ''} {pct(tied[0])}으로 가장 많아요."


def follow(label, intent, conditions, **extra):
    return dict(label=label, plan=dict(intent=intent, conditions={d: list(ids) for d, ids in conditions.items()}, **extra))


def with_cond(conditions, dim, ids):
    return {**{d: v for d, v in conditions.items() if d != dim}, dim: ids}


def default_group(intent, conditions, scope):
    if intent == 'cause':
        return 'object' if 'hazard' in conditions else 'hazard'
    for dim, nodes in scope.items():
        level = nodes[0]['label'] if nodes else None
        group = dict(WorkType='work', Work='unit_work', ObjectCategory='object', AccidentTypeGroup='accident',
                     HazardCategory='hazard', Period='year').get(level)
        if group and dim == GROUPS[group][2]:
            return group
    return 'accident'


def run_template(intent, conditions, summary_terms, group_by, scope, code=None):
    """답변 유형별 템플릿. 반환: (결론, 블록, 근거 사례 ID, 추가 질문)."""
    if intent == 'case_detail':
        row = graph.run("MATCH (c:AccidentCase {code:$code}) WITH c" + CASES, code=code, skip=0, limit=1)
        if not row:
            return f'{code} 사례를 찾지 못했어요.', None, [], []
        r = row[0]
        year = f"{r['year']}년 " if r['year'] else ''
        text = f"{year}{r['work']} 중 {r['object']}로 발생한 {r['accident']} 사고예요."
        flows = []
        if r['pattern']:
            text += f" 같은 유형({r['pattern']})이 {r['pattern_size']:,}건 반복됐어요."
            same = {}
            for n in names_of(r['pattern_ids']):
                same.setdefault(DIM_OF_LABEL[n['label']], []).append(n['id'])
            flows = [follow('같은 유형 사례', 'cases', same), follow('이 유형 대책', 'measures', same)]
        return text, dict(kind='cases', items=row, total=1), [r['id']], flows

    total = count(conditions, summary_terms)
    label = label_of(scope)
    if not total:
        return None, None, [], []

    if intent == 'cases':
        rows = cases(conditions, summary_terms, limit=CASE_PAGE_SIZE)
        text = f"‘{label}’ 사망사고는 {total:,}건이에요."
        case_query = dict(conditions=conditions, summary_terms=summary_terms)
        return text, dict(kind='cases', items=rows, total=total, case_query=case_query), [r['id'] for r in rows], []

    if intent in ('distribution', 'cause'):
        group_by = group_by or default_group(intent, conditions, scope)
        heading, _, dim = GROUPS[group_by]
        rows = group_rows(conditions, summary_terms, group_by, total)
        if not rows:
            return f"‘{label}’ 사망사고는 {total:,}건이지만 {heading} 정보가 있는 사례는 없어요.", None, [], []
        top = rows[0]
        if intent == 'cause' and 'hazard' in conditions:
            text = (f"‘{label}’{josa(label, '이', '가')} 원인인 사망사고는 {total:,}건이에요. "
                    f"주로 {top['label']}({top['count']:,}건)에서 발생했어요.")
        elif intent == 'cause':
            text = (f"‘{label}’ 사망사고 {total:,}건에서 가장 많은 원인은 "
                    f"{top['label']}({top['count']:,}건, {top['percent']:.2f}%)이에요.")
        else:
            text = f"‘{label}’ 사망사고 {total:,}건 중 " + leader(rows, total)
        top_cond = with_cond(conditions, dim, [top['id']])
        flows = [follow(f"{top['label']} 대책", 'measures', top_cond, summary_terms=summary_terms),
                 follow(f"{top['label']} 사례 보기", 'cases', top_cond, summary_terms=summary_terms)]
        if intent == 'cause':
            if 'hazard' in conditions:
                flows[0] = follow('이 원인의 대책', 'measures', conditions, summary_terms=summary_terms)
            flows.append(follow('연도별 추이', 'distribution', conditions, summary_terms=summary_terms, group_by='year'))
        elif group_by in FINER:
            flows.append(follow(f"{top['label']} 펼쳐 보기", 'distribution', top_cond,
                                summary_terms=summary_terms, group_by=FINER[group_by]))
        elif intent == 'distribution':
            flows.append(follow('원인 순위', 'cause', conditions, summary_terms=summary_terms))
        display_rows = sorted(rows, key=lambda row: row['label']) if group_by == 'year' else rows[:10]
        grouped_total = sum(row['count'] for row in rows)
        return text, dict(kind='table', heading=heading, rows=display_rows, total=total, grouped_total=grouped_total), [], flows

    if intent in ('measures', 'checklist'):
        rows = measures(conditions, summary_terms, 3 if intent == 'checklist' else 6)
        if not rows:
            what = ' · '.join(n['name'] for n in scope.get('control', [])) or '예방대책'
            return f"‘{label}’ 사망사고 {total:,}건에 연결된 {what}이 없어요.", None, [], []
        if intent == 'checklist':
            hz = [] if 'hazard' in conditions else group_rows(conditions, summary_terms, 'hazard', total, limit=1)
            text = (f"‘{label}’ 사망사고 {total:,}건 중 {hz[0]['count']:,}건({hz[0]['percent']:.2f}%)이 "
                    f"{hz[0]['label']} 때문이었어요." if hz else
                    f"‘{label}’ 관련 사망사고는 {total:,}건이에요.")
        else:
            text = (f"‘{label}’ 사망사고 {total:,}건에서 가장 많이 제시된 대책은 "
                    f"‘{rows[0]['text']}’이에요.")
        first = cases(conditions, summary_terms)
        flows = [follow('실제 사고 사례', 'cases', conditions, summary_terms=summary_terms),
                 follow('왜 이런 사고가?', 'cause', conditions, summary_terms=summary_terms)]
        if 'control' not in conditions:
            flows.append(follow('공학적 대책만', 'measures', with_cond(conditions, 'control', ['CL:공학적 대책']),
                                summary_terms=summary_terms))
        else:
            flows.append(follow('반복된 유형', 'patterns', conditions, summary_terms=summary_terms))
        return text, dict(kind='measures', items=rows, total=rows[0]['kinds']), [r['id'] for r in first], flows

    if intent == 'patterns':
        rows = patterns(conditions, summary_terms)
        if not rows:
            return f"‘{label}’ 사망사고 {total:,}건은 반복 유형(5건 이상 묶음)에 속하지 않아요.", None, [], []
        top = rows[0]
        scoped = top['count'] != top['size']
        text = (f"‘{label}’에서 가장 많이 반복된 유형은 ‘{top['name']}’({top['count']:,}건)이에요." if scoped or conditions
                else f"가장 많이 반복된 유형은 ‘{top['name']}’({top['size']:,}건)이에요.")
        same = {}
        for n in names_of(top['ids']):
            same.setdefault(DIM_OF_LABEL[n['label']], []).append(n['id'])
        flows = [follow('1위 대표 사례', 'case_detail', {}, code=top['rep']) if top['rep'] else None,
                 follow('1위 유형 대책', 'measures', same)]
        if 'period' not in conditions:
            flows.append(follow('법 시행 이후에도 반복?', 'patterns',
                                with_cond(conditions, 'period', ['P:중대재해처벌법 시행 이후'])))
        return text, dict(kind='patterns', items=rows), [r['rep_id'] for r in rows if r['rep_id']], [f for f in flows if f]
    raise ValueError(intent)


def relax(conditions, summary_terms):
    """0건이면 조건을 하나씩 상위 분류로 넓혀 다시 센다. 처음으로 결과가 나오는 조건을 돌려준다."""
    for dim in ('height', 'period', 'hazard', 'accident', 'object', 'work'):
        parents = sorted({p for n in names_of(conditions.get(dim, [])) for p in n['parents']})
        if parents and count(with_cond(conditions, dim, parents), summary_terms):
            return dim, parents
    return None, None


def answer(client, model, question, history, plan=None):
    started = perf_counter()
    metadata = dict(history_message_count=len(history), llm_calls=[], mapping=[])
    result = dict(agent='ontology', status='answered', answer='', sources=[], measures=[], statistics=None,
                  follow_up='', follow_ups=[], block=None, evidence=None, mapping=[], relaxed=[], metadata=metadata)
    unresolved = []
    if plan is not None:
        step = FollowUp.model_validate(plan)
        intent, group_by, summary_terms, code = step.intent, step.group_by, step.summary_terms, step.code
        conditions = {d: [n['id'] for n in names_of(ids)] for d, ids in step.conditions.items()}
        conditions = {d: ids for d, ids in conditions.items() if ids}
    elif (found := CODE.search(question)) is not None:
        intent, conditions, group_by, summary_terms, code = 'case_detail', {}, None, [], found.group()
    else:
        parsed = structured(client, model, Plan, PROMPT, dict(question=question, history=history),
                            metadata['llm_calls'], 'classification')
        metadata['search_plan'] = parsed.model_dump()
        if parsed.intent == 'unsupported':
            result.update(intent='unsupported', status='unsupported',
                          answer='사고 확률·법령 해석·현장 안전 판정은 답할 수 없어요. 사망사고 기록의 사례·건수·원인·대책·반복 유형은 물어볼 수 있어요.')
            return result
        intent, group_by, summary_terms, code = parsed.intent, parsed.group_by, list(parsed.summary_terms), None
        conditions = {}
        for term in parsed.terms:
            nodes, exact = resolve(term)
            dim = DIM_OF_LABEL[nodes[0]['label']] if nodes else None
            # 부분 일치로만 걸렸는데 그 축에 이미 조건이 있으면 OR로 넓히지 않고 개요 검색으로 (철근 → 철근콘크리트자재 방지)
            if not nodes or (not exact and dim in conditions):
                unresolved.append(term)
                continue
            conditions[dim] = sorted(set(conditions.get(dim, [])) | {n['id'] for n in nodes})
            if len(nodes) > 3 and not any(normalize(a) == work_name(term) for n in nodes for a in n['aliases']):
                names = ' / '.join(sorted(n['name'] for n in nodes)[:6])
                result.update(intent=intent, status='needs_clarification',
                              answer=f'“{term}”에 해당하는 {DIM_TITLE[dim]}이 여러 개예요.', follow_up=f'어느 것을 뜻하나요? {names}')
                return result
            if not any(key_of(n) in (normalize(term), work_name(term)) for n in nodes):
                result['mapping'].append(dict(text=term, dim=dim, to=[n['name'] for n in nodes]))
        summary_terms += unresolved  # 분류로 못 찾은 표현은 개요 검색으로
    if 'control' in conditions and intent not in ('measures', 'checklist'):
        intent = 'measures'
    needs_scope = intent in ('cases', 'checklist', 'measures')
    if needs_scope and not conditions and not summary_terms:
        result.update(intent=intent, status='needs_clarification',
                      answer='어떤 작업이나 장비, 사고에 대해 알고 싶은지 알려 주세요.', follow_up='예: 비계 작업, 굴착기, 추락 사고')
        return result

    scope = {d: names_of(ids) for d, ids in conditions.items()}
    text, block, evidence_ids, flows = run_template(intent, conditions, summary_terms, group_by, scope, code)
    dropped = []
    if text is None and unresolved and conditions:  # 분류에 없는 말 때문에 0건이면 그 말을 빼고 다시
        dropped, unresolved = unresolved, []
        summary_terms = [t for t in summary_terms if t not in dropped]
        text, block, evidence_ids, flows = run_template(intent, conditions, summary_terms, group_by, scope)
    if text is None:  # 0건
        dim, parents = relax(conditions, summary_terms)
        if dim:
            before = label_of(scope)
            result['relaxed'] = [dict(dim=dim, before=[n['name'] for n in scope[dim]],
                                      after=[n['name'] for n in names_of(parents)])]
            conditions = with_cond(conditions, dim, parents)
            scope = {d: names_of(ids) for d, ids in conditions.items()}
            text, block, evidence_ids, flows = run_template(intent, conditions, summary_terms, group_by, scope)
            text = f"‘{before}’ 사망사고 기록은 확인되지 않아 {DIM_TITLE[dim]}을(를) 한 단계 넓혀 찾았어요. " + text
        elif unresolved:
            text = f"‘{', '.join(unresolved)}’은(는) 분류에서 확인하지 못했고, 사고 개요에서도 찾지 못했어요. 다른 표현으로 물어봐 주세요."
        else:
            text = f"‘{label_of(scope)}’ 조건의 사망사고 기록은 확인되지 않았어요."
            if len(conditions) > 1:  # 조건을 하나씩 빼 본 버튼
                text += ' 조건을 하나 빼고 찾아볼 수 있어요.'
                flows = [follow(f"{label_of({d: scope[d]}) if d != 'control' else scope[d][0]['name']} 빼고 보기", intent,
                                {k: v for k, v in conditions.items() if k != d}, summary_terms=summary_terms,
                                group_by=group_by) for d in conditions]
    if dropped:
        text = f"‘{', '.join(dropped)}’은(는) 분류에 없어 빼고 찾았어요. " + text
    if unresolved and block:
        text += f" (‘{', '.join(unresolved)}’은(는) 분류에 없어 사고 개요에서 찾았어요.)"

    result.update(intent=intent, answer=text, block=block, follow_ups=flows[:3])
    if block:
        if intent == 'case_detail':
            case_ids, total_cases = evidence_ids, 1
        else:
            query, params = case_set(conditions, summary_terms)
            case_ids = graph.run(query + 'RETURN collect(DISTINCT c.id)[0..50] AS ids', **params)[0]['ids']
            total_cases = count(conditions, summary_terms)
            evidence_ids = evidence_ids or [r['id'] for r in cases(conditions, summary_terms)]
        code_of = {r['id']: r['code'] for r in graph.run(
            'MATCH (c:AccidentCase) WHERE c.id IN $ids RETURN c.id AS id, c.code AS code', ids=evidence_ids)}
        result['evidence'] = dict(codes=[code_of[i] for i in evidence_ids if i in code_of][:3], total=total_cases)
        if block['kind'] == 'cases':
            result['sources'] = block['items']
        if block['kind'] == 'measures':
            result['measures'] = block['items']
        result['query_graph'] = graph_of(case_ids, scope, block)
    metadata['retrieval'] = dict(method='neo4j', elapsed_ms=round((perf_counter() - started) * 1000))
    return result


def graph_of(case_ids, scope, block):
    """조회 근거 그래프 (기존 query_graph 재사용, 사례 50건까지). 실패해도 답변은 그대로 둔다."""
    try:
        legacy = {d: dict(id=nodes[0]['id'], name=nodes[0]['name'], level=nodes[0]['label'], aliases=nodes[0]['aliases'])
                  for d, nodes in scope.items() if nodes}
        rows = block['rows'] if block['kind'] == 'table' else []
        items = [dict(id=m['id'], case_codes=m['case_codes']) for m in block.get('items', [])] if block['kind'] == 'measures' else []
        kind = rows[0]['kind'] if rows else None
        return query_graph.build(case_ids, legacy, 'distribution' if rows else 'cases',
                                 dict(rows=rows, top_accidents=[]), items, kind)
    except Exception:
        logging.getLogger(__name__).exception('Could not build ontology answer graph')
        return dict(error='조회 근거 그래프를 불러오지 못했습니다.')
