"""Construction-only graph QA. Query code and all statistics belong to the backend."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from neo4j import Query, READ_ACCESS
from pydantic import BaseModel, ConfigDict, Field, ValidationError

import graph
from chat_templates import TEMPLATES

PROMPT_VERSION = 'paper-minimal-v3'
EVIDENCE_LIMIT = 10
MEASURE_LIMIT = 10

# Metadata inspection only; these are not additional user retrieval templates.
CATALOG_QUERY = """
MATCH (c:AccidentCase {sectorCode: 'C'})
OPTIONAL MATCH (c)-[:OCCURRED_DURING]->(u:UnitWork)
OPTIONAL MATCH (u)-[:BROADER]->(w:Work)-[:BROADER]->(t:WorkType)
OPTIONAL MATCH (c)-[:INVOLVES]->(leaf:CausalObject)
OPTIONAL MATCH (leaf)-[:BROADER*0..1]->(o:CausalObject)
RETURN count(DISTINCT c) AS construction_count,
       count(DISTINCT CASE WHEN t IS NOT NULL THEN c END) AS hierarchy_coverage,
       collect(DISTINCT u {.id, .name, label: 'UnitWork'}) AS unit_works,
       collect(DISTINCT w {.id, .name, label: 'Work'}) AS works,
       collect(DISTINCT t {.id, .name, label: 'WorkType'}) AS work_types,
       collect(DISTINCT o {.id, .name, label: 'CausalObject'}) AS objects
"""
ALIASES_QUERY = """
MATCH (term:Term)-[:REFERS_TO]->(n) WHERE n.id IN $node_ids
RETURN DISTINCT term.name AS term, n.id AS node_id ORDER BY term, node_id
"""

SUPPORT_MESSAGE = (
    '현재 건설업 데이터에서 다음 질의만 지원합니다.\n'
    '1. 단위작업 하나 또는 기인물 하나의 사고사례 조회\n'
    '2. 공종·작업·단위작업의 전체 사고 건수와 비율 집계\n'
    '3. 단위작업과 기인물을 함께 지정한 예방대책 종합\n'
    '기간·재해종류 등의 추가 조건과 자유서술 상황 검색은 지원하지 않습니다.'
)


class LLMError(Exception):
    """Provider failure; do not expose credentials or provider messages."""


class DataIntegrityError(Exception):
    """The inspected graph does not satisfy the required hierarchy/evidence contract."""


class Clarification(Exception):
    pass


class Interpretation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    intent: Literal['case_lookup', 'hierarchy_aggregate', 'measure_summary',
                    'unsupported', 'needs_clarification']
    unit_work: str | None = None
    causal_object: str | None = None
    scope: str | None = None
    group_by: Literal['WorkType', 'Work', 'UnitWork'] | None = None
    unsupported_conditions: list[str] = []
    reason: str | None = None


class CaseExplanation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_code: str
    text: str = Field(min_length=1, max_length=800)


class Explanation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    explanations: list[CaseExplanation] = Field(min_length=1, max_length=3)


def read_query(cypher, **params):
    with graph.get_driver().session(
        database=os.getenv('NEO4J_DATABASE') or None, default_access_mode=READ_ACCESS,
    ) as session:
        return [r.data() for r in session.run(Query(cypher, timeout=10), **params)]


def _normalize(value):
    return re.sub(r'\s+', '', value).casefold()


def _short_name(name):
    return re.sub(r'^\s*\d+(?:\.\d+)*\.?\s*', '', name)


def _unsupported(question, catalog):
    # A complete catalog name is one condition, even when its spelling contains
    # words such as "추락", "낙하", or "또는". Check only the surrounding text.
    remaining = question
    names = {name for node in catalog['nodes'].values()
             for name in (node['name'], _short_name(node['name'])) if name}
    for name in sorted(names, key=lambda value: (-len(_normalize(value)), value)):
        pattern = r'\s*'.join(re.escape(char) for char in _normalize(name))
        remaining = re.sub(pattern, ' ', remaining, flags=re.IGNORECASE)
    patterns = [
        r'제조업|전\s*업종|전체\s*업종',
        r'(?:19|20)\d{2}\s*(?:년|부터|이후|이전|[~～-])|최근|작년|올해|연도별|월별',
        r'사고\s*패턴|통제위계|비교|제외|아닌|또는|혹은|\b(?:OR|NOT)\b',
        r'재해종류|사고유형|추락|낙하|끼임|충돌|감전|붕괴|전도|질식|폭발|화재',
    ]
    return any(re.search(p, remaining, re.IGNORECASE) for p in patterns)


def _mentioned_hierarchy_nodes(question, catalog):
    """Detect explicit hierarchy anchors independently of the LLM's scope field."""
    mentions = []
    normalized = _normalize(question)
    for node in catalog['nodes'].values():
        if node['label'] not in ('WorkType', 'Work', 'UnitWork'):
            continue
        terms = [node['name'], _short_name(node['name'])]
        terms += [alias['term'] for alias in catalog['aliases'] if alias['node_id'] == node['id']]
        if any(_normalize(term) in normalized for term in terms if term):
            mentions.append(node)
    return mentions


def _complete(client, model, messages, trace, purpose):
    try:
        response = client.chat.completions.create(
            model=model, messages=messages, temperature=0,
            max_tokens=1800, timeout=45,
        )
    except Exception as exc:
        raise LLMError('Upstage request failed.') from exc
    content = response.choices[0].message.content if response.choices else None
    if not content:
        raise LLMError('Upstage returned an empty response.')
    usage = getattr(response, 'usage', None)
    trace['llm_calls'].append({
        'purpose': purpose, 'content': content,
        'usage': usage.model_dump() if usage else None,
    })
    return content


def _interpret(question, catalog, client, model, trace):
    names = {}
    for node in catalog['nodes'].values():
        names.setdefault(node['label'], []).append(node['name'])
    names = {label: sorted(values) for label, values in names.items()}
    prompt = '''너는 건설업 사고사례 DB의 제한된 질의 해석기다. 현재 질문만 해석한다.
너의 역할은 DB 결과 생성이나 실제 조회가 아니라 질의 유형과 조건을 추출하는 것이다.
DB 결과가 아직 없다는 이유로 지원되는 질의를 거부하지 않는다. 실제 조회는 다음 단계에서 수행한다.
질문 속 조건을 삭제하거나 추정하지 않는다. 아래 실제 이름 목록과 동의어만 참고한다.
실제 목록의 단일 이름 안에 포함된 '추락', '낙하', '또는'는 추가 필터나 OR 조건이 아니다.
예를 들어 안전가시설(가설통로 또는 가설계단)은 하나의 단위작업명이다.
출력은 JSON 객체 하나이며 아래 필드를 모두 사용한다. Cypher를 생성하지 않는다.
intent: case_lookup / hierarchy_aggregate / measure_summary / unsupported / needs_clarification
unit_work: 명시된 단위작업 표현 또는 null
causal_object: 명시된 기인물 표현 또는 null
scope: 집계 대상 공종/작업/단위작업 표현. 전체 건설업이면 null
group_by: 집계 그룹 WorkType/Work/UnitWork 또는 null(기본 하위 단계)
unsupported_conditions: 지원 불가능한 모든 명시 조건의 문자열 배열
reason: 미지원 또는 모호함의 간단한 이유. 정상 질의이면 null
세 유형의 구분 기준:
- case_lookup: 사고사례 목록/사례 자체를 보여 달라는 요청.
- hierarchy_aggregate: 공종·작업·단위작업의 건수·비율·분포를 집계하는 요청.
- measure_summary: 예방대책·감소대책을 모아서 빈도·근거와 함께 정리하는 요청.
  단위작업과 기인물이 명시된 대책·빈도·근거 요청은 반드시 이 유형이다.
  대책 종합은 이 시스템의 지원 기능이며, 아직 DB 조회 전이라는 이유로 case_lookup으로 바꾸지 않는다.
사례 조회는 단위작업 하나 또는 기인물 하나만 지원한다.
계층 집계는 공종/작업/단위작업 범위 하나만 지원한다.
대책 종합은 단위작업 하나와 기인물 하나가 모두 필요하다.
기간, 재해종류 필터, 복잡한 조건, 제조업, 자유서술 상황·유사 검색, 패턴은 미지원이다.
지원하지 않는 조건이 있으면 unsupported로 판정하고 조건을 전부 기록한다.
예방대책을 묻는데 단위작업/기인물이 빠졌거나 '그 작업'처럼 불명확하면 needs_clarification이다.
'굴착 작업'을 임의로 세부 단위작업으로 바꾸거나 '철근 인양'을 '철근 반입'으로 추정하지 않는다.
필드에 없는 설명을 추가하지 않는다. 이름의 분류 숫자를 조건의 연도로 오인하지 않는다.
'''
    messages = [
        {'role': 'system', 'content': prompt + '\n출력 스키마: ' + json.dumps(Interpretation.model_json_schema(), ensure_ascii=False)
         + '\n실제 목록: ' + json.dumps(names, ensure_ascii=False)
         + '\n동의어: ' + json.dumps(catalog['aliases'], ensure_ascii=False)},
        {'role': 'user', 'content': question},
    ]
    for attempt in range(2):
        raw = _complete(client, model, messages, trace, 'interpretation')
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip())
        try:
            result = Interpretation.model_validate_json(text)
            trace['extracted_conditions'] = result.model_dump()
            return result
        except ValidationError:
            if attempt == 0:
                messages.extend([
                    {'role': 'assistant', 'content': raw},
                    {'role': 'user', 'content': 'JSON 형식 또는 필드가 잘못되었습니다. 지정한 스키마의 JSON 객체 하나만 다시 출력하세요.'},
                ])
    raise Clarification('질문 조건을 정해진 형식으로 확인하지 못했습니다. 단위작업명 또는 기인물명을 명시해 주세요.')


def _resolve(value, labels, question, catalog):
    nodes = [n for n in catalog['nodes'].values() if n['label'] in labels]
    aliases = catalog['aliases']
    normalized = _normalize(value)
    candidates = [n for n in nodes if normalized in {
        _normalize(n['name']), _normalize(_short_name(n['name'])),
    }]
    if not candidates:
        ids = {a['node_id'] for a in aliases if _normalize(a['term']) == normalized}
        candidates = [n for n in nodes if n['id'] in ids]
        # A synonym may point to a base object and its subtypes. Use the base
        # only when all candidates have exactly the same base name.
        bases = {n['name'].split('(')[0].strip() for n in candidates}
        if len(bases) == 1:
            base_nodes = [n for n in candidates if n['name'] in bases]
            if base_nodes:
                candidates = base_nodes
    if len(candidates) != 1:
        choices = ' / '.join(n['name'] for n in candidates[:5])
        raise Clarification(f"'{value}'에 해당하는 조건을 하나로 확인할 수 없습니다. "
                            + (f'후보: {choices}. ' if choices else '')
                            + '실제 단위작업명 또는 기인물명을 구체적으로 입력해 주세요.')
    node = candidates[0]
    mentions = [node['name'], _short_name(node['name'])]
    mentions += [a['term'] for a in aliases if a['node_id'] == node['id']]
    if not any(_normalize(m) in _normalize(question) for m in mentions if m):
        raise Clarification(f"'{node['name']}' 조건은 질문에서 확인되지 않습니다. 사용할 조건을 직접 명시해 주세요.")
    return node


def _plan(parsed, question, catalog):
    if parsed.unsupported_conditions or parsed.intent == 'unsupported':
        raise Clarification('요청에 지원하지 않는 조건이 포함되어 있습니다.\n' + SUPPORT_MESSAGE)
    if parsed.intent == 'needs_clarification':
        raise Clarification('조회할 단위작업·기인물 또는 집계할 공종·작업명을 구체적으로 명시해 주세요.\n' + SUPPORT_MESSAGE)
    plan = {'intent': parsed.intent, 'nodes': {}, 'parameters': {}}
    if parsed.intent in ('case_lookup', 'measure_summary'):
        if parsed.scope or parsed.group_by:
            raise Clarification(SUPPORT_MESSAGE)
        if parsed.unit_work:
            plan['nodes']['unit_work'] = _resolve(parsed.unit_work, ['UnitWork'], question, catalog)
        if parsed.causal_object:
            plan['nodes']['object'] = _resolve(parsed.causal_object, ['CausalObject'], question, catalog)
        needed = 1 if parsed.intent == 'case_lookup' else 2
        if len(plan['nodes']) != needed:
            raise Clarification('사례 조회는 단위작업 또는 기인물 하나, 대책 종합은 단위작업과 기인물 모두를 명시해 주세요.')
        plan['template_id'] = 'T01' if needed == 1 else 'T03'
        plan['parameters'] = {
            'unit_work_id': plan['nodes'].get('unit_work', {}).get('id'),
            'object_id': plan['nodes'].get('object', {}).get('id'),
        }
        plan['parameters'].update({'evidence_limit': EVIDENCE_LIMIT} if needed == 1 else {'measure_limit': MEASURE_LIMIT})
    else:
        if parsed.unit_work or parsed.causal_object:
            raise Clarification('계층 집계는 공종·작업·단위작업 범위 하나만 지정해 주세요.')
        node = _resolve(parsed.scope, ['WorkType', 'Work', 'UnitWork'], question, catalog) if parsed.scope else None
        if node is None:
            if _mentioned_hierarchy_nodes(question, catalog):
                raise Clarification('질문에 공종·작업·단위작업이 명시되어 있지만 집계 범위를 추출하지 못했습니다. '
                                    '대상 이름을 다시 명시해 주세요. 건설업 전체로 범위를 넓히지 않습니다.')
            if not re.search(r'건설업|공종별', question):
                raise Clarification('집계할 공종·작업·단위작업 또는 건설업 전체 범위를 명시해 주세요.')
        default = {'WorkType': 'Work', 'Work': 'UnitWork', 'UnitWork': 'UnitWork'}
        group_by = parsed.group_by or (default[node['label']] if node else 'WorkType')
        levels = {'WorkType': 0, 'Work': 1, 'UnitWork': 2}
        if node and levels[group_by] < levels[node['label']]:
            raise Clarification('선택한 범위의 같은 단계 또는 하위 단계로 집계해 주세요.')
        plan['template_id'] = 'T02'
        plan['nodes'] = {'scope': node} if node else {}
        plan['parameters'] = {'scope_id': node['id'] if node else None, 'group_by': group_by}
    return plan


def _facts(plan, rows):
    intent = plan['intent']
    total = rows[0]['total'] if rows else 0
    scope = ' / '.join(n['name'] for n in plan['nodes'].values()) or '건설업 전체'
    lines = [f'조회 범위: 건설업 / {scope}', f'전체 일치 사고: {total:,}건']
    if intent == 'hierarchy_aggregate' and total:
        lines.append(f'비율의 분모: 해당 범위 전체 {total:,}건')
        lines.extend(f"- {r['name']}: {r['count']:,}건 ({r['percent']:.2f}%)" for r in rows)
        lines.append('비율은 각 행을 반올림하므로 합계에 반올림 오차가 있을 수 있습니다.')
    elif intent == 'measure_summary' and total:
        lines.append('대책별 등장 사례 수 (전체 조건 일치 사례에서 계산, 상위 10개):')
        for m in rows[0]['measures']:
            lines.append(f"- {m['text']}: {m['count']}건 [근거: {', '.join(m['source_codes'])}]")
        lines.append('빈도는 사례에 기록된 횟수이며 대책의 효과를 뜻하지 않습니다.')
    return '\n'.join(lines)


def _grounded_explanation(entry, evidence_by_code):
    case = evidence_by_code.get(entry.case_code)
    if case is None or re.search(r'SIF-|(?:^|\s)(?:한|두|세|네|다섯|여섯|일|이|삼|사|오|육|칠|팔|구|십)\s*건', entry.text):
        return False
    # Physical quantities such as "4변" or "2줄" are legitimate source facts.
    # Permit them only when they occur in this exact cited case, never as
    # newly generated statistics, dates, percentages, or classification codes.
    physical = r'\d+(?:\.\d+)?\s*(?:mm|cm|kg|ton|m|톤|미터|줄|변|도)'
    source = _normalize(case['summary'] + ' '.join(m['text'] for m in case['measures']))
    quantities = re.findall(physical, entry.text)
    if any(_normalize(q) not in source for q in quantities):
        return False
    return not re.search(r'\d', re.sub(physical, '', entry.text))


def answer_question(question, history, client, model, *, trace=None, reader=read_query):
    """Return the existing answer string; trace is private verification instrumentation."""
    del history  # Follow-up inference is outside this minimal implementation.
    trace = trace if trace is not None else {}
    trace.update(question=question, model_name=model, prompt_version=PROMPT_VERSION,
                 executed_queries=[], llm_calls=[], status='running', stage='scope_check')

    def execute(template_id, params):
        query = TEMPLATES[template_id]
        result = reader(query, **params)
        trace['executed_queries'].append({'template_id': template_id, 'cypher': query,
                                          'parameters': params, 'rows': result})
        return result

    try:
        trace['stage'] = 'database_inspection'
        metadata = reader(CATALOG_QUERY)[0]
        if not metadata['construction_count']:
            raise DataIntegrityError('건설업 데이터가 적재되어 있지 않습니다.')
        if metadata['hierarchy_coverage'] != metadata['construction_count']:
            raise DataIntegrityError('건설업 데이터의 작업 계층 연결이 누락되어 있습니다.')
        nodes = {n['id']: n for key in ('unit_works', 'works', 'work_types', 'objects') for n in metadata[key]}
        if _unsupported(question, {'nodes': nodes}):
            raise Clarification('요청에 지원하지 않는 조건이 포함되어 있습니다.\n' + SUPPORT_MESSAGE)
        aliases = reader(ALIASES_QUERY, node_ids=sorted(nodes))
        catalog = {'nodes': nodes, 'aliases': aliases}
        trace['database_inspection'] = {
            'verified_at_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
            'construction_count': metadata['construction_count'],
            'hierarchy_coverage': metadata['hierarchy_coverage'],
            'catalog_sha256': hashlib.sha256(json.dumps(catalog, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        }
        trace['stage'] = 'interpretation'
        parsed = _interpret(question, catalog, client, model, trace)
        plan = _plan(parsed, question, catalog)
        trace['resolved_plan'] = plan
        trace['stage'] = 'retrieval'
        rows = execute(plan['template_id'], plan['parameters'])
        total = rows[0]['total'] if rows else 0
        trace['scope_total'] = total
        if total == 0:
            trace.update(status='no_match', final_answer='해당 사례 없음: 입력한 조건에 일치하는 건설업 사고사례가 없습니다.')
            return trace['final_answer']
        if plan['intent'] == 'hierarchy_aggregate':
            ids = [r['evidence_id'] for r in rows]
            scope_ids = {i for r in rows for i in r['group_case_ids']}
            if sum(r['count'] for r in rows) != total or len(scope_ids) != total:
                raise DataIntegrityError('작업별 사례 집합의 중복 또는 누락이 있습니다.')
            if not plan['parameters']['scope_id'] and total != metadata['construction_count']:
                raise DataIntegrityError('건설업 전체 집계에 누락된 사례가 있습니다.')
        elif plan['intent'] == 'measure_summary':
            ids = [m['evidence_id'] for m in rows[0]['measures']]
        else:
            ids = rows[0]['evidence_ids']
        ids = list(dict.fromkeys(ids))[:EVIDENCE_LIMIT]
        evidence = execute('T04', {'case_ids': ids})
        if {e['id'] for e in evidence} != set(ids):
            raise DataIntegrityError('설명용 근거 사례가 누락되었습니다.')
        trace['evidence'] = evidence
        facts = _facts(plan, rows)
        if not evidence:
            trace.update(status='insufficient_evidence', final_answer=facts + '\n연결된 예방대책 근거가 없습니다.')
            return trace['final_answer']
        trace['stage'] = 'explanation'
        # Only original source codes go to the model. Internal content hashes are
        # never presented as an alternative citation identifier.
        prompt_rows = [{'total': total}]
        if plan['intent'] == 'hierarchy_aggregate':
            prompt_rows = [{k: r[k] for k in ('name', 'count', 'percent')} for r in rows]
        if plan['intent'] == 'measure_summary':
            prompt_rows = [{'total': total, 'measures': [
                {k: m[k] for k in ('text', 'count')}
                for m in rows[0]['measures']
            ]}]
        prompt_evidence = [{
            'original_case_code': e['code'], 'summary': e['summary'],
            'unit_work': _short_name(e['unit_work']), 'causal_object': e['causal_object'],
            'measures': [m['text'] for m in e['measures']],
        } for e in evidence]
        raw = _complete(client, model, [
            {'role': 'system', 'content': '제공된 건설업 사고사례만 근거로 JSON 객체 하나를 작성하세요. '
             '출력 형식은 {"explanations":[{"case_code":"제공된 original_case_code","text":"사고 상황과 해당 사례의 대책 설명"}]} 입니다. '
             '서로 다른 사례를 최대 세 개만 선택하세요. case_code는 해당 사례의 original_case_code를 그대로 사용하세요. '
             'text는 한두 문장으로 그 사례의 상황과 그 사례에 기록된 예방대책만 연결해 설명하세요. '
             'text에는 사례번호, 날짜, 분류 코드, 건수·빈도·비율, 전체 요약을 쓰지 마세요. '
             '물리적 수치가 필요하면 해당 사례 원문에 그대로 있는 값과 단위만 사용하세요. '
             '전체 건수와 설명용 사례 수는 다릅니다. 통계와 사례번호는 백엔드가 직접 표시합니다. '
             '다른 사례의 대책을 섞거나 패턴·인과관계·대책 효과를 만들어내지 마세요. '
             '제공된 자료에 없는 현장 권고나 법령을 추가하지 마세요. '
             '스키마: ' + json.dumps(Explanation.model_json_schema(), ensure_ascii=False)},
            {'role': 'user', 'content': json.dumps({'confirmed_statistics': prompt_rows,
                                                   'evidence': prompt_evidence}, ensure_ascii=False)},
        ], trace, 'explanation')
        evidence_by_code = {e['code']: e for e in evidence}
        try:
            parsed_explanation = Explanation.model_validate_json(
                re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip()))
            entries = parsed_explanation.explanations
            valid = all(_grounded_explanation(e, evidence_by_code) for e in entries)
            valid = valid and len({e.case_code for e in entries}) == len(entries)
        except ValidationError:
            entries, valid = [], False
        trace['explanation_accepted'] = valid
        explanation = '\n\n'.join(f'{e.text} [{e.case_code}]' for e in entries) if valid else '생성 설명의 출처 또는 숫자를 확인하지 못해 아래의 DB 근거만 제시합니다.'
        source_lines = ['설명용 근거 사례 (전체 집계와 별도, 최대 10건):']
        for e in evidence:
            source_lines.append(f"- [{e['code']}] {e['summary']}")
            if plan['intent'] != 'hierarchy_aggregate' and e['measures']:
                source_lines.append('  예방대책(원문 일부): ' + e['measures'][0]['text'])
        answer = facts + '\n\n' + explanation + '\n\n' + '\n'.join(source_lines)
        trace.update(status='ok', stage='complete', final_answer=answer)
        return answer
    except Clarification as exc:
        trace.update(status='needs_clarification', final_answer=str(exc))
        return str(exc)
    except Exception as exc:
        trace.update(status='failed', error_type=type(exc).__name__)
        raise
