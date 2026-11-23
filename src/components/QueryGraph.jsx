import { useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { nodeTypes } from '../data/mockData';
import { useSettings } from '../settings';

const styles = {
  WorkType: { ...nodeTypes.task, label: '공종' },
  Work: nodeTypes.task,
  UnitWork: { ...nodeTypes.task, label: '단위작업' },
  CausalObject: nodeTypes.equipment,
  AccidentType: nodeTypes.accident,
  Measure: nodeTypes.prevention,
  AccidentCase: { color: '#cc914b', label: '사고 사례' },
  Term: { color: '#8aa197', label: '동의어' },
};
const endpoint = value => value?.id ?? value;
const short = label => label.length > 22 ? label.slice(0, 22) + '…' : label;

function NodeDetails({ node, neighbors }) {
  const p = node.props;
  const hierarchy = neighbors.filter(link => link.relation === 'BROADER' && endpoint(link.source) === node.id)
    .map(link => link.target.label);
  return <div className="query-graph-detail">
    <strong>{styles[node.type].label} · {node.label}</strong>
    {p.code && p.code !== node.label && <div>코드 {p.code}</div>}
    {hierarchy.length > 0 && <div>상위 분류 {hierarchy.join(', ')}</div>}
    {p.file && <div>{p.file} · {p.sheet} {p.row}행</div>}
    {p.summary && <div>{p.summary}</div>}
    {p.count != null && <div>{p.count.toLocaleString('ko-KR')}건{p.percent != null && ` · ${p.percent.toFixed(2)}%`}</div>}
    {p.case_codes?.length > 0 && <div>근거 {p.case_codes.join(', ')}</div>}
    {neighbors.length > 0 && <div>연결 관계 {Array.from(new Set(neighbors.map(link => link.relation))).join(', ')}</div>}
  </div>;
}

export default function QueryGraph({ graph }) {
  const settings = useSettings();
  const container = useRef(null);
  const canvas = useRef(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [fullscreen, setFullscreen] = useState(false);
  const [hover, setHover] = useState(null);
  const [pinned, setPinned] = useState(null);
  const [hoverLink, setHoverLink] = useState(null);
  const data = useMemo(() => ({
    nodes: graph.nodes.map(node => ({ ...node })),
    links: graph.links.map(link => ({ ...link })),
  }), [graph]);
  const active = hover ?? pinned;
  const neighbors = useMemo(() => active ? data.links.filter(link =>
    endpoint(link.source) === active.id || endpoint(link.target) === active.id) : [], [active, data]);
  const activeLinks = useMemo(() => new Set(neighbors), [neighbors]);
  const activeNodes = useMemo(() => new Set(neighbors.flatMap(link =>
    [endpoint(link.source), endpoint(link.target)])), [neighbors]);
  const types = [...new Set(data.nodes.map(node => node.type))];
  const fit = () => canvas.current?.zoomToFit(250, 32);
  const background = settings.dark ? '#182630' : '#f8fafb';

  useEffect(() => {
    const observer = new ResizeObserver(([{ contentRect }]) => setSize({
      width: Math.floor(contentRect.width), height: Math.floor(contentRect.height),
    }));
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);

  const ready = size.width > 0 && size.height > 0;
  useEffect(() => {
    const fg = canvas.current;
    if (!ready || !fg) return;
    fg.d3Force('charge')?.strength(-95);
    fg.d3Force('link')?.distance(68);
    fg.d3ReheatSimulation();
  }, [data, ready]);

  useEffect(() => {
    if (!ready) return;
    const timer = setTimeout(() => canvas.current?.zoomToFit(180, 28), 70);
    return () => clearTimeout(timer);
  }, [ready, size, fullscreen]);

  useEffect(() => {
    if (!fullscreen) return;
    const close = event => {
      if (event.key === 'Escape') setFullscreen(false);
    };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [fullscreen]);

  function drawLabels(ctx, scale) {
    const occupied = [];
    const candidates = active ? [active, ...data.nodes.filter(node => node.id !== active.id && activeNodes.has(node.id))] : data.nodes;
    const labels = candidates.filter(node => node.x != null && node.y != null).sort((a, b) => {
      const priority = node => node.id === active?.id ? 0 : node.type === 'AccidentCase' || node.type === 'Measure' ? 2 : 1;
      return priority(a) - priority(b);
    });
    ctx.font = `500 ${12 / scale}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (const node of labels) {
      if (node.id !== active?.id && scale < 0.85 && ['AccidentCase', 'Measure'].includes(node.type)) continue;
      const label = short(node.label);
      const halfWidth = ctx.measureText(label).width / 2 + 5 / scale;
      const y = node.y + 8 + 10 / scale;
      const box = { left: node.x - halfWidth, right: node.x + halfWidth, top: y - 9 / scale, bottom: y + 9 / scale };
      if (occupied.some(other => box.left < other.right && box.right > other.left &&
          box.top < other.bottom && box.bottom > other.top)) continue;
      occupied.push(box);
      ctx.fillStyle = background;
      ctx.fillRect(box.left, box.top, halfWidth * 2, box.bottom - box.top);
      ctx.fillStyle = settings.dark ? '#edf5f1' : '#293b49';
      ctx.fillText(label, node.x, y);
    }
  }

  return <div className={`query-graph${fullscreen ? ' query-graph-expanded' : ''}`}>
    <div className="query-graph-toolbar">
      <span>일치 사례 {graph.matched_case_count.toLocaleString('ko-KR')}건 · 노드 {data.nodes.length}개 · 관계 {data.links.length}개</span>
      {data.nodes.length > 0 && <div>
        <button type="button" className="secondary-button" aria-label="그래프 확대" onClick={() => canvas.current?.zoom(canvas.current.zoom() * 1.4, 180)}>+</button>
        <button type="button" className="secondary-button" aria-label="그래프 축소" onClick={() => canvas.current?.zoom(canvas.current.zoom() / 1.4, 180)}>−</button>
        <button type="button" className="secondary-button" onClick={fit}>화면 맞춤</button>
        <button type="button" className="secondary-button" aria-expanded={fullscreen}
          onClick={() => setFullscreen(value => !value)}>{fullscreen ? '전체보기 닫기' : '그래프 전체보기'}</button>
      </div>}
    </div>
    {graph.conditions.length > 0 && <div>조회 조건 · {graph.conditions.join(' · ')}</div>}
    {graph.summary_terms.length > 0 && <div>개요 검색 · {graph.summary_terms.join(' · ')}</div>}
    <div ref={container} className={`query-graph-canvas${data.nodes.length ? ' has-nodes' : ''}`}>
      {ready && data.nodes.length > 0 && <ForceGraph2D ref={canvas} width={size.width} height={size.height}
        graphData={data} backgroundColor={background} nodeVal={node => node.type === 'AccidentCase' ? 1 : 3}
        nodeColor={node => !active || active.id === node.id || activeNodes.has(node.id) ? styles[node.type].color : '#aebbc3'}
        onRenderFramePost={drawLabels}
        onNodeHover={setHover} onNodeClick={node => setPinned(previous => previous?.id === node.id ? null : node)}
        onBackgroundClick={() => setPinned(null)} onLinkHover={setHoverLink}
        linkColor={link => activeLinks.has(link) || link === hoverLink ? '#d2632b' : active ? '#bac7d025' : '#9aafbc65'}
        linkDirectionalArrowLength={link => data.links.length <= 35 || activeLinks.has(link) || link === hoverLink ? 4 : 0}
        linkDirectionalArrowRelPos={0.88}
        minZoom={0.05} maxZoom={8} cooldownTicks={110} onEngineStop={fit}/>}
      {hoverLink && <div className="query-graph-relation">{hoverLink.source.label} → {hoverLink.relation} → {hoverLink.target.label}</div>}
    </div>
    {types.length > 0 && <div className="query-graph-legend">{types.map(type =>
      <span key={type}><i style={{ backgroundColor: styles[type].color }}/>{styles[type].label}</span>)}</div>}
    {active && <NodeDetails node={active} neighbors={neighbors}/>}
  </div>;
}
