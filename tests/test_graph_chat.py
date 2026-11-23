"""Service/API boundaries; live Cypher correctness is checked by the verification runner."""
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable

import legacy_main as main
from chat_service import (
    ALIASES_QUERY, CATALOG_QUERY, Clarification, DataIntegrityError, Interpretation,
    CaseExplanation, _grounded_explanation, _plan, answer_question,
)
from chat_templates import TEMPLATES
import verify_graph_chat as verification


def interpretation(**updates):
    fields = dict(intent='case_lookup', unit_work='철근 반입', causal_object=None,
                  scope=None, group_by=None, unsupported_conditions=[], reason='')
    fields.update(updates)
    return json.dumps(fields, ensure_ascii=False)


def explanation(text='출입 통제 대책이 기록되어 있습니다.', code='SIF-C-0453'):
    return json.dumps({'explanations': [{'case_code': code, 'text': text}]}, ensure_ascii=False)


class FakeLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=response))], usage=None)


U = {'id': 'UW:2.3.1 철근 반입', 'name': '2.3.1 철근 반입', 'label': 'UnitWork'}
W = {'id': 'W:2.3 철근 작업', 'name': '2.3 철근 작업', 'label': 'Work'}
WT = {'id': 'WT:2. 철근콘크리트 공사', 'name': '2. 철근콘크리트 공사', 'label': 'WorkType'}
O = {'id': 'CO:굴착기(백호우)', 'name': '굴착기(백호우)', 'label': 'CausalObject'}
CATALOG = dict(construction_count=12, hierarchy_coverage=12, unit_works=[U], works=[W], work_types=[WT], objects=[O])
EVIDENCE = dict(id='case-a', code='SIF-C-0453', legacy_id='sif-2-457', summary='철근 반입 중 사고.',
                unit_work=U['name'], work=W['name'], work_type=WT['name'], causal_object=O['name'],
                raw_hazard='자재 낙하', raw_measures='출입 통제', measures=[{'id': 'm1', 'text': '출입 통제'}])


def reader(overrides=None):
    results = {
        CATALOG_QUERY: [CATALOG], ALIASES_QUERY: [],
        TEMPLATES['T01']: [dict(total=12, scope_ids=['case-a'] * 12, evidence_ids=['case-a'])],
        TEMPLATES['T04']: [EVIDENCE],
    }
    results.update(overrides or {})
    calls = []

    def run(query, **params):
        calls.append((query, params))
        result = results[query]
        if isinstance(result, Exception):
            raise result
        return result
    run.calls = calls
    return run


class GraphChatTests(unittest.TestCase):
    def test_existing_api_contract_and_db_total(self):
        llm = FakeLLM(interpretation(), explanation('철근 반입 상황과 출입 통제 대책을 확인할 수 있습니다.'))
        trace = {}
        run = reader()

        def instrument(question, history, client, model):
            return answer_question(question, history, client, model, reader=run, trace=trace)

        with patch.object(main, 'client', llm), patch.object(main, 'answer_question', side_effect=instrument):
            response = TestClient(main.app).post('/api/chat', json={'message': '철근 반입 사고사례를 보여줘', 'history': []})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {'answer'})
        self.assertIn('12건', response.json()['answer'])
        self.assertIn('SIF-C-0453', response.json()['answer'])
        self.assertEqual(trace['scope_total'], 12)
        self.assertTrue(trace['explanation_accepted'])
        self.assertEqual([x['template_id'] for x in trace['executed_queries']], ['T01', 'T04'])

    def test_object_only_lookup(self):
        llm = FakeLLM(interpretation(unit_work=None, causal_object=O['name']), explanation())
        run = reader()
        answer_question(f"{O['name']}의 사고사례", [], llm, 'test', reader=run)
        params = next(p for q, p in run.calls if q == TEMPLATES['T01'])
        self.assertIsNone(params['unit_work_id'])
        self.assertEqual(params['object_id'], O['id'])

    def test_format_retry_only_once(self):
        llm = FakeLLM('bad-json', 'bad-json')
        result = answer_question('철근 반입 사례', [], llm, 'test', reader=reader())
        self.assertIn('형식', result)
        self.assertEqual(len(llm.calls), 2)

    def test_null_reason_in_valid_model_json_is_accepted_without_retry(self):
        llm = FakeLLM(interpretation(reason=None), explanation())
        trace = {}
        answer_question('철근 반입 사례', [], llm, 'test', reader=reader(), trace=trace)
        self.assertEqual(trace['status'], 'ok')
        self.assertEqual(len(llm.calls), 2)
        self.assertEqual([c['purpose'] for c in trace['llm_calls']], ['interpretation', 'explanation'])

    def test_unsupported_conditions_do_not_reach_retrieval_or_llm(self):
        for question in ['2020년 철근 반입 사례', '제조업 사례', '사다리 또는 굴착기 사례', '추락 사고만 조회', '철근 작업과 굴착 작업 비교']:
            with self.subTest(question=question):
                run = reader()
                llm = FakeLLM()
                result = answer_question(question, [], llm, 'test', reader=run)
                self.assertIn('지원', result)
                self.assertEqual([q for q, _ in run.calls], [CATALOG_QUERY])
                self.assertEqual(llm.calls, [])

    def test_catalog_work_names_with_reserved_words_are_queryable(self):
        names = ['13.1.6 안전가시설(추락방지망)',
                 '13.1.7 안전가시설(가설통로 또는 가설계단)',
                 '13.1.8 안전가시설(낙하물방지망)']
        for name in names:
            for mention in [name, name.split(' ', 1)[1]]:
                with self.subTest(name=name, mention=mention):
                    node = {'id': 'UW:' + name, 'name': name, 'label': 'UnitWork'}
                    run = reader({CATALOG_QUERY: [{**CATALOG, 'unit_works': [U, node]}]})
                    llm = FakeLLM(interpretation(unit_work=name), explanation())
                    trace = {}
                    answer_question(mention + ' 사고사례를 보여줘', [], llm, 'test', reader=run, trace=trace)
                    self.assertEqual(trace['status'], 'ok')
                    self.assertEqual(trace['resolved_plan']['parameters']['unit_work_id'], node['id'])
                    self.assertEqual([q['template_id'] for q in trace['executed_queries']], ['T01', 'T04'])

    def test_extra_filter_outside_a_valid_work_name_is_still_rejected(self):
        name = '13.1.7 안전가시설(가설통로 또는 가설계단)'
        node = {'id': 'UW:' + name, 'name': name, 'label': 'UnitWork'}
        for suffix in [' 중 추락 사고만 보여줘', ' 또는 철근 반입 사례를 보여줘', ' 중 2020년 사례를 보여줘']:
            with self.subTest(suffix=suffix):
                run = reader({CATALOG_QUERY: [{**CATALOG, 'unit_works': [U, node]}]})
                llm = FakeLLM()
                trace = {}
                result = answer_question(name + suffix, [], llm, 'test', reader=run, trace=trace)
                self.assertIn('지원하지 않는 조건', result)
                self.assertEqual(trace['executed_queries'], [])
                self.assertEqual(llm.calls, [])

    def test_omitted_named_scope_never_queries_all_construction(self):
        for node in [WT, W, U]:
            for mention in [node['name'], node['name'].split(' ', 1)[1]]:
                with self.subTest(node=node, mention=mention):
                    run = reader()
                    llm = FakeLLM(interpretation(intent='hierarchy_aggregate', unit_work=None, scope=None, group_by='Work'))
                    trace = {}
                    result = answer_question(mention + '에 속한 전체 사고를 집계해줘', [], llm, 'test', reader=run, trace=trace)
                    self.assertIn('범위를 추출하지 못했습니다', result)
                    self.assertEqual(trace['executed_queries'], [])
                    self.assertEqual(len(llm.calls), 1)

    def test_omitted_alias_scope_requests_clarification(self):
        catalog = {'nodes': {n['id']: n for n in [U, W, WT]},
                   'aliases': [{'term': '철콘', 'node_id': WT['id']}]}
        with self.assertRaisesRegex(Clarification, '범위를 추출하지 못했습니다'):
            _plan(Interpretation(intent='hierarchy_aggregate'), '철콘 전체 사고 집계', catalog)

    def test_unspecified_total_does_not_default_to_all_construction(self):
        catalog = {'nodes': {n['id']: n for n in [U, W, WT]}, 'aliases': []}
        with self.assertRaisesRegex(Clarification, '범위를 명시'):
            _plan(Interpretation(intent='hierarchy_aggregate'), '전체 사고를 작업별로 집계해줘', catalog)

    def test_model_reported_extra_condition_is_not_dropped(self):
        llm = FakeLLM(interpretation(unsupported_conditions=['남성 근로자']))
        trace = {}
        result = answer_question('남성 근로자의 철근 반입 사례', [], llm, 'test', reader=reader(), trace=trace)
        self.assertIn('지원하지 않는 조건', result)
        self.assertEqual(trace['executed_queries'], [])

    def test_missing_summary_condition_requests_clarification(self):
        llm = FakeLLM(interpretation(intent='measure_summary'))
        result = answer_question('철근 반입 예방대책', [], llm, 'test', reader=reader())
        self.assertIn('모두', result)
        self.assertEqual(len(llm.calls), 1)

    def test_inferred_unmentioned_condition_is_rejected(self):
        llm = FakeLLM(interpretation())
        result = answer_question('굴착 작업에서 조심할 점', [], llm, 'test', reader=reader())
        self.assertIn('질문에서 확인되지', result)

    def test_unknown_and_ambiguous_names_are_not_selected(self):
        nodes = {U['id']: U, 'UW:other': {**U, 'id': 'UW:other', 'name': '9.1 철근 반입'}}
        catalog = {'nodes': nodes, 'aliases': []}
        for name in ['철근 반입', '없는 단위작업']:
            with self.subTest(name=name), self.assertRaises(Exception) as raised:
                _plan(Interpretation(intent='case_lookup', unit_work=name), name, catalog)
            self.assertIn('하나로 확인', str(raised.exception))

    def test_no_match_skips_explanation(self):
        llm = FakeLLM(interpretation())
        run = reader({TEMPLATES['T01']: [dict(total=0, scope_ids=[], evidence_ids=[])]})
        trace = {}
        result = answer_question('철근 반입 사례', [], llm, 'test', reader=run, trace=trace)
        self.assertIn('해당 사례 없음', result)
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(trace['status'], 'no_match')

    def test_db_error_returns_503_without_llm(self):
        llm = FakeLLM()
        run = reader({CATALOG_QUERY: ServiceUnavailable('offline')})

        def instrument(question, history, client, model):
            return answer_question(question, history, client, model, reader=run)

        with patch.object(main, 'client', llm), patch.object(main, 'answer_question', side_effect=instrument):
            response = TestClient(main.app).post('/api/chat', json={'message': '철근 반입 사례'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(llm.calls, [])

    def test_provider_failure_returns_502(self):
        llm = FakeLLM(RuntimeError('provider-error'))

        def instrument(question, history, client, model):
            return answer_question(question, history, client, model, reader=reader())

        with patch.object(main, 'client', llm), patch.object(main, 'answer_question', side_effect=instrument):
            response = TestClient(main.app).post('/api/chat', json={'message': '철근 반입 사례'})
        self.assertEqual(response.status_code, 502)

    def test_unverified_source_or_numeric_claim_uses_db_fallback(self):
        for raw in [explanation('가짜 사례입니다.', 'SIF-C-9999'), explanation('사고는 99건입니다.'), explanation('전체 사고는 두 건입니다.')]:
            with self.subTest(explanation=raw):
                trace = {}
                result = answer_question('철근 반입 사례', [], FakeLLM(interpretation(), raw),
                                         'test', reader=reader(), trace=trace)
                self.assertFalse(trace['explanation_accepted'])
                self.assertNotIn('9999', result)
                self.assertNotIn('99건', result)
                self.assertIn('12건', result)

    def test_physical_quantity_must_belong_to_the_same_cited_case(self):
        case = {**EVIDENCE, 'measures': [{'id': 'm1', 'text': '자재 4변 모퉁이에 완충재 설치'}]}
        records = {case['code']: case}
        self.assertTrue(_grounded_explanation(CaseExplanation(case_code=case['code'], text='자재 4변 모퉁이에 완충재를 설치하는 대책이다.'), records))
        for text in ['자재 5변에 완충재 설치', '사고는 4건이다.', '비율은 4%이다.']:
            self.assertFalse(_grounded_explanation(CaseExplanation(case_code=case['code'], text=text), records))

    def test_hierarchy_partition_error_is_not_explained(self):
        rows = [dict(total=2, count=2, group_case_ids=['a', 'b'], evidence_id='a'),
                dict(total=2, count=1, group_case_ids=['a'], evidence_id='a')]
        llm = FakeLLM(interpretation(intent='hierarchy_aggregate', unit_work=None, scope=WT['name']))
        run = reader({TEMPLATES['T02']: rows})
        with self.assertRaises(DataIntegrityError):
            answer_question(f"{WT['name']}를 작업별 집계", [], llm, 'test', reader=run)
        self.assertEqual(len(llm.calls), 1)

    def test_hierarchy_levels_and_default_denominators(self):
        catalog = {'nodes': {n['id']: n for n in [U, W, WT, O]}, 'aliases': []}
        for scope, group in [(WT, 'Work'), (W, 'UnitWork'), (U, 'UnitWork')]:
            with self.subTest(scope=scope):
                plan = _plan(Interpretation(intent='hierarchy_aggregate', scope=scope['name']), scope['name'], catalog)
                self.assertEqual(plan['parameters'], {'scope_id': scope['id'], 'group_by': group})
        plan = _plan(Interpretation(intent='hierarchy_aggregate'), '건설업 전체 공종별 집계', catalog)
        self.assertEqual(plan['parameters'], {'scope_id': None, 'group_by': 'WorkType'})

    def test_summary_requires_both_conditions_and_keeps_supporting_counts(self):
        measure = dict(id='m1', text='출입 통제', count=2, case_ids=['case-a', 'case-b'],
                       source_codes=['SIF-C-0453', 'SIF-C-0454'], evidence_id='case-a')
        rows = [dict(total=3, scope_ids=['case-a', 'case-b', 'case-c'], measures=[measure])]
        llm = FakeLLM(interpretation(intent='measure_summary', causal_object=O['name']), explanation())
        trace = {}
        result = answer_question(f"철근 반입 {O['name']} 예방대책", [], llm, 'test',
                                 reader=reader({TEMPLATES['T03']: rows}), trace=trace)
        self.assertIn('3건', result)
        self.assertIn('출입 통제: 2건', result)
        self.assertEqual(len(trace['evidence']), 1)
        prompt = llm.calls[-1]['messages'][-1]['content']
        self.assertNotIn('case-b', prompt)

    def test_live_verification_blocks_changed_db_text_before_provider_call(self):
        source = json.loads((Path(__file__).resolve().parents[1] / 'public/data/cases.json').read_text())['records']
        original = next(r for r in source if r['id'] == 'sif-2-457')
        evidence = {**EVIDENCE, 'id': verification.case_id(original), 'legacy_id': original['id'],
                    'summary': 'this is a changed private database field'}
        checked = verification.public_source_reader([original])
        with patch.object(verification, 'read_query', return_value=[evidence]):
            with self.assertRaisesRegex(AssertionError, 'provider call blocked'):
                checked(TEMPLATES['T04'], case_ids=[evidence['id']])


if __name__ == '__main__':
    unittest.main()
