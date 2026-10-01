import { menus } from '../data/mockData';
import Icon from './Icon';
export default function Sidebar({ selectedMenu, onSelectMenu }) {
  return <aside className="sidebar">
    <div className="brand"><span className="brand-mark"><Icon name="graph" size={24}/></span><div>Safety Agent<small>산업안전 지식 플랫폼</small></div></div>
    <div className="workspace-label">WORKSPACE</div>
    <nav aria-label="주 메뉴">{menus.map((menu) => <button key={menu.id} className={`menu-item ${selectedMenu === menu.id ? 'active' : ''}`} aria-current={selectedMenu === menu.id ? 'page' : undefined} onClick={() => onSelectMenu(menu.id)}><Icon name={menu.icon}/><span>{menu.label}</span>{selectedMenu === menu.id && <span className="active-dot"/>}</button>)}</nav>
    <div className="sidebar-bottom"><div className="prototype-label"><span/> UI PROTOTYPE</div><p>관계에서 발견하는<br/>더 안전한 작업 환경</p><div className="workspace-user"><span className="user-avatar">S</span><div>Capstone Project<small>Safety research workspace</small></div></div></div>
  </aside>;
}
