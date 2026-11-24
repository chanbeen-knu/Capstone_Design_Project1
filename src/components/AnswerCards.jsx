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

function Breakdown({ rows, label, title, showTable }) {
  if (!rows?.length) return null;
  const ranked = rows.filter(row => validCount(row.count)).sort((a, b) => b.count - a.count);
  const peak = ranked[0]?.count;
  const chart = ranked.length >= 2 && peak > 0;
  const percent = rows.some(row => Number.isFinite(row.percent));
  return <div className="answer-breakdown">
    <h4>{title}</h4>
    {chart && <figure>
      {ranked.length > 8 && <figcaption>사례 수 상위 8개</figcaption>}
      <ul className="answer-bars">{ranked.slice(0, 8).map(row => <li key={row.label}>
        <div className="answer-bar-label"><span>{row.label}</span><strong>{countText(row.count)}건
          {Number.isFinite(row.percent) && <small> · {row.percent.toFixed(2)}%</small>}</strong></div>
        <div className="answer-bar-track" aria-hidden="true"><i style={{ width: (100 * row.count / peak) + '%' }}/></div>
      </li>)}</ul>
    </figure>}
    {rows.length === 1 && validCount(peak) && <p>{ranked[0].label} <strong>{countText(peak)}건</strong></p>}
    <details open={showTable || (!chart && rows.length > 1)}>
      <summary>전체 표 보기 ({rows.length}개 항목)</summary>
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
  const { total, rows, top_accidents: accidents } = statistics;
  if (!validCount(total) && !rows?.length && !accidents?.length) return null;
  const label = statistics.group_label || ({ patterns: '사고 패턴', work_distribution: '작업' }[statistics.kind] || '재해종류');
  const showTable = /표(?:로|를|\s*(?:형태|형식|보여|정리|만들))|테이블|\btable\b/i.test(question || '');
  return <section className="answer-card answer-stats">
    <h3>사고 통계</h3>
    {validCount(total) && <p className="answer-total">조건에 맞는 사례 <strong>{countText(total)}건</strong></p>}
    <Breakdown rows={rows} label={label} title={label + '별 사례 수'} showTable={showTable}/>
    {(!rows?.length || label !== '재해종류') && <Breakdown rows={accidents} label="재해종류" title="상위 재해종류" showTable={showTable}/>}
  </section>;
}
