'use client';

import React, { useState } from 'react';
import { AdImage } from './AdImage';
import useSWR, { useSWRConfig } from 'swr';
import { ImageIcon, Upload } from 'lucide-react';
import { Campaign, MediaItem, fetcher, imageUrl, uploadCampaignImage, deleteMedia } from '../lib/api';
import { Dialog, ErrorBox, errorMessage, inputCls, labelCls } from './Dialog';

function useMedia() {
  return useSWR<MediaItem[]>('/v1/media', fetcher);
}

function MediaThumb({ item, children }: { item: MediaItem; children?: React.ReactNode }) {
  return (
    <div className="border-b border-[#EDE6DD] dark:border-white/10 flex flex-col">
      <div className="relative w-full aspect-square bg-slate-100 dark:bg-slate-900">
        <AdImage src={imageUrl(item.id)} alt={item.filename} fill className="object-cover" />
        <span className="absolute top-2 left-2 bg-black/60 px-2 py-0.5 rounded-md text-[10px] font-bold text-white capitalize">
          {item.source}
        </span>
      </div>
      <div className="p-3 space-y-1 text-[11px]">
        <p className="font-bold text-[#1F1A18] dark:text-white truncate">{item.filename}</p>
        {item.prompt && <p className="text-[#7A6C63] dark:text-slate-400 line-clamp-2">{item.prompt}</p>}
        {item.source_campaign && <p className="text-[#9C8F85]">From: {item.source_campaign}</p>}
        <p className="text-[#9C8F85] dark:text-slate-500">{new Date(item.created_at).toLocaleDateString()}</p>
        {children}
      </div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="p-10 text-center border-b border-[#EDE6DD] dark:border-white/10">
      <ImageIcon className="w-7 h-7 text-[#F26D5B] mx-auto mb-2" />
      <p className="text-xs text-[#7A6C63] dark:text-slate-400">{text}</p>
    </div>
  );
}

export function MediaView() {
  const { data: media, error, mutate } = useMedia();
  const { data: campaigns } = useSWR<Campaign[]>('/v1/campaigns', fetcher);
  const { mutate: globalMutate } = useSWRConfig();
  const [filter, setFilter] = useState<'ALL' | 'generated' | 'uploaded'>('ALL');
  const [target, setTarget] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const drafts = (campaigns ?? []).filter((c) => c.status === 'DRAFT');
  const items = (media ?? []).filter((m) => filter === 'ALL' || m.source === filter);

  const upload = async (file: File | undefined) => {
    if (!file || !target) return;
    setUploading(true);
    setUploadError(null);
    try {
      await uploadCampaignImage(target, file);
      mutate();
      globalMutate('/v1/campaigns');
    } catch (e) {
      setUploadError(errorMessage(e));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4 py-6 border-b border-[#EDE6DD] dark:border-white/10">
        <div>
          <h2 className="text-xl font-extrabold text-[#1F1A18] dark:text-white tracking-tight">Media Library</h2>
          <p className="text-xs text-[#7A6C63] dark:text-slate-400 mt-1">
            Every AI-generated or uploaded ad image. Reuse one from a draft&apos;s Creative step (Choose from Media Library).
          </p>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-end gap-3">
          <div>
            <label htmlFor="media-target" className={labelCls}>Use in campaign</label>
            <select id="media-target" value={target} onChange={(e) => setTarget(e.target.value)} className={inputCls}>
              <option value="">Choose a draft…</option>
              {drafts.map((c) => (
                <option key={c.id} value={c.id}>{c.title || 'Untitled draft'}</option>
              ))}
            </select>
          </div>
          <label
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-xs font-bold ${target && !uploading ? 'cursor-pointer hover:bg-[#FAF8F5]' : 'opacity-50 cursor-not-allowed'}`}
          >
            <Upload className="w-4 h-4 text-[#F26D5B]" />
            <span>{uploading ? 'Uploading…' : 'Upload image'}</span>
            <input
              type="file"
              accept="image/jpeg,image/png"
              className="sr-only"
              disabled={!target || uploading}
              aria-describedby="upload-help"
              onChange={(e) => upload(e.target.files?.[0])}
            />
          </label>
        </div>
      </div>
      <p id="upload-help" className="text-[11px] text-[#7A6C63] dark:text-slate-400 -mt-3">
        Uploads are attached to a draft campaign (the API stores images per campaign), so choose a draft first. Use 1:1
        or 4:5 images; 9:16 is rejected.
      </p>
      <ErrorBox message={uploadError} />

      <div className="flex items-center gap-2">
        {(['ALL', 'generated', 'uploaded'] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setFilter(t)}
            aria-pressed={filter === t}
            className={`px-3.5 py-1.5 rounded-xl text-xs font-bold cursor-pointer ${filter === t ? 'bg-[#F26D5B] text-white' : 'bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 text-[#7A6C63] dark:text-slate-400'}`}
          >
            {t === 'ALL' ? 'All' : t === 'generated' ? 'Generated' : 'Uploaded'}
          </button>
        ))}
      </div>

      {error ? (
        <ErrorBox message={errorMessage(error)} />
      ) : !media ? (
        <Empty text="Loading media…" />
      ) : items.length === 0 ? (
        <Empty text="No images yet. Generate an ad or upload an image into a draft." />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {items.map((m) => <MediaThumb key={m.id} item={m}><button type="button" onClick={async () => { try { await deleteMedia(m.id); mutate(); } catch (e) { setUploadError(errorMessage(e)); } }} className="text-rose-600 font-bold">Delete image</button></MediaThumb>)}
        </div>
      )}
    </div>
  );
}

export function MediaPicker({ onPick, onClose }: { onPick: (imageId: string) => void; onClose: () => void }) {
  const { data, error } = useMedia();
  return (
    <Dialog title="Media Library" onClose={onClose} wide>
      {error ? (
        <ErrorBox message={errorMessage(error)} />
      ) : !data ? (
        <p className="text-xs">Loading…</p>
      ) : data.length === 0 ? (
        <p className="text-xs text-[#7A6C63] dark:text-slate-400">No images yet.</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {data.map((m) => (
            <MediaThumb key={m.id} item={m}>
              <button
                type="button"
                onClick={() => onPick(m.id)}
                aria-label={`Use ${m.filename}`}
                className="mt-1 w-full px-2 py-1 rounded-lg bg-[#F26D5B] text-white text-[11px] font-bold cursor-pointer"
              >
                Use this image
              </button>
            </MediaThumb>
          ))}
        </div>
      )}
    </Dialog>
  );
}

export default MediaView;
