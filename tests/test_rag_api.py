import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable
from openai import OpenAIError

import main


class RagApiTests(unittest.TestCase):
    def setUp(self):
        self.api = TestClient(main.app)
        self.result = dict(answer='근거 답변', agent='ontology', sources=[], status='answered')

    def test_default_routes_to_ontology_and_keeps_response_fields(self):
        with patch.object(main, 'client', object()), patch.object(
                main.ontology_chat, 'answer', return_value=self.result) as answer:
            response = self.api.post('/api/chat', json={'message': '  철근 반입 사례  '})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.result)
        self.assertEqual(answer.call_args.args[2:], ('철근 반입 사례', []))

    def test_vector_routes_to_vector_answer(self):
        with patch.object(main, 'client', object()), patch.object(main.vector_index, 'load_index'), patch.object(
                main.rag, 'answer', return_value={**self.result, 'agent': 'vector'}) as answer:
            response = self.api.post('/api/chat', json={'message': '사고 사례', 'agent': 'vector'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(answer.call_args.args[2], 'vector')

    def test_missing_generation_key_returns_503(self):
        with patch.object(main, 'client', None):
            self.assertEqual(self.api.post('/api/chat', json={'message': '사고 사례'}).status_code, 503)

    def test_index_missing_returns_503(self):
        with patch.object(main, 'client', object()), patch.object(main.vector_index, 'load_index',
                side_effect=main.vector_index.IndexUnavailable('인덱스 없음')):
            response = self.api.post('/api/chat', json={'message': '사고 사례', 'agent': 'vector'})
        self.assertEqual(response.status_code, 503)

    def test_upstream_and_output_errors_return_502_db_error_returns_503(self):
        for error, status in [(OpenAIError('provider failed'), 502),
                              (main.rag.InvalidModelOutput('invalid output'), 502),
                              (ServiceUnavailable('offline'), 503)]:
            with self.subTest(error=type(error).__name__), patch.object(main, 'client', object()), patch.object(
                    main.ontology_chat, 'answer', side_effect=error):
                response = self.api.post('/api/chat', json={'message': '사고 사례'})
                self.assertEqual(response.status_code, status)

    def test_request_validation(self):
        self.assertEqual(self.api.post('/api/chat', json={'message': '  '}).status_code, 400)
        self.assertEqual(self.api.post('/api/chat', json={'message': '질문', 'agent': 'bad'}).status_code, 422)


if __name__ == '__main__':
    unittest.main()
