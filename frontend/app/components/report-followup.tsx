import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { reportRequest, type Answer, type ChatMessage, type Conversation, type DuplicatePreview, type History, type Question } from "~/lib/analysis";

export function DuplicateRemovalPreview({ analysisId, disabled = false }: { analysisId: number; disabled?: boolean }) {
  const [result, setResult] = useState<DuplicatePreview | null>(null), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  const preview = async () => {
    if (busy || disabled) return;
    const controller = new AbortController(); request.current = controller; setBusy(true); setError("");
    try { const next = await reportRequest<DuplicatePreview>(analysisId, "duplicate-preview", controller.signal, {}); if (!controller.signal.aborted) setResult(next); }
    catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Preview unavailable."); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  return <section className="panel duplicate-preview"><h2>Duplicate-cleaning preview</h2><p>Preview only. The original dataset has not changed. No changes will be applied.</p><button className="button button-secondary" type="button" disabled={busy || disabled} onClick={() => void preview()}>{busy ? "Loading preview…" : error ? "Retry duplicate preview" : "Preview duplicate removal"}</button>{error && <p className="notice notice-error" role="alert">{error}</p>}{result && <div aria-live="polite"><dl className="comparison-metrics"><div><dt>Original row count</dt><dd>{result.original_rows}</dd></div><div><dt>Proposed removed count</dt><dd>{result.proposed_removed_rows}</dd></div><div><dt>Resulting row count</dt><dd>{result.resulting_rows}</dd></div></dl>{result.proposed_removed_rows === 0 && <p>No exact duplicate rows were found.</p>}<p>{result.definition}</p><p className="notice notice-info">{result.note}</p></div>}</section>;
}

export function ReportFollowup({ analysisId, disabled }: { analysisId: number; disabled: boolean }) {
  const [conversations, setConversations] = useState<Conversation[]>([]), [conversationId, setConversationId] = useState<number | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([]), [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [pending, setPending] = useState<Question | null>(null);
  const [retryAction, setRetryAction] = useState<"history" | "question">("history");
  const request = useRef<AbortController | null>(null);
  const begin = () => { request.current?.abort(); const controller = new AbortController(); request.current = controller; setBusy(true); setError(""); return controller; };
  const load = async (id?: number) => {
    if (disabled) return;
    const controller = begin(); setRetryAction("history"); setMessages([]); setPending(null); setQuestion("");
    try {
      const list = await reportRequest<{ analysis_id: number; conversations: Conversation[] }>(analysisId, "conversations", controller.signal);
      const selected = id ?? list.conversations[0]?.conversation_id;
      const history = selected == null ? null : await reportRequest<History>(analysisId, `conversations/${selected}`, controller.signal);
      if (controller.signal.aborted) return;
      if (history && history.conversation_id !== selected) throw new Error("Conversation response does not match the selected thread.");
      setConversations(list.conversations); setConversationId(selected); setMessages(history?.messages ?? []);
      const last = history?.messages.at(-1);
      if (last?.role === "user") { setPending({ question: last.content, request_id: last.request_id, conversation_id: selected }); setRetryAction("question"); setError("This saved question has no answer yet. Retry to ask again."); }
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Conversation history unavailable."); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  useEffect(() => { void load(); return () => request.current?.abort(); }, [analysisId, disabled]);
  const ask = async (retry = false) => {
    if (disabled || busy || (!retry && !question.trim())) return;
    const payload = retry && pending ? pending : { question: question.trim(), request_id: crypto.randomUUID(), conversation_id: conversationId };
    const controller = begin(); setPending(payload); setRetryAction("question");
    try {
      const answer = await reportRequest<Answer>(analysisId, "questions", controller.signal, payload);
      if (controller.signal.aborted) return;
      if (payload.conversation_id != null && answer.conversation_id !== payload.conversation_id) throw new Error("Answer belongs to a different conversation.");
      setConversationId(answer.conversation_id);
      setConversations(current => current.some(c => c.conversation_id === answer.conversation_id) ? current : [{ conversation_id: answer.conversation_id, first_question: payload.question }, ...current]);
      setMessages(current => [...current.filter(m => m.request_id !== payload.request_id), answer.user_message, ...(answer.assistant_message ? [answer.assistant_message] : [])]);
      setQuestion("");
      if (answer.status === "unavailable") { setPending({ ...payload, conversation_id: answer.conversation_id }); setError(answer.unavailable_reason ?? "AI answers are unavailable. Retry this saved question."); }
      else setPending(null);
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Answer unavailable. Retry your question."); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const startNew = () => { request.current?.abort(); setConversationId(undefined); setMessages([]); setQuestion(""); setPending(null); setError(""); setBusy(false); };
  return <><section className="panel report-chat"><h2>Ask about this report</h2><p>Answers use saved report evidence. Questions cannot modify your dataset.</p>{disabled ? <p>Follow-up questions are unavailable in the illustrative sample.</p> : <><div className="chat-controls"><label>Conversation history<select disabled={busy} value={conversationId ?? ""} onChange={e => e.target.value ? void load(Number(e.target.value)) : startNew()}><option value="">New conversation</option>{conversations.map(c => <option value={c.conversation_id} key={c.conversation_id}>#{c.conversation_id} · {c.first_question ?? "Empty conversation"}</option>)}</select></label><button type="button" className="button button-secondary" onClick={startNew}>Start new conversation</button></div><div className="chat-messages" aria-live="polite">{messages.map(m => <article key={m.message_id}><strong>{m.role === "user" ? "You" : "Assistant"}</strong>{m.status === "insufficient_evidence" && <p className="notice notice-warning">Insufficient saved evidence</p>}<p className="chat-content">{m.content}</p>{m.sources?.map(s => <Link key={s.source_id} to={s.comparison_id != null ? `?view=columns&comparison=${s.comparison_id}#comparison-${s.comparison_id}` : "?view=columns"}>Evidence: {s.label}{s.comparison_id != null ? ` (#${s.comparison_id})` : ""}</Link>)}</article>)}</div>{pending && !messages.some(m => m.request_id === pending.request_id) && <p><strong>Your pending question:</strong> {pending.question}</p>}{busy && <p role="status">Loading conversation…</p>}{error && <p className="notice notice-error" role="alert">{error} <button type="button" disabled={busy} onClick={() => retryAction === "question" ? void ask(true) : void load(conversationId)}>Retry {retryAction === "question" ? "question" : "history"}</button></p>}<form onSubmit={e => { e.preventDefault(); void ask(); }}><label>Follow-up question<textarea maxLength={1000} value={question} disabled={busy || !!pending} onChange={e => setQuestion(e.target.value)} rows={3} /></label><button type="submit" className="button button-primary" disabled={busy || !!pending || !question.trim()}>Ask question</button></form></>}</section><DuplicateRemovalPreview key={analysisId} analysisId={analysisId} disabled={disabled} /></>;
}
