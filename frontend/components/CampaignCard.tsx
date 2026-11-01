'use client';

import React, { useState } from 'react';
import { AdImage } from './AdImage';
import { RefreshCw, Trash2, Pencil, Send, Play, Pause, ListChecks } from 'lucide-react';
import {
  Campaign,
  CampaignStatus,
  activateCampaign,
  deleteCampaign,
  POST_TARGETS,
  PostResults,
  PostTarget,
  fixIssues,
  pauseCampaign,
  postCampaign,
  refreshInsights,
  resumeCampaign,
} from '../lib/api';
import { Dialog, ErrorBox, btnDanger, btnPrimary, btnSecondary, errorMessage } from './Dialog';
import { PostResultLines, PublishFlow, publishBlockReason, rupees } from './PublishFlow';

export const STATUS_BADGES: Record<CampaignStatus, [string, string]> = {
  DRAFT: ['Draft', 'bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/30'],
  PUBLISHING: ['Publishing', 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/30'],
  PUBLISH_FAILED: ['Publish failed', 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/30'],
  PAUSED_ON_META: ['Paused on Meta', 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30'],
  ACTIVE: ['Active', 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30'],
  PAUSED: ['Paused', 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30'],
  COMPLETED: ['Completed', 'bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/30'],
};

export function StatusBadge({ status }: { status: CampaignStatus }) {
  const [label, cls] = STATUS_BADGES[status] ?? [status, STATUS_BADGES.DRAFT[1]];
  return (
    <span data-testid="status-badge" className={`inline-flex px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${cls}`}>
      {label}
    </span>
  );
}

const SPEND_OFF = 'Real spend is off (SAFE_MODE_NO_SPEND / ALLOW_REAL_AD_SPEND)';
const ON_META: CampaignStatus[] = ['PAUSED_ON_META', 'ACTIVE', 'PAUSED', 'COMPLETED'];

interface CampaignCardProps {
  campaign: Campaign;
  onEdit: (id: string, campaign?: Campaign) => void;
  onChanged: () => void;
}

export function CampaignCard({ campaign: c, onEdit, onChanged }: CampaignCardProps) {
  const [dialog, setDialog] = useState<'publish' | 'activate' | 'delete' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [understood, setUnderstood] = useState(false);
  const [fixResult, setFixResult] = useState<{ fixed: string[]; manual: string[] } | null>(null);
  const [postResults, setPostResults] = useState<PostResults | null>(null);

  const post = (target: PostTarget, label: string) => {
    if (c.posted?.[target] && !window.confirm(`${label} was already posted. Post it again?`)) return;
    return run(async () => setPostResults((await postCampaign(c.id, [target])).results));
  };
  const v =c.variants?.[c.selected_variant] ?? c.variants?.[0];
  const ins = c.insights;
  const publishReason = publishBlockReason(c);
  const failure = c.status === 'PUBLISH_FAILED' ? c.publish?.error?.message : null;
  const problems = [...(ON_META.includes(c.status) ? (c.meta?.issues ?? []) : []), ...(failure ? [failure] : [])];

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setDialog(null);
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const action = (label: string, icon: React.ReactNode, onClick: () => void, opts: { disabled?: boolean; title?: string; describedBy?: string } = {}) => (
    <button
      type="button"
      onClick={onClick}
      disabled={busy || opts.disabled}
      title={opts.title}
      aria-describedby={opts.describedBy}
      className={btnSecondary}
    >
      {icon}
      <span>{label}</span>
    </button>
  );

  const spendBlocked = !c.can_activate;
  const stats: [string, string][] = [
    ['Impressions', (ins?.impressions ?? 0).toLocaleString('en-IN')],
    ['Reach', (ins?.reach ?? 0).toLocaleString('en-IN')],
    ['Clicks', (ins?.clicks ?? 0).toLocaleString('en-IN')],
    ['CTR', `${(ins?.ctr ?? 0).toFixed(2)}%`],
    ['Spend', rupees((ins?.spend_minor ?? 0) / 100)],
  ];

  return (
    <div className="border-b border-[#EDE6DD] dark:border-white/10 flex flex-col">
      <div className="flex gap-3 p-4">
        <div className="relative w-16 h-16 shrink-0 rounded-xl overflow-hidden bg-gradient-to-tr from-[#FAF8F5] to-[#FEECE7] dark:from-slate-900 dark:to-slate-800">
          {c.image_url && <AdImage src={c.image_url} alt={`${c.title} image`} fill className="object-cover" />}
        </div>
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2">
            <StatusBadge status={c.status} />
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#F26D5B]">{c.objective}</span>
          </div>
          <h4 className="text-sm font-extrabold text-[#1F1A18] dark:text-white line-clamp-1">{c.title || 'Untitled ad'}</h4>
          <p className="text-[11px] text-[#7A6C63] dark:text-slate-400 line-clamp-1">{v?.headline || 'No ad text yet'}</p>
          <p className="text-[11px] text-[#8C7E74] dark:text-slate-500">
            ₹{c.daily_budget ?? 0}/day{c.start_date ? ` · ${c.start_date} → ${c.end_date ?? '?'}` : ''}
          </p>
        </div>
      </div>

      <dl className="px-4 pb-3 grid grid-cols-5 gap-1 text-left">
        {stats.map(([k, val]) => (
          <div key={k}>
            <dt className="text-[9px] uppercase font-semibold text-[#8C7E74] dark:text-slate-400">{k}</dt>
            <dd className="text-xs font-bold text-[#1F1A18] dark:text-white">{val}</dd>
          </div>
        ))}
      </dl>

      {(problems.length > 0 || fixResult) && (
        <div role="alert" className="mx-4 mb-3 text-xs text-rose-700 dark:text-rose-300 space-y-1">
          {problems.length > 0 && (
            <>
              <p className="font-bold">Meta says this ad cannot deliver yet:</p>
              <ul className="list-disc pl-4">
                {problems.map((issue) => <li key={issue}>{issue}</li>)}
              </ul>
              <button type="button" disabled={busy} className={btnPrimary} onClick={() => run(async () => setFixResult(await fixIssues(c.id)))}>
                Fix with AI
              </button>
            </>
          )}
          {fixResult?.fixed.map((line) => <p key={line} className="text-emerald-700 dark:text-emerald-300">Fixed: {line}</p>)}
          {fixResult?.manual.map((line) => <p key={line}>You need to do this: {line}</p>)}
          <p>
            <a href="/meta-ad-requirements.md" download className="underline font-semibold">Download the ad requirements checklist</a>
          </p>
        </div>
      )}

      {ON_META.includes(c.status) && c.image_url && (
        <div className="px-4 pb-3 space-y-1.5">
          <p className="text-[10px] uppercase font-semibold text-[#8C7E74] dark:text-slate-400">Post as a normal post (free, public)</p>
          <div className="flex flex-wrap gap-1.5">
            {POST_TARGETS.map(([key, label]) => (
              <button key={key} type="button" disabled={busy} className={btnSecondary} onClick={() => post(key, label)}>
                {c.posted?.[key] ? `✓ ${label}` : label}
              </button>
            ))}
          </div>
          <PostResultLines results={postResults} />
        </div>
      )}

      <div className="px-4 pb-3"><ErrorBox message={dialog ? null : error} /></div>

      <div className="mt-auto p-3 border-t border-[#EDE6DD]/70 dark:border-white/5 bg-[#FAF8F5]/60 dark:bg-black/20 flex flex-wrap gap-1.5">
        {c.status === 'DRAFT' ? (
          <>
            {action('Edit', <Pencil className="w-3.5 h-3.5" />, () => onEdit(c.id, c))}
            {action('Publish', <Send className="w-3.5 h-3.5" />, () => setDialog('publish'), {
              disabled: !!publishReason,
              title: publishReason ?? undefined,
              describedBy: publishReason ? `publish-reason-${c.id}` : undefined,
            })}
            {publishReason && <span id={`publish-reason-${c.id}`} className="sr-only">{publishReason}</span>}
          </>
        ) : (
          action('View / Edit', <Pencil className="w-3.5 h-3.5" />, () => onEdit(c.id, c))
        )}
        {(c.status === 'PUBLISHING' || c.status === 'PUBLISH_FAILED') &&
          action('View progress', <ListChecks className="w-3.5 h-3.5" />, () => setDialog('publish'))}
        {c.status === 'PAUSED_ON_META' &&
          action('Activate', <Play className="w-3.5 h-3.5" />, () => { setUnderstood(false); setDialog('activate'); }, {
            disabled: spendBlocked,
            title: spendBlocked ? SPEND_OFF : undefined,
          })}
        {c.status === 'ACTIVE' && action('Pause', <Pause className="w-3.5 h-3.5" />, () => run(() => pauseCampaign(c.id)))}
        {c.status === 'PAUSED' &&
          action('Resume', <Play className="w-3.5 h-3.5" />, () => run(() => resumeCampaign(c.id)), {
            disabled: spendBlocked,
            title: spendBlocked ? SPEND_OFF : undefined,
          })}
        {ON_META.includes(c.status) &&
          action('Refresh insights', <RefreshCw className="w-3.5 h-3.5" />, () => run(() => refreshInsights(c.id)))}
        <button type="button" onClick={() => setDialog('delete')} disabled={busy} className={`${btnSecondary} ml-auto hover:text-rose-600`}>
          <Trash2 className="w-3.5 h-3.5" />
          <span>Delete</span>
        </button>
      </div>

      {dialog === 'publish' && <PublishFlow campaign={c} onClose={() => setDialog(null)} onFinished={onChanged} />}

      {dialog === 'activate' && (
        <Dialog title="Activate campaign" onClose={() => setDialog(null)}>
          <p className="text-xs leading-relaxed">
            Activating starts real delivery on Instagram and spends up to <strong>₹{c.daily_budget ?? 0}/day</strong> from
            your Meta ad account until {c.end_date ?? 'the end date'}. You can pause it at any time.
          </p>
          <label className="flex items-center gap-2 text-xs font-semibold">
            <input type="checkbox" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} />
            I understand this spends money
          </label>
          <ErrorBox message={error} />
          <div className="flex justify-end gap-2">
            <button type="button" className={btnSecondary} onClick={() => setDialog(null)}>Cancel</button>
            <button type="button" className={btnPrimary} disabled={!understood || busy} onClick={() => run(() => activateCampaign(c.id))}>
              Activate and spend
            </button>
          </div>
        </Dialog>
      )}

      {dialog === 'delete' && (
        <Dialog title="Delete campaign" onClose={() => setDialog(null)}>
          <p className="text-xs leading-relaxed">
            Delete <strong>{c.title || 'this draft'}</strong>? If it was published, its ad, creative, ad set and campaign are
            also deleted on Meta. This cannot be undone.
          </p>
          <ErrorBox message={error} />
          <div className="flex justify-end gap-2">
            <button type="button" className={btnSecondary} onClick={() => setDialog(null)}>Cancel</button>
            <button type="button" className={btnDanger} disabled={busy} onClick={() => run(() => deleteCampaign(c.id))}>
              Delete permanently
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}

export default CampaignCard;
