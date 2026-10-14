import { useEffect, useRef, useState } from 'react';
import Icon from './Icon';
import { useSettings } from '../settings';
const suggestions = ['크레인과 연결된 위험요인은?', '낙하 위험의 예방대책은?'];
const HISTORY_LIMIT = 10;
export default function ChatPanel({ selectedNode, expanded, onToggleSize, clearVersion }) {
  const settings = useSettings();
  const request = useRef(null);
  const generation = useRef(0);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const end = useRef(null);
  useEffect(() => {
    generation.current += 1;
    request.current?.abort();
    request.current = null;
    setMessages([]);
    setIsSending(false);
  }, [clearVersion]);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, [messages, isSending]);
  async function sendMessage(text = input) {
    const question = text.trim();
    if (!question || request.current) return;
    const currentGeneration = generation.current;
    const controller = new AbortController();
    request.current = controller;
    const history = messages.slice(-HISTORY_LIMIT).map((message) => ({ role: message.role, content: message.content }));
    setMessages((previous) => [...previous, { id: crypto.randomUUID(), role: 'user', content: question }]);
    setInput('');
    setIsSending(true);
    try {
      const response = await fetch('/api/chat', { method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: question, history }) });
      if (!response.ok) throw new Error(`요청 실패 (${response.status})`);
      const data = await response.json();
      if (generation.current !== currentGeneration) return;
      setMessages((previous) => [...previous, { id: crypto.randomUUID(), role: 'assistant', content: data.answer }]);
    } catch {
      if (generation.current !== currentGeneration || controller.signal.aborted) return;
      setMessages((previous) => [...previous, { id: crypto.randomUUID(), role: 'assistant', content: '답변을 가져오지 못했습니다. 백엔드 서버가 실행 중인지 확인해주세요.' }]);
    } finally {
      if (generation.current === currentGeneration) { request.current = null; setIsSending(false); }
    }
  }
  return <section className={`chat-panel ${settings.reading ? 'reading-mode' : ''}`} aria-label="AI 채팅">
    <header className="chat-header"><div className="chat-title"><span className="assistant-icon"><Icon name="chat"/></span><div><h2>링키 <small>Linky</small></h2><p>안전 도우미 링키</p></div></div><button className="text-button" onClick={onToggleSize}>{expanded ? "작게 보기 ↙" : "크게 보기 ↗"}</button></header>
    <div className="context-bar"><Icon name="graph" size={15}/><span>{selectedNode ? `선택된 노드 · ${selectedNode.label}` : '사고와 예방대책에 관해 질문해 보세요'}</span></div>
    <div className="messages" role="log" aria-label="대화 메시지" aria-live="polite"><div className="chat-intro"><span className="intro-mark"><Icon name="graph" size={26}/></span><div className="eyebrow">YOUR SAFETY COMPANION</div><h3>안전한 작업, 함께 알아봐요</h3><p>작업과 위험요인, 예방대책 사이의<br/>연결을 질문하며 살펴보세요.</p></div>
      <div className="message assistant"><div className="message-label"><span className="small-assistant">L</span> 링키</div><p>안녕하세요, 안전 도우미 링키예요. 어떤 작업의 예방대책이 궁금하신가요?</p></div>
      {messages.length === 0 && <div className="suggestions"><span>이렇게 질문해 보세요</span>{suggestions.map((question) => <button key={question} onClick={() => sendMessage(question)}>{question}<span>↗</span></button>)}</div>}
      {messages.map((message) => <div key={message.id} className={`message ${message.role}`}>{message.role === 'assistant' && <div className="message-label"><span className="small-assistant">S</span> 링키</div>}<p>{message.content}</p></div>)}
      {isSending && <div className="message assistant"><div className="message-label"><span className="small-assistant">S</span> 링키</div><p>답변을 생성하는 중...</p></div>}
      <div ref={end}/>
    </div>
    <div className="composer-area"><form onSubmit={(event) => { event.preventDefault(); sendMessage(); }}><label className="sr-only" htmlFor="chat-input">산업안전 관련 질문</label><textarea id="chat-input" value={input} onChange={(event) => setInput(event.target.value)} placeholder="산업안전에 대해 질문하세요..." rows={3} disabled={isSending} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) { event.preventDefault(); sendMessage(); } }}/><div className="composer-bottom"><span>Shift + Enter로 줄바꿈</span><button className="send-button" type="submit" disabled={!input.trim() || isSending} aria-label="메시지 전송"><Icon name="arrow" size={18}/></button></div></form></div>
  </section>;
}
