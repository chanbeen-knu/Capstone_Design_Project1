'''Neo4j 지식그래프 조회 + 프론트(GraphPanel)용 {nodes, links} 변환.

Neo4j 라벨 -> 프론트 nodeTypes 매핑
  UnitWork          -> task        (작업)
  CausalObject      -> equipment   (기인물)
  AccidentType      -> accident    (사고유형)
  PreventiveMeasure -> prevention  (예방대책)
'''
import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

_driver = None


def get_driver():
    
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "password123")),
        )
    return _driver


def run(query, **params):
    with get_driver().session() as session:
        return [record.data() for record in session.run(query, **params)]


def _short(text, limit=12):
    return text if len(text) <= limit else text[:limit] + "…"


def object_list():
    
    return run(
        """
        MATCH (c:AccidentCase)-[:INVOLVES]->(o:CausalObject)
        RETURN o.name AS name, count(c) AS cases
        ORDER BY cases DESC
        """
    )


def object_graph(name, per_type=6):

    #기인물 하나 중심, 작업 -> 기인물 -> 사고유형 / 예방대책 그래프 생성
    center = run(
        """
        MATCH (o:CausalObject {name: $name})
        OPTIONAL MATCH (c:AccidentCase)-[:INVOLVES]->(o)
        WITH o, count(c) AS cases, collect(c.id)[0..5] AS examples
        RETURN o.name AS name, cases, examples
        """,
        name=name,
    )
    if not center:
        return None

    works = run(
        """
        MATCH (u:UnitWork)-[r:HAS_HAZARD]->(:CausalObject {name: $name})
        RETURN u.code AS code, u.name AS name, r.count AS count
        ORDER BY count DESC LIMIT $limit
        """,
        name=name, limit=per_type,
    )
    accidents = run(
        """
        MATCH (:CausalObject {name: $name})-[r:LEADS_TO]->(a:AccidentType)
        RETURN a.name AS name, r.count AS count
        ORDER BY count DESC LIMIT $limit
        """,
        name=name, limit=per_type,
    )
    measures = run(
        """
        MATCH (:CausalObject {name: $name})-[r:MITIGATED_BY]->(m:PreventiveMeasure)
        RETURN m.text AS text, r.count AS count
        ORDER BY count DESC LIMIT $limit
        """,
        name=name, limit=per_type,
    )
    return build_graph(center[0], works, accidents, measures)


def build_graph(center, works, accidents, measures):
    #조화 결과 graph 그리는 것.
    obj_id = f"obj:{center['name']}"
    nodes = [{
        "id": obj_id,
        "label": center["name"],
        "type": "equipment",
        "props": {"cases": center["cases"], "examples": center["examples"]},
    }]
    links = []

    for w in works:
        node_id = f"uw:{w['code']}"
        nodes.append({"id": node_id, "label": _short(w["name"]), "type": "task",
                      "props": {"code": w["code"], "fullName": w["name"], "count": w["count"]}})
        links.append({"source": node_id, "target": obj_id,
                      "relation": f"위험 기인물 · {w['count']}건", "count": w["count"]})

    for a in accidents:
        node_id = f"acc:{a['name']}"
        nodes.append({"id": node_id, "label": a["name"], "type": "accident",
                      "props": {"count": a["count"]}})
        links.append({"source": obj_id, "target": node_id,
                      "relation": f"사고 · {a['count']}건", "count": a["count"]})

    for i, m in enumerate(measures):
        node_id = f"pm:{center['name']}:{i}"
        nodes.append({"id": node_id, "label": _short(m["text"]), "type": "prevention",
                      "props": {"fullName": m["text"], "count": m["count"]}})
        links.append({"source": obj_id, "target": node_id,
                      "relation": f"예방대책 · {m['count']}건", "count": m["count"]})

    return {
        "source": "neo4j",
        "title": center["name"],
        "subtitle": f"사고사례 {center['cases']}건 기반 · 작업 → 기인물 → 사고유형 / 예방대책",
        "nodes": nodes,
        "links": links,
    }


def case_detail(case_id):
    rows = run(
        """
        MATCH (c:AccidentCase {id: $id})
        OPTIONAL MATCH (c)-[:DURING]->(u:UnitWork)
        OPTIONAL MATCH (c)-[:INVOLVES]->(o:CausalObject)
        OPTIONAL MATCH (c)-[:RESULTED_IN]->(a:AccidentType)
        OPTIONAL MATCH (c)-[:HAS_MEASURE]->(m:PreventiveMeasure)
        RETURN c.id AS id, c.year AS year, c.fatal AS fatal, c.summary AS summary,
               c.risk_text AS riskText, u.name AS unitWork, o.name AS causalObject,
               a.name AS accidentType, collect(m.text) AS measures
        """,
        id=case_id,
    )
    return rows[0] if rows and rows[0]["id"] else None


def ping():
    run("RETURN 1 AS ok")
    return True
