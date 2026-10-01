import { useState } from 'react';
import Sidebar from './components/Sidebar';
import GraphPanel from './components/GraphPanel';
import ChatPanel from './components/ChatPanel';
import { mockGraph } from './data/mockData';
import './App.css';
export default function App() {
  const [selectedMenu, setSelectedMenu] = useState('explore');
  const [selectedNode, setSelectedNode] = useState(null);
  return <div className="app"><Sidebar selectedMenu={selectedMenu} onSelectMenu={setSelectedMenu}/><GraphPanel graph={mockGraph} selectedMenu={selectedMenu} selectedNode={selectedNode} onSelectNode={setSelectedNode}/><ChatPanel selectedNode={selectedNode}/></div>;
}
