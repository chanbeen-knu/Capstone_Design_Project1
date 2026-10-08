import { useEffect, useState } from 'react';
import Sidebar from './components/Sidebar';
import GraphPanel from './components/GraphPanel';
import ChatPanel from './components/ChatPanel';
import { mockGraph } from './data/mockData';
import { fetchObjectGraph, fetchObjects } from './api/graph';
import './App.css';

const DEFAULT_OBJECT = '비계';

export default function App() {
  const [selectedMenu, setSelectedMenu] = useState('explore');
  const [selectedNode, setSelectedNode] = useState(null);
  const [graph, setGraph] = useState(mockGraph);
  const [objects, setObjects] = useState([]);
  const [currentObject, setCurrentObject] = useState(DEFAULT_OBJECT);
  const [graphError, setGraphError] = useState(null);

  // 기인물 목록 (툴바 선택 상자용.)
  useEffect(() => {
    fetchObjects().then(setObjects).catch(() => setObjects([]));
  }, []);

  // 선택한 기인물의 그래프를 Neo4j에서 불러오고, 실패하면 샘플 데이터로 대체하게 만듦...
  useEffect(() => {
    let cancelled = false;
    setSelectedNode(null);
    fetchObjectGraph(currentObject)
      .then((data) => {
        if (cancelled) return;
        setGraph(data);
        setGraphError(null);
      })
      .catch((error) => {
        if (cancelled) return;
        setGraph(mockGraph);
        setGraphError(error.message);
      });
    return () => { cancelled = true; };
  }, [currentObject]);

  return <div className="app">
    <Sidebar selectedMenu={selectedMenu} onSelectMenu={setSelectedMenu}/>
    <GraphPanel
      graph={graph}
      selectedMenu={selectedMenu}
      selectedNode={selectedNode}
      onSelectNode={setSelectedNode}
      objects={objects}
      currentObject={currentObject}
      onSelectObject={setCurrentObject}
      graphError={graphError}
    />
    <ChatPanel selectedNode={selectedNode}/>
  </div>;
}
