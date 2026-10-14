import { useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { menus, nodeTypes, nodeDescriptions } from '../data/mockData';
import Icon from './Icon';
import { useSettings } from '../settings';


// Neo4j 노드의 상세 설명.
function describeNode(node) {
  if (nodeDescriptions[node.id]) return nodeDescriptions[node.id];
  const p = node.props ?? {};
  switch (node.type) {
    case 'equipment':
      return `기인물 · 사고사례 ${p.cases ?? '-'}건${p.examples?.length ? ` · 예: ${p.examples.join(', ')}` : ''}`;
    case 'task':
      return `단위작업 ${p.code ?? ''} ${p.fullName ?? node.label} · 이 기인물 관련 사례 ${p.count ?? '-'}건`;
    case 'accident':
      return `사고유형 · 이 기인물에서 ${p.count ?? '-'}건 발생`;
    case 'prevention':
      return `${p.fullName ?? node.label} (근거 사례 ${p.count ?? '-'}건)`;
    default:
      return node.label;
  }
}

export default function GraphPanel({ graph, selectedMenu, selectedNode, 
  onSelectNode, objects = [], currentObject, onSelectObject, graphError }) {
  const settings = useSettings();
  const canvasColor = settings.dark ? '#182630' : '#f8fafb';
  const textColor = settings.dark ? '#edf5f1' : '#293b49';
  const container = useRef(null);
  const graphRef = useRef(null);
  const fittedFor = useRef(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [filter, setFilter] = useState('all');
  const activeMenu = menus.find((menu) => menu.id === selectedMenu);
  const isMock = graph.source !== 'neo4j';

  // 샘플(노드 4개)은 기존처럼 고정 배치, Neo4j 데이터는 힘 기반 자동 배치

  const graphData = useMemo(() => ({
    nodes: graph.nodes.map((node, index) => (isMock
      ? { ...node, x: index % 2 ? 42 : -42, y: (index - 1.5) * 88, fx: index % 2 ? 42 : -42, fy: (index - 1.5) * 88 }
      : { ...node })),
    links: graph.links.map((link) => ({ ...link })),
  }), [graph, isMock]);

  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);

  const fit = () => graphRef.current?.zoomToFit(350, 60);

  useEffect(() => {
    if (!isMock || !size.width || !size.height) return;
    graphRef.current?.centerAt(0, 12, 0);
    graphRef.current?.zoom(Math.min((size.height - 90) / 340, (size.width - 140) / 200, 1.5), 0);
  }, [size, isMock]);

  useEffect(() => { setFilter('all'); }, [graph]);

  // Neo4j 그래프는 노드가 많아서 서로 더 밀어내고 연결선을 길게 해 안겹치도록 만ㄷ름.
  const hasCanvas = size.width > 0;

  useEffect(() => {
    const fg = graphRef.current;
    if (!fg || isMock) return;
    fg.d3Force('charge')?.strength(-750);
    fg.d3Force('link')?.distance(150);
    fg.d3ReheatSimulation();
  }, [graphData, isMock, hasCanvas]);

  // Neo4j 그래프는 배치가 끝나면 한 번 화면에 맞춤.
  const handleEngineStop = () => {

    if (isMock || fittedFor.current === graph) return;
    fittedFor.current = graph;
    fit();
  };

  function drawNode(node, ctx) {
    const style = nodeTypes[node.type] ?? nodeTypes.equipment;
    const selected = selectedNode?.id === node.id;
    const dimmed = filter !== 'all' && filter !== node.type;
    const radius = isMock ? 25 : 20;
    ctx.globalAlpha = dimmed ? 0.25 : 1;
    ctx.beginPath(); ctx.arc(node.x, node.y, selected ? radius + 4 : radius, 0, Math.PI * 2);
    ctx.fillStyle = style.background; ctx.fill(); ctx.strokeStyle = style.color; ctx.lineWidth = selected ? 3 : 1.5; ctx.stroke();
    ctx.fillStyle = style.color; ctx.font = '600 9px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; if (settings.nodeDisplay === 'both') ctx.fillText(style.label, node.x, node.y);
    ctx.fillStyle = textColor; ctx.font = '600 12px sans-serif'; ctx.fillText(node.label, node.x, node.y + radius + 14); ctx.globalAlpha = 1;
  }

  const caption = isMock ? 'CRANE OPERATIONS' : `${graph.title}`;
  const captionSub = isMock ? '인양 작업의 위험과 예방 관계' : graph.subtitle;
  const legendTypes = Object.entries(nodeTypes).filter(([type]) => graph.nodes.some((node) => node.type === type));

  return <main className="graph-panel">
    <header className="graph-header"><div className="eyebrow">WORKSPACE <span>/</span> {activeMenu.label}</div><div className="heading-row"><div><h1>Knowledge Graph</h1><p>산업재해 관계 탐색</p></div><span className="sample-badge"><span/> {isMock ? '샘플 데이터' : 'Neo4j 실데이터'}</span></div></header>
    <div className="graph-toolbar">
      <div className="graph-count">관계 네트워크 <span>{graph.nodes.length} nodes · {graph.links.length} links</span></div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {objects.length > 0 && <label className="graph-count" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          기인물
          <select value={currentObject} onChange={(event) => onSelectObject(event.target.value)} style={{ fontSize: 11, padding: '4px 6px', border: '1px solid #e3ece6', borderRadius: 4 }}>
            {objects.map((object) => <option key={object.name} value={object.name}>{object.name} ({object.cases})</option>)}
          </select>
        </label>}
        <button className="text-button" onClick={() => { setFilter('all'); onSelectNode(null); fit(); }}><Icon name="fit" size={15}/> 전체 보기</button>
      </div>
    </div>
    {graphError && <div className="graph-count" style={{ padding: '8px 25px', background: '#fcf3e7', color: '#9a6b2f' }}>Neo4j 그래프를 불러오지 못해 샘플 데이터를 표시합니다 · {graphError}</div>}
    <div className="graph-canvas" ref={container}>
      <div className="canvas-caption"><span className="tiny-square"/> {caption}<span>{captionSub}</span></div>
      {size.width > 0 && <ForceGraph2D ref={graphRef} width={size.width} height={size.height} graphData={graphData} backgroundColor={canvasColor} nodeId="id" nodeLabel={(node) => describeNode(node)} nodeCanvasObject={drawNode} nodePointerAreaPaint={(node, color, ctx) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(node.x, node.y, 30, 0, Math.PI * 2); ctx.fill(); }} linkColor={() => '#bac7d0'} linkWidth={(link) => (isMock ? 1.4 : Math.min(1 + (link.count ?? 0) / 40, 5))} linkDirectionalArrowLength={6} linkDirectionalArrowRelPos={0.72} linkCanvasObjectMode={() => 'after'} linkCanvasObject={(link, ctx) => { if (!settings.relations || typeof link.source !== 'object') return; const x = (link.source.x + link.target.x) / 2; const y = (link.source.y + link.target.y) / 2; ctx.font = '10px sans-serif'; ctx.textAlign = 'center'; ctx.fillStyle = canvasColor; ctx.fillRect(x - 44, y - 7, 88, 15); ctx.fillStyle = textColor; ctx.fillText(link.relation, x, y + 4); }} d3VelocityDecay={0.35} cooldownTicks={120} onEngineStop={handleEngineStop} onNodeClick={(node) => onSelectNode(graph.nodes.find((item) => item.id === node.id))} enableNodeDrag={!isMock} minZoom={0.3} maxZoom={3}/>}
      <div className="zoom-controls"><button aria-label="그래프 확대" onClick={() => graphRef.current?.zoom(Math.min(3, graphRef.current.zoom() * 1.25), 200)}><Icon name="plus" size={17}/></button><button aria-label="그래프 축소" onClick={() => graphRef.current?.zoom(Math.max(0.3, graphRef.current.zoom() / 1.25), 200)}><Icon name="minus" size={17}/></button><button aria-label="그래프 화면 맞춤" onClick={fit}><Icon name="fit" size={17}/></button></div>
      <div className="graph-hint">드래그하여 이동 · 스크롤하여 확대</div>
    </div>
    <div className="graph-footer"><div className="legend" aria-label="노드 유형 강조">{legendTypes.map(([type, style]) => <button key={type} aria-pressed={filter === type} onClick={() => setFilter(filter === type ? 'all' : type)} className={filter === type ? 'selected' : ''}><span style={{ background: style.color }}/>{style.label}</button>)}</div><div className="node-list" aria-label="노드 선택">{graph.nodes.map((node) => <button key={node.id} aria-pressed={selectedNode?.id === node.id} onClick={() => onSelectNode(node)}>{node.label}</button>)}</div><div className="node-detail"><span className="detail-icon"><Icon name={selectedNode ? 'graph' : 'shield'}/></span><div><strong>{selectedNode ? (selectedNode.props?.fullName ?? selectedNode.label) : selectedMenu === 'explore' ? '연결된 관계를 탐색해 보세요' : `${activeMenu.label} · 미리보기`}</strong><p>{selectedNode ? describeNode(selectedNode) : selectedMenu === 'explore' ? '노드를 선택하면 상세정보를 확인할 수 있습니다.' : '이 메뉴의 전용 기능은 준비 중입니다. 현재는 공통 그래프를 표시합니다.'}</p></div>{selectedNode && <button className="close-button" aria-label="노드 선택 해제" onClick={() => onSelectNode(null)}>×</button>}</div></div>
  </main>;
}
