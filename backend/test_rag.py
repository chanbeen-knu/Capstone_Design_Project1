import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import rag


def response(content, finish_reason='stop'):
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=content), finish_reason=finish_reason)], usage=None)


class StructuredOutputTests(unittest.TestCase):
    def test_retry_reports_excess_citations(self):
        statement = dict(text='사고 사례입니다.', case_ids=['case'] * 10, quotes=['원문 구절'] * 10)
        client = Mock()
        client.chat.completions.create.side_effect = [
            response(json.dumps(dict(statements=[statement]))),
            response('{"statements": []}'),
        ]
        calls = []
        rag.structured(client, 'test', rag.Draft, '답변', {}, calls, 'answer')
        errors = calls[0]['validation_errors']
        self.assertEqual(errors[0]['loc'], ('statements', 0, 'case_ids'))
        retry = client.chat.completions.create.call_args.kwargs
        self.assertIn('case_ids', retry['messages'][-1]['content'])
        self.assertNotIn('input', errors[0])
        self.assertTrue(calls[1]['schema_valid'])

    def test_truncated_json_gets_larger_retry_budget(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            response('{"statements": [', 'length'), response('{"statements": []}')]
        rag.structured(client, 'test', rag.Draft, '답변', {}, [], 'answer')
        self.assertEqual(client.chat.completions.create.call_args.kwargs['max_tokens'], 3600)

    def test_invalid_output_stops_after_two_attempts(self):
        client = Mock()
        client.chat.completions.create.return_value = response('invalid JSON')
        with self.assertRaises(rag.InvalidModelOutput):
            rag.structured(client, 'test', rag.Draft, '답변', {}, [], 'answer')
        self.assertEqual(client.chat.completions.create.call_count, 2)


class VectorAggregateTests(unittest.TestCase):
    def test_aggregate_requests_return_examples_without_generated_totals(self):
        evidence = [dict(id=f'case-{i}', code=f'SIF-{i}', summary=f'원문 사고 경위 {i}')
                    for i in range(10)]
        for intent in ('count', 'distribution', 'patterns'):
            with self.subTest(intent=intent), patch('rag.structured', return_value=rag.SearchPlan(
                    intent=intent, query='철근콘크리트 공사 전체 사고')) as generate, patch(
                    'vector_index.retrieve', return_value=evidence):
                result = rag.answer(Mock(), 'test', 'vector', '작업별 건수와 비율', [])
                self.assertEqual(result['status'], 'limited')
                self.assertIsNone(result['statistics'])
                self.assertEqual(result['sources'], evidence[:3])
                self.assertIn('온톨로지 RAG', result['answer'])
                self.assertIn('원문 사고 경위 0 [1]', result['answer'])
                generate.assert_called_once()

    def test_empty_aggregate_search_still_explains_limitation(self):
        with patch('rag.structured', return_value=rag.SearchPlan(intent='count', query='사고')), patch(
                'vector_index.retrieve', return_value=[]):
            result = rag.answer(Mock(), 'test', 'vector', '전체 사고 건수', [])
        self.assertEqual(result['status'], 'limited')
        self.assertEqual(result['sources'], [])
        self.assertIn('집계할 수 없습니다', result['answer'])


if __name__ == '__main__':
    unittest.main()
