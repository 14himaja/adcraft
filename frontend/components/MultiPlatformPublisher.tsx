'use client';

import React, { useMemo, useState } from 'react';
import useSWR from 'swr';
import {
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  Image as ImageIcon,
  Link2,
  Loader2,
  RefreshCw,
  Send,
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

  const [selectedPlatforms, setSelectedPlatforms] = useState<SocialPlatformId[]>([]);
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [linkUrl, setLinkUrl] = useState('');
  const [imageId, setImageId] = useState<string | null>(null);
  const [imagePrompt, setImagePrompt] = useState('');
  const [hashtags, setHashtags] = useState<string[]>([]);
  const [targetOverrides, setTargetOverrides] = useState<Record<string, string>>({});

  const [previews, setPreviews] = useState<Record<string, MultiPublishPreviewItem> | null>(null);
  const [results, setResults] = useState<Record<string, MultiPublishResultItem> | null>(null);
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
      });
      setPreviews(res.previews);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setPreviewBusy(false);
    }
  };

  const handlePublish = async () => {
    if (selectedPlatforms.length === 0) return;
    setBusy(true);
    setError(null);
    setResults(null);
    try {
      const res = await publishMultiPlatform({
        platforms: selectedPlatforms,
        text,
        title: title.trim() || undefined,
        link_url: linkUrl.trim() || undefined,
        image_id: imageId || undefined,
        hashtags,
        targets: targetOverrides,
      });
      setResults(res.results);
      await Promise.all([mutateHistory(), mutateConns()]);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl" data-testid="multi-platform-publisher">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-[#1F1A18] dark:text-white tracking-tight">
            Multi-Platform Content Publisher
          </h2>
          <p className="text-xs text-[#7A6C63] dark:text-slate-400 mt-0.5">
            Create once, validate per-platform requirements, preview, and publish independently to connected accounts.
          </p>
        </div>
        {onOpenConnections && (
          <button
            type="button"
            onClick={onOpenConnections}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-[#EDE6DD] dark:border-white/10 text-xs font-semibold hover:bg-white dark:hover:bg-white/5 cursor-pointer self-start"
          >
            <Link2 className="w-3.5 h-3.5 text-[#F26D5B]" />
            <span>Manage Connections ({connectedPlatforms.length})</span>
          </button>
        )}
      </div>

      {/* Step 1: Select Connected Platforms */}
      <section className="p-5 rounded-3xl bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-[#1F1A18] dark:text-white">
            1. Select Target Platforms
          </h3>
          <span className="text-xs text-[#7A6C63] dark:text-slate-400">
            {selectedPlatforms.length} selected
          </span>
        </div>

        {connectedPlatforms.length === 0 ? (
          <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-800 dark:text-amber-300 flex items-center justify-between gap-3">
            <span>No social media platforms are connected yet. Connect at least one platform to publish.</span>
            {onOpenConnections && (
              <button
                type="button"
                onClick={onOpenConnections}
                className="px-3 py-1.5 rounded-xl bg-amber-600 text-white font-bold text-xs shrink-0 cursor-pointer"
              >
                Connect Platforms
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
            {platforms.map((p) => {
              const isConnected = p.status === 'ACTIVE';
              const isSelected = selectedPlatforms.includes(p.platform);
              const targetDisplay =
                p.selected_target_name ||
                p.account_display_name ||
                (p.account_username ? `@${p.account_username}` : 'Default account');

              return (
                <button
                  key={p.platform}
                  type="button"
                  disabled={!isConnected}
                  onClick={() => togglePlatform(p.platform)}
                  data-testid={`select-platform-${p.platform}`}
                  className={`flex items-center gap-3 p-3 rounded-2xl border text-left transition-all ${
                    !isConnected
                      ? 'opacity-50 cursor-not-allowed border-[#EDE6DD] dark:border-white/5 bg-[#FAF8F5] dark:bg-white/5'
                      : isSelected
                      ? 'border-[#F26D5B] bg-[#FEECE7]/40 dark:bg-[#F26D5B]/15 cursor-pointer'
                      : 'border-[#EDE6DD] dark:border-white/10 hover:border-[#F26D5B]/50 cursor-pointer'
                  }`}
                >
                  <PlatformLogo platform={p.platform} className="w-8 h-8 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-xs font-bold text-[#1F1A18] dark:text-white">{p.name}</span>
                      <span
                        className={`w-4 h-4 rounded-md border flex items-center justify-center text-[10px] ${
                          isSelected
                            ? 'bg-[#F26D5B] border-[#F26D5B] text-white'
                            : 'border-[#D5C9BC] dark:border-white/20'
                        }`}
                      >
                        {isSelected && '✓'}
                      </span>
                    </div>
                    <p className="text-[11px] text-[#7A6C63] dark:text-slate-400 truncate">
                      {isConnected ? targetDisplay : 'Not connected'}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </section>

      {/* Step 2: Compose Content */}
      <section className="p-5 rounded-3xl bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 space-y-4">
        <h3 className="text-sm font-bold text-[#1F1A18] dark:text-white">2. Create Content</h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor="mp-title" className={labelCls}>
              Post Title <span className="font-normal text-[#9C8F85]">(Optional article or image title for LinkedIn)</span>
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
              placeholder="e.g., Launching AdCraft Multi-Platform Studio"
            />
          </div>
          <div>
            <label htmlFor="mp-link" className={labelCls}>
              Destination Link URL <span className="font-normal text-[#9C8F85]">(Optional)</span>
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
              placeholder="https://example.com/launch"
            />
          </div>
        </div>

        <div>
          <label htmlFor="mp-text" className={labelCls}>
            Post Text / Caption
          </label>
          <textarea
            id="mp-text"
            rows={4}
            className={inputCls}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setPreviews(null);
            }}
            placeholder="Write your post copy. Platform limits (e.g., 2,200 chars on Instagram, 3,000 on LinkedIn, 63,206 on Facebook) are validated before publishing."
          />
          <p className="text-[11px] text-[#7A6C63] dark:text-slate-400 mt-1">
            {text.length} characters
          </p>
        </div>

        {/* Target Override per selected platform (e.g., Facebook Page or LinkedIn Organization Page) */}
        {selectedPlatforms.some((pid) => {
          const obj = platforms.find((p) => p.platform === pid);
          return obj?.capabilities.requires_target_selection;
        }) && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-[#EDE6DD] dark:border-white/10">
            {selectedPlatforms.map((pid) => {
              const obj = platforms.find((p) => p.platform === pid);
              if (!obj) return null;
              return (
                <div key={pid}>
                  <label className={labelCls}>
                    {obj.name} {obj.capabilities.target_label} ID
                  </label>
                  <input
                    className={inputCls}
                    value={targetOverrides[pid] ?? obj.selected_target_id ?? ''}
                    onChange={(e) =>
                      setTargetOverrides((prev) => ({ ...prev, [pid]: e.target.value }))
                    }
                    placeholder={`Default: ${obj.selected_target_name || obj.selected_target_id || 'Select in Connections'}`}
                  />
                </div>
              );
            })}
          </div>
        )}

        {/* Media Picker */}
        <div className="space-y-2.5 pt-2 border-t border-[#EDE6DD] dark:border-white/10">
          <div className="flex items-center justify-between">
            <span className={labelCls + ' flex items-center gap-1.5'}>
              <ImageIcon className="w-3.5 h-3.5" />
              Attach Visual Media (Required for Instagram, optional for Facebook &amp; LinkedIn)
            </span>
            {imageId && (
              <button
                type="button"
                onClick={() => setImageId(null)}
                className="text-[11px] text-rose-600 dark:text-rose-400 hover:underline cursor-pointer"
              >
                Clear image
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
                placeholder="Generate image with AI (e.g., minimalist product showcase)"
              />
            </div>
            <button
              type="button"
              className={btnSecondary}
              disabled={busy || imagePrompt.trim().length < 3}
              onClick={() => handleImageAction(() => generateOrganicImage(imagePrompt.trim()))}
            >
              Generate
            </button>
            <label className={btnSecondary + (busy ? ' opacity-50' : '')}>
              Upload
              <input
                type="file"
                accept="image/png,image/jpeg"
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

          {(media ?? []).length > 0 && (
            <ul className="grid grid-cols-5 sm:grid-cols-8 gap-2">
              {(media ?? []).slice(0, 8).map((m) => (
                <li key={m.id}>
                  <button
                    type="button"
                    aria-label={`Select media ${m.filename}`}
                    onClick={() => {
                      setImageId(m.id);
                      setPreviews(null);
                    }}
                    className={`relative block w-full aspect-square overflow-hidden rounded-xl border-2 cursor-pointer ${
                      imageId === m.id ? 'border-[#F26D5B]' : 'border-transparent'
                    }`}
                  >
                    <AdImage src={imageUrl(m.id)} alt={m.filename} fill className="object-cover" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <HashtagSelector
          selectedHashtags={hashtags}
          onChange={setHashtags}
          contextText={`${title} ${text}`}
          primaryText={text}
          imagePrompt={imagePrompt}
          disabled={busy}
          title="Hashtags"
        />
      </section>

      {/* Step 3: Validate & Preview + Publish */}
      <section className="p-5 rounded-3xl bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-bold text-[#1F1A18] dark:text-white">
            3. Preview &amp; Publish
          </h3>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handlePreview}
              disabled={previewBusy || selectedPlatforms.length === 0}
              data-testid="btn-preview-multi"
              className={btnSecondary}
            >
              {previewBusy ? 'Validating…' : 'Validate & Preview'}
            </button>
            <button
              type="button"
              onClick={handlePublish}
              disabled={busy || selectedPlatforms.length === 0}
              data-testid="btn-publish-multi"
              className={btnPrimary + ' inline-flex items-center gap-1.5'}
            >
              {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
              <span>{busy ? 'Publishing…' : `Publish to ${selectedPlatforms.length || 0} Platform${selectedPlatforms.length === 1 ? '' : 's'}`}</span>
            </button>
          </div>
        </div>

        <ErrorBox message={error} />

        {/* Platform Previews */}
        {previews && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="multi-previews">
            {Object.values(previews).map((pv) => (
              <div
                key={pv.platform}
                className={`p-3.5 rounded-2xl border text-xs space-y-2 ${
                  pv.valid
                    ? 'border-emerald-500/30 bg-emerald-500/5'
                    : 'border-rose-500/30 bg-rose-500/5'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <PlatformLogo platform={pv.platform} className="w-5 h-5" />
                    <span className="font-bold">{pv.name}</span>
                  </div>
                  <span className="text-[11px] font-mono text-[#7A6C63] dark:text-slate-400">
                    {pv.character_count}/{pv.max_text_length}
                  </span>
                </div>
                {pv.target_name && (
                  <p className="text-[11px] text-[#7A6C63] dark:text-slate-400">
                    Target: <strong>{pv.target_name}</strong>
                  </p>
                )}
                <p className="whitespace-pre-wrap text-[#1F1A18] dark:text-slate-200 bg-white dark:bg-black/20 p-2 rounded-xl border border-[#EDE6DD] dark:border-white/5">
                  {pv.formatted_text || '(No text)'}
                </p>
                {!pv.valid && (
                  <ul className="text-[11px] text-rose-700 dark:text-rose-300 space-y-0.5 list-disc pl-4">
                    {pv.errors.map((err) => (
                      <li key={err}>{err}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Independent Publishing Results */}
        {results && (
          <div className="space-y-2" data-testid="multi-publish-results">
            <h4 className="text-xs font-bold uppercase tracking-wider text-[#7A6C63] dark:text-slate-400">
              Publishing Results
            </h4>
            <div className="space-y-2">
              {Object.values(results).map((r) => (
                <div
                  key={r.platform}
                  className={`flex items-center justify-between gap-3 p-3 rounded-2xl border text-xs ${
                    r.status === 'PUBLISHED'
                      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-800 dark:text-emerald-300'
                      : 'border-rose-500/30 bg-rose-500/10 text-rose-800 dark:text-rose-300'
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <PlatformLogo platform={r.platform} className="w-5 h-5 shrink-0" />
                    <div className="min-w-0">
                      <p className="font-bold capitalize flex items-center gap-1.5">
                        {r.status === 'PUBLISHED' ? (
                          <CheckCircle2 className="w-3.5 h-3.5" />
                        ) : (
                          <AlertCircle className="w-3.5 h-3.5" />
                        )}
                        <span>
                          {r.platform}: {r.status}
                        </span>
                      </p>
                      {r.error && <p className="text-[11px] mt-0.5">{r.error}</p>}
                    </div>
                  </div>
                  {r.post_url && (
                    <a
                      href={r.post_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] font-bold hover:underline shrink-0"
                    >
                      <span>View</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Publishing History */}
      <section className="p-5 rounded-3xl bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-[#1F1A18] dark:text-white">Publishing History</h3>
          <button
            type="button"
            onClick={() => mutateHistory()}
            className="inline-flex items-center gap-1 text-xs font-semibold text-[#7A6C63] dark:text-slate-400 hover:text-[#1F1A18] dark:hover:text-white cursor-pointer"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Refresh</span>
          </button>
        </div>

        {history.length === 0 ? (
          <p className="text-xs text-[#7A6C63] dark:text-slate-400">
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

