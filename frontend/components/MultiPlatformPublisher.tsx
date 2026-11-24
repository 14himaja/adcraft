'use client';

import React, { useMemo, useState } from 'react';
import useSWR from 'swr';
import {
  AlertCircle,
  AlertTriangle,
  Calendar,
  Check,
  CheckCircle2,
  Clock,
  ExternalLink,
  Film,
  Heart,
  Image as ImageIcon,
  Link2,
  Loader2,
  MessageCircle,
  MessageSquare,
  RefreshCw,
  Repeat,
  Send,
  Share2,
  Sparkles,
  ThumbsUp,
  X as CloseIcon,
} from 'lucide-react';
import {
  MediaItem,
  fetcher,
  generateOrganicImage,
  imageUrl,
  uploadOrganicImage,
} from '../lib/api';
import {
  previewMultiPublish,
  publishMultiPlatform,
  usePublishHistory,
  useSocialConnections,
} from '../lib/integrations';
import {
  MultiPublishPreviewItem,
  MultiPublishResultItem,
  SocialPlatformId,
} from '../lib/types';
import { AdImage } from './AdImage';
import { ErrorBox, btnPrimary, btnSecondary, errorMessage, inputCls, labelCls } from './Dialog';
import { HashtagSelector } from './HashtagSelector';
import { PlatformLogo } from './PlatformIcons';

interface MultiPlatformPublisherProps {
  onOpenConnections?: () => void;
}

export function MultiPlatformPublisher({ onOpenConnections }: MultiPlatformPublisherProps) {
  const { platforms, mutate: mutateConns } = useSocialConnections();
  const { data: media, mutate: mutateMedia } = useSWR<MediaItem[]>('/v1/media', fetcher);
  const { history, mutate: mutateHistory } = usePublishHistory();

  // Step 1: Content
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [linkUrl, setLinkUrl] = useState('');
  const [imageId, setImageId] = useState<string | null>(null);
  const [imagePrompt, setImagePrompt] = useState('');
  const [hashtags, setHashtags] = useState<string[]>([]);
  const [targetOverrides, setTargetOverrides] = useState<Record<string, string>>({});

  // Step 2: Selected Platforms
  const [selectedPlatforms, setSelectedPlatforms] = useState<SocialPlatformId[]>([]);

  // Step 3: Previews
  const [previews, setPreviews] = useState<Record<string, MultiPublishPreviewItem> | null>(null);

  // Step 4: Scheduling & Results
  const [isScheduled, setIsScheduled] = useState(false);
  const [scheduledAt, setScheduledAt] = useState('');
  const [results, setResults] = useState<Record<string, MultiPublishResultItem> | null>(null);
  const [retryingPlatform, setRetryingPlatform] = useState<SocialPlatformId | null>(null);

  const [busy, setBusy] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const connectedPlatforms = useMemo(
    () => platforms.filter((p) => p.status === 'ACTIVE'),
    [platforms]
  );

  const togglePlatform = (pid: SocialPlatformId) => {
    setSelectedPlatforms((prev) =>
      prev.includes(pid) ? prev.filter((x) => x !== pid) : [...prev, pid]
    );
    setPreviews(null);
  };

  const handleImageAction = async (make: () => Promise<MediaItem>) => {
    setBusy(true);
    setError(null);
    try {
      const item = await make();
      setImageId(item.id);
      await mutateMedia();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const handlePreview = async () => {
    if (selectedPlatforms.length === 0) return;
    setPreviewBusy(true);
    setError(null);
    try {
      const res = await previewMultiPublish({
        platforms: selectedPlatforms,
        text,
        title: title.trim() || undefined,
        link_url: linkUrl.trim() || undefined,
        image_id: imageId || undefined,
        hashtags,
        targets: targetOverrides,
        scheduled_at: isScheduled && scheduledAt ? new Date(scheduledAt).toISOString() : undefined,
      });
      setPreviews(res.previews);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setPreviewBusy(false);
    }
  };

  const handlePublish = async (platformsToPublish = selectedPlatforms) => {
    if (platformsToPublish.length === 0) return;
    setBusy(true);
    setError(null);
    if (platformsToPublish === selectedPlatforms) {
      setResults(null);
    }
    try {
      const res = await publishMultiPlatform({
        platforms: platformsToPublish,
        text,
        title: title.trim() || undefined,
        link_url: linkUrl.trim() || undefined,
        image_id: imageId || undefined,
        hashtags,
        targets: targetOverrides,
        scheduled_at: isScheduled && scheduledAt ? new Date(scheduledAt).toISOString() : undefined,
      });
      setResults((prev) => ({
        ...(prev || {}),
        ...res.results,
      }));
      await Promise.all([mutateHistory(), mutateConns()]);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const handleRetryPlatform = async (platformId: SocialPlatformId) => {
    setRetryingPlatform(platformId);
    setError(null);
    try {
      await handlePublish([platformId]);
    } finally {
      setRetryingPlatform(null);
    }
  };

  // Determine strictest character limit
  const selectedPlatformObjs = useMemo(
    () => platforms.filter((p) => selectedPlatforms.includes(p.platform)),
    [platforms, selectedPlatforms]
  );

  const minCharLimit = useMemo(() => {
    if (selectedPlatformObjs.length === 0) return 3000;
    return Math.min(...selectedPlatformObjs.map((p) => p.capabilities.max_text_length));
  }, [selectedPlatformObjs]);

  return (
    <div className="space-y-8 max-w-5xl" data-testid="multi-platform-publisher">
      {/* Header */}
      <div className="rounded-3xl bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 p-6 shadow-2xs dark:shadow-xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <h2 className="text-xl sm:text-2xl font-extrabold text-[#1F1A18] dark:text-white tracking-tight">
                Publish Posts
              </h2>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20">
                Multi-Platform Studio
              </span>
            </div>
            <p className="text-xs sm:text-sm text-[#7A6C63] dark:text-slate-400 mt-1">
              Platform-independent publishing composer. Compose your message once, customize for Facebook, Instagram, LinkedIn and future platforms, preview in real time, and publish or schedule.
            </p>
          </div>
          {onOpenConnections && (
            <button
              type="button"
              onClick={onOpenConnections}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-[#EDE6DD] dark:border-white/10 text-xs font-semibold hover:bg-black/5 dark:hover:bg-white/5 cursor-pointer self-start sm:self-center transition-colors"
            >
              <Link2 className="w-3.5 h-3.5 text-[#F26D5B]" />
              <span>Manage Accounts ({connectedPlatforms.length})</span>
            </button>
          )}
        </div>

        {/* Workflow Progress Breadcrumb */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-6 mt-6 border-t border-[#EDE6DD] dark:border-white/10">
          <div className="flex items-center gap-2 text-xs font-bold text-[#F26D5B]">
            <span className="w-5 h-5 rounded-full bg-[#F26D5B] text-white flex items-center justify-center text-[10px]">1</span>
            <span>Compose Content</span>
          </div>
          <div className={`flex items-center gap-2 text-xs font-bold ${selectedPlatforms.length > 0 ? 'text-[#F26D5B]' : 'text-[#7A6C63] dark:text-slate-500'}`}>
            <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] ${selectedPlatforms.length > 0 ? 'bg-[#F26D5B] text-white' : 'bg-black/10 dark:bg-white/10'}`}>2</span>
            <span>Select Accounts</span>
          </div>
          <div className={`flex items-center gap-2 text-xs font-bold ${previews ? 'text-[#F26D5B]' : 'text-[#7A6C63] dark:text-slate-500'}`}>
            <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] ${previews ? 'bg-[#F26D5B] text-white' : 'bg-black/10 dark:bg-white/10'}`}>3</span>
            <span>Platform Preview</span>
          </div>
          <div className={`flex items-center gap-2 text-xs font-bold ${results ? 'text-emerald-600 dark:text-emerald-400' : 'text-[#7A6C63] dark:text-slate-500'}`}>
            <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] ${results ? 'bg-emerald-600 text-white' : 'bg-black/10 dark:bg-white/10'}`}>4</span>
            <span>Publish / Results</span>
          </div>
        </div>
      </div>

      {/* Step 1: Compose Content */}
      <section className="p-6 rounded-3xl bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 space-y-5 shadow-2xs">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-extrabold text-[#1F1A18] dark:text-white flex items-center gap-2">
            <span className="w-6 h-6 rounded-lg bg-[#F26D5B]/10 text-[#F26D5B] flex items-center justify-center text-xs font-bold">1</span>
            <span>Compose Content</span>
          </h3>
          <span className="text-xs text-[#7A6C63] dark:text-slate-400">
            {text.length} / {minCharLimit.toLocaleString()} characters
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="mp-title" className={labelCls}>
              Post Title <span className="font-normal text-[#9C8F85] dark:text-slate-400">(Optional article or headline for LinkedIn)</span>
            </label>
            <input
              id="mp-title"
              className={inputCls}
              maxLength={300}
              value={title}
              onChange={(e) => {
                setTitle(e.target.value);
                setPreviews(null);
              }}
              placeholder="e.g., Exciting Announcement: Launching our new product line!"
            />
          </div>
          <div>
            <label htmlFor="mp-link" className={labelCls}>
              Destination Link URL <span className="font-normal text-[#9C8F85] dark:text-slate-400">(Optional website or article link)</span>
            </label>
            <input
              id="mp-link"
              type="url"
              className={inputCls}
              value={linkUrl}
              onChange={(e) => {
                setLinkUrl(e.target.value);
                setPreviews(null);
              }}
              placeholder="https://example.com/product"
            />
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label htmlFor="mp-text" className={labelCls}>
              Post Text / Caption <span className="text-rose-500">*</span>
            </label>
            <span className="text-[11px] text-[#7A6C63] dark:text-slate-400">
              {text.length} characters
            </span>
          </div>
          <textarea
            id="mp-text"
            rows={4}
            className={inputCls}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setPreviews(null);
            }}
            placeholder="Write your post caption here. Platform character limits (2,200 on Instagram, 3,000 on LinkedIn, 63,206 on Facebook) are validated automatically before publishing."
          />
        </div>

        {/* Media Attachments */}
        <div className="space-y-3 pt-3 border-t border-[#EDE6DD] dark:border-white/10">
          <div className="flex items-center justify-between">
            <span className={labelCls + ' flex items-center gap-1.5'}>
              <ImageIcon className="w-3.5 h-3.5 text-[#F26D5B]" />
              Attach Visual Media (Required for Instagram, optional for Facebook &amp; LinkedIn)
            </span>
            {imageId && (
              <button
                type="button"
                onClick={() => {
                  setImageId(null);
                  setPreviews(null);
                }}
                className="text-xs text-rose-600 dark:text-rose-400 hover:underline cursor-pointer flex items-center gap-1"
              >
                <CloseIcon className="w-3 h-3" />
                <span>Remove selected media</span>
              </button>
            )}
          </div>

          <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
            <div className="flex-1">
              <input
                aria-label="AI image prompt"
                className={inputCls}
                value={imagePrompt}
                onChange={(e) => setImagePrompt(e.target.value)}
                placeholder="Generate an image with AI (e.g., sleek modern product packaging on minimalist background)"
              />
            </div>
            <button
              type="button"
              className={btnSecondary + ' flex items-center gap-1.5'}
              disabled={busy || imagePrompt.trim().length < 3}
              onClick={() => handleImageAction(() => generateOrganicImage(imagePrompt.trim()))}
            >
              <Sparkles className="w-3.5 h-3.5 text-[#F26D5B]" />
              <span>Generate</span>
            </button>
            <label className={btnSecondary + (busy ? ' opacity-50' : '') + ' flex items-center gap-1.5 cursor-pointer'}>
              <ImageIcon className="w-3.5 h-3.5" />
              <span>Upload File</span>
              <input
                type="file"
                accept="image/png,image/jpeg,video/mp4"
                className="sr-only"
                disabled={busy}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleImageAction(() => uploadOrganicImage(file));
                  e.target.value = '';
                }}
              />
            </label>
          </div>

          {/* Media Library thumbnail selector */}
          {(media ?? []).length > 0 && (
            <div className="pt-2">
              <p className="text-[11px] font-semibold text-[#7A6C63] dark:text-slate-400 mb-2">
                Choose from Media Library:
              </p>
              <ul className="grid grid-cols-4 sm:grid-cols-8 gap-2.5">
                {(media ?? []).slice(0, 8).map((m) => {
                  const isSelected = imageId === m.id;
                  return (
                    <li key={m.id}>
                      <button
                        type="button"
                        aria-label={`Select media ${m.filename}`}
                        onClick={() => {
                          setImageId(m.id);
                          setPreviews(null);
                        }}
                        className={`group relative block w-full aspect-square overflow-hidden rounded-xl border-2 transition-all cursor-pointer ${
                          isSelected
                            ? 'border-[#F26D5B] ring-2 ring-[#F26D5B]/30'
                            : 'border-transparent hover:border-[#EDE6DD] dark:hover:border-white/20'
                        }`}
                      >
                        <AdImage src={imageUrl(m.id)} alt={m.filename} fill className="object-cover" />
                        {isSelected && (
                          <div className="absolute inset-0 bg-[#F26D5B]/20 flex items-center justify-center">
                            <Check className="w-5 h-5 text-white bg-[#F26D5B] rounded-full p-0.5 shadow-md" />
                          </div>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>

        {/* Hashtags */}
        <div className="pt-3 border-t border-[#EDE6DD] dark:border-white/10">
          <HashtagSelector
            selectedHashtags={hashtags}
            onChange={setHashtags}
            contextText={`${title} ${text}`}
            primaryText={text}
            imagePrompt={imagePrompt}
            disabled={busy}
            title="Recommended Hashtags"
          />
        </div>
      </section>

      {/* Step 2: Select Connected Platforms & Accounts */}
      <section className="p-6 rounded-3xl bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 space-y-4 shadow-2xs">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-extrabold text-[#1F1A18] dark:text-white flex items-center gap-2">
            <span className="w-6 h-6 rounded-lg bg-[#F26D5B]/10 text-[#F26D5B] flex items-center justify-center text-xs font-bold">2</span>
            <span>Select Target Platforms &amp; Accounts</span>
          </h3>
          <span className="text-xs font-semibold text-[#F26D5B]">
            {selectedPlatforms.length} platform{selectedPlatforms.length === 1 ? '' : 's'} selected
          </span>
        </div>

        {connectedPlatforms.length === 0 ? (
          <div className="p-5 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-800 dark:text-amber-300 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <p className="font-bold">No social media platforms are currently connected.</p>
              <p className="mt-0.5 opacity-90">Connect Facebook, Instagram, or LinkedIn in Social Accounts to begin publishing.</p>
            </div>
            {onOpenConnections && (
              <button
                type="button"
                onClick={onOpenConnections}
                className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white font-bold text-xs shrink-0 cursor-pointer transition-colors"
              >
                Connect Platforms
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {platforms.map((p) => {
              const isConnected = p.status === 'ACTIVE';
              const isSelected = selectedPlatforms.includes(p.platform);
              const targetDisplay =
                p.selected_target_name ||
                p.account_display_name ||
                (p.account_username ? `@${p.account_username}` : `${p.name} Page`);

              return (
                <div
                  key={p.platform}
                  className={`rounded-2xl border transition-all p-3.5 flex flex-col justify-between gap-2.5 ${
                    !isConnected
                      ? 'opacity-55 border-[#EDE6DD] dark:border-white/5 bg-[#FAF8F5] dark:bg-white/5'
                      : isSelected
                      ? 'border-[#F26D5B] bg-[#FEECE7]/30 dark:bg-[#F26D5B]/10 ring-1 ring-[#F26D5B]/30'
                      : 'border-[#EDE6DD] dark:border-white/10 hover:border-[#F26D5B]/40 bg-white dark:bg-[#111827]'
                  }`}
                >
                  <button
                    type="button"
                    disabled={!isConnected}
                    onClick={() => togglePlatform(p.platform)}
                    data-testid={`select-platform-${p.platform}`}
                    className="flex items-center gap-3 text-left w-full cursor-pointer disabled:cursor-not-allowed"
                  >
                    <PlatformLogo platform={p.platform} className="w-9 h-9 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-xs font-bold text-[#1F1A18] dark:text-white">{p.name}</span>
                        <span
                          className={`w-5 h-5 rounded-md border flex items-center justify-center text-xs font-bold transition-colors ${
                            isSelected
                              ? 'bg-[#F26D5B] border-[#F26D5B] text-white'
                              : 'border-[#D5C9BC] dark:border-white/20 bg-white dark:bg-white/5'
                          }`}
                        >
                          {isSelected && '✓'}
                        </span>
                      </div>
                      <p className="text-[11px] text-[#7A6C63] dark:text-slate-400 truncate mt-0.5">
                        {isConnected ? targetDisplay : p.status === 'EXPIRED' ? 'Token expired' : 'Not connected'}
                      </p>
                    </div>
                  </button>

                  {/* Capabilities pill list */}
                  <div className="flex flex-wrap gap-1 text-[9px] text-[#7A6C63] dark:text-slate-400">
                    {p.capabilities?.supports_text_post && <span>Text</span>}
                    {p.capabilities?.supports_image_post && <span>· Image</span>}
                    {p.capabilities?.supports_video_post && <span>· Video</span>}
                    {p.capabilities?.supports_link_post && <span>· Links</span>}
                    {p.capabilities?.supports_scheduling && <span>· Scheduling</span>}
                  </div>

                  {/* Target override when selected */}
                  {isSelected && p.capabilities?.requires_target_selection && (
                    <div className="pt-2 border-t border-[#EDE6DD] dark:border-white/10">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-[#7A6C63] dark:text-slate-400 block mb-1">
                        Target {p.capabilities.target_label} ID
                      </label>
                      <input
                        className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-[#EDE6DD] dark:border-white/10 bg-white dark:bg-white/5 font-mono text-[#1F1A18] dark:text-white"
                        value={targetOverrides[p.platform] ?? p.selected_target_id ?? ''}
                        onChange={(e) =>
                          setTargetOverrides((prev) => ({ ...prev, [p.platform]: e.target.value }))
                        }
                        placeholder={`Default: ${p.selected_target_name || p.selected_target_id || 'Active Page'}`}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Step 3: Platform-Specific Preview */}
      <section className="p-6 rounded-3xl bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 space-y-5 shadow-2xs">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="w-6 h-6 rounded-lg bg-[#F26D5B]/10 text-[#F26D5B] flex items-center justify-center text-xs font-bold">3</span>
            <h3 className="text-base font-extrabold text-[#1F1A18] dark:text-white">
              Platform-Specific Preview &amp; Validation
            </h3>
          </div>
          <button
            type="button"
            onClick={handlePreview}
            disabled={previewBusy || selectedPlatforms.length === 0}
            data-testid="btn-preview-multi"
            className={btnSecondary + ' flex items-center gap-1.5'}
          >
            {previewBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            <span>{previewBusy ? 'Validating…' : 'Validate & Preview'}</span>
          </button>
        </div>

        <ErrorBox message={error} />

        {/* Render previews if available */}
        {previews && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="multi-previews">
            {Object.values(previews).map((pv) => {
              const platformObj = platforms.find((p) => p.platform === pv.platform);
              const isInstagram = pv.platform === 'instagram';
              const isFacebook = pv.platform === 'facebook';
              const isLinkedIn = pv.platform === 'linkedin';

              return (
                <div
                  key={pv.platform}
                  className={`rounded-2xl border flex flex-col justify-between overflow-hidden shadow-xs transition-all ${
                    pv.valid
                      ? 'border-emerald-500/30 bg-emerald-500/5'
                      : 'border-rose-500/30 bg-rose-500/5'
                  }`}
                >
                  {/* Platform Card Header */}
                  <div className="p-3.5 bg-black/5 dark:bg-white/5 border-b border-inherit flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <PlatformLogo platform={pv.platform} className="w-5 h-5" />
                      <span className="text-xs font-bold text-[#1F1A18] dark:text-white">{pv.name}</span>
                    </div>
                    <span className="text-[11px] font-mono text-[#7A6C63] dark:text-slate-400">
                      {pv.character_count}/{pv.max_text_length}
                    </span>
                  </div>

                  {/* Realistic Social Feed Mock */}
                  <div className="p-4 space-y-3 flex-1 flex flex-col justify-between text-xs">
                    <div className="space-y-2.5">
                      {/* Author Header */}
                      <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-full bg-[#F26D5B]/20 text-[#F26D5B] font-bold flex items-center justify-center uppercase text-xs">
                          {pv.name[0]}
                        </div>
                        <div className="min-w-0">
                          <p className="font-bold text-[#1F1A18] dark:text-white truncate">
                            {pv.target_name || `${pv.name} Brand Page`}
                          </p>
                          <p className="text-[10px] text-[#7A6C63] dark:text-slate-400">
                            {isFacebook && 'Just now · 🌍 Public'}
                            {isInstagram && 'AdCraft Studio · Original Audio'}
                            {isLinkedIn && 'Now · 🌐 Professional Feed'}
                          </p>
                        </div>
                      </div>

                      {/* LinkedIn Headline / Title */}
                      {title && isLinkedIn && (
                        <p className="font-extrabold text-sm text-[#1F1A18] dark:text-white">
                          {title}
                        </p>
                      )}

                      {/* Post Body Text */}
                      <p className="whitespace-pre-wrap text-[#1F1A18] dark:text-slate-200 bg-white dark:bg-black/25 p-3 rounded-xl border border-black/5 dark:border-white/5 leading-relaxed">
                        {pv.formatted_text || '(No text)'}
                      </p>

                      {/* Visual Media Frame */}
                      {imageId ? (
                        <div className="relative aspect-video rounded-xl overflow-hidden border border-black/10 dark:border-white/10 bg-black/5">
                          <AdImage src={imageUrl(imageId)} alt="Attached media" fill className="object-cover" />
                        </div>
                      ) : isInstagram ? (
                        <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-800 dark:text-amber-300 text-[11px] flex items-center gap-2">
                          <AlertTriangle className="w-4 h-4 shrink-0 text-amber-600" />
                          <span>Instagram requires an image or video attachment to publish.</span>
                        </div>
                      ) : null}

                      {/* Link Preview Card */}
                      {linkUrl && !imageId && (
                        <div className="p-2.5 rounded-xl border border-[#EDE6DD] dark:border-white/10 bg-white dark:bg-white/5 space-y-1">
                          <span className="text-[10px] font-mono text-[#F26D5B] flex items-center gap-1">
                            <ExternalLink className="w-3 h-3" />
                            {linkUrl}
                          </span>
                          <p className="text-[11px] font-bold truncate">{title || 'Destination Link Preview'}</p>
                        </div>
                      )}

                      {/* Validation Warnings */}
                      {!pv.valid && (
                        <ul className="p-2.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-[11px] text-rose-700 dark:text-rose-300 space-y-1 list-disc pl-5">
                          {pv.errors.map((err) => (
                            <li key={err}>{err}</li>
                          ))}
                        </ul>
                      )}
                    </div>

                    {/* Interactive Action Bar Mock */}
                    <div className="pt-2 border-t border-black/5 dark:border-white/10 flex items-center justify-around text-[#7A6C63] dark:text-slate-400 text-[11px]">
                      {isFacebook && (
                        <>
                          <span className="flex items-center gap-1"><ThumbsUp className="w-3.5 h-3.5" /> Like</span>
                          <span className="flex items-center gap-1"><MessageSquare className="w-3.5 h-3.5" /> Comment</span>
                          <span className="flex items-center gap-1"><Share2 className="w-3.5 h-3.5" /> Share</span>
                        </>
                      )}
                      {isInstagram && (
                        <>
                          <span className="flex items-center gap-1"><Heart className="w-3.5 h-3.5" /> Like</span>
                          <span className="flex items-center gap-1"><MessageCircle className="w-3.5 h-3.5" /> Comment</span>
                          <span className="flex items-center gap-1"><Send className="w-3.5 h-3.5" /> Share</span>
                        </>
                      )}
                      {isLinkedIn && (
                        <>
                          <span className="flex items-center gap-1"><ThumbsUp className="w-3.5 h-3.5" /> Like</span>
                          <span className="flex items-center gap-1"><MessageSquare className="w-3.5 h-3.5" /> Comment</span>
                          <span className="flex items-center gap-1"><Repeat className="w-3.5 h-3.5" /> Repost</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Step 4: Publishing & Scheduling Options */}
      <section className="p-6 rounded-3xl bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 space-y-5 shadow-2xs">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-extrabold text-[#1F1A18] dark:text-white flex items-center gap-2">
            <span className="w-6 h-6 rounded-lg bg-[#F26D5B]/10 text-[#F26D5B] flex items-center justify-center text-xs font-bold">4</span>
            <span>Publish or Schedule</span>
          </h3>
          <div className="inline-flex p-1 rounded-xl bg-black/5 dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-xs font-bold">
            <button
              type="button"
              onClick={() => setIsScheduled(false)}
              className={`px-3 py-1.5 rounded-lg transition-colors cursor-pointer ${
                !isScheduled
                  ? 'bg-white dark:bg-[#1F2937] text-[#1F1A18] dark:text-white shadow-xs'
                  : 'text-[#7A6C63] dark:text-slate-400'
              }`}
            >
              Publish Now
            </button>
            <button
              type="button"
              onClick={() => setIsScheduled(true)}
              className={`px-3 py-1.5 rounded-lg transition-colors cursor-pointer flex items-center gap-1 ${
                isScheduled
                  ? 'bg-white dark:bg-[#1F2937] text-[#1F1A18] dark:text-white shadow-xs'
                  : 'text-[#7A6C63] dark:text-slate-400'
              }`}
            >
              <Clock className="w-3 h-3 text-[#F26D5B]" />
              <span>Schedule for Later</span>
            </button>
          </div>
        </div>

        {isScheduled && (
          <div className="p-4 rounded-2xl bg-[#FAF8F5] dark:bg-[#0B1120] border border-[#EDE6DD] dark:border-white/10 space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <label htmlFor="schedule-time" className="text-xs font-bold text-[#1F1A18] dark:text-white flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-[#F26D5B]" />
                <span>Select Target Publish Date &amp; Time</span>
              </label>
              <input
                id="schedule-time"
                type="datetime-local"
                value={scheduledAt}
                onChange={(e) => setScheduledAt(e.target.value)}
                className="px-3 py-2 rounded-xl text-xs border border-[#EDE6DD] dark:border-white/10 bg-white dark:bg-white/5 font-sans text-[#1F1A18] dark:text-white"
              />
            </div>
            {selectedPlatformObjs.some((p) => !p.capabilities?.supports_scheduling) && (
              <p className="text-[11px] text-amber-700 dark:text-amber-300">
                ⚠️ Some selected platforms (e.g. LinkedIn) do not support scheduled API publishing and will be published immediately or require manual authorization.
              </p>
            )}
          </div>
        )}

        {/* Publish Action Button */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={() => handlePublish()}
            disabled={busy || selectedPlatforms.length === 0}
            data-testid="btn-publish-multi"
            className={btnPrimary + ' px-6 py-3 text-sm font-bold shadow-lg shadow-[#F26D5B]/20 inline-flex items-center gap-2'}
          >
            {busy ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : isScheduled ? (
              <Clock className="w-4 h-4" />
            ) : (
              <Send className="w-4 h-4" />
            )}
            <span>
              {busy
                ? 'Processing…'
                : isScheduled
                ? `Schedule for ${selectedPlatforms.length || 0} Platform${selectedPlatforms.length === 1 ? '' : 's'}`
                : `Publish to ${selectedPlatforms.length || 0} Platform${selectedPlatforms.length === 1 ? '' : 's'}`}
            </span>
          </button>
        </div>

        {/* Independent Results Panel */}
        {results && (
          <div className="space-y-3 pt-4 border-t border-[#EDE6DD] dark:border-white/10" data-testid="multi-publish-results">
            <h4 className="text-xs font-bold uppercase tracking-wider text-[#7A6C63] dark:text-slate-400">
              Publishing Results &amp; Platform Status
            </h4>
            <div className="space-y-2">
              {Object.values(results).map((r) => {
                const isSuccess = r.status === 'PUBLISHED' || r.status === 'SCHEDULED';
                const isFailed = r.status === 'FAILED';
                const isRetrying = retryingPlatform === r.platform;

                return (
                  <div
                    key={r.platform}
                    className={`flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-2xl border text-xs transition-all ${
                      isSuccess
                        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-800 dark:text-emerald-300'
                        : 'border-rose-500/30 bg-rose-500/10 text-rose-800 dark:text-rose-300'
                    }`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <PlatformLogo platform={r.platform} className="w-6 h-6 shrink-0" />
                      <div className="min-w-0">
                        <p className="font-bold capitalize flex items-center gap-2">
                          {isSuccess ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                          ) : (
                            <AlertCircle className="w-4 h-4 text-rose-600 dark:text-rose-400" />
                          )}
                          <span>
                            {r.platform}: {r.status}
                          </span>
                        </p>
                        {r.error && <p className="text-[11px] mt-0.5 opacity-90">{r.error}</p>}
                        {r.scheduled_at && (
                          <p className="text-[11px] mt-0.5 opacity-90">
                            Scheduled for: {new Date(r.scheduled_at).toLocaleString()}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-end sm:self-center">
                      {isFailed && (
                        <button
                          type="button"
                          disabled={busy || isRetrying}
                          onClick={() => handleRetryPlatform(r.platform)}
                          className="px-3 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold shadow-xs cursor-pointer inline-flex items-center gap-1"
                        >
                          {isRetrying ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                          <span>Retry</span>
                        </button>
                      )}
                      {r.post_url && (
                        <a
                          href={r.post_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-white dark:bg-white/10 text-xs font-bold hover:underline shrink-0"
                        >
                          <span>View Post</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </section>

      {/* Publishing History */}
      <section className="p-6 rounded-3xl bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 space-y-4 shadow-2xs">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-extrabold text-[#1F1A18] dark:text-white">Publishing History</h3>
            <p className="text-xs text-[#7A6C63] dark:text-slate-400">Audit trail of multi-platform social publications.</p>
          </div>
          <button
            type="button"
            onClick={() => mutateHistory()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-[#EDE6DD] dark:border-white/10 text-xs font-semibold text-[#7A6C63] dark:text-slate-400 hover:text-[#1F1A18] dark:hover:text-white cursor-pointer transition-colors"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Refresh</span>
          </button>
        </div>

        {history.length === 0 ? (
          <p className="text-xs text-[#7A6C63] dark:text-slate-400 py-3">
            No multi-platform posts published yet.
          </p>
        ) : (
          <ul className="divide-y divide-[#EDE6DD] dark:divide-white/10 text-xs">
            {history.map((item) => (
              <li key={item.id} className="py-3 flex items-start justify-between gap-3">
                <div className="flex items-start gap-2.5 min-w-0">
                  <PlatformLogo platform={item.platform} className="w-5 h-5 mt-0.5 shrink-0" />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold capitalize">{item.platform}</span>
                      {item.target_name && (
                        <span className="text-[11px] text-[#7A6C63] dark:text-slate-400">
                          · {item.target_name}
                        </span>
                      )}
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                          item.status === 'PUBLISHED'
                            ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
                            : item.status === 'SCHEDULED'
                            ? 'bg-blue-500/15 text-blue-700 dark:text-blue-400'
                            : 'bg-rose-500/15 text-rose-700 dark:text-rose-400'
                        }`}
                      >
                        {item.status}
                      </span>
                    </div>
                    <p className="text-[#1F1A18] dark:text-slate-200 mt-0.5 truncate">
                      {item.title || item.text || '(No text)'}
                    </p>
                    {item.error && (
                      <p className="text-[11px] text-rose-600 dark:text-rose-400 mt-0.5">{item.error}</p>
                    )}
                  </div>
                </div>
                <span className="text-[10px] text-[#9C8F85] shrink-0">
                  {new Date(item.created_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export default MultiPlatformPublisher;
