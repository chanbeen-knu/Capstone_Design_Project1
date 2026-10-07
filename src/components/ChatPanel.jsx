import { useEffect, useRef, useState } from 'react';
import Icon from './Icon';
const suggestions = ['크레인과 연결된 위험요인은?', '낙하 위험의 예방대책은?'];
const HISTORY_LIMIT = 10;
export default function ChatPanel({ selectedNode }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, [messages, isSending]);
  async function sendMessage(text = input) {
    const question = text.trim();
    if (!question || isSending) return;
    const history = messages.slice(-HISTORY_LIMIT).map((message) => ({ role: message.role, content: message.content }));
    setMessages((previous) => [...previous, { id: crypto.randomUUID(), role: 'user', content: question }]);
    setInput('');
    setIsSending(true);
    try {
      const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: question, history }) });
      if (!response.ok) throw new Error(`요청 실패 (${response.status})`);
      const data = await response.json();
      setMessages((previous) => [...previous, { id: crypto.randomUUID(), role: 'assistant', content: data.answer }]);
    } catch {
      setMessages((previous) => [...previous, { id: crypto.randomUUID(), role: 'assistant', content: '답변을 가져오지 못했습니다. 백엔드 서버가 실행 중인지 확인해주세요.' }]);
    } finally {
      setIsSending(false);
    }
  }
  return <section className="chat-panel" aria-label="AI 채팅">
    <header className="chat-header"><div className="chat-title"><span className="assistant-icon"><Icon name="chat"/></span><div><h2>AI Assistant</h2><p>산업안전 탐색 도우미</p></div></div></header>
    <div className="context-bar"><Icon name="graph" size={15}/><span>{selectedNode ? `선택된 노드 · ${selectedNode.label}` : '현재 지식그래프를 함께 탐색합니다'}</span></div>
    <div className="messages" role="log" aria-label="대화 메시지" aria-live="polite"><div className="chat-intro"><span className="intro-mark"><Icon name="graph" size={26}/></span><div className="eyebrow">SAFETY INTELLIGENCE</div><h3>어떤 관계가 궁금하신가요?</h3><p>작업과 위험요인, 예방대책 사이의<br/>연결을 질문하며 살펴보세요.</p></div>
      <div className="message assistant"><div className="message-label"><span className="small-assistant">S</span> Safety Agent <span>예시 안내</span></div><p>안녕하세요. 산업재해 관계 탐색을 도와드릴게요. 왼쪽 그래프의 크레인 인양 작업부터 살펴볼까요?</p></div>
      {messages.length === 0 && <div className="suggestions"><span>이렇게 질문해 보세요</span>{suggestions.map((question) => <button key={question} onClick={() => sendMessage(question)}>{question}<span>↗</span></button>)}</div>}
      {messages.map((message) => <div key={message.id} className={`message ${message.role}`}>{message.role === 'assistant' && <div className="message-label"><span className="small-assistant">S</span> Safety Agent</div>}<p>{message.content}</p></div>)}
      {isSending && <div className="message assistant"><div className="message-label"><span className="small-assistant">S</span> Safety Agent</div><p>답변을 생성하는 중...</p></div>}
      <div ref={end}/>
    </div>
    <div className="composer-area"><form onSubmit={(event) => { event.preventDefault(); sendMessage(); }}><label className="sr-only" htmlFor="chat-input">산업안전 관련 질문</label><textarea id="chat-input" value={input} onChange={(event) => setInput(event.target.value)} placeholder="산업안전에 대해 질문하세요..." rows={3} disabled={isSending} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) { event.preventDefault(); sendMessage(); } }}/><div className="composer-bottom"><span>Shift + Enter로 줄바꿈</span><button className="send-button" type="submit" disabled={!input.trim() || isSending} aria-label="메시지 전송"><Icon name="arrow" size={18}/></button></div></form></div>
  </section>;
}
