import { useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { menus, nodeTypes, nodeDescriptions } from '../data/mockData';
import Icon from './Icon';
export default function GraphPanel({ graph, selectedMenu, selectedNode, onSelectNode }) {
  const container = useRef(null);
  const graphRef = useRef(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [filter, setFilter] = useState('all');
  const activeMenu = menus.find((menu) => menu.id === selectedMenu);
  // The canvas library mutates nodes/links; keep the API-shaped source data untouched.
  const graphData = useMemo(() => ({ nodes: graph.nodes.map((node, index) => ({ ...node, x: index % 2 ? 42 : -42, y: (index - 1.5) * 88, fx: index % 2 ? 42 : -42, fy: (index - 1.5) * 88 })), links: graph.links.map((link) => ({ ...link })) }), [graph]);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const fit = () => graphRef.current?.zoomToFit(350, 80);
  useEffect(() => { if (size.width && size.height) { graphRef.current?.centerAt(0, 12, 0); graphRef.current?.zoom(Math.min((size.height - 90) / 340, (size.width - 140) / 200, 1.5), 0); } }, [size]);
  function drawNode(node, ctx) {
    const style = nodeTypes[node.type];
    const selected = selectedNode?.id === node.id;
    const dimmed = filter !== 'all' && filter !== node.type;
    ctx.globalAlpha = dimmed ? 0.25 : 1;
    ctx.beginPath(); ctx.arc(node.x, node.y, selected ? 29 : 25, 0, Math.PI * 2);
    ctx.fillStyle = style.background; ctx.fill(); ctx.strokeStyle = style.color; ctx.lineWidth = selected ? 3 : 1.5; ctx.stroke();
    ctx.fillStyle = style.color; ctx.font = '600 10px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(style.label, node.x, node.y);
    ctx.fillStyle = '#293b49'; ctx.font = '600 13px sans-serif'; ctx.fillText(node.label, node.x, node.y + 42); ctx.globalAlpha = 1;
  }
  return <main className="graph-panel">
    <header className="graph-header"><div className="eyebrow">WORKSPACE <span>/</span> {activeMenu.label}</div><div className="heading-row"><div><h1>Knowledge Graph</h1><p>산업재해 관계 탐색</p></div><span className="sample-badge"><span/> 샘플 데이터</span></div></header>
    <div className="graph-toolbar"><div className="graph-count">관계 네트워크 <span>{graph.nodes.length} nodes · {graph.links.length} links</span></div><button className="text-button" onClick={() => { setFilter('all'); onSelectNode(null); fit(); }}><Icon name="fit" size={15}/> 전체 보기</button></div>
    <div className="graph-canvas" ref={container}>
      <div className="canvas-caption"><span className="tiny-square"/> CRANE OPERATIONS<span>인양 작업의 위험과 예방 관계</span></div>
      {size.width > 0 && <ForceGraph2D ref={graphRef} width={size.width} height={size.height} graphData={graphData} backgroundColor="#f8fafb" nodeId="id" nodeLabel="label" nodeCanvasObject={drawNode} nodePointerAreaPaint={(node, color, ctx) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(node.x, node.y, 30, 0, Math.PI * 2); ctx.fill(); }} linkColor={() => '#bac7d0'} linkWidth={1.4} linkDirectionalArrowLength={6} linkDirectionalArrowRelPos={0.72} linkCanvasObjectMode={() => 'after'} linkCanvasObject={(link, ctx) => { if (typeof link.source !== 'object') return; const x = (link.source.x + link.target.x) / 2; const y = (link.source.y + link.target.y) / 2; ctx.font = '10px sans-serif'; ctx.textAlign = 'center'; ctx.fillStyle = '#f8fafb'; ctx.fillRect(x - 40, y - 7, 80, 15); ctx.fillStyle = '#7c8d9b'; ctx.fillText(link.relation, x, y + 4); }} onNodeClick={(node) => onSelectNode(graph.nodes.find((item) => item.id === node.id))} enableNodeDrag={false} minZoom={0.3} maxZoom={3}/ >}
      <div className="zoom-controls"><button aria-label="그래프 확대" onClick={() => graphRef.current?.zoom(Math.min(3, graphRef.current.zoom() * 1.25), 200)}><Icon name="plus" size={17}/></button><button aria-label="그래프 축소" onClick={() => graphRef.current?.zoom(Math.max(0.3, graphRef.current.zoom() / 1.25), 200)}><Icon name="minus" size={17}/></button><button aria-label="그래프 화면 맞춤" onClick={fit}><Icon name="fit" size={17}/></button></div>
      <div className="graph-hint">드래그하여 이동 · 스크롤하여 확대</div>
    </div>
    <div className="graph-footer"><div className="legend" aria-label="노드 유형 강조">{Object.entries(nodeTypes).map(([type, style]) => <button key={type} aria-pressed={filter === type} onClick={() => setFilter(filter === type ? 'all' : type)} className={filter === type ? 'selected' : ''}><span style={{ background: style.color }}/>{style.label}</button>)}</div><div className="node-list" aria-label="노드 선택">{graph.nodes.map((node) => <button key={node.id} aria-pressed={selectedNode?.id === node.id} onClick={() => onSelectNode(node)}>{node.label}</button>)}</div><div className="node-detail"><span className="detail-icon"><Icon name={selectedNode ? 'graph' : 'shield'}/></span><div><strong>{selectedNode ? selectedNode.label : selectedMenu === 'explore' ? '연결된 관계를 탐색해 보세요' : `${activeMenu.label} · 미리보기`}</strong><p>{selectedNode ? nodeDescriptions[selectedNode.id] : selectedMenu === 'explore' ? '노드를 선택하면 상세정보를 확인할 수 있습니다.' : '이 메뉴의 전용 기능은 준비 중입니다. 현재는 공통 샘플 그래프를 표시합니다.'}</p></div>{selectedNode && <button className="close-button" aria-label="노드 선택 해제" onClick={() => onSelectNode(null)}>×</button>}</div></div>
  </main>;
}
