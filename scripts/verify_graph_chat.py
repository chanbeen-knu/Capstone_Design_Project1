"""Run three real POST /api/chat requests and compare DB results with source data.

Explicit --live is required: this reads Neo4j, calls Upstage, and writes reports.
It never writes to Neo4j. Reports require a separate semantic review before verified.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from dotenv import load_dotenv
load_dotenv(ROOT / 'backend' / '.env')
from fastapi.testclient import TestClient

import legacy_main as main
from chat_service import ALIASES_QUERY, CATALOG_QUERY, read_query
from chat_templates import TEMPLATES

PUBLIC_SOURCE_URL = 'https://www.moel.go.kr/policy/policydata/view.do?bbs_seq=20260400196'

QUESTIONS = {
    'V01': '단위작업 2.3.1 철근 반입의 사고사례를 보여줘.',
    'V02': '2. 철근콘크리트 공사에 속한 전체 사고를 작업별 건수와 비율로 집계해줘.',
    'V03': '단위작업 2.3.1 철근 반입에서 기인물이 굴착기(백호우)인 사례의 예방대책을 빈도와 근거와 함께 정리해줘.',
}


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def case_id(record):
    # Independently recover the existing content-based ID from original fields.
    f = record['fields']
    parts = ['C', record['summary'], f.get('기인물', ''), f.get('재해유발요인', '')]
    key = '|'.join(re.sub(r'\s+', '', str(p)) for p in parts)
    return 'SIF-C-' + hashlib.sha1(key.encode()).hexdigest()[:10]


def source_measures(record):
    text = record['fields'].get('위험성 감소대책(예시)', '')
    pieces = text.split('▶') if '▶' in text else text.splitlines()
    result = {}
    for piece in pieces:
        clean = piece.strip(' \n\r\t-·•')
        if clean:
            mid = 'M:' + hashlib.sha1(re.sub(r'\s+', '', clean).encode()).hexdigest()[:12]
            result[mid] = clean
    return result


def check(value, message):
    if not value:
        raise AssertionError(message)


def public_source_reader(source):
    """Verify every DB text field before any provider call can receive it.

    Source: the ministry's public SIF workbook, already imported into public/data.
    A changed/private DB field aborts the run instead of sending that field.
    """
    by_code = {'SIF-C-' + str(int(r['fields']['연번'])).zfill(4): r for r in source}
    allowed_names = {
        label: {r['fields'].get(field, '') for r in source}
        for label, field in [('UnitWork', '단위작업명'), ('Work', '작업명'), ('WorkType', '공종')]
    }
    with (ROOT / 'ontology/config/causal_object_category.csv').open(encoding='utf-8-sig') as file:
        objects = {r['기인물'] for r in csv.DictReader(file)}
    objects |= {r['fields'].get('기인물', '') for r in source}
    objects |= {name.split('(')[0].split('[')[0].strip() for name in objects}
    allowed_names['CausalObject'] = objects
    with (ROOT / 'ontology/config/aliases.csv').open(encoding='utf-8-sig') as file:
        allowed_aliases = {r['용어'] for r in csv.DictReader(file)}

    def run(query, **params):
        rows = read_query(query, **params)
        if query == CATALOG_QUERY:
            for key in ['unit_works', 'works', 'work_types', 'objects']:
                for node in rows[0][key]:
                    check(node['name'] in allowed_names[node['label']], 'Non-source catalog name; provider call blocked')
                    prefix = {'UnitWork': 'UW:', 'Work': 'W:', 'WorkType': 'WT:', 'CausalObject': 'CO:'}[node['label']]
                    check(node['id'] == prefix + node['name'], 'Non-source catalog ID; provider call blocked')
        elif query == ALIASES_QUERY:
            check(all(r['term'] in allowed_aliases for r in rows), 'Non-source alias; provider call blocked')
        elif query == TEMPLATES['T04']:
            field_map = {'summary': None, 'unit_work': '단위작업명', 'work': '작업명',
                         'work_type': '공종', 'causal_object': '기인물',
                         'raw_hazard': '재해유발요인', 'raw_measures': '위험성 감소대책(예시)'}
            for row in rows:
                check(row['code'] in by_code, 'Non-source evidence case; provider call blocked')
                original = by_code[row['code']]
                check(row['id'] == case_id(original), 'Non-source case ID; provider call blocked')
                check(row['legacy_id'] == original['id'], 'Non-source legacy ID; provider call blocked')
                for name, field in field_map.items():
                    expected = original['summary'] if field is None else original['fields'].get(field, '')
                    check(str(row[name] or '').strip() == str(expected or '').strip(),
                          'Changed evidence field; provider call blocked')
                measures = source_measures(original)
                for measure in row['measures']:
                    check(measure['id'] in measures, 'Non-source measure; provider call blocked')
                    check(re.sub(r'\s+', '', measure['text']) == re.sub(r'\s+', '', measures[measure['id']]),
                          'Changed measure text; provider call blocked')
        return rows
    return run


def validate(number, trace, source):
    check(trace.get('status') == 'ok', 'Service did not complete: ' + trace.get('status', 'missing'))
    check(trace.get('explanation_accepted') is True, 'LLM explanation failed citation/number validation')
    check([c['purpose'] for c in trace['llm_calls']].count('explanation') == 1, 'No real explanation call recorded')
    check(0 < len(trace['evidence']) <= 10, 'Evidence count must be between one and ten')
    expected_intents = {'V01': 'case_lookup', 'V02': 'hierarchy_aggregate', 'V03': 'measure_summary'}
    check(trace['resolved_plan']['intent'] == expected_intents[number], 'Wrong extracted query intent')
    query = trace['executed_queries'][0]
    rows = query['rows']
    if number == 'V02':
        check(trace['resolved_plan']['parameters'] == {
            'scope_id': 'WT:2. 철근콘크리트 공사', 'group_by': 'Work',
        }, 'Wrong hierarchy scope/group')
        selected = [r for r in source if r['fields'].get('공종') == '2. 철근콘크리트 공사']
        expected_groups = Counter(r['fields']['작업명'] for r in selected)
        check({r['name']: r['count'] for r in rows} == dict(expected_groups), 'Hierarchy counts differ from original data')
        for row in rows:
            ids = {case_id(r) for r in selected if r['fields']['작업명'] == row['name']}
            check(set(row['group_case_ids']) == ids, 'Hierarchy case membership differs from original data')
            check(abs(row['percent'] - 100.0 * len(ids) / len(selected)) <= 0.0051, 'Wrong DB percentage')
    else:
        selected = [r for r in source if r['fields'].get('단위작업명') == '2.3.1 철근 반입']
        check(trace['resolved_plan']['parameters']['unit_work_id'] == 'UW:2.3.1 철근 반입', 'Wrong unit work')
        if number == 'V03':
            check(trace['resolved_plan']['parameters']['object_id'] == 'CO:굴착기(백호우)', 'Wrong causal object')
            selected = [r for r in selected if r['fields'].get('기인물') == '굴착기(백호우)']
            frequency = Counter()
            supporting = {}
            for r in selected:
                for mid in source_measures(r):
                    frequency[mid] += 1
                    supporting.setdefault(mid, set()).add('SIF-C-' + str(int(r['fields']['연번'])).zfill(4))
            expected = sorted(frequency, key=lambda mid: (-frequency[mid], mid))[:10]
            check([m['id'] for m in rows[0]['measures']] == expected, 'Wrong measure order or membership')
            for m in rows[0]['measures']:
                check(m['count'] == frequency[m['id']], 'Measure frequency differs from original data')
                check(set(m['source_codes']) == supporting[m['id']], 'Wrong measure support codes')
        check(set(rows[0]['scope_ids']) == {case_id(r) for r in selected}, 'Case membership differs from original data')
    check(trace['scope_total'] == len(selected), 'Scope total differs from original data')
    by_code = {'SIF-C-' + str(int(r['fields']['연번'])).zfill(4): r for r in source}
    for e in trace['evidence']:
        check(e['code'] in by_code, 'Unknown original source code')
        original = by_code[e['code']]
        check(e['id'] == case_id(original), 'Wrong internal-to-original ID mapping')
        check(e['summary'] == original['summary'], 'Evidence summary differs from original data')
        expected_measures = source_measures(original)
        for measure in e['measures']:
            check(measure['id'] in expected_measures, 'Measure is attached to the wrong case')
            check(re.sub(r'\s+', '', measure['text']) == re.sub(r'\s+', '', expected_measures[measure['id']]),
                  'Measure text differs from original data')
    return {
        'actual_http_endpoint': True, 'real_neo4j_and_llm': True,
        'intent_and_conditions': True, 'source_membership_and_counts': True,
        'source_measure_connections': True, 'evidence_limit': True,
        'denominator_or_frequency': True,
    }


def write_reports(record, path):
    path.with_suffix('.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = [f"# {record['scenario_id']} 실제 채팅 실행 기록", '',
             f"- 실행 ID: `{record['run_id']}`", f"- 검증 상태: `{record['verification_status']}`",
             f"- 실행 시각: {record['verified_at_kst']}", f"- 모델: `{record['model_name']}`",
             f"- HTTP 상태: {record.get('http_status')}", '', '## 질문', '', record['question'], '',
             '## 추출·확정 조건', '', '```json',
             json.dumps({'extracted': record.get('extracted_conditions'), 'resolved': record.get('resolved_plan')}, ensure_ascii=False, indent=2),
             '```', '', '## DB 결과 요약', '', f"- 전체 해당 사고: {record.get('scope_total', '미확인')}건",
             '- 실제 쿼리·전체 DB 반환 행·원본 식별자·토큰 사용량은 같은 실행 ID의 JSON에 보존한다.', '',
             '## 최종 답변 (실제 API 응답 원문)', '', record.get('final_answer', '생성되지 않음'), '',
             '## 검증', '', '```json', json.dumps({
                 'automated_checks': record.get('automated_checks'),
                 'manual_checks': record.get('manual_checks'), 'errors': record.get('errors'),
             }, ensure_ascii=False, indent=2), '```', '']
    path.with_suffix('.md').write_text('\n'.join(lines), encoding='utf-8')


def main_cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Call actual Neo4j and Upstage; API usage is billed by the provider')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs' / 'verification')
    args = parser.parse_args()
    if not args.live:
        parser.error('--live is required; no mock result is reported as a live verification')
    if main.client is None:
        parser.error('UPSTAGE_API_KEY is not configured')
    source_file = ROOT / 'public' / 'data' / 'cases.json'
    raw_source = source_file.read_bytes()
    source = [r for r in json.loads(raw_source)['records'] if r.get('group') == '건설업']
    checked_reader = public_source_reader(source)
    before = checked_reader(CATALOG_QUERY)[0]
    check(before['construction_count'] == len(source), 'DB/source construction counts differ')
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    run_id = now.strftime('%Y%m%dT%H%M%S%f%z')
    args.output.mkdir(parents=True, exist_ok=True)
    version = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    code_hashes = {name: sha256((ROOT / name).read_bytes()) for name in [
        'backend/main.py', 'backend/chat_service.py', 'backend/chat_templates.py', 'scripts/verify_graph_chat.py',
    ]}
    real_answer = main.answer_question
    failures = []
    for number, question in QUESTIONS.items():
        record = dict(run_id=f'{run_id}-{number}', scenario_id=number, question=question,
                      verified_at_kst=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
                      verification_status='not_run', model_name=main.MODEL_NAME,
                      code_version=version, code_file_sha256=code_hashes,
                      source_json_sha256=sha256(raw_source), construction_case_count=len(source),
                      public_source_url=PUBLIC_SOURCE_URL,
                      outbound_data_policy='Only DB text verified against the public SIF source; at most ten evidence cases.',
                      manual_checks=[], errors=[])

        def instrument(q, history, client, model):
            return real_answer(q, history, client, model, trace=record, reader=checked_reader)

        print(f'{number}: running actual POST /api/chat', flush=True)
        started = time.monotonic()
        try:
            with patch.object(main, 'answer_question', side_effect=instrument):
                response = TestClient(main.app).post('/api/chat', json={'message': question, 'history': []})
            record['http_status'] = response.status_code
            check(response.status_code == 200, f'HTTP {response.status_code}; no successful response')
            check(set(response.json()) == {'answer'}, 'Public response contract changed')
            record['final_answer'] = response.json()['answer']
            record['automated_checks'] = validate(number, record, source)
            record['verification_status'] = 'pending_review'
        except Exception as exc:
            record['verification_status'] = 'failed'
            # Only validation errors are serialized; provider/auth exception messages are excluded.
            record['errors'].append(str(exc) if isinstance(exc, AssertionError) else type(exc).__name__)
            failures.append(number)
        record['total_latency_ms'] = round((time.monotonic() - started) * 1000)
        path = args.output / record['run_id']
        write_reports(record, path)
        print(f"{number}: {record['verification_status']}, total={record.get('scope_total')}, report={path.name}.json", flush=True)
    after = checked_reader(CATALOG_QUERY)[0]
    if after['construction_count'] != before['construction_count'] or source_file.read_bytes() != raw_source:
        raise SystemExit('Source/DB counts changed during verification; reports must be rerun.')
    print('Live execution complete. Semantic review is still required; no report is automatically marked verified.', flush=True)
    if failures:
        raise SystemExit('Failed scenarios: ' + ', '.join(failures))


if __name__ == '__main__':
    main_cli()
