import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import Icon from './Icon';
import './answerCards.css';

// Preserve explicit numbering and keep wrapped lines with their item.
export function AnswerText({ text }) {
  const blocks = [];
  for (const paragraph of (text || '').trim().split(/\n\s*\n/)) {
    let block;
    for (const line of paragraph.split('\n')) {
      if (!line.trim()) continue;
      const marker = line.trim().match(/^(?:([-*•])|(\d+)[.)])\s+(.+)$/);
      if (!marker && block) {
        block.items.at(-1).text += '\n' + line.trim();
        continue;
      }
      const type = marker ? (marker[1] ? 'ul' : 'ol') : 'p';
      if (!block || block.type !== type) {
        block = { type, items: [] };
        blocks.push(block);
      }
      block.items.push({ text: marker ? marker[3] : line.trim(), number: marker?.[2] });
    }
  }
  // After the lead, render adjacent prose paragraphs as a list of points.
  return blocks.map(({ type: Tag, items }, index) => {
    if (Tag === 'p') {
      if (!index) return <p key={index}>{items[0].text}</p>;
      if (index > 1 && blocks[index - 1].type === 'p') return null;
      const points = [];
      for (let i = index; blocks[i]?.type === 'p'; i++) {
        points.push(<li key={i}>{blocks[i].items[0].text}</li>);
      }
      return <ul key={index}>{points}</ul>;
    }
    return <Tag key={index}>{items.map((item, i) => <li key={i} value={item.number}>{item.text}</li>)}</Tag>;
  });
}

const countText = value => value.toLocaleString('ko-KR');
const validCount = value => Number.isFinite(value) && value >= 0;
const casePageSize = 5;

function casePresentation(record) {
  const work = (record.work || record.task || '').replace(/^\d+(?:\.\d+)*\.?\s+/, '').trim();
  const object = record.object?.trim();
  const accident = (record.classified_accident || record.accident)?.trim();
  const accidentTitle = accident?.endsWith('사고') ? accident : [accident, '사고'].filter(Boolean).join(' ');
  const title = record.title?.trim() || [work && `${work} 중`, object, accidentTitle].filter(Boolean).join(' ');
  const year = record.year || /^\s*(20\d{2})\s*(?:년|월|\.)/.exec(record.summary || '')?.[1];
  const date = year ? `${year}년${record.month ? ` ${record.month}월` : ''}` : '';
  return { title, year, date, accident };
}

export function CaseCards({ cases, total, query }) {
  const [page, setPage] = useState(0);
  const [pages, setPages] = useState({});
  const [selected, setSelected] = useState(null);
  const dialog = useRef(null);
  const trigger = useRef(null);
  const titleId = useId();
  const detail = selected && casePresentation(selected);
  const totalCount = query && validCount(total) ? total : cases.length;
  const pageCount = Math.ceil(totalCount / casePageSize);
  const offset = page * casePageSize;
  const result = pages[page];
  const needsPage = Boolean(query && !result && (page > 0 || cases.length < Math.min(totalCount, casePageSize)));
  const items = result?.items ?? cases.slice(offset, offset + casePageSize);

  useEffect(() => {
    if (!needsPage) return;
    const controller = new AbortController();
    const { conditions, summary_terms } = query;
    async function loadPage() {
      try {
        const response = await fetch('/api/chat/cases', {
          method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ conditions, summary_terms, offset }),
        });
        if (!response.ok) throw new Error('사례 조회 실패');
        const data = await response.json();
        if (!Array.isArray(data.items)) throw new Error('사례 데이터 형식 오류');
        if (!controller.signal.aborted) setPages(previous => ({ ...previous, [page]: { items: data.items } }));
      } catch {
        if (!controller.signal.aborted) setPages(previous => ({ ...previous, [page]: { error: true } }));
      }
    }
    loadPage();
    return () => controller.abort();
  }, [needsPage, offset, page, query]);

  function retryPage() {
    setPages(previous => {
      const next = { ...previous };
      delete next[page];
      return next;
    });
  }

  useLayoutEffect(() => {
    if (selected && dialog.current && !dialog.current.open) dialog.current.showModal();
  }, [selected]);

  function openCase(event, record) {
    trigger.current = event.currentTarget;
    setSelected(record);
  }

  function closeCase() {
    setSelected(null);
    trigger.current?.focus({ preventScroll: true });
    trigger.current = null;
  }

  return <section className="answer-card answer-cases">
    <header className="answer-case-header">
      <h3>사고 사례 <span>(총 {countText(totalCount)}건)</span></h3>
      {pageCount > 1 && <nav className="answer-case-pages" aria-label="사고 사례 페이지">
        <button className="secondary-button" type="button" aria-label="이전 사례 페이지" disabled={page === 0}
          onClick={() => setPage(page - 1)}><Icon name="chevronLeft" size={16}/></button>
        <span role="status">{page + 1} / {pageCount}</span>
        <button className="secondary-button" type="button" aria-label="다음 사례 페이지" disabled={page === pageCount - 1}
          onClick={() => setPage(page + 1)}><Icon name="chevronRight" size={16}/></button>
      </nav>}
    </header>
    <div className="answer-case-window" aria-busy={needsPage}>
      {items.length > 0 && <div className="answer-case-grid" key={page}>{items.map(record => {
        const { title, year } = casePresentation(record);
        return <button className="answer-case-button" type="button" key={record.id || record.code} aria-haspopup="dialog"
          onClick={event => openCase(event, record)}>
          {year && <span className="answer-case-year">{year}년</span>}
          <span className="answer-case-title">{title}</span>
        </button>;
      })}</div>}
      {needsPage && !items.length && <p role="status">사고 사례를 불러오는 중…</p>}
      {result?.error && <div className="answer-case-error">
        <p role="status">사고 사례를 불러오지 못했어요.</p>
        <button className="secondary-button" type="button" onClick={retryPage}>다시 시도</button>
      </div>}
      {result?.items?.length === 0 && <p role="status">이 페이지에 표시할 사고 사례가 없어요.</p>}
    </div>
    {createPortal(<dialog className="answer-case-dialog" ref={dialog} aria-labelledby={titleId}
      onClose={closeCase} onClick={event => { if (event.target === event.currentTarget) event.currentTarget.close(); }}>
      <div className="answer-case-detail">
        <header>
          <h2 id={titleId}>{detail?.title}</h2>
          <form method="dialog"><button className="secondary-button" type="submit">닫기</button></form>
        </header>
        {selected && <>
          <dl>
            <div><dt>사고사례 번호</dt><dd>{selected.code || selected.id}</dd></div>
            {detail.date && <div><dt>사고 시기</dt><dd>{detail.date}</dd></div>}
            {detail.accident && <div><dt>재해종류</dt><dd>{detail.accident}</dd></div>}
          </dl>
          <h3>사고 개요</h3><p>{selected.summary || '등록된 사고 개요가 없습니다.'}</p>
          {selected.hazard && <><h3>재해유발요인</h3><p>{selected.hazard}</p></>}
          {selected.measures && <><h3>사고 예방 대책</h3><p>{selected.measures}</p></>}
          {selected.pattern && <><h3>같은 유형</h3><p>{selected.pattern}</p></>}
        </>}
      </div>
    </dialog>, document.body)}
  </section>;
}

const pieColors = ['#9abfea', '#f4d295', '#9fd8be', '#c8afe7', '#efabbc', '#9bd8e1', '#f3ba9d', '#c2c8e6'];
const otherColor = '#d5dce4';
const piePercent = new Intl.NumberFormat('ko-KR', { style: 'percent', maximumFractionDigits: 1 });
const pieRadius = 50;
const pieLabelSize = 4.6;

function piePoint(turn, radius = pieRadius) {
  const angle = 2 * Math.PI * turn;
  return [pieRadius + radius * Math.sin(angle), pieRadius - radius * Math.cos(angle)];
}

function pieLabelBox(label, start, end) {
  if (typeof label !== 'string' || !label.trim()) return null;
  const share = end - start;
  const distance = share === 1 ? 0 : 30;
  const width = Array.from(label).length * pieLabelSize + 4;
  const height = pieLabelSize + 3;
  // Check the whole box against the sector edges and the rim.
  const radius = Math.hypot(width / 2, height / 2);
  const edge = distance === 0 ? pieRadius : distance * Math.sin(Math.min(Math.PI / 2, Math.PI * share));
  if (radius > Math.min(edge, pieRadius - distance - 1)) return null;
  const [x, y] = piePoint((start + end) / 2, distance);
  return { x, y, width, height };
}

function PieChart({ slices, total, title }) {
  const layout = useRef(null);
  const [hover, setHover] = useState(null);
  const hovered = hover && slices[hover.index];
  let end = 0;

  function showHover(event, index) {
    const { left, top } = layout.current.getBoundingClientRect();
    setHover({ index, x: event.clientX - left, y: event.clientY - top });
  }

  return <div className="answer-pie-layout" ref={layout}>
    <svg className="answer-pie" viewBox="0 0 100 100" aria-hidden="true">
      {slices.map(({ color, count, label }, index) => {
        const props = {
          fill: color,
          'data-active': index === hover?.index,
          onPointerEnter: event => showHover(event, index),
          onPointerMove: event => showHover(event, index),
          onPointerLeave: () => setHover(null),
        };
        const start = end;
        const share = count / total;
        end = index === slices.length - 1 ? 1 : start + share;
        const box = pieLabelBox(label, start, end);
        const arc = `M 50 50 L ${piePoint(start).join(' ')} A 50 50 0 ${share > .5 ? 1 : 0} 1 ${piePoint(end).join(' ')} Z`;
        return <g key={color}>
          {slices.length === 1
            ? <circle cx={pieRadius} cy={pieRadius} r={pieRadius} {...props}/>
            : <path d={arc} {...props}/>}
          {box && <g className="answer-pie-label">
            <rect x={box.x - box.width / 2} y={box.y - box.height / 2} width={box.width} height={box.height} rx={1.2}/>
            <text x={box.x} y={box.y} fontSize={pieLabelSize} textAnchor="middle" dominantBaseline="central">{label}</text>
          </g>}
        </g>;
      })}
    </svg>
    <ul className="answer-pie-legend" aria-label={title}>{slices.map(({ label: name, count, color }) => {
      const share = count / total;
      return <li key={color}>
        <span className="answer-pie-swatch" style={{ backgroundColor: color }} aria-hidden="true"/>
        <span>{name}</span>
        <span className="answer-pie-value">{countText(count)}건</span>
        <small className="answer-pie-value">{share < .001 ? '<0.1%' : piePercent.format(share)}</small>
      </li>;
    })}</ul>
    {hovered && <div className="answer-pie-tooltip" aria-hidden="true" data-below={hover.y < 64}
      style={{ '--tooltip-x': `${hover.x}px`, '--tooltip-y': `${hover.y}px` }}>
      <span className="answer-pie-swatch" style={{ backgroundColor: hovered.color }}/>
      <span>{hovered.label}{' '}<span className="answer-pie-value">{countText(hovered.count)}건</span></span>
    </div>}
  </div>;
}

function Breakdown({ rows, label, title, showTable, total, groupedTotal }) {
  if (!rows?.length) return null;
  const ranked = rows.filter(row => validCount(row.count) && row.count > 0).sort((a, b) => b.count - a.count);
  const listedTotal = ranked.reduce((sum, row) => sum + row.count, 0);
  const chartTotal = Math.max(listedTotal, groupedTotal ?? 0);
  const needsOther = ranked.length > pieColors.length || chartTotal > listedTotal;
  const slices = ranked.slice(0, needsOther ? pieColors.length - 1 : pieColors.length)
    .map((row, index) => ({ ...row, color: pieColors[index] }));
  if (needsOther) {
    const otherCount = chartTotal - slices.reduce((sum, row) => sum + row.count, 0);
    slices.push({ label: '그 외 항목', count: otherCount, color: otherColor });
  }
  const percent = rows.some(row => Number.isFinite(row.percent));
  return <div className="answer-breakdown">
    <h4>{title}</h4>
    {slices.length > 0 && <figure>
      <PieChart slices={slices} total={chartTotal} title={title}/>
      {chartTotal !== total && <figcaption>비율은 {groupedTotal == null ? '표시된 ' : ''}항목별 건수 합계 기준</figcaption>}
    </figure>}
    <details open={showTable || slices.length === 0}>
      <summary>표 보기 ({rows.length}개 항목)</summary>
      <div className="answer-table-scroll"><table className="rag-statistics" aria-label={title}>
        <thead><tr><th scope="col">{label}</th><th scope="col">사례 수</th>{percent && <th scope="col">비율</th>}</tr></thead>
        <tbody>{rows.map(row => <tr key={row.label}><th scope="row">{row.label}</th>
          <td>{validCount(row.count) ? countText(row.count) : '—'}</td>
          {percent && <td>{Number.isFinite(row.percent) ? row.percent.toFixed(2) + '%' : '—'}</td>}</tr>)}</tbody>
      </table></div>
    </details>
  </div>;
}

export function StatisticsCard({ statistics, question }) {
  if (!statistics) return null;
  const { total, rows, top_accidents: accidents, grouped_total: groupedTotal } = statistics;
  if (!validCount(total) && !rows?.length && !accidents?.length) return null;
  const label = statistics.group_label || ({ patterns: '사고 패턴', work_distribution: '작업' }[statistics.kind] || '재해종류');
  const showTable = /표(?:로|를|\s*(?:형태|형식|보여|정리|만들))|테이블|\btable\b/i.test(question || '');
  return <section className="answer-card answer-stats">
    <h3>사고 통계</h3>
    {validCount(total) && <p className="answer-total">조건에 맞는 사례 <strong>{countText(total)}건</strong></p>}
    <Breakdown rows={rows} label={label} title={label + '별 사례 수'} showTable={showTable} total={total} groupedTotal={groupedTotal}/>
    {(!rows?.length || label !== '재해종류') && <Breakdown rows={accidents} label="재해종류" title="상위 재해종류" showTable={showTable} total={total}/>}
  </section>;
}
