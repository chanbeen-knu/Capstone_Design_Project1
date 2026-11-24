import { useEffect, useRef, useState } from 'react';
import Icon from './Icon';
import { AnswerText, StatisticsCard } from './AnswerCards';
import QueryGraph from './QueryGraph';
import { useSettings } from '../settings';

const labels = { ontology: '온톨로지 RAG', vector: '벡터 RAG', compare: '나란히 비교' };
const suggestions = [
  ['advice', '단위작업이 철근 가공 및 운반인 사고 사례를 참고해서 작업 전 주의사항을 알려줘.'],
  ['briefing', '오늘 이동식 크레인을 사용해. 관련 사고 사례를 바탕으로 1분 안전 브리핑을 만들어줘.'],
  ['cases', '기인물이 백호기이고 재해종류가 부딪힘인 사고 사례를 찾아줘.'],
  ['count', 'SIF 건설업 자료에서 기인물이 백호기인 사고는 몇 건이야?'],
  ['distribution', '백호기가 기인물인 사고의 재해종류별 분포를 표로 보여줘.'],
  ['patterns', '백호기 사고에서 반복되는 사고 패턴을 알려줘.'],
  ['unsupported', '오늘 우리 현장에서 사고가 발생할 확률은 몇 퍼센트야?'],
  ['count', '기인물이 타워크레인이고 재해종류가 질식인 건설업 사고는 몇 건이야?'],
  ['cases', '철근 반입 작업의 사고사례를 보여줘.'],
  ['distribution', '철근콘크리트 공사에 속한 전체 사고를 작업별 건수와 비율로 집계해줘.'],
  ['advice', '굴착기를 이용한 철근 반입 작업의 예방대책을 종합해줘.'],
];

const ontologyIntents = { cases: '사례 조회', distribution: '조건 집계', advice: '대책 종합' };
const sourcePageSize = 12;

function MeasureList({ measures }) {
  return <ul className="rag-measures">
    {measures.map(measure => <li key={measure.id || measure.text}>
      {measure.text}<br/><small>{measure.count != null && `등장 사례 ${measure.count}건 · `}근거 {(measure.case_codes || []).join(', ')}</small>
    </li>)}
  </ul>;
}

function Answer({ message, onRetry, compare, question }) {
  const [graphOpen, setGraphOpen] = useState(false);
  const [copyStatus, setCopyStatus] = useState('');
  const [sourceLimit, setSourceLimit] = useState(sourcePageSize);
  const measuresForAnswer = message.measures || [];
  async function copy() {
    try {
      await navigator.clipboard.writeText([message.content, message.follow_up].filter(Boolean).join('\n\n'));
      setCopyStatus('복사됨');
    } catch {
      setCopyStatus('복사 실패');
    }
    setTimeout(() => setCopyStatus(''), 2000);
  }
  return <article className="message assistant">
    {compare && <div className="message-label">{labels[message.agent]}</div>}
    <section className="answer-card answer-main">
      <h3>{message.failed ? '답변 요청 실패' : '핵심 답변'}</h3>
      <AnswerText text={message.content}/>
    </section>
    <StatisticsCard statistics={message.statistics} question={question}/>
    {message.agent === 'ontology' && message.intent === 'advice' && message.statistics?.top_accidents?.length > 0
      // 대책이 똑같은 재해종류는 한 문단으로 합치고, 근거 사례도 합쳐서 보여 줌
      ? Object.values(Object.groupBy(message.statistics.top_accidents, accident => measuresForAnswer
        .filter(measure => measure.accident_id === accident.id).map(measure => measure.id).sort().join() || accident.id)).map(group => {
        const accident = group[0], ids = group.map(row => row.id);
        const measures = Object.values(Object.groupBy(measuresForAnswer.filter(measure => ids.includes(measure.accident_id)), measure => measure.id))
          .map(rows => { const case_codes = [...new Set(rows.flatMap(row => row.case_codes))].sort(); return { ...rows[0], case_codes, count: case_codes.length }; });
        const summary = accident.measure_summary?.length
          ? accident.measure_summary
          : (accident.measure_explanation || '').split(/\n+|(?<=[.!?。])\s+/).map(line => line.trim()).filter(Boolean);
        return <section key={ids.join()} className="answer-card answer-measures">
          <h3>{group.map(row => row.label).join('·')} 사고 예방대책</h3>
          {summary.length > 0
            ? <ul>{summary.map((item, i) => <li key={i}>{item}</li>)}</ul>
            : !measures.length && <p>연결된 예방대책이 없습니다.</p>}
          {measures.length > 0 && <details>
            <summary>예방대책 원문 및 근거 {measures.length}종</summary>
            <MeasureList measures={measures}/>
          </details>}
        </section>;
      })
      : message.measures?.length > 0 && <section className="answer-card answer-measures"><h3>예방대책</h3><MeasureList measures={message.measures}/></section>}
    {message.sources?.length > 0 && <details className="answer-card answer-evidence rag-sources">
      <summary>근거 사례 {message.sources.length}건</summary>
      {message.sources.slice(0, sourceLimit).map((source, index) => <details key={source.id}>
        <summary>[{index + 1}] {source.code} · {source.work || source.object}</summary>
        <small>{source.file} · {source.sheet} {source.row}행</small>
        {(source.classified_accident || source.accident) && <p><strong>재해종류</strong> {source.classified_accident || source.accident}</p>}
        <p>{source.summary}</p>
        {source.hazard && <p><strong>재해유발요인</strong> {source.hazard}</p>}
        {source.measures && <p><strong>위험성 감소대책</strong>{'\n'}{source.measures}</p>}
      </details>)}
      {sourceLimit < message.sources.length && <button type="button" className="secondary-button"
        onClick={() => setSourceLimit(limit => limit + sourcePageSize)}>사례 더 보기</button>}
    </details>}
    {message.agent === 'ontology' && message.query_graph && <details className="answer-card answer-evidence rag-sources"
      onToggle={event => setGraphOpen(event.currentTarget.open)}>
      <summary>조회 근거 그래프 보기</summary>
      {graphOpen && (message.query_graph.error
        ? <p role="status">{message.query_graph.error}</p>
        : <QueryGraph graph={message.query_graph}/>)}
    </details>}
    {message.follow_up && <section className="answer-card answer-main"><h3>후속 질문</h3><AnswerText text={message.follow_up}/></section>}
    {!message.failed && <button type="button" className="copy-button" onClick={copy} aria-label="답변 복사" title={copyStatus || '답변 복사'}><Icon name="copy" size={15}/>{copyStatus && <span>{copyStatus}</span>}</button>}
    {message.failed && <button type="button" className="secondary-button" onClick={onRetry}>이 답변 다시 시도</button>}
  </article>;
}

export default function ChatPanel({ messages, setMessages, storageError, onNewConversation }) {
  const settings = useSettings();
  const request = useRef(null);
  const end = useRef(null);
  const [mode, setMode] = useState('ontology');
  const [input, setInput] = useState('');
  const [pending, setPending] = useState([]);
  const first = messages.find(message => message.role === 'user');
  const activeMode = first?.mode || mode;
  const legacy = Boolean(first && !first.mode);
  const busy = pending.length > 0;

  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }); }, [messages, pending]);

  async function fetchAnswer(turn, agent, history, controller) {
    let message;
    try {
      const response = await fetch('/api/chat', {
        method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: turn.content, agent, history }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '질문을 처리할 수 없습니다.');
      if (typeof data.answer !== 'string') throw new Error('답변 형식 오류');
      message = { ...data, content: data.answer };
    } catch (error) {
      if (controller.signal.aborted) return;
      message = { content: error.message === 'Failed to fetch' ? '백엔드에 연결할 수 없습니다.' : error.message, failed: true };
    }
    if (controller.signal.aborted) return;
    setMessages(previous => [
      ...previous.filter(item => !(item.turnId === turn.id && item.agent === agent)),
      { ...message, agent, turnId: turn.id, id: crypto.randomUUID(), role: 'assistant', createdAt: Date.now() },
    ]);
    setPending(previous => previous.filter(item => item.agent !== agent));
  }

  async function runTurn(turn, agents, previous) {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setPending(agents.map(agent => ({ agent, turnId: turn.id })));
    try {
      await Promise.all(agents.map(agent => {
        const history = previous.filter(item => item.role === 'user').flatMap(user => {
          const reply = previous.find(item => item.turnId === user.id && item.agent === agent && !item.failed);
          return reply ? [user, reply] : [user];
        }).slice(-10).map(({ role, content, follow_up }) => {
          const question = role === 'assistant' && follow_up ? '\n\n' + follow_up.slice(0, 2000) : '';
          return { role, content: content.slice(0, 6000 - question.length) + question };
        });
        return fetchAnswer(turn, agent, history, controller);
      }));
    } finally {
      if (request.current === controller) {
        request.current = null;
        setPending([]);
      }
    }
  }

  function sendMessage(text = input) {
    const content = text.trim();
    if (!content || request.current || legacy) return;
    const turn = { id: crypto.randomUUID(), role: 'user', content, mode: activeMode, createdAt: Date.now() };
    setMessages(previous => [...previous, turn]);
    setInput('');
    runTurn(turn, activeMode === 'compare' ? ['ontology', 'vector'] : [activeMode], messages);
  }

  function stopResponse() {
    request.current?.abort();
    request.current = null;
    setPending([]);
  }

  const turns = messages.filter(message => message.role === 'user');
  return <section className={`chat-panel ${settings.reading ? 'reading-mode' : ''}`} aria-label="안전 채팅">
    <div className="rag-chat-header">
      {legacy ? <span>이전 대화</span> : <label>답변 방식 <select value={activeMode} onChange={event => setMode(event.target.value)} disabled={Boolean(first)}>
        {Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>}
      {first && <button type="button" className="secondary-button" onClick={onNewConversation}>새 대화</button>}
    </div>
    {storageError && <p className="chat-storage-error" role="status">{storageError}</p>}
    <div className="messages rag-messages" role="log" aria-label="대화 메시지" aria-live="polite">
      {!messages.length && <>
        <div className="chat-intro"><h1>안전대책 물어보기</h1><p>SIF 건설업 사고 사례에서 근거를 찾아 답합니다.</p></div>
        <div className="suggestions" aria-label="분류별 예시 질문">
          {suggestions.filter(([intent]) => activeMode !== 'ontology' || intent in ontologyIntents || intent === 'count')
            .map(([, question]) => <button type="button" key={question} onClick={() => sendMessage(question)}>
              {question}
            </button>)}
        </div>
      </>}
      {legacy ? messages.map((message, index) => message.role === 'assistant'
        ? <Answer key={message.id} message={message} question={messages.slice(0, index).findLast(item => item.role === 'user')?.content}/>
        : <article key={message.id} className="message user"><p>{message.content}</p></article>) : turns.map(turn => {
        const agents = turn.mode === 'compare' ? ['ontology', 'vector'] : [turn.mode];
        return <div className="rag-turn" key={turn.id}>
          <article className="message user"><p>{turn.content}</p></article>
          <div className={`rag-answers ${agents.length === 2 ? 'rag-compare' : ''}`}>
            {agents.map(agent => {
              const reply = messages.find(message => message.turnId === turn.id && message.agent === agent);
              const loading = pending.some(item => item.turnId === turn.id && item.agent === agent);
              const previousTurns = new Set(turns.slice(0, turns.indexOf(turn)).map(item => item.id));
              const previous = messages.filter(item => previousTurns.has(item.turnId || item.id));
              if (loading) return <article className="message assistant" key={agent}><div className="message-label">{labels[agent]}</div><p>근거를 검색하고 있습니다…</p></article>;
              if (reply) return <Answer key={agent} message={reply} question={turn.content} compare={agents.length === 2} onRetry={() => runTurn(turn, [agent], previous)}/>;
              return <article className="message assistant" key={agent}><div className="message-label">{labels[agent]}</div><button type="button" className="secondary-button" disabled={busy} onClick={() => runTurn(turn, [agent], previous)}>답변 요청</button></article>;
            })}
          </div>
        </div>;
      })}
      <div ref={end}/>
    </div>
    {!legacy && <div className="composer-area">
      <form onSubmit={event => { event.preventDefault(); sendMessage(); }}>
        <label className="sr-only" htmlFor="chat-input">산업안전 관련 질문</label>
        <textarea id="chat-input" value={input} maxLength={2000} rows={2} placeholder="어떤 작업이나 장비에 대해 궁금하세요?" onChange={event => setInput(event.target.value)} onKeyDown={event => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
            event.preventDefault();
            sendMessage();
          }
        }}/>
        <div className="composer-bottom">{busy
          ? <button type="button" className="send-button stop-button" onClick={stopResponse} aria-label="답변 생성 중단"><Icon name="stop" size={18}/></button>
          : <button type="submit" className="send-button" disabled={!input.trim()} aria-label="메시지 전송"><Icon name="arrow" size={18}/></button>}</div>
      </form>
    </div>}
  </section>;
}
