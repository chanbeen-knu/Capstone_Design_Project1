import { useEffect, useMemo, useState } from 'react';
import { filterCases, loadCases } from '../data/caseRepository';
import { useSettings } from '../settings';
const emptyFilters = { query: '', group: '', category: '', task: '' };
const noRecords = [];
const options = (records, key) => [...new Set(records.map(r => r[key]).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ko'));
export default function CasesPanel() {
  const settings = useSettings();
  const [archive, setArchive] = useState(null);
  const [error, setError] = useState('');
  const [filters, setFilters] = useState(emptyFilters);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(null);
  function load() { setError(''); loadCases().then(setArchive).catch(e => setError(e.message)); }
  useEffect(() => { load(); }, []);
  const records = archive?.records || noRecords;
  const filtered = useMemo(() => filterCases(records, filters), [records, filters]);
  const scoped = records.filter(r => !filters.group || r.group === filters.group);
  const pages = Math.max(1, Math.ceil(filtered.length / 15));
  function change(key, value) { setFilters(previous => ({ ...previous, [key]: value, ...(key === 'group' ? { category: '', task: '' } : {}) })); setPage(1); setSelected(null); }
  return <main className="cases-panel">
    <header className="graph-header"><div className="eyebrow">ACCIDENT ARCHIVE</div><div className="heading-row"><div><h1>사고 사례 조회</h1><p>사고 사례를 검색하고 원인과 예방대책을 확인하세요.</p></div><span className="sample-badge">원본 기반</span></div></header>
    {error ? <div className="empty-state" role="alert">{error}<button onClick={load}>다시 시도</button></div> : !archive ? <div className="empty-state" role="status">사고 사례를 불러오고 있습니다.</div> : <>
      <div className="case-filters"><label>키워드 검색<input placeholder="예: 굴착기, 리프트, 개구부" value={filters.query} onChange={e => change('query', e.target.value)}/></label><div className="filter-row">
        <label>자료 구분<select value={filters.group} onChange={e => change('group', e.target.value)}><option value="">전체 자료</option>{options(records, 'group').map(v => <option key={v}>{v}</option>)}</select></label>
        <label>업종 / 공종<select value={filters.category} onChange={e => change('category', e.target.value)}><option value="">전체 분류</option>{options(scoped, 'category').map(v => <option key={v}>{v}</option>)}</select></label>
        <label>작업 / 상황<select value={filters.task} onChange={e => change('task', e.target.value)}><option value="">전체 작업</option>{options(scoped, 'task').map(v => <option key={v}>{v}</option>)}</select></label>
        <button className="secondary-button" onClick={() => { setFilters(emptyFilters); setPage(1); setSelected(null); }}>초기화</button>
      </div></div>
      <div className="results-bar"><strong>{filtered.length.toLocaleString()}건</strong><span>전체 {records.length.toLocaleString()}건 · 엑셀 원본 조회</span></div>
      <div className="case-scroll">{selected ? <article className="case-detail"><button className="secondary-button" onClick={() => setSelected(null)}>← 목록으로</button><div className="case-meta">{selected.group} · 사례 {selected.fields['연번']}</div><h2>사고 사례 상세</h2><dl>{Object.entries(selected.fields).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? '정보 없음'}</dd></div>)}</dl>{settings.sources && <div className="source-note"><strong>원본 출처</strong><p>{archive.sourceFile}</p><p>{selected.sourceSheet} · {selected.sourceRow}행 · {selected.id}</p></div>}</article> : <>
        {filtered.length === 0 ? <div className="empty-state"><h2>검색 결과가 없습니다.</h2><p>검색어나 필터를 변경해 보세요.</p></div> : filtered.slice((page - 1) * 15, page * 15).map(record => <button className="case-card" key={record.id} onClick={() => setSelected(record)}><div className="case-meta"><span>{record.group}</span><span>{record.category || '정보 없음'}</span><span>#{record.fields['연번']}</span></div><h2>{record.task || '작업 정보 없음'}</h2><p>{record.summary || '재해개요 정보 없음'}</p><span className="case-link">원문 및 감소대책 확인 ↗</span></button>)}
      </>}</div>
      {!selected && <div className="pagination"><button disabled={page === 1} onClick={() => setPage(page - 1)}>이전</button><span>{page} / {pages}</span><button disabled={page >= pages} onClick={() => setPage(page + 1)}>다음</button></div>}
    </>}
  </main>;
}
