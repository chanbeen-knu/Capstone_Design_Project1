import { useEffect, useMemo, useState } from 'react';
import { filterCases, loadCases } from '../data/caseRepository';
import { fetchPattern, fetchPatterns } from '../api/graph';
import { nodeTypes } from '../data/mockData';
import { useSettings } from '../settings';

const emptyFilters = { query: '', group: '', category: '', task: '' };
const noRecords = [];
const PAGE = 15; // 한 줄에 3개 × 5줄
const options = (records, key) => [...new Set(records.map(r => r[key]).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ko'));
const SECTOR = { '제조업 등': 'M', '건설업': 'C' };
const LEVEL_ORDER = ['제거·대체', '공학적 대책', '관리적 대책', '개인보호구'];
const PART_TYPE = { 기인물: 'equipment', 재해종류: 'accident', 유발요인: 'risk' };
const levelRank = (levels) => Math.min(9, ...levels.map(l => (LEVEL_ORDER.indexOf(l) + 10) % 10));

function PartChips({ parts }) {
  return <div className="pattern-parts">{['기인물', '재해종류', '유발요인'].map(role => parts.find(p => p.role === role)).filter(Boolean).map(p => {
    const style = nodeTypes[PART_TYPE[p.role]];
    return <span key={p.role} style={{ color: style.color, background: style.background, borderColor: style.color }}>{p.name}</span>;
  })}</div>;
}

// 사고 패턴: 같은 기인물·재해종류·유발요인으로 일어난 사고 묶음과 대표 사례 (현장 작업자·교육 담당자용)
function PatternsView({ group, onOpenRecord }) {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [detail, setDetail] = useState(null);
  const [limit, setLimit] = useState(30);
  useEffect(() => {
    const timer = setTimeout(() => {
      setError('');
      fetchPatterns({ q: query, sector: SECTOR[group] ?? '', limit }).then(setResult).catch(e => { setResult(null); setError(e.message); });
    }, 250);
    return () => clearTimeout(timer);
  }, [query, group, limit]);
  function open(id) { setError(''); fetchPattern(id).then(setDetail).catch(e => setError(e.message)); }

  if (detail) {
    const total = detail.controlLevels.reduce((s, x) => s + x.n, 0) || 1;
    return <article className="case-detail pattern-detail">
      <button className="secondary-button" onClick={() => setDetail(null)}>← 패턴 목록으로</button>
      <div className="case-meta">사고 패턴 · 사례 {detail.pattern.size.toLocaleString()}건{detail.pattern.topWorks.length ? ` · 주요 작업: ${detail.pattern.topWorks.join(', ')}` : ''}</div>
      <h2>{detail.pattern.name}</h2>
      <PartChips parts={detail.parts}/>
      <div className="level-bars" aria-label="이 패턴 대책의 통제위계">
        {[...detail.controlLevels].sort((a, b) => LEVEL_ORDER.indexOf(a.k) - LEVEL_ORDER.indexOf(b.k)).map(x => <div key={x.k}><span>{x.k}</span><i style={{ width: `${(x.n / total) * 100}%` }}/><b>{x.n}</b></div>)}
      </div>
      {detail.representatives.map((r, i) => <section key={r.case.id} className="rep-case">
        <div className="case-meta"><span>대표 사례 {i + 1}</span><span>{r.case.sector}</span><span>{r.case.code}</span>{r.case.year && <span>{r.case.year}년</span>}</div>
        <p className="rep-summary">{r.case.summary}</p>
        <h3>원인</h3>
        <p>{r.hazards.join(', ')}{r.case.raw_hf ? ` — ${r.case.raw_hf}` : ''}</p>
        <h3>예방대책</h3>
        <ul>{[...r.measures].sort((a, b) => levelRank(a.levels) - levelRank(b.levels)).map((m, k) => <li key={k}>{m.text}{m.levels.length > 0 && <small>{m.levels.join(' · ')}</small>}</li>)}</ul>
        {r.case.legacyId && <button className="text-button" onClick={() => onOpenRecord(r.case.legacyId)}>원문 전체 보기 ↗</button>}
      </section>)}
    </article>;
  }
  return <>
    <div className="pattern-search"><input placeholder="패턴 찾기: 포크레인, 사다리, 추락, 안전대…" value={query} onChange={e => { setQuery(e.target.value); setLimit(30); }}/>
      <span>{result ? `패턴 ${result.total.toLocaleString()}개` : ''}</span></div>
    {error ? <div className="empty-state" role="alert"><h2>사고 패턴을 불러오지 못했습니다.</h2><p>사고 패턴은 백엔드와 Neo4j 연결이 필요합니다 · {error}</p></div>
      : !result ? <div className="empty-state" role="status">사고 패턴을 불러오고 있습니다.</div>
        : result.items.length === 0 ? <div className="empty-state"><h2>맞는 패턴이 없습니다.</h2><p>다른 말로 찾아보세요.</p></div>
          : <div className="case-grid">{result.items.map(({ pattern, reps, parts }) => <button className="case-card pattern-card" key={pattern.id} onClick={() => open(pattern.id)}>
            <PartChips parts={parts}/>
            <div className="case-meta"><span>사례 {pattern.size.toLocaleString()}건</span><span>{pattern.sectors.map(s => (s === 'C' ? '건설' : '제조')).join('·')}</span>{pattern.topWorks[0] && <span>주로 {pattern.topWorks[0]}</span>}</div>
            {reps[0] && <p><b>{reps[0].code}</b> {reps[0].summary}</p>}
            <span className="case-link">대표 사례 · 원인 · 대책 보기 ↗</span>
          </button>)}</div>}
    {result && result.items.length < result.total && <div className="pagination"><button onClick={() => setLimit(limit + 30)}>패턴 더 보기</button></div>}
  </>;
}

export default function CasesPanel() {
  const settings = useSettings();
  const [archive, setArchive] = useState(null);
  const [error, setError] = useState('');
  const [filters, setFilters] = useState(emptyFilters);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(null);
  const [mode, setMode] = useState('list'); // list: 사례 목록 · patterns: 사고 패턴
  function load() { setError(''); loadCases().then(setArchive).catch(e => setError(e.message)); }
  useEffect(() => { load(); }, []);
  const records = archive?.records || noRecords;
  const filtered = useMemo(() => filterCases(records, filters), [records, filters]);
  const scoped = records.filter(r => !filters.group || r.group === filters.group);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE));
  function change(key, value) { setFilters(previous => ({ ...previous, [key]: value, ...(key === 'group' ? { category: '', task: '' } : {}) })); setPage(1); setSelected(null); }
  function openRecord(id) { const record = records.find(r => r.id === id); if (record) { setMode('list'); setSelected(record); } }
  return <main className="cases-panel">
    <header className="graph-header"><div className="eyebrow">ACCIDENT ARCHIVE</div><div className="heading-row"><div><h1>사고 사례 조회</h1><p>건설업 사고 사례를 검색하고 원인과 예방대책을 확인하세요.</p></div><span className="sample-badge">원본 기반</span></div></header>
    <div className="case-tabs" role="tablist">
      <button role="tab" aria-selected={mode === 'list'} className={mode === 'list' ? 'active' : ''} onClick={() => setMode('list')}>사례 목록</button>
      <button role="tab" aria-selected={mode === 'patterns'} className={mode === 'patterns' ? 'active' : ''} onClick={() => { setMode('patterns'); setSelected(null); }}>사고 패턴 <small>비슷한 사고 묶음</small></button>
    </div>
    {error ? <div className="empty-state" role="alert">{error}<button onClick={load}>다시 시도</button></div> : !archive ? <div className="empty-state" role="status">사고 사례를 불러오고 있습니다.</div> : <>
      <div className="case-filters">{mode === 'list' && <label>키워드 검색<input placeholder="예: 굴착기, 리프트, 개구부" value={filters.query} onChange={e => change('query', e.target.value)}/></label>}<div className="filter-row">
        {options(records, 'group').length > 1 && <label>자료 구분<select value={filters.group} onChange={e => change('group', e.target.value)}><option value="">전체 자료</option>{options(records, 'group').map(v => <option key={v}>{v}</option>)}</select></label>}
        {mode === 'list' && <>
          <label>공종<select value={filters.category} onChange={e => change('category', e.target.value)}><option value="">전체 분류</option>{options(scoped, 'category').map(v => <option key={v}>{v}</option>)}</select></label>
          <label>작업 / 상황<select value={filters.task} onChange={e => change('task', e.target.value)}><option value="">전체 작업</option>{options(scoped, 'task').map(v => <option key={v}>{v}</option>)}</select></label>
          <button className="secondary-button" onClick={() => { setFilters(emptyFilters); setPage(1); setSelected(null); }}>초기화</button>
        </>}
      </div></div>
      {mode === 'patterns' ? <div className="case-scroll"><PatternsView group={filters.group} onOpenRecord={openRecord}/></div> : <>
        <div className="results-bar"><strong>{filtered.length.toLocaleString()}건</strong><span>전체 {records.length.toLocaleString()}건 · 엑셀 원본 조회</span></div>
        <div className="case-scroll">{selected ? <article className="case-detail"><button className="secondary-button" onClick={() => setSelected(null)}>← 목록으로</button><div className="case-meta">{selected.group} · 사례 {selected.fields['연번']}</div><h2>사고 사례 상세</h2><dl>{Object.entries(selected.fields).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? '정보 없음'}</dd></div>)}</dl>{settings.sources && <div className="source-note"><strong>원본 출처</strong><p>{archive.sourceFile}</p><p>{selected.sourceSheet} · {selected.sourceRow}행 · {selected.id}</p></div>}</article> : <>
          {filtered.length === 0 ? <div className="empty-state"><h2>검색 결과가 없습니다.</h2><p>검색어나 필터를 변경해 보세요.</p></div> : <div className="case-grid">{filtered.slice((page - 1) * PAGE, page * PAGE).map(record => <button className="case-card" key={record.id} onClick={() => setSelected(record)}><div className="case-meta"><span>{record.group}</span><span>{record.category || '정보 없음'}</span><span>#{record.fields['연번']}</span></div><h2>{record.task || '작업 정보 없음'}</h2><p>{record.summary || '재해개요 정보 없음'}</p><span className="case-link">원문 및 감소대책 확인 ↗</span></button>)}</div>}
        </>}</div>
        {!selected && <div className="pagination"><button disabled={page === 1} onClick={() => setPage(page - 1)}>이전</button><span>{page} / {pages}</span><button disabled={page >= pages} onClick={() => setPage(page + 1)}>다음</button></div>}
      </>}
    </>}
  </main>;
}
