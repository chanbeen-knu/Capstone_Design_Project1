import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { contextTypes, indexGraph, projectGraph, relationLabels } from './queryGraphData';
import './queryGraph.css';

const typeLabels = {
  WorkType: '공종', Work: '작업', UnitWork: '단위작업', CausalObject: '기인물',
  AccidentType: '재해종류', AccidentCase: '사고 사례', Measure: '예방대책',
};

function NodeDetails({ node, links, nodes }) {
  const p = node.props ?? {};
  return <div className="query-graph-detail" aria-live="polite">
    <strong>{typeLabels[node.type]} · {node.label}</strong>
    {p.code && p.code !== node.label && <div>코드 {p.code}</div>}
    {p.file && <div>{p.file} · {p.sheet} {p.row}행</div>}
    {p.summary && <div>{p.summary}</div>}
    {p.count != null && <div>{p.count.toLocaleString('ko-KR')}건{p.percent != null && ` · ${p.percent.toFixed(2)}%`}</div>}
    {p.case_codes?.length > 0 && <div>근거 {p.case_codes.join(', ')}</div>}
    {links.length > 0 && <ul>{links.map(link => <li key={link.id}>
      {relationLabels[link.relation]} · {nodes.get(link.source === node.id ? link.target : link.source).label}
    </li>)}</ul>}
  </div>;
}

function Connections({ links, highlighted, selected, zoom }) {
  const canvas = useRef(null);
  useLayoutEffect(() => {
    const surface = canvas.current;
    const element = surface.parentElement;
    function draw() {
      const width = element.clientWidth;
      const height = element.clientHeight;
      const box = surface.getBoundingClientRect();
      if (!box.width || !box.height) return;
      const resolution = Math.min(devicePixelRatio * zoom, 2);
      const ctx = surface.getContext('2d');
      surface.width = Math.round(width * resolution);
      surface.height = Math.round(height * resolution);
      ctx.scale(resolution, resolution);
      const rects = new Map([...element.querySelectorAll('[data-node-id]')].map(button =>
        [button.dataset.nodeId, button.getBoundingClientRect()]));
      const theme = getComputedStyle(element);
      const sorted = links.slice().sort((a, b) => Number(highlighted.has(a.id)) - Number(highlighted.has(b.id)));
      for (const link of sorted) {
        const source = rects.get(link.source), target = rects.get(link.target);
        if (!source || !target) continue;
        const [up, down] = source.top <= target.top ? [source, target] : [target, source];
        const x1 = (up.left + up.width / 2 - box.left) * width / box.width;
        const y1 = (up.bottom - box.top) * height / box.height;
        const x2 = (down.left + down.width / 2 - box.left) * width / box.width;
        const y2 = (down.top - box.top) * height / box.height;
        const active = highlighted.has(link.id);
        const middle = (y1 + y2) / 2;
        ctx.strokeStyle = theme.getPropertyValue(active ? '--query-edge-active' : '--query-edge');
        ctx.globalAlpha = selected && !active ? 0.22 : 1;
        ctx.lineWidth = active ? 2.5 : 1.25;
        ctx.setLineDash(link.relation === 'BROADER' ? [4, 3] : []);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.bezierCurveTo(x1, middle, x2, middle, x2, y2);
        ctx.stroke();
      }
    }
    const observer = new ResizeObserver(draw);
    observer.observe(element);
    element.querySelectorAll('[data-node-id]').forEach(node => observer.observe(node));
    const themeObserver = new MutationObserver(draw);
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'data-text-size'] });
    draw();
    return () => { observer.disconnect(); themeObserver.disconnect(); };
  }, [links, highlighted, selected, zoom]);
  return <canvas ref={canvas} className="query-graph-connections" aria-hidden="true"/>;
}

export default function QueryGraph({ graph }) {
  const viewport = useRef(null);
  const fullscreenButton = useRef(null);
  const [limit, setLimit] = useState(3);
  const [expanded, setExpanded] = useState({});
  const [selected, setSelected] = useState(null);
  const [zoom, setZoom] = useState(1);
  const [fullscreen, setFullscreen] = useState(false);
  const indexed = useMemo(() => indexGraph(graph), [graph]);
  const view = useMemo(() => projectGraph(indexed, limit, expanded), [indexed, limit, expanded]);
  const node = indexed.nodes.get(selected);
  const direct = view.links.filter(link => link.source === selected || link.target === selected);
  const neighborIds = new Set(direct.flatMap(link => [link.source, link.target]));
  const highlighted = new Set(direct.map(link => link.id));
  // Keep a selected case's route to higher-level question conditions visible.
  for (const link of direct.filter(link => link.source === selected)) {
    for (const edge of indexed.pathsToConditions(link.target)) {
      highlighted.add(edge.id);
      neighborIds.add(edge.target);
    }
  }

  useEffect(() => {
    if (!fullscreen) return;
    const close = event => {
      if (event.key !== 'Escape') return;
      setFullscreen(false);
      fullscreenButton.current?.focus();
    };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [fullscreen]);

  function renderNode(item) {
    const omitted = view.additions.get(item.id);
    return <div className="query-node-wrap" key={item.id}>
      <button type="button" className="query-node" data-node-id={item.id} data-node-type={item.type}
        data-related={neighborIds.has(item.id) || undefined} aria-pressed={item.id === selected}
        onClick={() => setSelected(previous => previous === item.id ? null : item.id)}>
        <span className="query-node-type">{typeLabels[item.type]}</span>
        <strong className="query-node-label">{item.label}</strong>
        {item.type === 'AccidentCase' && item.props?.summary && <span className="query-node-summary">{item.props.summary}</span>}
      </button>
      {omitted && Object.entries(omitted).filter(([, count]) => count > 0).map(([kind, count]) => {
        const open = Boolean(expanded[item.id]?.[kind]);
        const label = kind === 'measures' ? '예방대책' : '사고 맥락';
        return <button key={kind} type="button" className="query-node-more" aria-expanded={open}
          onClick={() => {
            if (open) setSelected(null);
            setExpanded(previous => ({ ...previous, [item.id]: { ...previous[item.id], [kind]: !open } }));
          }}>{open ? `${label} 접기` : `${label} ${count}개 더 보기`}</button>;
      })}
    </div>;
  }

  const hasConditions = indexed.conditions.length > 0 || indexed.textConditions.length > 0;
  const number = value => value.toLocaleString('ko-KR');
  return <div className={`query-graph${fullscreen ? ' query-graph-expanded' : ''}`}>
    <div className="query-graph-toolbar">
      <span role="status">전체 {number(graph.matched_case_count ?? indexed.cases.length)}건 중 {number(view.cases.length)}건 표시</span>
      {(hasConditions || view.cases.length > 0) && <div>
        <button type="button" className="secondary-button" aria-label="그래프 확대" disabled={zoom >= 1.8}
          onClick={() => setZoom(value => Math.min(1.8, value + .2))}>+</button>
        <button type="button" className="secondary-button" aria-label="그래프 축소" disabled={zoom <= .6}
          onClick={() => setZoom(value => Math.max(.6, value - .2))}>−</button>
        <button type="button" className="secondary-button" onClick={() => {
          setZoom(1);
          viewport.current?.scrollTo(0, 0);
        }}>화면 맞춤</button>
        <button ref={fullscreenButton} type="button" className="secondary-button" aria-expanded={fullscreen}
          onClick={() => setFullscreen(value => !value)}>{fullscreen ? '전체화면 닫기' : '전체화면'}</button>
      </div>}
    </div>
    {node && <NodeDetails node={node} links={direct} nodes={indexed.nodes}/>}
    <div className="query-graph-viewport" ref={viewport}>
      <div className="query-graph-stage" style={{ zoom }}>
        <Connections links={view.links} highlighted={highlighted} selected={selected} zoom={zoom}/>
        {hasConditions && <section className="query-tier query-tier-conditions">
          <h4>질문 조건</h4>
          <div className="query-tier-nodes">
            {indexed.conditions.map(renderNode)}
            {indexed.textConditions.map((term, i) => <span key={i} className="query-text-condition">{term}</span>)}
          </div>
        </section>}
        {view.context.length > 0 && <section className="query-tier">
          <h4>사고 맥락</h4>
          <div className="query-context">
            {contextTypes.map(type => {
              const group = view.context.filter(item => item.type === type);
              return group.length > 0 && <div className="query-tier-nodes" key={type}>{group.map(renderNode)}</div>;
            })}
          </div>
        </section>}
        <section className="query-tier">
          <h4>사고 사례</h4>
          <div className="query-tier-nodes">{view.cases.map(renderNode)}</div>
          {!view.cases.length && <p>그래프에 표시할 사고 사례가 없습니다.</p>}
        </section>
        {view.measures.length > 0 && <section className="query-tier">
          <h4>예방대책</h4>
          <div className="query-tier-nodes">{view.measures.map(renderNode)}</div>
        </section>}
      </div>
    </div>
    {limit < indexed.cases.length && <button type="button" className="secondary-button query-cases-more"
      onClick={() => setLimit(value => value + 3)}>사례 {Math.min(3, indexed.cases.length - limit)}건 더 보기</button>}
  </div>;
}
