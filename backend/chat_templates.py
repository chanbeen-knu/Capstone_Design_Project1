"""The four fixed, parameterized, read-only queries used by graph chat."""

CASE_LOOKUP = """
MATCH (c:AccidentCase {sectorCode: 'C'})
WHERE ($unit_work_id IS NULL OR EXISTS {
  MATCH (c)-[:OCCURRED_DURING]->(:UnitWork {id: $unit_work_id})
}) AND ($object_id IS NULL OR EXISTS {
  MATCH (c)-[:INVOLVES]->(:CausalObject)-[:BROADER*0..1]->
        (:CausalObject {id: $object_id})
})
WITH DISTINCT c ORDER BY c.code, c.id
WITH collect(c) AS cs
RETURN size(cs) AS total, [c IN cs | c.id] AS scope_ids,
       [c IN cs[0..$evidence_limit] | c.id] AS evidence_ids
"""

HIERARCHY_AGGREGATE = """
MATCH (c:AccidentCase {sectorCode: 'C'})-[:OCCURRED_DURING]->(u:UnitWork)
      -[:BROADER]->(w:Work)-[:BROADER]->(t:WorkType)
WHERE $scope_id IS NULL OR u.id = $scope_id OR w.id = $scope_id OR t.id = $scope_id
WITH DISTINCT c, u, w, t ORDER BY c.code, c.id
WITH collect(DISTINCT c) AS cs,
     collect(DISTINCT {case_id: c.id, node: CASE $group_by
       WHEN 'WorkType' THEN t WHEN 'Work' THEN w ELSE u END}) AS matches
UNWIND matches AS item
WITH cs, size(cs) AS total, item.node AS g, item.case_id AS case_id
WITH cs, total, g, collect(DISTINCT case_id) AS case_ids
RETURN total, g.id AS group_id, g.name AS name, size(case_ids) AS count,
       round(100.0 * size(case_ids) / total, 2) AS percent,
       case_ids AS group_case_ids,
       [c IN cs WHERE c.id IN case_ids | c.id][0] AS evidence_id
ORDER BY count DESC, group_id
"""

MEASURE_SUMMARY = """
MATCH (c:AccidentCase {sectorCode: 'C'})
WHERE EXISTS {
  MATCH (c)-[:OCCURRED_DURING]->(:UnitWork {id: $unit_work_id})
} AND EXISTS {
  MATCH (c)-[:INVOLVES]->(:CausalObject)-[:BROADER*0..1]->
        (:CausalObject {id: $object_id})
}
WITH DISTINCT c ORDER BY c.code, c.id
WITH collect(c) AS cs
CALL (cs) {
  UNWIND cs AS c
  MATCH (c)-[:HAS_MEASURE]->(m:Measure)
  WITH DISTINCT m, c ORDER BY c.code, c.id
  WITH m, collect(c) AS supporting
  ORDER BY size(supporting) DESC, m.id LIMIT $measure_limit
  RETURN collect({id: m.id, text: m.text, count: size(supporting),
                  case_ids: [c IN supporting | c.id],
                  source_codes: [c IN supporting | c.code],
                  evidence_id: supporting[0].id}) AS measures
}
RETURN size(cs) AS total, [c IN cs | c.id] AS scope_ids, measures
"""

EVIDENCE_DETAILS = """
MATCH (c:AccidentCase {sectorCode: 'C'}) WHERE c.id IN $case_ids
OPTIONAL MATCH (c)-[hm:HAS_MEASURE]->(m:Measure)
WITH c, hm, m ORDER BY c.code, c.id, hm.order, m.id
WITH c, collect(DISTINCT m {.id, .text}) AS measures
RETURN c.id AS id, c.code AS code, c.legacyId AS legacy_id,
       c.summary AS summary, c.raw_uw AS unit_work, c.raw_w AS work,
       c.raw_wt AS work_type, c.raw_co AS causal_object,
       c.raw_hf AS raw_hazard, c.raw_ms AS raw_measures, measures
ORDER BY code, id
"""

TEMPLATES = {
    'T01': CASE_LOOKUP,
    'T02': HIERARCHY_AGGREGATE,
    'T03': MEASURE_SUMMARY,
    'T04': EVIDENCE_DETAILS,
}
