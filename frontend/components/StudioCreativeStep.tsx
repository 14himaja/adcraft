'use client';

import React, { useState } from 'react';
import { AdImage } from './AdImage';
import { ArrowRight, Heart, MessageCircle, Share2, Bookmark, Sparkles, Upload, ImageIcon, RefreshCw } from 'lucide-react';
import {
  AdVariant,
  CTA_OPTIONS,
  Campaign,
  PostTarget,
  improveCopy,
  regenerateImage,
  uploadCampaignImage,
} from '../lib/api';
import { btnSecondary, inputCls, labelCls } from './Dialog';

export const LIMITS = { headline: 40, primary_text: 125, description: 30 } as const;
const chars = (s: string) => Array.from(s ?? '').length; // code points, like the backend's len()
export const ctaLabel = (cta: string) => cta.toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase());

const BLANK_VARIANT: AdVariant = { headline: '', primary_text: '', description: '', call_to_action: 'LEARN_MORE' };

/** Instagram feed mock-up of the selected version. */
export function AdPreview({ campaign }: { campaign: Campaign }) {
  const v = campaign.variants?.[campaign.selected_variant] ?? campaign.variants?.[0] ?? BLANK_VARIANT;
  return (
    <div className="w-[280px] bg-white dark:bg-black rounded-3xl border border-[#EDE6DD] dark:border-white/20 shadow-xl overflow-hidden flex flex-col">
      <div className="px-3 py-2 flex items-center gap-2 border-b border-slate-100 dark:border-white/5">
        <div className="w-6 h-6 rounded-full bg-gradient-to-tr from-[#FD1D1D] via-[#E1306C] to-[#405DE6]" />
        <div>
          <p className="text-[11px] font-bold leading-none">Your Instagram</p>
          <p className="text-[9px] text-[#7A6C63] dark:text-slate-400">Sponsored</p>
        </div>
      </div>
      <div className="relative w-full aspect-square bg-slate-100 dark:bg-slate-900 flex items-center justify-center">
        {campaign.image_url ? (
          <AdImage src={campaign.image_url} alt="Ad image" fill className="object-cover" />
        ) : (
          <span className="text-[11px] text-[#9C8F85] flex flex-col items-center gap-1"><ImageIcon className="w-6 h-6" />No image yet</span>
        )}
      </div>
      <div className="px-3 py-2 bg-[#FAF8F5] dark:bg-white/5 border-y border-[#EDE6DD] dark:border-white/5 flex items-center justify-between text-xs font-bold text-[#F26D5B]">
        <span>{ctaLabel(v.call_to_action)}</span>
        <ArrowRight className="w-3.5 h-3.5" />
      </div>
      <div className="p-3 space-y-1.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5"><Heart className="w-4 h-4" /><MessageCircle className="w-4 h-4" /><Share2 className="w-4 h-4" /></div>
          <Bookmark className="w-4 h-4" />
        </div>
        <p className="text-[11px] font-bold">{v.headline}</p>
        <p className="text-[10px] text-[#7A6C63] dark:text-slate-300 line-clamp-3">{v.primary_text}</p>
        {campaign.selected_hashtags && campaign.selected_hashtags.length > 0 && (
          <p className="text-[10px] text-[#F26D5B] font-medium line-clamp-2">
            {campaign.selected_hashtags.join(' ')}
          </p>
        )}
      </div>
    </div>
  );
}

interface Props {
  draft: Campaign;
  busy: boolean;
  onVariant: (patch: Partial<AdVariant>) => void;
  onSelectVariant: (index: number) => void;
  run: (label: string, fn: (id: string) => Promise<Campaign>) => Promise<boolean>;
  onOpenMedia: () => void;
  onPublishingDestinationsChange?: (destinations: Record<PostTarget, boolean>) => void;
  onHashtagsChange?: (hashtags: string[]) => void;
  onAiRecommendedChange?: (tags: string[]) => void;
}

function CountedField({ name, label, value, multiline, onChange }: {
  name: keyof typeof LIMITS; label: string; value: string; multiline?: boolean; onChange: (v: string) => void;
}) {
  const max = LIMITS[name];
  const n = chars(value);
  const over = n > max;
  const props = {
    id: `field-${name}`,
    value,
    'aria-invalid': over,
    'aria-describedby': `count-${name}`,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(e.target.value),
    className: `${inputCls} ${over ? 'border-rose-500 dark:border-rose-500' : ''}`,
  };
  return (
    <div>
      <div className="flex items-center justify-between">
        <label htmlFor={props.id} className={labelCls}>{label}</label>
        <span id={`count-${name}`} className={`text-[10px] font-bold ${over ? 'text-rose-600' : 'text-[#9C8F85]'}`}>
          {`${n}/${max}`}
        </span>
      </div>
      {multiline ? <textarea rows={3} {...props} /> : <input type="text" {...props} />}
    </div>
  );
}

export function StudioCreativeStep({
  draft,
  busy,
  onVariant,
  onSelectVariant,
  run,
  onOpenMedia,
  onPublishingDestinationsChange,
  onHashtagsChange,
  onAiRecommendedChange,
}: Props) {
  const [extraPrompt, setExtraPrompt] = useState('');
  const [instruction, setInstruction] = useState('');
  const variants = draft.variants?.length ? draft.variants : [{ headline: '', primary_text: '', description: '', call_to_action: 'LEARN_MORE' }];
  const v = variants[draft.selected_variant] ?? variants[0];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <div className="lg:col-span-7 space-y-4">
        {variants.length > 1 && (
          <fieldset className="space-y-1.5">
            <legend className={labelCls}>Ad versions (pick the one to publish)</legend>
            {variants.map((x, i) => (
              <label key={i} className={`flex items-center gap-2 p-2 rounded-xl border text-xs cursor-pointer ${i === draft.selected_variant ? 'border-[#F26D5B] bg-[#FEECE7] dark:bg-[#F26D5B]/15' : 'border-[#EDE6DD] dark:border-white/10'}`}>
                <input type="radio" name="variant" checked={i === draft.selected_variant} onChange={() => onSelectVariant(i)} />
                <span className="font-semibold">Version {i + 1}: {x.headline || '(no headline)'}</span>
              </label>
            ))}
          </fieldset>
        )}

        <CountedField name="headline" label="Headline" value={v.headline} onChange={(headline) => onVariant({ headline })} />
        <CountedField name="primary_text" label="Primary text" value={v.primary_text} multiline onChange={(primary_text) => onVariant({ primary_text })} />
        <CountedField name="description" label="Description" value={v.description} onChange={(description) => onVariant({ description })} />
        <div>
          <label htmlFor="field-cta" className={labelCls}>Call to action</label>
          <select id="field-cta" value={v.call_to_action} onChange={(e) => onVariant({ call_to_action: e.target.value })} className={inputCls}>
            {CTA_OPTIONS.map((c) => <option key={c} value={c}>{ctaLabel(c)}</option>)}
          </select>
        </div>

        <div className="py-3 border-b border-[#EDE6DD] dark:border-white/10 space-y-2">
          <label htmlFor="rewrite" className={labelCls}>Rewrite instruction</label>
          <textarea
            id="rewrite"
            rows={2}
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="e.g. make version 2 about saving review time and mention the free trial"
            className={inputCls}
          />
          <button
            type="button"
            className={btnSecondary}
            disabled={busy || !instruction.trim()}
            aria-describedby={instruction.trim() ? undefined : 'rewrite-help'}
            onClick={() => run('Rewriting your ad…', (id) => improveCopy(id, instruction.trim()))}
          >
            <Sparkles className="w-3.5 h-3.5 text-[#F26D5B]" />
            <span>AI rewrite</span>
          </button>
          {!instruction.trim() && <p id="rewrite-help" className="text-[10px] text-[#9C8F85]">Type an instruction to enable AI rewrite.</p>}
        </div>
      </div>

      <div className="lg:col-span-5 space-y-3 flex flex-col items-center">
        <AdPreview campaign={draft} />

        <div className="w-full space-y-2">
          <label htmlFor="extra-prompt" className={labelCls}>Extra image instructions (optional)</label>
          <input id="extra-prompt" value={extraPrompt} onChange={(e) => setExtraPrompt(e.target.value)} placeholder="e.g. add a chocolate cake in front" className={inputCls} />
          <div className="flex flex-wrap gap-2">
            <button type="button" className={btnSecondary} disabled={busy} onClick={() => run('Creating a new image…', (id) => regenerateImage(id, extraPrompt.trim() || undefined))}>
              <RefreshCw className="w-3.5 h-3.5" /><span>Regenerate image</span>
            </button>
            <label className={`${btnSecondary} ${busy ? 'opacity-50 pointer-events-none' : ''}`}>
              <Upload className="w-3.5 h-3.5" />
              <span>Upload my image</span>
              <input
                type="file"
                accept="image/jpeg,image/png"
                className="sr-only"
                disabled={busy}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = '';
                  if (file) run('Uploading your image…', (id) => uploadCampaignImage(id, file));
                }}
              />
            </label>
            <button type="button" className={btnSecondary} disabled={busy} onClick={onOpenMedia}>
              <ImageIcon className="w-3.5 h-3.5" /><span>Choose from Media Library</span>
            </button>
          </div>
          <p className="text-[10px] text-[#9C8F85]">Uploads must be 1:1 or 4:5 (9:16 phone screenshots are rejected).</p>
        </div>
      </div>
    </div>
  );
}
