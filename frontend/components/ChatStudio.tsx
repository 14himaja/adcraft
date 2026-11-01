'use client';

import React, { useEffect, useRef, useState } from 'react';
import { ArrowUp, ImageIcon, RefreshCw, Send, Settings2, Sparkles, Upload, X } from 'lucide-react';
import {
  CTA_OPTIONS,
  Campaign,
  CampaignFields,
  chatCampaign,
  createDraftFromIdea,
  updateCampaign,
  uploadCampaignImage,
} from '../lib/api';
import { EXAMPLE_IDEAS } from './AIAssistantCard';
import { ErrorBox, btnPrimary, btnSecondary, errorMessage } from './Dialog';
import { PublishFlow, fieldLabel, publishBlockReason } from './PublishFlow';
import { AdPreview, ctaLabel } from './StudioCreativeStep';

type Message = { role: 'user' | 'assistant'; text: string; warnings?: string[] };

const BUDGETS = [50, 100, 200, 500];
const DURATIONS = [7, 14, 30];
const SUGGESTIONS = ['Make the text shorter', 'Write it in Telugu', 'Show a different image', 'Target ages 18-35'];
const NEW_IMAGE = 'Make a new image with a completely different concept, layout and colours';
const READY = "Here's your ad. Tap an option to change it, or tell me what to change.";

const iso = (d: Date) => d.toISOString().slice(0, 10);
const daysBetween = (a: string, b: string) => Math.round((Date.parse(b) - Date.parse(a)) / 86_400_000);

/** Start tomorrow unless the draft already starts later; the backend rejects past start dates. */
function runFor(c: Campaign, days: number): CampaignFields {
  const tomorrow = new Date(Date.now() + 86_400_000);
  const start = c.start_date && c.start_date > iso(new Date()) ? c.start_date : iso(tomorrow);
  return { start_date: start, end_date: iso(new Date(Date.parse(start) + days * 86_400_000)) };
}

const chip = (on: boolean) =>
  `px-3 py-1.5 rounded-full border text-xs font-semibold cursor-pointer transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
    on
      ? 'bg-[#FEECE7] dark:bg-[#F26D5B]/20 border-[#F26D5B] text-[#F26D5B]'
      : 'bg-white dark:bg-white/5 border-[#EDE6DD] dark:border-white/10 text-[#5C5047] dark:text-slate-300 hover:border-[#F26D5B]/60'
  }`;

function Options({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div role="group" aria-label={label} className="space-y-1.5">
      <p className="text-[11px] font-bold uppercase tracking-wide text-[#9C8F85]">{label}</p>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

interface DraftCardProps {
  draft: Campaign;
  busy: boolean;
  onPatch: (fields: CampaignFields) => void;
  onImage: (fn: (id: string) => Promise<Campaign>, label: string) => void;
  onPublish: () => void;
  onAdvanced: () => void;
  /** Sends a chat message, so the AI writes a fresh image concept instead of re-rendering the same one. */
  onAsk: (text: string) => void;
}

function DraftCard({ draft, busy, onPatch, onImage, onPublish, onAdvanced, onAsk }: DraftCardProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const v = draft.variants[draft.selected_variant] ?? draft.variants[0];
  const days = draft.start_date && draft.end_date ? daysBetween(draft.start_date, draft.end_date) : null;
  const a = draft.audience;
  const blocked = publishBlockReason(draft);
  const setCta = (cta: string) =>
    onPatch({ variants: draft.variants.map((x, i) => (i === draft.selected_variant ? { ...x, call_to_action: cta } : x)) });

  return (
    <div className="border-b border-[#EDE6DD] dark:border-white/10 py-4 grid grid-cols-1 md:grid-cols-[280px_1fr] gap-5">
      <div className="space-y-2 flex flex-col items-center">
        <AdPreview campaign={draft} />
        <div className="flex gap-2">
          <button type="button" className={btnSecondary} disabled={busy} onClick={() => onAsk(NEW_IMAGE)}>
            <RefreshCw className="w-3.5 h-3.5" /><span>New image</span>
          </button>
          <button type="button" className={btnSecondary} disabled={busy} onClick={() => fileRef.current?.click()}>
            <Upload className="w-3.5 h-3.5" /><span>Upload</span>
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png"
            aria-label="Upload your own image"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = '';
              if (file) onImage((id) => uploadCampaignImage(id, file), 'Uploading your image…');
            }}
          />
        </div>
      </div>

      <div className="space-y-4 min-w-0">
        <p className="text-sm font-bold">{draft.title || 'Untitled ad'}</p>
        {draft.variants.length > 1 && (
          <Options label="Ad text">
            {draft.variants.map((x, i) => (
              <button key={i} type="button" aria-pressed={i === draft.selected_variant} disabled={busy} className={chip(i === draft.selected_variant)} onClick={() => onPatch({ selected_variant: i })}>
                {x.headline}
              </button>
            ))}
          </Options>
        )}
        <Options label="Daily budget">
          {BUDGETS.map((b) => (
            <button key={b} type="button" aria-pressed={draft.daily_budget === b} disabled={busy} className={chip(draft.daily_budget === b)} onClick={() => onPatch({ daily_budget: b })}>
              ₹{b}/day
            </button>
          ))}
          {draft.daily_budget !== null && !BUDGETS.includes(draft.daily_budget) && <span className={chip(true)}>₹{draft.daily_budget}/day</span>}
        </Options>
        <Options label="Run for">
          {DURATIONS.map((d) => (
            <button key={d} type="button" aria-pressed={days === d} disabled={busy} className={chip(days === d)} onClick={() => onPatch(runFor(draft, d))}>
              {d} days
            </button>
          ))}
          {days !== null && !DURATIONS.includes(days) && <span className={chip(true)}>{days} days</span>}
        </Options>
        <Options label="Goal">
          {([['TRAFFIC', 'Website visits'], ['AWARENESS', 'Reach more people']] as const).map(([id, name]) => (
            <button key={id} type="button" aria-pressed={draft.objective === id} disabled={busy} className={chip(draft.objective === id)} onClick={() => onPatch({ objective: id })}>
              {name}
            </button>
          ))}
        </Options>
        {v && (
          <Options label="Button">
            {CTA_OPTIONS.map((cta) => (
              <button key={cta} type="button" aria-pressed={v.call_to_action === cta} disabled={busy} className={chip(v.call_to_action === cta)} onClick={() => setCta(cta)}>
                {ctaLabel(cta)}
              </button>
            ))}
          </Options>
        )}
        <Options label={`Who sees it · ages ${a.age_min}-${a.age_max}${a.genders === 'ALL' ? '' : `, ${a.genders.toLowerCase()}`}`}>
          {a.countries.map((c) => <span key={c} className={chip(false)}>{c === 'IN' ? 'All of India' : c}</span>)}
          {a.cities.map((c) => (
            <span key={c.key} className={chip(true)}>
              {c.name}
              <button type="button" aria-label={`Remove city ${c.name}`} disabled={busy} className="ml-1 align-middle cursor-pointer" onClick={() => onPatch({ audience: { ...a, cities: a.cities.filter((x) => x.key !== c.key) } })}>
                <X className="w-3 h-3 inline" />
              </button>
            </span>
          ))}
          {a.interests.map((i) => (
            <span key={i.id} className={chip(false)}>
              {i.name}
              <button type="button" aria-label={`Remove interest ${i.name}`} disabled={busy} className="ml-1 align-middle cursor-pointer" onClick={() => onPatch({ audience: { ...a, interests: a.interests.filter((x) => x.id !== i.id) } })}>
                <X className="w-3 h-3 inline" />
              </button>
            </span>
          ))}
        </Options>

        {draft.special_category_reason && (
          <div className="p-3 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-800 dark:text-amber-200 space-y-2">
            <p>This ad {draft.special_category_reason}. Meta restricts job, housing, credit and political ads.</p>
            <button type="button" className={btnSecondary} disabled={busy} onClick={() => onPatch({ not_special_category: true })}>
              It&apos;s not a job, housing, credit or political ad
            </button>
          </div>
        )}
        {draft.missing_fields.length > 0 && (
          <p className="text-xs text-amber-700 dark:text-amber-300">
            Still needed: {draft.missing_fields.map(fieldLabel).join(', ')}.{' '}
            {draft.missing_fields.includes('image_id') ? 'Press New image or Upload a photo. ' : ''}
            Anything else, tell me in the chat (for example your website link).
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <button type="button" className={btnPrimary} disabled={busy || !!blocked} title={blocked ?? undefined} onClick={onPublish}>
            <Send className="w-3.5 h-3.5" /><span>Publish and start Instagram ad</span>
          </button>
          <button type="button" className={btnSecondary} disabled={busy} onClick={onAdvanced}>
            <Settings2 className="w-3.5 h-3.5" /><span>Advanced edit</span>
          </button>
        </div>
        <p className="text-[11px] text-[#9C8F85]">Publishing starts delivery after Meta review. The connected ad account is charged up to the daily budget.</p>
      </div>
    </div>
  );
}

interface ChatStudioProps {
  /** Existing draft to continue; null starts a new chat. */
  campaign: Campaign | null;
  onClose: () => void;
  onChanged: () => void;
  onAdvanced: (campaign: Campaign) => void;
}

export function ChatStudio({ campaign, onClose, onChanged, onAdvanced }: ChatStudioProps) {
  const [draft, setDraft] = useState<Campaign | null>(campaign);
  const [messages, setMessages] = useState<Message[]>(() =>
    campaign
      ? [
          // Saved history when there is one; older drafts only have the idea.
          ...(campaign.chat?.length ? campaign.chat : campaign.idea ? [{ role: 'user' as const, text: campaign.idea }] : []),
          { role: 'assistant', text: READY, warnings: campaign.warnings },
        ]
      : [{ role: 'assistant', text: 'Hi! What do you want to promote? Tell me the product or offer, the city and your website.' }],
  );
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth' });
  }, [messages, busy, draft]);

  const work = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    setError(null);
    try {
      await fn();
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const send = (raw: string) => {
    const text = raw.trim();
    if (!text || busy) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', text }]);
    if (!draft) {
      return work('Writing your ad and creating the image… (up to a minute)', async () => {
        const created = await createDraftFromIdea(text);
        setDraft(created);
        setMessages((m) => [...m, { role: 'assistant', text: READY, warnings: created.warnings }]);
      });
    }
    return work('Updating your ad…', async () => {
      const turn = await chatCampaign(draft.id, text);
      setDraft(turn.campaign);
      setMessages((m) => [...m, { role: 'assistant', text: turn.reply || 'Done.', warnings: turn.warnings }]);
    });
  };

  const patch = (fields: CampaignFields) => draft && work('Saving…', async () => setDraft(await updateCampaign(draft.id, fields)));
  const image = (fn: (id: string) => Promise<Campaign>, label: string) => draft && work(label, async () => setDraft(await fn(draft.id)));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-black/60 backdrop-blur-sm">
      <div role="dialog" aria-modal="true" aria-label="AI Ad Chat" className="bg-white dark:bg-[#0B0F19] text-[#1F1A18] dark:text-white w-full max-w-4xl h-[94vh] rounded-3xl border border-[#EDE6DD] dark:border-white/10 shadow-2xl flex flex-col overflow-hidden">
        <div className="px-5 py-3 border-b border-[#EDE6DD] dark:border-white/10 flex items-center gap-3 shrink-0">
          <div className="w-9 h-9 rounded-xl bg-[#F26D5B] flex items-center justify-center text-white"><Sparkles className="w-4 h-4" /></div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-bold leading-tight">AI Ad Chat</h3>
            <p className="text-[11px] text-[#7A6C63] dark:text-slate-400">Drafts stay on AdCraft. Nothing reaches Meta until you publish.</p>
          </div>
          <button type="button" aria-label="Close chat" onClick={onClose} className="w-8 h-8 rounded-full border border-[#EDE6DD] dark:border-white/10 flex items-center justify-center text-[#7A6C63] hover:text-[#1F1A18] dark:hover:text-white cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-5 space-y-4" aria-live="polite">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap ${m.role === 'user' ? 'bg-[#F26D5B] text-white rounded-br-md' : 'bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 rounded-bl-md'}`}>
                {m.text}
                {!!m.warnings?.length && (
                  <ul className="mt-2 list-disc list-inside text-xs text-amber-700 dark:text-amber-300 space-y-0.5">
                    {m.warnings.map((w) => <li key={w}>{w}</li>)}
                  </ul>
                )}
              </div>
            </div>
          ))}

          {!draft && !busy && (
            <div className="flex flex-wrap gap-1.5" aria-label="Example ideas">
              {EXAMPLE_IDEAS.map((ex) => (
                <button key={ex.label} type="button" className={chip(false)} onClick={() => send(ex.idea)}>{ex.label}</button>
              ))}
            </div>
          )}

          {draft && !done && (
            <DraftCard draft={draft} busy={!!busy} onPatch={patch} onImage={image} onPublish={() => setPublishing(true)} onAdvanced={() => onAdvanced(draft)} onAsk={send} />
          )}
          {done && <p role="status" className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-800 dark:text-emerald-300 text-sm font-semibold">{done}</p>}

          {busy && (
            <p role="status" className="flex items-center gap-2 text-xs text-[#7A6C63] dark:text-slate-400">
              <span className="w-3.5 h-3.5 border-2 border-[#F26D5B] border-t-transparent rounded-full animate-spin" />{busy}
            </p>
          )}
          <ErrorBox message={error} />
          <div ref={endRef} />
        </div>

        <div className="px-4 sm:px-6 py-3 border-t border-[#EDE6DD] dark:border-white/10 space-y-2 shrink-0">
          {draft && !done && (
            <div className="flex flex-wrap gap-1.5" aria-label="Suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" disabled={!!busy} className={chip(false)} onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          )}
          <form
            className="flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <textarea
              aria-label="Message"
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              placeholder={draft ? 'Tell me what to change, e.g. "budget 200 and add Secunderabad"' : 'e.g. 50% off on tiffins above ₹500 in Hyderabad, https://…'}
              className="flex-1 resize-none max-h-32 px-4 py-3 border-b border-[#EDE6DD] dark:border-white/10 text-sm focus:outline-none focus:ring-2 focus:ring-[#F26D5B]/30"
            />
            <button type="submit" aria-label="Send" disabled={!!busy || !input.trim()} className="w-11 h-11 rounded-full bg-[#F26D5B] hover:bg-[#E05C4A] text-white flex items-center justify-center cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shrink-0">
              <ArrowUp className="w-5 h-5" />
            </button>
          </form>
          {draft && !draft.image_url && (
            <p className="text-[11px] text-[#9C8F85] flex items-center gap-1"><ImageIcon className="w-3 h-3" />No image yet: press New image or Upload.</p>
          )}
        </div>
      </div>

      {publishing && draft && (
        <PublishFlow
          campaign={draft}
          onClose={() => setPublishing(false)}
          onFinished={(outcome) => {
            setPublishing(false);
            onChanged();
            setDone(
              outcome === 'DONE'
                ? 'Submitted and activated on Meta. Meta review and delivery availability still apply.'
                : 'Publishing was discarded. Anything created on Meta was deleted and your draft is kept.',
            );
          }}
        />
      )}
    </div>
  );
}

export default ChatStudio;
