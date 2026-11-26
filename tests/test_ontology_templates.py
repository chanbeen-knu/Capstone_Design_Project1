"""온톨로지 답변 템플릿 검증 (실제 Neo4j 필요, LLM 불필요 — 추가 질문 plan으로 바로 실행).
기대값은 2026-11-24 Aura(건설업 3,459건)에서 직접 센 값. docs/answer-structure.md 7절.
실행: backend/.venv/Scripts/python -m unittest tests/test_ontology_templates.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

import ontology_chat as o  # noqa: E402

try:
    o.catalog()
    LIVE = True
except Exception:  # Neo4j 연결이 없으면 건너뜀
    LIVE = False


def run(**plan):
    return o.answer(None, None, '', [], plan=plan)


@unittest.skipUnless(LIVE, 'Neo4j 연결 필요')
class TemplateTests(unittest.TestCase):
    def test_cases_unit_work(self):
        self.assertEqual(run(intent='cases', conditions={'work': ['UW:2.3.1 철근 반입']})['block']['total'], 12)

    def test_distribution_work_hierarchy(self):
        block = run(intent='distribution', conditions={'work': ['WT:2. 철근콘크리트 공사']}, group_by='work')['block']
        self.assertEqual(block['total'], 433)
        self.assertEqual([r['count'] for r in block['rows']], [213, 120, 67, 33])

    def test_measures_work_and_object(self):
        r = run(intent='measures', conditions={'work': ['UW:2.3.1 철근 반입'], 'object': ['CO:굴착기']})
        self.assertEqual(r['evidence']['total'], 3)
        self.assertEqual(r['block']['total'], 6)
        self.assertEqual(sorted(r['evidence']['codes']), ['SIF-C-0455', 'SIF-C-0461', 'SIF-C-0462'])

    def test_object_category(self):
        self.assertEqual(run(intent='distribution', conditions={'object': ['COC:차량·건설기계']})['block']['total'], 614)

    def test_accident_group(self):
        self.assertEqual(run(intent='distribution', conditions={'accident': ['ATG:맞음·부딪힘']})['block']['total'], 410)

    def test_hazard(self):
        r = run(intent='cause', conditions={'hazard': ['HF:추락방지시설 미설치']})
        self.assertEqual(r['block']['total'], 1406)
        self.assertEqual(r['block']['rows'][0]['label'], '비계')

    def test_control_level(self):
        r = run(intent='measures', conditions={'object': ['CO:비계'], 'accident': ['AT:추락'], 'control': ['CL:공학적 대책']})
        self.assertEqual(r['block']['total'], 122)
        self.assertTrue(all('공학적 대책' in m['levels'] for m in r['block']['items']))

    def test_patterns(self):
        top = run(intent='patterns')['block']['items'][0]
        self.assertEqual((top['name'], top['size']), ('비계 · 추락 · 추락방지시설 미설치', 168))

    def test_checklist(self):
        r = run(intent='checklist', conditions={'object': ['CO:비계']})
        self.assertIn('196건 중 172건', r['answer'])
        self.assertEqual(len(r['block']['items']), 3)

    def test_case_detail(self):
        self.assertIn('12건 반복', run(intent='case_detail', code='SIF-C-0455')['answer'])

    def test_period_and_height(self):
        self.assertTrue(run(intent='patterns', conditions={'period': ['P:중대재해처벌법 시행 이후']})['block']['items'])
        self.assertEqual(run(intent='distribution', conditions={'accident': ['AT:추락']}, group_by='height')['block']['heading'],
                         '추락 높이')

    def test_zero_never_says_none_silently(self):
        r = run(intent='distribution', conditions={'object': ['CO:타워크레인'], 'accident': ['AT:질식']})
        self.assertIsNone(r['block'])
        self.assertIn('확인되지 않았어요', r['answer'])

    def test_resolve(self):
        self.assertEqual([n['id'] for n in o.resolve('포크레인')[0]], ['CO:굴착기'])
        self.assertEqual([n['id'] for n in o.resolve('건설기계')[0]], ['COC:차량·건설기계'])
        self.assertNotIn('CO:굴착기', [n['id'] for n in o.resolve('크레인')[0]])

    def test_follow_ups_are_runnable(self):
        r = run(intent='distribution', conditions={'object': ['CO:굴착기']})
        for item in r['follow_ups']:
            self.assertEqual(run(**item['plan'])['status'], 'answered', item['label'])


class HeightPhraseTests(unittest.TestCase):  # DB 불필요
    def test_height_name(self):
        cases = {'2m도 안 되는 높이에서 떨어진 사고': '2m 미만', '10미터 넘는 곳에서 추락': '10m 이상',
                 '2m 이상 고소작업': '고소(2m 이상)', '1.5m 이하 사다리': '2m 미만', '5m 아래': None, '굴착기 사고': None}
        for text, expected in cases.items():
            self.assertEqual(o.height_name(text), expected, text)


if __name__ == '__main__':
    unittest.main()
