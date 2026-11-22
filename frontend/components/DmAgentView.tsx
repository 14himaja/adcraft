'use client';

import React, { useState, useEffect, useRef } from 'react';
import useSWR from 'swr';
import { Bot, MessageCircle } from 'lucide-react';
import { DmConfig, DmMessage, DmThread, deleteDmThread, fetcher, previewDm, replyDm, resumeDm, saveDmConfig } from '../lib/api';
import { ErrorBox, btnPrimary, btnSecondary, errorMessage, inputCls, labelCls } from './Dialog';

const KNOWLEDGE_MAX = 6000;
const EXAMPLE_KNOWLEDGE = `Business: Priya Bakery, Hyderabad.
Hours: 9am to 6pm, Monday to Saturday. Closed Sunday.
Prices: Birthday cakes from Rs 800. Order 2 days ahead.
Delivery: Within 10 km, Rs 60. Free above Rs 1500.
Payment: UPI and cash.
Do not discuss: refunds beyond 24 hours (hand over).`;

function getStatusLine(dmStatus?: { agent_enabled: boolean; webhook_verified: boolean; webhook_subscribed: boolean; last_inbound_at: string | null; last_error: string | null } | null) {
  if (!dmStatus) return '';
  if (!dmStatus.agent_enabled) return 'Agent is off';
  if (!dmStatus.webhook_verified) return 'Webhook not verified';
  return `Webhook ${dmStatus.webhook_subscribed ? 'subscribed' : 'not subscribed'}${dmStatus.last_error ? ` · Last error: ${dmStatus.last_error}` : ''}${dmStatus.last_inbound_at ? ` · Last inbound ${new Date(dmStatus.last_inbound_at).toLocaleString()}` : ''}`;
}
const STATUS_LABEL: Record<DmThread['status'], string> = {
  BOT: 'AI replying',
  NEEDS_HUMAN: 'Needs you',
  HUMAN: 'You are replying',
};

const displayName = (t: DmThread) => t.customer_name || `Customer ${t.customer_id.slice(-6)}`;
const initial = (t: DmThread) => displayName(t).replace(/^Customer\s+/, '').charAt(0).toUpperCase() || '?';
const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

/** One conversation, laid out like a chat: customer bubbles on the left, our replies on the right. */
/** One conversation, laid out like a chat: customer bubbles on the left, our replies on the right. */
function Chat({
  thread,
  onThreadUpdated,
  onThreadDeleted,
}: {
  thread: DmThread;
  onThreadUpdated: (updated: DmThread) => void;
  onThreadDeleted: (deletedId: string) => void;
}) {
  const [text, setText] = useState('');
  const [optimisticMessages, setOptimisticMessages] = useState<DmMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setOptimisticMessages([]);
    setError(null);
  }, [thread.id]);

  const allMessages = [...thread.messages, ...optimisticMessages];

  useEffect(() => {
    if (typeof messagesEndRef.current?.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [allMessages.length]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const msg = text.trim();
    if (!msg || busy) return;

    const optMsg: DmMessage = {
      role: 'admin',
      text: msg,
      at: new Date().toISOString(),
    };
    setOptimisticMessages((prev) => [...prev, optMsg]);
    setText('');
    setBusy(true);
    setError(null);
    try {
      const updated = await replyDm(thread.id, msg);
      setOptimisticMessages([]);
      onThreadUpdated(updated);
    } catch (e) {
      setOptimisticMessages([]);
      setText(msg);
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const handleResume = async () => {
    setBusy(true);
    setError(null);
    try {
      const updated = await resumeDm(thread.id);
      onThreadUpdated(updated);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm('Delete this conversation and its stored messages?')) return;
    setBusy(true);
    setError(null);
    try {
      await deleteDmThread(thread.id);
      onThreadDeleted(thread.id);
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col min-h-[420px]">
      <div className="flex items-center gap-3 px-4 py-3 border-b border-[#EDE6DD] dark:border-white/10">
        <span className="w-9 h-9 rounded-full bg-[#FEECE7] text-[#F26D5B] font-bold flex items-center justify-center">{initial(thread)}</span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-bold text-[#1F1A18] dark:text-white truncate">{displayName(thread)}</p>
          <p className="text-[11px] text-[#7A6C63]">
            Last messaged {thread.minutes_since_inbound ?? 0} minutes ago
            {thread.reply_window_warning && <strong className="text-amber-700 font-bold ml-1">Less than 2 hours left to reply.</strong>}
            {(thread.minutes_since_inbound ?? 0) >= 24 * 60 && (
              <span className="text-rose-600 font-bold ml-1">Reply window closed (over 24 hours ago).</span>
            )}
          </p>
        </div>
        <span className={`px-2 py-0.5 rounded-md text-xs font-bold ${thread.status === 'NEEDS_HUMAN' ? 'bg-rose-500/10 text-rose-600' : 'bg-[#FEECE7] text-[#F26D5B]'}`}>
          {STATUS_LABEL[thread.status]}
        </span>
        {thread.needs_attention && thread.status === 'BOT' && (
          <span className="px-2 py-0.5 rounded-md text-xs font-bold bg-amber-500/10 text-amber-600">Needs attention</span>
        )}
      </div>
      <ul className="flex-1 flex flex-col gap-2 px-4 py-3 overflow-y-auto max-h-[420px] text-sm">
        {allMessages.map((m, i) => {
          const mine = m.role !== 'customer';
          return (
            <li
              key={i}
              className={`max-w-[75%] px-3 py-2 rounded-2xl ${
                mine
                  ? 'self-end rounded-tr-sm bg-[#F26D5B] text-white'
                  : 'self-start rounded-tl-sm bg-[#F1ECE6] dark:bg-white/10 text-[#1F1A18] dark:text-white'
              }`}
            >
              {m.role === 'agent' && <span className="block text-[10px] font-bold opacity-80">AI</span>}
              <span className="whitespace-pre-wrap">{m.text}</span>
              <span className="block text-[10px] opacity-70 text-right mt-0.5">{clock(m.at)}</span>
            </li>
          );
        })}
        <div ref={messagesEndRef} />
      </ul>
      <form
        className="flex gap-2 px-4 py-3 border-t border-[#EDE6DD] dark:border-white/10"
        onSubmit={handleSend}
      >
        <input
          aria-label={`Reply to ${displayName(thread)}`}
          className={inputCls}
          value={text}
          maxLength={1000}
          onChange={(e) => setText(e.target.value)}
          placeholder="Reply yourself (within 24 hours of their message)"
        />
        <button type="submit" disabled={busy || !text.trim()} className={btnSecondary}>
          Send
        </button>
        {thread.status !== 'BOT' && (
          <button type="button" disabled={busy} className={btnSecondary} onClick={handleResume}>
            Hand back to AI
          </button>
        )}
      </form>
      <div className="px-4 pb-3 flex items-center gap-3">
        <button type="button" className="text-xs text-rose-600 font-bold" disabled={busy} onClick={handleDelete}>Delete conversation</button>
        <ErrorBox message={error} />
      </div>
    </div>
  );
}

export function DmAgentView() {
  const { data: saved, mutate: mutateConfig } = useSWR<DmConfig>('/v1/dm/config', fetcher);
  const { data: threads, mutate: mutateThreads } = useSWR<DmThread[]>('/v1/dm/threads', fetcher, {
    refreshInterval: 2_000,
    revalidateOnFocus: true,
    revalidateOnReconnect: true,
    dedupingInterval: 500,
  });
  const { data: dmStatus } = useSWR<{ agent_enabled: boolean; webhook_verified: boolean; webhook_subscribed: boolean; last_inbound_at: string | null; last_error: string | null }>('/v1/dm/status', fetcher, {
    refreshInterval: 5_000,
    revalidateOnFocus: true,
  });
  const [edits, setEdits] = useState<Partial<DmConfig>>({});
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<{ reply: string; needs_human: boolean } | null>(null);
  const [asking, setAsking] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = threads?.find((t) => t.id === selectedId) ?? threads?.[0];

  if (!saved) return <p className="text-xs text-[#7A6C63] dark:text-slate-400">Loading DM agent…</p>;
  const form: DmConfig = { ...saved, ...edits };
  const set = (patch: Partial<DmConfig>) => setEdits({ ...edits, ...patch });

  const save = async () => {
    setError(null);
    setStatus(null);
    try {
      await saveDmConfig(form);
      await mutateConfig(form, false);
      setEdits({});
      setStatus(form.enabled ? 'Saved. The AI is answering DMs.' : 'Saved. Auto-reply is off.');
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const ask = async () => {
    setAsking(true);
    setError(null);
    try {
      setAnswer(await previewDm(question.trim()));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setAsking(false);
    }
  };

  const handleThreadUpdated = (updated: DmThread) => {
    mutateThreads(
      (prev) => prev?.map((t) => (t.id === updated.id ? updated : t)) ?? [updated],
      false
    );
    mutateThreads();
  };

  const handleThreadDeleted = (deletedId: string) => {
    mutateThreads((prev) => prev?.filter((t) => t.id !== deletedId) ?? [], false);
    setSelectedId((current) => (current === deletedId ? null : current));
    mutateThreads();
  };

  return (
    <div className="space-y-6">
      <div className="border-b border-[#EDE6DD] dark:border-white/10 pb-8 space-y-4">
        <div className="flex items-start gap-3">
          <Bot className="w-5 h-5 text-[#F26D5B] mt-0.5" />
          <div>
            <h2 className="text-xl font-extrabold text-[#1F1A18] dark:text-white tracking-tight">DM Agent</h2>
            <p className="text-xs text-[#7A6C63] dark:text-slate-400 mt-1">
              Write what the AI may say about your business. It answers Instagram DMs only from this text and hands
              over to you when it is not sure. Instagram allows replies for 24 hours after a customer&apos;s message.
            </p>
          </div>
        </div>
        <p role="status" className="text-xs text-[#7A6C63]">{getStatusLine(dmStatus)}</p>

        <label className="flex items-center gap-2 text-sm font-bold text-[#1F1A18] dark:text-white cursor-pointer">
          <input type="checkbox" checked={form.enabled} onChange={(e) => set({ enabled: e.target.checked })} />
          Auto-reply to Instagram DMs
        </label>

        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="dm-business" className={labelCls}>Business name</label>
            <input id="dm-business" className={inputCls} maxLength={120} value={form.business_name}
              onChange={(e) => set({ business_name: e.target.value })} />
          </div>
          <div>
            <label htmlFor="dm-tone" className={labelCls}>Tone</label>
            <input id="dm-tone" className={inputCls} maxLength={200} value={form.tone}
              onChange={(e) => set({ tone: e.target.value })} />
          </div>
        </div>

        <div>
          <label htmlFor="dm-knowledge" className={labelCls}>What the AI knows (hours, prices, policies, FAQs)</label>
          <textarea id="dm-knowledge" rows={8} className={inputCls} maxLength={KNOWLEDGE_MAX} value={form.knowledge}
            onChange={(e) => set({ knowledge: e.target.value })} />
          <div className="flex items-center justify-between mt-1 text-[11px] text-[#9C8F85]">
            <span>{form.knowledge.length}/{KNOWLEDGE_MAX} characters</span>
            {form.knowledge.length > KNOWLEDGE_MAX && (
              <span className="text-rose-600 font-bold">Knowledge block must be 6,000 characters or fewer</span>
            )}
          </div>
          <div className="mt-3 bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 rounded-lg p-3 text-xs space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="font-bold text-[#1F1A18] dark:text-white">Example knowledge block:</span>
              {!form.knowledge && (
                <button
                  type="button"
                  className="text-[11px] font-bold text-[#F26D5B] hover:underline cursor-pointer"
                  onClick={() => set({ knowledge: EXAMPLE_KNOWLEDGE, business_name: form.business_name || 'Priya Bakery' })}
                >
                  Use this example
                </button>
              )}
            </div>
            <pre className="font-mono text-[11px] whitespace-pre-wrap leading-relaxed text-[#7A6C63] dark:text-slate-300 bg-white dark:bg-black/20 p-2.5 rounded border border-[#EDE6DD] dark:border-white/10">
              {EXAMPLE_KNOWLEDGE}
            </pre>
          </div>
        </div>

        <div>
          <label htmlFor="dm-handoff" className={labelCls}>Message sent when a person needs to take over</label>
          <input id="dm-handoff" className={inputCls} maxLength={300} value={form.handoff_message}
            onChange={(e) => set({ handoff_message: e.target.value })} />
        </div>

        <div className="flex items-center gap-3">
          <button type="button" className={btnPrimary} onClick={save}>Save</button>
          {status && <span role="status" className="text-xs font-semibold text-emerald-600">{status}</span>}
        </div>
        <ErrorBox message={error} />
      </div>

      <div className="border-b border-[#EDE6DD] dark:border-white/10 pb-8 space-y-3">
        <h3 className="text-sm font-bold text-[#1F1A18] dark:text-white">Try it (saved text only, nothing is sent)</h3>
        <div className="flex gap-2">
          <input aria-label="Test question" className={inputCls} value={question} maxLength={1000}
            onChange={(e) => setQuestion(e.target.value)} placeholder="What time do you open?" />
          <button type="button" className={btnSecondary} disabled={asking || !question.trim()} onClick={ask}>Ask</button>
        </div>
        {answer && (
          <p role="status" aria-label="Agent answer" className="text-xs text-[#1F1A18] dark:text-white">
            {answer.reply}
            {answer.needs_human && <span className="ml-2 font-bold text-rose-600">(the AI would hand over to you)</span>}
          </p>
        )}
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-sm font-bold text-[#1F1A18] dark:text-white">
            <MessageCircle className="w-4 h-4 text-[#F26D5B]" /> Conversations
          </h3>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" /> Live
          </span>
        </div>
        {threads && threads.length === 0 && (
          <p className="text-xs text-[#7A6C63] dark:text-slate-400">No DMs yet.</p>
        )}
        {selected && (
          <div className="grid md:grid-cols-[280px_1fr] border border-[#EDE6DD] dark:border-white/10 rounded-xl overflow-hidden">
            <ul className="md:border-r border-b md:border-b-0 border-[#EDE6DD] dark:border-white/10 max-h-[560px] overflow-y-auto">
              {(threads ?? []).map((t) => {
                const last = t.messages[t.messages.length - 1];
                return (
                  <li key={t.id}>
                    <button
                      type="button"
                      aria-current={t.id === selected.id}
                      onClick={() => setSelectedId(t.id)}
                      className={`w-full flex items-center gap-3 px-3 py-3 text-left border-b border-[#EDE6DD]/60 dark:border-white/5 cursor-pointer ${
                        t.id === selected.id ? 'bg-[#FEECE7] dark:bg-white/10' : 'hover:bg-[#FAF8F5] dark:hover:bg-white/5'
                      }`}
                    >
                      <span className="w-9 h-9 shrink-0 rounded-full bg-[#FEECE7] text-[#F26D5B] font-bold flex items-center justify-center">{initial(t)}</span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center justify-between gap-2">
                          <span className="text-sm font-bold text-[#1F1A18] dark:text-white truncate">{displayName(t)}</span>
                          {last && <span className="text-[10px] text-[#9C8F85] shrink-0">{clock(last.at)}</span>}
                        </span>
                        <span className="flex items-center gap-1.5">
                          {t.status === 'NEEDS_HUMAN' && <span className="w-2 h-2 shrink-0 rounded-full bg-rose-500" title="Needs you" />}
                          {t.status !== 'NEEDS_HUMAN' && t.needs_attention && <span className="w-2 h-2 shrink-0 rounded-full bg-amber-500" title="The AI had no knowledge to answer with. Add business knowledge or reply yourself." />}
                          <span className="text-xs text-[#7A6C63] dark:text-slate-400 truncate">{last?.text}</span>
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <Chat
              key={selected.id}
              thread={selected}
              onThreadUpdated={handleThreadUpdated}
              onThreadDeleted={handleThreadDeleted}
            />
          </div>
        )}
      </div>
    </div>
  );
}
