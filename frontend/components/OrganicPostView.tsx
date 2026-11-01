'use client';

import React, { useState } from 'react';
import { AdImage } from './AdImage';
import useSWR from 'swr';
import { Trash2 } from 'lucide-react';
import {
  MediaItem,
  OrganicAccounts,
  OrganicPost,
  deleteOrganicPost,
  fetcher,
  generateOrganicImage,
  imageUrl,
  publishOrganicPost,
  uploadOrganicImage,
} from '../lib/api';
import { Dialog, ErrorBox, btnPrimary, btnSecondary, errorMessage, inputCls, labelCls } from './Dialog';
import { HashtagSelector } from './HashtagSelector';

const CAPTION_MAX = 2200;
const REQUIREMENTS = [
  'An Instagram Business or Creator account. Apps cannot post to personal accounts.',
  'The account is linked to a Facebook Page.',
  'The Facebook login connected here manages that Page (Page admin, or a role with content access).',
  "For someone else's account: they connect their own login under Settings > Meta Connection, or give your login access to their Page.",
  'Picture: JPEG or PNG at least 600 px wide, shape between 4:5 and 1.91:1. PNG is converted to JPEG.',
  'Instagram allows about 50 posts per account every 24 hours.',
];
const heading = 'text-sm font-bold text-[#1F1A18] dark:text-white';
const section = 'border-b border-[#EDE6DD] dark:border-white/10 pb-6 space-y-3';
const muted = 'text-xs text-[#7A6C63] dark:text-slate-400';

export function OrganicPostView() {
  const { data: accounts, error: accountsError } = useSWR<OrganicAccounts>('/v1/organic/accounts', fetcher);
  const { data: media, mutate: mutateMedia } = useSWR<MediaItem[]>('/v1/media', fetcher);
  const { data: posts, mutate: mutatePosts } = useSWR<OrganicPost[]>('/v1/organic/posts', fetcher, {
    refreshInterval: 5_000,
    revalidateOnFocus: true,
  });
  const [chosen, setChosen] = useState('');
  const [imageId, setImageId] = useState<string | null>(null);
  const [caption, setCaption] = useState('');
  const [selectedHashtags, setSelectedHashtags] = useState<string[]>([]);
  const [prompt, setPrompt] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const list = accounts?.accounts ?? [];
  const account = chosen || accounts?.default || list[0]?.instagram_user_id || '';
  const label = (id: string) => {
    const a = list.find((x) => x.instagram_user_id === id);
    return a ? '@' + a.username : id;
  };

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      await action();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const addImage = (make: () => Promise<MediaItem>) =>
    run(async () => {
      const item = await make();
      setImageId(item.id);
      await mutateMedia();
    });

  const publish = () =>
    run(async () => {
      setConfirming(false);
      try {
        const newPost = await publishOrganicPost(
          imageId!,
          caption.trim(),
          account || undefined,
          selectedHashtags
        );
        setDone('Posted to ' + label(account) + '.');
        setCaption('');
        setSelectedHashtags([]);
        // Retain imageId so user can post again without button becoming disabled!
        if (newPost) {
          await mutatePosts((prev) => [newPost, ...(prev ?? []).filter((p) => p.id !== newPost.id)], false);
        }
      } finally {
        await mutatePosts();
      }
    });

  const handleDeletePost = async (id: string) => {
    setDeletingId(id);
    setError(null);
    try {
      await deleteOrganicPost(id);
      await mutatePosts((prev) => (prev ?? []).filter((p) => p.id !== id), false);
      await mutatePosts();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="space-y-1">
        <h2 className="text-xl font-bold text-[#1F1A18] dark:text-white tracking-tight">Post to Instagram</h2>
        <p className={muted}>An ordinary feed post (not an ad, no spend), published on the account you choose.</p>
      </div>

      <section className={section}>
        <h3 className={heading}>1. Account</h3>
        {accountsError && <ErrorBox message={errorMessage(accountsError)} />}
        {accounts && list.length > 0 && (
          <div>
            <label htmlFor="post-account" className={labelCls}>Post as</label>
            <select id="post-account" className={inputCls} value={account} onChange={(e) => setChosen(e.target.value)}>
              {list.map((a) => (
                <option key={a.instagram_user_id} value={a.instagram_user_id}>
                  @{a.username} ({a.page_name})
                </option>
              ))}
            </select>
          </div>
        )}
        {accounts && list.length === 0 && (
          <p className={muted}>No usable Instagram account found for this login. See the requirements below.</p>
        )}
        {accounts && accounts.unavailable.length > 0 && (
          <ul className={muted + ' list-disc pl-5'}>
            {accounts.unavailable.map((u) => (
              <li key={u.page_id}>
                {u.page_name}: {u.reason}
              </li>
            ))}
          </ul>
        )}
        <div>
          <p className={heading}>What the account needs</p>
          <ul className={muted + ' list-disc pl-5 mt-1 space-y-0.5'}>
            {REQUIREMENTS.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      </section>

      <section className={section}>
        <h3 className={heading}>2. Picture</h3>
        <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
          <div className="flex-1">
            <label htmlFor="post-prompt" className={labelCls}>Generate a picture with AI</label>
            <input
              id="post-prompt"
              className={inputCls}
              maxLength={500}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="A birthday cake on a wooden table, soft light"
            />
          </div>
          <button
            type="button"
            className={btnSecondary}
            disabled={busy || prompt.trim().length < 3}
            onClick={() => addImage(() => generateOrganicImage(prompt.trim()))}
          >
            Generate
          </button>
          <label className={btnSecondary + (busy ? ' opacity-50' : '')}>
            Upload image
            <input
              aria-label="Upload image"
              type="file"
              accept="image/png,image/jpeg"
              className="sr-only"
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) addImage(() => uploadOrganicImage(file));
                e.target.value = '';
              }}
            />
          </label>
        </div>
        <ul className="grid grid-cols-4 sm:grid-cols-6 gap-2" aria-label="Pictures">
          {(media ?? []).map((m) => (
            <li key={m.id}>
              <button
                type="button"
                aria-label={'Use ' + m.filename}
                aria-pressed={imageId === m.id}
                onClick={() => setImageId(m.id)}
                className={
                  'relative block w-full aspect-square overflow-hidden border-2 cursor-pointer ' +
                  (imageId === m.id ? 'border-[#F26D5B]' : 'border-transparent')
                }
              >
                <AdImage src={imageUrl(m.id)} alt={m.filename} fill className="object-cover" />
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className={section}>
        <h3 className={heading}>3. Caption</h3>
        <textarea
          id="post-caption"
          aria-label="Caption"
          rows={4}
          className={inputCls}
          maxLength={CAPTION_MAX}
          value={caption}
          onChange={(e) => {
            setCaption(e.target.value);
            if (done) setDone(null);
          }}
        />
        <p className={muted}>
          {caption.length}/{CAPTION_MAX}
        </p>
      </section>

      <section className={section}>
        <HashtagSelector
          selectedHashtags={selectedHashtags}
          onChange={setSelectedHashtags}
          contextText={`${caption} ${prompt}`}
          primaryText={caption}
          imagePrompt={prompt}
          disabled={busy}
          title="Hashtags"
        />
      </section>

      <section className={section}>
        <h3 className={heading}>4. Publish</h3>

        {/* Publishing Preview */}
        <div className="p-3.5 rounded-2xl bg-[#FAF8F5] dark:bg-[#0E1524] border border-[#EDE6DD] dark:border-white/10 space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="font-bold text-[#1F1A18] dark:text-white">Publishing Preview</span>
            <span className="text-[10px] text-[#7A6C63] dark:text-slate-400">Instagram Feed Post</span>
          </div>
          <p className="whitespace-pre-wrap text-[#1F1A18] dark:text-slate-200">
            {caption || <span className="text-slate-400 italic">No caption entered</span>}
          </p>
          {selectedHashtags.length > 0 && (
            <p className="font-semibold text-[#F26D5B] text-xs">
              {selectedHashtags.join(' ')}
            </p>
          )}
          <p className="text-[10px] text-[#9C8F85] pt-1 border-t border-[#EDE6DD] dark:border-white/5">
            Will be published on {account ? label(account) : 'your connected Instagram account'}.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            className={btnPrimary}
            disabled={busy || !imageId || !account}
            onClick={() => setConfirming(true)}
          >
            {busy ? 'Posting…' : 'Post to Instagram'}
          </button>
          {done && (
            <span role="status" className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
              {done}
            </span>
          )}
        </div>
        {!imageId && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            Please choose or upload a picture in section 2 to post.
          </p>
        )}
        <ErrorBox message={error} />
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className={heading}>Recent posts</h3>
          {posts && posts.length > 0 && (
            <span className={muted}>{posts.length} {posts.length === 1 ? 'post' : 'posts'}</span>
          )}
        </div>
        {posts && posts.length === 0 && <p className={muted}>No posts yet.</p>}
        <ul className="divide-y divide-[#EDE6DD] dark:divide-white/10 text-xs" aria-label="Recent posts">
          {(posts ?? []).map((p) => (
            <li key={p.id} className="py-2.5 flex items-start justify-between gap-3 group">
              <div className="min-w-0 flex-1 space-y-1">
                <div>
                  <span
                    className={
                      'font-bold mr-1.5 ' +
                      (p.status === 'PUBLISHED'
                        ? 'text-emerald-600 dark:text-emerald-400'
                        : 'text-rose-600 dark:text-rose-400')
                    }
                  >
                    {p.status}
                  </span>
                  <span className="text-[#1F1A18] dark:text-slate-200">
                    {p.ig_user_id ? '· ' + label(p.ig_user_id) + ' · ' : '· '}
                    {p.caption || '(no caption)'}
                    {p.selected_hashtags && p.selected_hashtags.length > 0 && (
                      <span className="text-[#F26D5B] font-semibold ml-1.5">
                        {p.selected_hashtags.join(' ')}
                      </span>
                    )}
                  </span>
                </div>
                {p.error && (
                  <p className="text-rose-600 dark:text-rose-400 text-[11px] leading-relaxed break-words bg-rose-50/50 dark:bg-rose-950/20 p-2 rounded-lg border border-rose-100 dark:border-rose-900/30">
                    {p.error}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => handleDeletePost(p.id)}
                disabled={deletingId === p.id}
                aria-label={'Delete post ' + p.id}
                title="Delete this post from recent posts"
                className="opacity-60 group-hover:opacity-100 hover:text-rose-600 dark:hover:text-rose-400 text-slate-400 p-1.5 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-all cursor-pointer flex-shrink-0"
              >
                {deletingId === p.id ? (
                  <span className="w-3.5 h-3.5 border-2 border-rose-500 border-t-transparent rounded-full animate-spin inline-block" />
                ) : (
                  <Trash2 className="w-3.5 h-3.5" />
                )}
              </button>
            </li>
          ))}
        </ul>
      </section>

      {confirming && (
        <Dialog title="Post to Instagram?" onClose={() => setConfirming(false)}>
          <div className="space-y-3 text-xs text-[#5C5047] dark:text-slate-300">
            <p>
              This publishes the picture and caption publicly on {label(account)}.
            </p>
            {selectedHashtags.length > 0 && (
              <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-white/5 border border-slate-200 dark:border-white/10 space-y-1">
                <span className="font-bold text-[11px] text-[#1F1A18] dark:text-white">Included Hashtags ({selectedHashtags.length}/5):</span>
                <p className="text-[#F26D5B] font-semibold">{selectedHashtags.join(' ')}</p>
              </div>
            )}
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className={btnSecondary} onClick={() => setConfirming(false)}>
              Cancel
            </button>
            <button type="button" className={btnPrimary} onClick={publish}>
              Post now
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
