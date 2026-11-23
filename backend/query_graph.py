"""Project actual Neo4j relationships for the cases in an ontology answer."""
import graph

PATHS = """
MATCH (c:AccidentCase) WHERE c.id IN $case_ids
WITH c,
  [(c)-[r:OCCURRED_DURING]->(u:UnitWork) | r] +
  [(c)-[:OCCURRED_DURING]->(:UnitWork)-[r:BROADER]->(:Work) | r] +
  [(c)-[:OCCURRED_DURING]->(:UnitWork)-[:BROADER]->(:Work)-[r:BROADER]->(:WorkType) | r] +
  [(c)-[r:HAS_ACCIDENT_TYPE]->(:AccidentType) | r] +
  [(c)-[r:INVOLVES]->(o:CausalObject)
     WHERE ($include_details AND $object_id IS NULL) OR o.id = $object_id
        OR (o)-[:BROADER]->(:CausalObject {id:$object_id}) | r] +
  [(c)-[:INVOLVES]->(:CausalObject)-[r:BROADER]->(:CausalObject {id:$object_id}) | r] +
  [(c)-[r:HAS_MEASURE]->(:Measure) WHERE $include_details AND ($top_ids IS NULL OR EXISTS {
       MATCH (c)-[:HAS_ACCIDENT_TYPE]->(a:AccidentType) WHERE a.id IN $top_ids
     }) | r] AS relations
UNWIND relations AS r
WITH DISTINCT r
WITH r, startNode(r) AS s, endNode(r) AS t
RETURN elementId(r) AS id, type(r) AS relation,
       s{.*, key:elementId(s), kinds:labels(s)} AS s,
       t{.*, key:elementId(t), kinds:labels(t)} AS t
"""
CONDITIONS = """
UNWIND $conditions AS condition
MATCH (n {id:condition.id}) WHERE condition.level IN labels(n)
OPTIONAL MATCH (term:Term)-[r:REFERS_TO]->(n) WHERE term.name IN condition.aliases
RETURN n{.*, key:elementId(n), kinds:labels(n)} AS n,
       term{.*, key:elementId(term), kinds:labels(term)} AS term, elementId(r) AS id
"""

TYPES = ('AccidentCase', 'UnitWork', 'Work', 'WorkType', 'CausalObject',
         'AccidentType', 'Measure', 'Term')


def build(case_ids, scope, intent, statistics, measures, group_type):
    nodes, links = {}, {}
    counts = {(group_type, row['label']): row for row in statistics['rows']}
    for row in statistics.get('top_accidents', []):
        counts['AccidentType', row['label']] = row
    measure_by_id = {}
    for row in measures:
        measure_by_id.setdefault(row['id'], set()).update(row['case_codes'])
    top_ids = [row['id'] for row in statistics['top_accidents']] if intent == 'advice' else None

    def add_node(node):
        key = node['key']
        if key not in nodes:
            kind = next(label for label in TYPES if label in node['kinds'])
            props = {field: node[field] for field in ('id', 'name', 'code', 'summary', 'sheet', 'row', 'text')
                     if node.get(field) is not None}
            if node.get('sources'):
                props['file'] = node['sources'][0]
            label = node.get('name') or node.get('code') or node.get('text') or key
            stats = counts.get((kind, label))
            if stats:
                props.update(count=stats['count'], percent=stats['percent'])
            if kind == 'Measure' and node.get('id') in measure_by_id:
                measure = measure_by_id[node['id']]
                props.update(count=len(measure), case_codes=sorted(measure))
            nodes[key] = dict(id=key, type=kind, label=label, props=props)
        return key

    def add_link(key, relation, source, target):
        links[key] = dict(id=key, relation=relation, source=add_node(source), target=add_node(target))

    for row in graph.run(PATHS, case_ids=case_ids, include_details=intent != 'distribution',
                         object_id=scope.get('object', {}).get('id'), top_ids=top_ids):
        add_link(row['id'], row['relation'], row['s'], row['t'])
    conditions = [value for value in scope.values() if isinstance(value, dict)]
    for row in graph.run(CONDITIONS, conditions=conditions):
        add_node(row['n'])
        if row['term'] is not None:
            add_link(row['id'], 'REFERS_TO', row['term'], row['n'])
    return dict(nodes=list(nodes.values()), links=list(links.values()), matched_case_count=len(case_ids),
                conditions=[value['name'] for value in conditions], summary_terms=scope.get('summary_terms', []))
