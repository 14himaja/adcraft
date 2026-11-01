'use client';

import React, { useEffect, useRef, useState } from 'react';
import { AdImage } from './AdImage';
import useSWR from 'swr';
import {
  Campaign,
  POST_TARGETS,
  PostResults,
  PostTarget,
  PublishBlock,
  discardPublish,
  fetcher,
  postCampaign,
  publishCampaign,
  publishPath,
  resumePublish,
} from '../lib/api';
import { useMetaConnection } from '../lib/meta';
import { Dialog, ErrorBox, btnDanger, btnPrimary, btnSecondary, errorMessage } from './Dialog';
import { PublishingDestinations } from './PublishingDestinations';

const FIELD_LABELS: Record<string, string> = {
  title: 'title',
  objective: 'objective',
  landing_url: 'landing URL',
  audience: 'audience location',
  daily_budget: 'daily budget',
  start_date: 'start date',
  end_date: 'end date',
  variants: 'a valid ad text',
  image_id: 'image',
};
export const fieldLabel = (f: string) => FIELD_LABELS[f] ?? f.replace(/_/g, ' ');

/** Why a draft can't be published yet, or null when it can. */
export function publishBlockReason(c: Campaign): string | null {
  if (c.can_publish) return null;
  if (c.missing_fields?.length) return `Fill the missing fields: ${c.missing_fields.map(fieldLabel).join(', ')}`;
  return c.warnings?.[0] ?? 'This draft cannot be published yet.';
}

export const rupees = (n: number | null | undefined) =>
  `₹${(n ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const STEPS = [
  ['CAMPAIGN', 'Campaign'],
  ['ADSET', 'Ad set'],
  ['IMAGE', 'Image'],
  ['CREATIVE', 'Creative'],
  ['AD', 'Ad'],
] as const;

interface PublishFlowProps {
  campaign: Campaign;
  onClose: () => void;
  /** Called when publishing finishes (DONE) or is discarded, so lists can refresh. */
  onFinished: (outcome: 'DONE' | 'DISCARDED') => void;
  /** Whether to render destination selector in confirm dialog. Defaults to true. */
  showDestinationSelector?: boolean;
}

/** What happened to each normal post, one line per target. */
export function PostResultLines({
  results,
  onRetry,
}: {
  results: PostResults | null;
  onRetry?: (target: PostTarget) => void;
}) {
  if (!results) return null;
  const label = Object.fromEntries(POST_TARGETS);
  return (
    <div className="p-3 rounded-2xl bg-[#FAF8F5] dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 space-y-2">
      <div className="flex items-center justify-between">
        <span className="font-bold text-xs">Publishing Destinations Results</span>
      </div>
      <ul className="space-y-1.5 text-xs" aria-label="Post results">
        {Object.entries(results).map(([target, r]) => (
          <li
            key={target}
            className={`flex items-center justify-between p-2 rounded-xl border ${
              r.status === 'PUBLISHED'
                ? 'bg-emerald-500/5 border-emerald-500/20 text-emerald-700 dark:text-emerald-300'
                : 'bg-rose-500/5 border-rose-500/20 text-rose-700 dark:text-rose-400'
            }`}
          >
            <span>
              {r.status === 'PUBLISHED'
                ? `✓ ${label[target] ?? target}: posted`
                : `✗ ${label[target] ?? target}: ${r.error}`}
            </span>
            {r.status === 'FAILED' && onRetry && (
              <button
                type="button"
                onClick={() => onRetry(target as PostTarget)}
                className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 hover:bg-rose-500/30 text-rose-800 dark:text-rose-200 cursor-pointer"
              >
                Retry
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function PublishFlow({
  campaign,
  onClose,
  onFinished,
  showDestinationSelector = true,
}: PublishFlowProps) {
  const [phase, setPhase] = useState<'confirm' | 'progress'>(campaign.status === 'DRAFT' ? 'confirm' : 'progress');
  const [posts, setPosts] = useState<PostResults | null>(null);

  const handleRetryPost = async (target: PostTarget) => {
    try {
      const res = await postCampaign(campaign.id, [target]);
      setPosts((prev) => ({ ...(prev || {}), ...res.results }));
    } catch (e) {
      setPosts((prev) => ({
        ...(prev || {}),
        [target]: { status: 'FAILED' as const, error: errorMessage(e) },
      }));
    }
  };

  return (
    <Dialog title="Publish and start Instagram ad" onClose={onClose}>
      {phase === 'confirm' ? (
        <ConfirmPublish
          campaign={campaign}
          showDestinationSelector={showDestinationSelector}
          onCancel={onClose}
          onStarted={(r) => {
            setPosts(r);
            setPhase('progress');
          }}
        />
      ) : (
        <>
          <PostResultLines results={posts} onRetry={handleRetryPost} />
          <PublishProgress campaignId={campaign.id} onClose={onClose} onFinished={onFinished} />
        </>
      )}
    </Dialog>
  );
}

function ConfirmPublish({
  campaign,
  showDestinationSelector = true,
  onCancel,
  onStarted,
}: {
  campaign: Campaign;
  showDestinationSelector?: boolean;
  onCancel: () => void;
  onStarted: (posts: PostResults | null) => void;
}) {
  const { connection } = useMetaConnection();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [targets, setTargets] = useState<PostTarget[]>(() => {
    const d = campaign.publishing_destinations;
    if (!d) return [];
    return (Object.keys(d) as PostTarget[]).filter((k) => d[k]);
  });

  const destinationMap: Record<PostTarget, boolean> = {
    facebook_feed: targets.includes('facebook_feed'),
    facebook_story: targets.includes('facebook_story'),
    instagram_feed: targets.includes('instagram_feed'),
    instagram_story: targets.includes('instagram_story'),
  };
  const v = campaign.variants?.[campaign.selected_variant] ?? campaign.variants?.[0];
  const selectedPlaces = campaign.audience.cities?.length
    ? campaign.audience.cities.map((city) => city.name).join(', ')
    : campaign.audience.countries.join(', ');
  const audienceSummary = [
    `Ages ${campaign.audience.age_min}–${campaign.audience.age_max}`,
    selectedPlaces,
    campaign.audience.interests?.length
      ? `Interests: ${campaign.audience.interests.map((interest) => interest.name).join(', ')}`
      : null,
  ].filter(Boolean).join(' · ');
  const reason = connection?.status !== 'ACTIVE'
    ? 'Connect Meta first (Meta Connection in the sidebar).'
    : campaign.live_delivery_enabled === false
      ? 'Live ad delivery is disabled on this server. Enable live delivery in the server environment before publishing.'
      : publishBlockReason(campaign);

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await publishCampaign(campaign.id);
      let posts: PostResults | null = null;
      if (targets.length) {
        // The posts are separate from the ad: a refused post must not hide that the ad has started.
        posts = await postCampaign(campaign.id, targets).then((r) => r.results, (e) => ({ error: { status: 'FAILED' as const, error: errorMessage(e) } }));
      }
      onStarted(posts);
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  };

  const rows: [string, React.ReactNode][] = [
    ['Ad account', connection?.ad_account_name ? `${connection.ad_account_name} (${connection.ad_account_id})` : connection?.ad_account_id ?? '—'],
    ['Facebook Page', connection?.page_name ?? connection?.page_id ?? '—'],
    ['Instagram', connection?.instagram_username ? `@${connection.instagram_username}` : '—'],
    ['Audience filters', audienceSummary],
    ['Placements', 'Instagram'],
    ['Budget', `₹${campaign.daily_budget ?? 0}/day`],
    ['Dates', `${campaign.start_date ?? '?'} → ${campaign.end_date ?? '?'}`],
    ['Headline', v?.headline],
    ['Text', v?.primary_text],
    ['Description', v?.description],
    ['Selected Hashtags', campaign.selected_hashtags?.length ? campaign.selected_hashtags.join(' ') : '—'],
    ['Button', v?.call_to_action?.replace(/_/g, ' ')],
  ];

  return (
    <div className="space-y-4 text-xs">
      <p className="text-[#7A6C63] dark:text-slate-400">
        This creates a sponsored Instagram ad using the connected account as its identity. It does not publish a regular post to that account’s profile.
        Meta uses the audience filters below to decide who is eligible to see the ad, then its ad auction determines delivery; not every eligible person is guaranteed an impression.
        Meta charges the connected ad account up to the daily budget shown below once the ad is approved and delivers.
        The ad account must have an active payment method in Meta Ads Manager.
      </p>
      <div className="flex gap-4">
        {campaign.image_url && (
          <div className="relative w-28 h-28 shrink-0 rounded-xl overflow-hidden bg-slate-100 dark:bg-slate-900">
            <AdImage src={campaign.image_url} alt="Ad image" fill className="object-cover" />
          </div>
        )}
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          {rows.map(([k, val]) => (
            <React.Fragment key={k}>
              <dt className="font-semibold text-[#7A6C63] dark:text-slate-400">{k}</dt>
              <dd className="font-semibold break-words">{val}</dd>
            </React.Fragment>
          ))}
        </dl>
      </div>

      {/* Publishing Preview */}
      <div className="p-3.5 rounded-2xl bg-[#FAF8F5] dark:bg-[#0E1524] border border-[#EDE6DD] dark:border-white/10 space-y-2.5">
        <div className="flex items-center justify-between">
          <span className="font-bold text-xs text-[#1F1A18] dark:text-white">Publishing Preview</span>
          <span className="text-[10px] text-[#7A6C63] dark:text-slate-400">Destination-Aware Format</span>
        </div>

        <div className="space-y-1">
          <span className="text-[10px] uppercase font-bold text-[#7A6C63] dark:text-slate-400 tracking-wider">Caption Text</span>
          <p className="p-2.5 rounded-xl bg-white dark:bg-black/30 border border-[#EDE6DD] dark:border-white/5 whitespace-pre-wrap text-xs">
            {v?.headline && v?.primary_text
              ? `${v.headline}\n\n${v.primary_text}`
              : v?.primary_text || v?.headline || '(No caption text)'}
          </p>
        </div>

        {campaign.selected_hashtags && campaign.selected_hashtags.length > 0 && (
          <div className="space-y-1">
            <span className="text-[10px] uppercase font-bold text-[#7A6C63] dark:text-slate-400 tracking-wider">Selected Hashtags ({campaign.selected_hashtags.length}/5)</span>
            <div className="flex flex-wrap gap-1.5 p-2 rounded-xl bg-white dark:bg-black/30 border border-[#EDE6DD] dark:border-white/5">
              {campaign.selected_hashtags.map((tag) => (
                <span key={tag} className="text-[#F26D5B] font-semibold text-xs">{tag}</span>
              ))}
            </div>
          </div>
        )}

        {targets.length > 0 && (
          <div className="space-y-1 pt-1">
            <span className="text-[10px] uppercase font-bold text-[#7A6C63] dark:text-slate-400 tracking-wider">Publishing Destinations Breakdown</span>
            <ul className="space-y-1 text-xs">
              {targets.map((target) => {
                const isFeed = target === 'facebook_feed' || target === 'instagram_feed';
                const label = target === 'facebook_feed' ? 'Facebook Feed'
                  : target === 'facebook_story' ? 'Facebook Story'
                  : target === 'instagram_feed' ? 'Instagram Feed'
                  : 'Instagram Story';
                return (
                  <li key={target} className="p-2 rounded-xl bg-white dark:bg-black/30 border border-[#EDE6DD] dark:border-white/5 flex items-center justify-between">
                    <span className="font-semibold">{label}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                      isFeed
                        ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300'
                        : 'bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300'
                    }`}>
                      {isFeed
                        ? (campaign.selected_hashtags?.length ? 'Published with Caption & Hashtags' : 'Published with Caption')
                        : 'Visual Creative Only (Stories API ignores captions/hashtags)'}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>

      {showDestinationSelector && (
        <PublishingDestinations
          destinations={destinationMap}
          onChange={(target, enabled) => {
            setTargets((prev) => (enabled ? (prev.includes(target) ? prev : [...prev, target]) : prev.filter((t) => t !== target)));
          }}
          disabled={busy}
          title="Publishing Destinations"
        />
      )}
      <ErrorBox message={error} />
      <div className="flex justify-end gap-2">
        <button type="button" className={btnSecondary} onClick={onCancel}>
          Cancel
        </button>
        <button
          type="button"
          className={btnPrimary}
          onClick={confirm}
          disabled={busy || !!reason}
          aria-describedby={reason ? 'publish-reason' : undefined}
        >
          {busy ? 'Starting…' : 'Publish and start ad'}
        </button>
      </div>
      {reason && (
        <p id="publish-reason" className="text-[11px] text-amber-700 dark:text-amber-400 text-right">
          {reason}
        </p>
      )}
    </div>
  );
}

function PublishProgress({ campaignId, onClose, onFinished }: { campaignId: string; onClose: () => void; onFinished: PublishFlowProps['onFinished'] }) {
  const { data, mutate } = useSWR<PublishBlock>(publishPath(campaignId), fetcher, {
    refreshInterval: (latest) => (latest && latest.status !== 'RUNNING' ? 0 : 1500),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const status = data?.status;

  const finished = useRef(onFinished);
  useEffect(() => {
    finished.current = onFinished;
  });
  useEffect(() => {
    if (status === 'DONE') finished.current('DONE');
  }, [status]);

  const act = async (fn: () => Promise<unknown>, after: () => void) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      after();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 text-xs">
      <ol className="space-y-1.5" aria-label="Publish steps">
        {STEPS.map(([name, label]) => {
          const s = data?.steps?.find((x) => x.name === name);
          const icon = s?.status === 'DONE' ? '✓' : s?.status === 'FAILED' ? '✗' : '○';
          const color = icon === '✓' ? 'text-emerald-600' : icon === '✗' ? 'text-rose-600' : 'text-[#9C8F85]';
          return (
            <li key={name} className="flex items-center gap-2 p-2 rounded-xl bg-[#FAF8F5] dark:bg-[#0F172A]">
              <span className={`w-4 text-center font-bold ${color}`} aria-hidden="true">{icon}</span>
              <span className="font-semibold">{label}</span>
              <span className="sr-only">{s?.status ?? 'PENDING'}</span>
              {s?.status === 'RUNNING' && <span className="text-[#9C8F85]">working…</span>}
              {s?.meta_object_id && <code className="ml-auto text-[10px] text-[#7A6C63] dark:text-slate-400">{s.meta_object_id}</code>}
            </li>
          );
        })}
      </ol>

      {!data && <p role="status">Checking progress…</p>}
      {status === 'DONE' && (
        <p role="status" className="p-3 rounded-xl bg-emerald-500/10 text-emerald-800 dark:text-emerald-300 font-semibold">
          Submitted and activated on Meta. Meta review and delivery availability still apply; billing is handled by your connected ad account.
        </p>
      )}
      {status === 'FAILED' && (
        <div className="space-y-2">
          <div role="alert" className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-700 dark:text-rose-400 font-semibold">
            {data?.error?.message ?? 'Publishing failed.'}
          </div>
          {/(payment|billing|funds)/i.test(data?.error?.message ?? '') && (
            <p className="text-[11px] text-[#7A6C63] dark:text-slate-400">
              Fix billing for the selected ad account in Meta Ads Manager under Billing &amp; payments, then choose Resume publishing.
            </p>
          )}
        </div>
      )}
      <ErrorBox message={error} />

      <div className="flex justify-end gap-2">
        {status === 'FAILED' && (
          <>
            <button type="button" className={btnDanger} disabled={busy} onClick={() => act(() => discardPublish(campaignId), () => { onFinished('DISCARDED'); onClose(); })}>
              Discard (delete what was created)
            </button>
            <button type="button" className={btnPrimary} disabled={busy} onClick={() => act(() => resumePublish(campaignId), () => mutate())}>
              Resume publishing
            </button>
          </>
        )}
        {status !== 'FAILED' && (
          <button type="button" className={btnSecondary} onClick={onClose}>
            {status === 'DONE' ? 'Done' : 'Hide (keeps running)'}
          </button>
        )}
      </div>
    </div>
  );
}

export default PublishFlow;
