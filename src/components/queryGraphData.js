export const contextTypes = ['WorkType', 'Work', 'UnitWork', 'CausalObject', 'AccidentType'];
export const contextRelations = {
  OCCURRED_DURING: '작업 중 발생',
  INVOLVES: '관련 기인물',
  HAS_ACCIDENT_TYPE: '재해종류',
};
export const relationLabels = { ...contextRelations, BROADER: '상위 분류', HAS_MEASURE: '예방대책' };

const byLabel = (a, b) => a.label.localeCompare(b.label, 'ko', { numeric: true }) || a.id.localeCompare(b.id);

export function indexGraph(graph) {
  const nodes = new Map(graph.nodes.map(node => [node.id, node]));
  const outgoing = new Map();
  for (const link of graph.links) {
    if (!nodes.has(link.source) || !nodes.has(link.target)) continue;
    if (!outgoing.has(link.source)) outgoing.set(link.source, []);
    outgoing.get(link.source).push(link);
  }
  const conditionNames = graph.conditions ?? [];
  const conditions = (graph.condition_node_ids ?? conditionNames.flatMap(name => {
    const matches = graph.nodes.filter(node => contextTypes.includes(node.type) && node.label === name);
    return matches.length === 1 ? [matches[0].id] : [];
  })).map(id => nodes.get(id)).filter(Boolean);
  const conditionIds = new Set(conditions.map(node => node.id));
  const conditionPaths = new Map();
  function pathsToConditions(id, visited = new Set()) {
    if (conditionIds.has(id) || visited.has(id)) return [];
    if (conditionPaths.has(id)) return conditionPaths.get(id);
    const seen = new Set(visited).add(id);
    const paths = (outgoing.get(id) ?? []).filter(link => link.relation === 'BROADER').flatMap(link => {
      const rest = pathsToConditions(link.target, seen);
      return rest.length || conditionIds.has(link.target) ? [link, ...rest] : [];
    });
    conditionPaths.set(id, paths);
    return paths;
  }

  const cases = graph.nodes.filter(node => node.type === 'AccidentCase').sort(byLabel).map(node => {
    const links = outgoing.get(node.id) ?? [];
    const context = links.filter(link => Object.hasOwn(contextRelations, link.relation)).sort((a, b) => {
      const priority = link => conditionIds.has(link.target) ? 0 : pathsToConditions(link.target).length ? 1 : 2;
      return priority(a) - priority(b) || byLabel(nodes.get(a.target), nodes.get(b.target));
    });
    return { node, context, measures: links.filter(link => link.relation === 'HAS_MEASURE') };
  });
  return {
    nodes, cases, conditions, conditionIds, pathsToConditions,
    textConditions: [...conditionNames.filter(name => !conditions.some(node => node.label === name)), ...(graph.summary_terms ?? [])],
  };
}

export function selectCases(cases, limit) {
  const remaining = cases.slice();
  const shown = new Set();
  const selected = [];
  while (remaining.length && selected.length < limit) {
    let best = 0;
    let bestAccidents = -1;
    let bestContext = -1;
    remaining.forEach(({ context }, index) => {
      const newLinks = context.filter(link => !shown.has(link.target));
      const accidents = newLinks.filter(link => link.relation === 'HAS_ACCIDENT_TYPE').length;
      const other = newLinks.length - accidents;
      if (accidents > bestAccidents || (accidents === bestAccidents && other > bestContext)) {
        best = index;
        bestAccidents = accidents;
        bestContext = other;
      }
    });
    const [entry] = remaining.splice(best, 1);
    selected.push(entry);
    entry.context.forEach(link => shown.add(link.target));
  }
  return selected;
}

export function projectGraph(index, limit, expanded) {
  const cases = selectCases(index.cases, limit);
  const frequency = new Map();
  for (const entry of cases) {
    for (const id of new Set(entry.measures.map(link => link.target))) {
      frequency.set(id, (frequency.get(id) ?? 0) + 1);
    }
  }
  const links = new Map();
  const contextIds = new Set();
  const measureIds = new Set();
  const additions = new Map();
  for (const entry of cases) {
    const id = entry.node.id;
    const types = new Set();
    const preferred = entry.context.filter(link => {
      const type = index.nodes.get(link.target).type;
      if (types.has(type)) return false;
      types.add(type);
      return true;
    });
    const coveredConditions = new Set();
    function markConditions(link) {
      const reached = [link.target, ...index.pathsToConditions(link.target).map(edge => edge.target)]
        .filter(target => index.conditionIds.has(target));
      const addsCondition = reached.some(target => !coveredConditions.has(target));
      reached.forEach(target => coveredConditions.add(target));
      return addsCondition;
    }
    preferred.forEach(markConditions);
    const required = entry.context.filter(markConditions);
    const baseContext = [...preferred, ...required];
    const measures = entry.measures.slice().sort((a, b) =>
      frequency.get(b.target) - frequency.get(a.target) || byLabel(index.nodes.get(a.target), index.nodes.get(b.target)));
    additions.set(id, { context: entry.context.length - baseContext.length, measures: Math.max(0, measures.length - 2) });
    const open = expanded[id] ?? {};
    for (const link of open.context ? entry.context : baseContext) {
      links.set(link.id, link);
      contextIds.add(link.target);
      for (const edge of index.pathsToConditions(link.target)) {
        links.set(edge.id, edge);
        contextIds.add(edge.target);
      }
    }
    for (const link of open.measures ? measures : measures.slice(0, 2)) {
      links.set(link.id, link);
      measureIds.add(link.target);
    }
  }
  const ordered = ids => [...ids].map(id => index.nodes.get(id)).sort(byLabel);
  return {
    cases: cases.map(entry => entry.node),
    context: ordered([...contextIds].filter(id => !index.conditionIds.has(id))),
    measures: ordered(measureIds),
    links: [...links.values()],
    additions,
  };
}
