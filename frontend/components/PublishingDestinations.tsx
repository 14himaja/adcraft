'use client';

import React from 'react';
import { AlertCircle, CheckCircle2, Loader2, RefreshCw, Sparkles } from 'lucide-react';
import { PostTarget } from '../lib/api';
import { useMetaConnection } from '../lib/meta';

export type DestinationStatusType =
  | 'IDLE'
  | 'PENDING'
  | 'PUBLISHING'
  | 'PUBLISHED'
  | 'FAILED'
  | 'UNSUPPORTED';

export interface DestinationState {
  status: DestinationStatusType;
  error?: string | null;
  media_id?: string | null;
  post_id?: string | null;
  at?: string | null;
}

export interface PublishingDestinationsProps {
  /** Map of which targets are currently toggled ON/OFF */
  destinations: Record<PostTarget, boolean>;
  /** Callback fired when a toggle switch changes state */
  onChange: (target: PostTarget, enabled: boolean) => void;
  /** Per-target live publishing status, if publishing has started */
  statuses?: Partial<Record<PostTarget, DestinationState>>;
  /** True while the overall publish operation is actively running */
  isPublishing?: boolean;
  /** Independent retry handler for a specific failed destination */
  onRetry?: (target: PostTarget) => void;
  /** Whether controls are disabled */
  disabled?: boolean;
  /** Optional container title, defaults to 'Publishing Destinations' */
  title?: string;
  /** Optional caption/creative notice */
  showCreativeNotice?: boolean;
}

export const DESTINATION_DETAILS: {
  key: PostTarget;
  title: string;
  platform: 'facebook' | 'instagram';
  description: string;
  captionSupportNote: string;
}[] = [
  {
    key: 'facebook_feed',
    title: 'Facebook Feed',
    platform: 'facebook',
    description: 'Publish the ad as a regular post on your connected Facebook Page.',
    captionSupportNote: 'Uses full creative image & caption.',
  },
  {
    key: 'facebook_story',
    title: 'Facebook Story',
    platform: 'facebook',
    description: 'Share the same creative as a Facebook Story, subject to API requirements.',
    captionSupportNote: 'Shares visual creative; captions differ from feed posts.',
  },
  {
    key: 'instagram_feed',
    title: 'Instagram Feed',
    platform: 'instagram',
    description: 'Publish the generated image and caption as an Instagram feed post.',
    captionSupportNote: 'Uses full creative image & caption.',
  },
  {
    key: 'instagram_story',
    title: 'Instagram Story',
    platform: 'instagram',
    description: 'Share the generated creative to Instagram Stories. Caption support differs from feed posts.',
    captionSupportNote: 'Shares visual creative; captions differ from feed posts.',
  },
];

/* Facebook Brand Icon SVG */
export function FacebookIcon({ className = 'w-10 h-10' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <circle cx="24" cy="24" r="24" fill="#1877F2" />
      <path
        d="M29.5 24H25.5V36H20.5V24H18V19.8H20.5V17.2C20.5 13.9 22.1 12 26 12C27.9 12 29.2 12.2 29.2 12.2L28.8 16.3C28.8 16.3 27.5 16.2 26.3 16.2C25 16.2 24.6 16.8 24.6 18V19.8H29.1L28.5 24H29.5Z"
        fill="white"
      />
    </svg>
  );
}

/* Facebook Story / Messenger Gradient Icon SVG */
export function FacebookStoryIcon({ className = 'w-10 h-10' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="fbStoryGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#00C6FF" />
          <stop offset="50%" stopColor="#0078FF" />
          <stop offset="100%" stopColor="#A033FF" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="24" fill="url(#fbStoryGrad)" />
      <path
        d="M24 13C17.4 13 12 17.9 12 24C12 27.5 13.7 30.6 16.4 32.6V37L20.6 34.7C21.7 35 22.8 35.1 24 35.1C30.6 35.1 36 30.2 36 24.1C36 17.9 30.6 13 24 13ZM25.2 27.5L22.1 24.2L16 27.5L22.7 20.4L25.9 23.7L31.9 20.4L25.2 27.5Z"
        fill="white"
      />
    </svg>
  );
}

/* Instagram Feed Icon SVG */
export function InstagramFeedIcon({ className = 'w-10 h-10' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <defs>
        <radialGradient id="igFeedGrad" cx="30%" cy="107%" r="130%">
          <stop offset="0%" stopColor="#fdf497" />
          <stop offset="5%" stopColor="#fdf497" />
          <stop offset="45%" stopColor="#fd5949" />
          <stop offset="60%" stopColor="#d6249f" />
          <stop offset="90%" stopColor="#285AEB" />
        </radialGradient>
      </defs>
      <rect width="48" height="48" rx="14" fill="url(#igFeedGrad)" />
      <rect x="12" y="12" width="24" height="24" rx="7" stroke="white" strokeWidth="2.5" />
      <circle cx="24" cy="24" r="5.5" stroke="white" strokeWidth="2.5" />
      <circle cx="30.5" cy="17.5" r="1.5" fill="white" />
    </svg>
  );
}

/* Instagram Story Icon SVG */
export function InstagramStoryIcon({ className = 'w-10 h-10' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="igStoryGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#F58529" />
          <stop offset="25%" stopColor="#DD2A7B" />
          <stop offset="50%" stopColor="#8134AF" />
          <stop offset="100%" stopColor="#515BD4" />
        </linearGradient>
      </defs>
      <rect width="48" height="48" rx="14" fill="#0B0F19" />
      <circle cx="24" cy="24" r="17" stroke="url(#igStoryGrad)" strokeWidth="3" />
      <rect x="15" y="15" width="18" height="18" rx="5" stroke="white" strokeWidth="2" />
      <circle cx="24" cy="24" r="4.2" stroke="white" strokeWidth="2" />
      <circle cx="28.8" cy="19.2" r="1.2" fill="white" />
    </svg>
  );
}

export function PublishingDestinations({
  destinations,
  onChange,
  statuses = {},
  isPublishing = false,
  onRetry,
  disabled = false,
  title = 'Publishing Destinations',
  showCreativeNotice = true,
}: PublishingDestinationsProps) {
  const { connection } = useMetaConnection();

  const activeCount = Object.values(destinations).filter(Boolean).length;
  const hasPage = Boolean(connection?.page_name || connection?.page_id);
  const hasInstagram = Boolean(connection?.instagram_username);

  return (
    <section className="space-y-4" aria-label="Publishing Destinations Section">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5 pb-2 border-b border-[#EDE6DD] dark:border-white/10">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-[#1F1A18] dark:text-white tracking-tight">
              {title}
            </h3>
            <span
              className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                activeCount > 0
                  ? 'bg-[#FEECE7] text-[#F26D5B] dark:bg-[#F26D5B]/20 dark:text-[#F26D5B]'
                  : 'bg-slate-100 text-slate-500 dark:bg-white/5 dark:text-slate-400'
              }`}
            >
              {activeCount} of 4 selected
            </span>
          </div>
          <p className="text-[11px] text-[#7A6C63] dark:text-slate-400 mt-0.5">
            Choose which destinations receive the generated image and caption upon publishing.
          </p>
        </div>

        {showCreativeNotice && (
          <div className="flex items-center gap-1.5 text-[11px] text-amber-700 dark:text-amber-400/90 bg-amber-50 dark:bg-amber-500/10 px-2.5 py-1 rounded-lg border border-amber-200/50 dark:border-amber-500/20">
            <Sparkles className="w-3 h-3 shrink-0 text-amber-500" />
            <span>Single creative reused across all selected channels</span>
          </div>
        )}
      </div>

      {/* 2-column Grid for desktop, 1-column on mobile */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5" role="group" aria-label="Publishing Destinations List">
        {DESTINATION_DETAILS.map((dest) => {
          const isChecked = !!destinations[dest.key];
          const st = statuses[dest.key];
          const isPublished = st?.status === 'PUBLISHED';
          const isFailed = st?.status === 'FAILED';
          const isTargetPublishing = isPublishing || st?.status === 'PUBLISHING';

          const isFacebook = dest.platform === 'facebook';
          const isConfigured = isFacebook ? hasPage : hasInstagram;
          const accountLabel = isFacebook
            ? (connection?.page_name ? `Page: ${connection.page_name}` : hasPage ? 'Page connected' : 'Facebook Page not connected')
            : (connection?.instagram_username ? `Account: @${connection.instagram_username}` : hasInstagram ? 'Instagram connected' : 'Instagram not connected');

          return (
            <div
              key={dest.key}
              className={`relative rounded-2xl p-4 transition-all border flex flex-col justify-between ${
                isPublished
                  ? 'border-emerald-500/30 bg-emerald-500/5 dark:bg-emerald-950/10'
                  : isFailed
                  ? 'border-rose-500/30 bg-rose-500/5 dark:bg-rose-950/10'
                  : isChecked
                  ? 'border-[#F26D5B]/40 bg-[#FFF9F8] dark:bg-[#141A28] shadow-sm'
                  : 'border-[#EDE6DD] dark:border-white/10 bg-white dark:bg-[#0E1524]/60 hover:border-slate-300 dark:hover:border-white/20'
              }`}
            >
              <div>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="shrink-0">
                      {dest.key === 'facebook_feed' && <FacebookIcon className="w-10 h-10" />}
                      {dest.key === 'facebook_story' && <FacebookStoryIcon className="w-10 h-10" />}
                      {dest.key === 'instagram_feed' && <InstagramFeedIcon className="w-10 h-10" />}
                      {dest.key === 'instagram_story' && <InstagramStoryIcon className="w-10 h-10" />}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <label
                          htmlFor={`toggle-${dest.key}`}
                          className="font-bold text-xs text-[#1F1A18] dark:text-white cursor-pointer select-none"
                        >
                          {dest.title}
                        </label>
                        <span
                          className={`text-[9px] px-1.5 py-0.2 rounded font-medium ${
                            isConfigured
                              ? 'text-emerald-700 bg-emerald-100 dark:text-emerald-400 dark:bg-emerald-900/40'
                              : 'text-amber-700 bg-amber-100 dark:text-amber-400 dark:bg-amber-900/40'
                          }`}
                        >
                          {accountLabel}
                        </span>
                      </div>
                      <p className="text-[11px] text-[#7A6C63] dark:text-slate-400 mt-1 leading-snug">
                        {dest.description}
                      </p>
                    </div>
                  </div>

                  {/* Toggle ON/OFF Switch */}
                  <div className="shrink-0 flex items-center pt-0.5">
                    <label className="relative inline-flex items-center cursor-pointer group">
                      <input
                        id={`toggle-${dest.key}`}
                        type="checkbox"
                        aria-label={dest.title}
                        aria-checked={isChecked}
                        checked={isChecked}
                        disabled={disabled || isTargetPublishing || isPublished}
                        onChange={(e) => onChange(dest.key, e.target.checked)}
                        className="sr-only peer"
                      />
                      <div
                        className={`w-11 h-6 rounded-full transition-colors relative flex items-center ${
                          isChecked
                            ? 'bg-emerald-600 peer-focus:ring-2 peer-focus:ring-emerald-400'
                            : 'bg-slate-300 dark:bg-slate-700 peer-focus:ring-2 peer-focus:ring-slate-400'
                        } ${disabled || isPublished ? 'opacity-70 cursor-not-allowed' : ''}`}
                      >
                        <div
                          className={`w-4 h-4 rounded-full bg-white shadow-md transform transition-transform ${
                            isChecked ? 'translate-x-6' : 'translate-x-1'
                          }`}
                        />
                      </div>
                      <span className="sr-only">{isChecked ? 'ON' : 'OFF'}</span>
                    </label>
                  </div>
                </div>

                <div className="mt-2 text-[10px] text-[#9C8F85] dark:text-slate-400/80">
                  {dest.captionSupportNote}
                </div>
              </div>

              {/* Status reporting & actions */}
              <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-white/5 flex items-center justify-between gap-2 min-h-[28px]">
                {/* State: Publishing in progress */}
                {isTargetPublishing && (
                  <div className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400 font-medium">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Publishing to {dest.title}…</span>
                  </div>
                )}

                {/* State: Published successfully */}
                {!isTargetPublishing && isPublished && (
                  <div className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400 font-semibold">
                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    <span>Published Successfully</span>
                    {st?.media_id && (
                      <span className="text-[10px] font-mono text-slate-400">({st.media_id})</span>
                    )}
                  </div>
                )}

                {/* State: Failed with retry option */}
                {!isTargetPublishing && isFailed && (
                  <div className="w-full flex flex-col gap-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 text-xs text-rose-600 dark:text-rose-400 font-semibold">
                        <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                        <span>Failed to publish</span>
                      </div>
                      {onRetry && (
                        <button
                          type="button"
                          onClick={() => onRetry(dest.key)}
                          disabled={disabled || isPublishing}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-bold rounded-lg bg-rose-500/10 text-rose-700 dark:text-rose-300 hover:bg-rose-500/20 transition-colors"
                        >
                          <RefreshCw className="w-3 h-3" />
                          <span>Retry</span>
                        </button>
                      )}
                    </div>
                    {st?.error && (
                      <p className="text-[11px] text-rose-700 dark:text-rose-300/90 break-words leading-tight">
                        {st.error}
                      </p>
                    )}
                  </div>
                )}

                {/* State: Idle / Pending */}
                {!isTargetPublishing && !isPublished && !isFailed && (
                  <div className="flex items-center justify-between w-full text-[11px]">
                    <span className="text-[#8C7E74] dark:text-slate-400">
                      {isChecked ? 'Ready to publish' : 'Disabled'}
                    </span>
                    {!isConfigured && (
                      <span className="text-amber-600 dark:text-amber-400 font-medium">
                        Requires Configuration
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default PublishingDestinations;
