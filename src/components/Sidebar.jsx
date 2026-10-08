import { menus } from '../data/mockData';
import Icon from './Icon';
export default function Sidebar({ selectedMenu, onSelectMenu }) {
  return <aside className="sidebar">
    <div className="brand"><span className="brand-mark"><Icon name="graph" size={24}/></span><div>SafeGori<small>산업 안전 지식 탐색 서비스</small></div></div>
    <div className="workspace-label">WORKSPACE</div>
    <nav aria-label="주 메뉴">{menus.map((menu) => <button key={menu.id} className={`menu-item ${selectedMenu === menu.id ? 'active' : ''}`} aria-current={selectedMenu === menu.id ? 'page' : undefined} onClick={() => onSelectMenu(menu.id)}><Icon name={menu.icon}/><span>{menu.label}</span>{selectedMenu === menu.id && <span className="active-dot"/>}</button>)}</nav>
    <div className="sidebar-bottom"><div className="workspace-user"><span className="user-avatar">S</span><div>안전고리<small className="platform-name">SafeGori Platform</small><small>사고와 예방을 잇는 연결</small></div></div></div>
  </aside>;
}
