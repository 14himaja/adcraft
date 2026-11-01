'use client';

import React, { useEffect, useId, useRef, useState } from 'react';
import {
  X,
  Sparkles,
  AlertCircle,
  Globe,
  Search,
  Plus,
  ArrowRight,
  ArrowLeft,
  ShieldCheck,
  Save,
  Send,
  Lightbulb,
  Users,
  Calendar,
  Palette,
  Hash,
  Share2,
  Check,
  ChevronRight,
  ExternalLink,
} from 'lucide-react';
import {
  AdVariant,
  ApiError,
  Audience,
  Campaign,
  CampaignFields,
  MetaInterest,
  MetaLocation,
  PostTarget,
  createCampaign,
  duplicateCampaign,
  getCampaign,
  searchInterests,
  searchLocations,
  setCampaignImage,
  updateCampaign,
} from '../lib/api';
import { ErrorBox, btnPrimary, btnSecondary, errorMessage, inputCls, labelCls } from './Dialog';
import { MediaPicker } from './MediaView';
import { PublishFlow, fieldLabel, publishBlockReason } from './PublishFlow';
import { StudioCreativeStep, AdPreview } from './StudioCreativeStep';
import { HashtagSelector } from './HashtagSelector';
import { DestinationState, PublishingDestinations } from './PublishingDestinations';
import { AdImage } from './AdImage';

export type StudioSection = 1 | 2 | 3 | 4 | 5 | 6;

export interface SectionMeta {
  id: StudioSection;
  title: string;
  name: string;
  subtitle: string;
  icon: React.ComponentType<{ className?: string }>;
}

export const SECTIONS: SectionMeta[] = [
  { id: 1, title: '1. Objective & Idea', name: 'Objective & Idea', subtitle: 'Campaign goal, title & promotion idea', icon: Lightbulb },
  { id: 2, title: '2. Target Audience', name: 'Target Audience', subtitle: 'Locations, demographics & interests', icon: Users },
  { id: 3, title: '3. Budget & Schedule', name: 'Budget & Schedule', subtitle: 'Daily budget & flight dates', icon: Calendar },
  { id: 4, title: '4. Creative & Preview', name: 'Creative & Preview', subtitle: 'Ad copy, image & live Instagram preview', icon: Palette },
  { id: 5, title: '5. Hashtags', name: 'Hashtags', subtitle: 'AI-recommended, trending & custom tags', icon: Hash },
  { id: 6, title: '6. Publishing', name: 'Publishing', subtitle: 'Social destinations & ad campaign launch', icon: Share2 },
];

const MAX_CITIES = 10;
const MAX_INTERESTS = 5;
const COUNTRIES: [string, string][] = [
  ['IN', 'India'],
  ['US', 'United States'],
  ['GB', 'United Kingdom'],
  ['CA', 'Canada'],
  ['AE', 'United Arab Emirates'],
  ['SG', 'Singapore'],
  ['', 'None (cities only)'],
];

const BLANK: Campaign = {
  id: '',
  status: 'DRAFT',
  idea: '',
  title: '',
  objective: 'TRAFFIC',
  landing_url: '',
  audience: { countries: ['IN'], cities: [], age_min: 18, age_max: 65, genders: 'ALL', interests: [] },
  daily_budget: 100,
  currency: 'INR',
  start_date: null,
  end_date: null,
  variants: [{ headline: '', primary_text: '', description: '', call_to_action: 'LEARN_MORE' }],
  selected_variant: 0,
  image_prompt: '',
  image_id: null,
  image_url: null,
  selected_hashtags: [],
  custom_hashtags: [],
  ai_recommended_hashtags: [],
  missing_fields: [],
  warnings: [],
  can_publish: false,
  can_activate: false,
};

const toFields = (d: Campaign): CampaignFields => ({
  title: d.title,
  objective: d.objective,
  landing_url: d.landing_url,
  audience: d.audience,
  daily_budget: d.daily_budget,
  start_date: d.start_date,
  end_date: d.end_date,
  variants: d.variants.some((v) => v.headline || v.primary_text || v.description) ? d.variants : undefined,
  selected_variant: d.selected_variant,
  publishing_destinations: d.publishing_destinations,
  selected_hashtags: d.selected_hashtags ?? undefined,
  custom_hashtags: d.custom_hashtags ?? undefined,
  ai_recommended_hashtags: d.ai_recommended_hashtags ?? undefined,
});

const chip =
  'inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#FEECE7] dark:bg-[#F26D5B]/20 text-[#F26D5B] border border-[#FAD6CD] dark:border-[#F26D5B]/30 text-xs font-bold';
const toggle = (on: boolean) =>
  `p-3 rounded-2xl border text-left cursor-pointer transition-all ${
    on
      ? 'bg-[#FEECE7] dark:bg-[#F26D5B]/15 border-[#F26D5B]'
      : 'bg-[#FAF8F5] dark:bg-[#0F172A] border-[#EDE6DD] dark:border-white/10 hover:border-[#F26D5B]/50'
  }`;

interface CampaignStudioModalProps {
  campaignId: string | null;
  initialCampaign?: Campaign | null;
  onClose: () => void;
  onChanged: () => void;
}

interface SectionSaveBarProps {
  sectionTitle: string;
  dirty: boolean;
  busy: boolean;
  onSave: () => void;
  onNext?: () => void;
  isLast?: boolean;
}

function SectionSaveBar({
  sectionTitle,
  dirty,
  busy,
  onSave,
  onNext,
  isLast,
}: SectionSaveBarProps) {
  return (
    <div className="pt-4 mt-6 border-t border-[#EDE6DD] dark:border-white/10 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        {busy ? (
          <span className="text-xs text-[#F26D5B] font-medium flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-[#F26D5B] animate-ping" />
            Saving changes…
          </span>
        ) : dirty ? (
          <span className="text-xs text-amber-600 dark:text-amber-400 font-medium flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-500" />
            Unsaved changes in {sectionTitle}
          </span>
        ) : (
          <span className="text-xs text-emerald-700 dark:text-emerald-400 font-medium flex items-center gap-1">
            <Check className="w-3.5 h-3.5" />
            {sectionTitle} saved
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onSave}
          disabled={busy}
          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-[#1F1A18] dark:text-white hover:bg-white dark:hover:bg-white/10 hover:border-[#F26D5B]/50 transition-colors cursor-pointer shadow-2xs"
          title={`Save changes in ${sectionTitle}`}
        >
          <Save className="w-3.5 h-3.5 text-[#F26D5B]" />
          <span>Save {sectionTitle}</span>
        </button>

        {!isLast && onNext && (
          <button
            type="button"
            onClick={onNext}
            disabled={busy}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-semibold bg-[#F26D5B]/10 hover:bg-[#F26D5B]/20 text-[#F26D5B] transition-colors cursor-pointer"
          >
            <span>Next</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

export function CampaignStudioModal({ campaignId, initialCampaign, onClose, onChanged }: CampaignStudioModalProps) {
  const [draft, setDraft] = useState<Campaign | null>(initialCampaign ?? (campaignId ? null : BLANK));
  const [dirty, setDirty] = useState(Boolean(initialCampaign && !initialCampaign.id));
  const [step, setStep] = useState<StudioSection>(1);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<'publish' | 'media' | null>(null);
  const [result, setResult] = useState<'DONE' | 'DISCARDED' | null>(null);

  // Search states for audience
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<MetaInterest[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [cityQuery, setCityQuery] = useState('');
  const [cityResults, setCityResults] = useState<MetaLocation[]>([]);
  const [cityError, setCityError] = useState<string | null>(null);
  const [cityCountry, setCityCountry] = useState('IN');
  const cityTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    if (!initialCampaign && campaignId) {
      getCampaign(campaignId).then(setDraft).catch((e) => setError(errorMessage(e)));
    }
  }, [campaignId, initialCampaign]);

  if (!draft) {
    return (
      <Shell onClose={onClose}>
        <div className="p-10 text-center text-xs">
          {error ? <ErrorBox message={error} /> : <p role="status">Loading draft…</p>}
        </div>
      </Shell>
    );
  }

  if (draft.id && draft.status !== 'DRAFT') {
    const publishedVariant = draft.variants?.[draft.selected_variant] ?? draft.variants?.[0];
    return (
      <Shell onClose={onClose} title={draft.title || 'Campaign'} statusBadge={draft.status}>
        <div className="p-6 space-y-4 overflow-y-auto">
          <p role="status" className="rounded-xl bg-amber-500/10 border border-amber-500/30 p-3 text-sm font-medium">
            Published ads cannot be edited. Duplicate as a new draft.
          </p>
          <h4 className="font-bold text-lg">{draft.title}</h4>
          <p className="text-xs text-[#7A6C63] dark:text-slate-400">
            {draft.status} · {draft.objective} · {draft.currency} {draft.daily_budget ?? '—'} per day
          </p>
          {publishedVariant && (
            <div className="space-y-1 text-sm bg-[#FAF8F5] dark:bg-white/5 p-4 rounded-2xl border border-[#EDE6DD] dark:border-white/10">
              <p className="font-semibold text-[#1F1A18] dark:text-white">{publishedVariant.headline}</p>
              <p className="whitespace-pre-wrap text-[#5C5047] dark:text-slate-300">{publishedVariant.primary_text}</p>
              {publishedVariant.description && (
                <p className="text-xs text-[#7A6C63] dark:text-slate-400">{publishedVariant.description}</p>
              )}
              <p className="text-xs font-bold text-[#F26D5B] mt-2">Call to action: {publishedVariant.call_to_action}</p>
            </div>
          )}
          {draft.landing_url && <p className="text-xs break-all">Landing page: {draft.landing_url}</p>}
          <p className="text-xs text-[#7A6C63] dark:text-slate-400">
            Audience: {draft.audience.countries.join(', ') || 'Cities only'} · ages {draft.audience.age_min}–
            {draft.audience.age_max} · {draft.audience.genders.toLowerCase()}
          </p>
          {draft.image_url && (
            <div className="relative w-64 aspect-square rounded-2xl overflow-hidden border border-[#EDE6DD] dark:border-white/10">
              <AdImage src={draft.image_url} alt="Ad image" fill unoptimized className="object-cover" />
            </div>
          )}
          <div className="flex justify-end gap-2 pt-4 border-t border-[#EDE6DD] dark:border-white/10">
            <button type="button" className={btnSecondary} onClick={onClose}>
              Close
            </button>
            <button
              type="button"
              className={btnPrimary}
              disabled={!!busy}
              onClick={async () => {
                setBusy('Duplicating…');
                try {
                  await duplicateCampaign(draft.id);
                  onChanged();
                  onClose();
                } catch (e) {
                  setError(errorMessage(e));
                } finally {
                  setBusy(null);
                }
              }}
            >
              Duplicate as new draft
            </button>
          </div>
          <ErrorBox message={error} />
        </div>
      </Shell>
    );
  }

  const edit = (patch: Partial<Campaign>) => {
    setDraft({ ...draft, ...patch });
    setDirty(true);
  };
  const editAudience = (patch: Partial<Audience>) => edit({ audience: { ...draft.audience, ...patch } });
  const editVariant = (patch: Partial<AdVariant>) =>
    edit({
      variants: (draft.variants.length ? draft.variants : BLANK.variants).map((v, i) =>
        i === draft.selected_variant ? { ...v, ...patch } : v
      ),
    });

  const run = async (label: string, fn?: (id: string) => Promise<Campaign>) => {
    setBusy(label);
    setError(null);
    try {
      let current = draft;
      if (dirty || !draft.id) {
        if (draft.id && draft.status === 'DRAFT') {
          current = await updateCampaign(draft.id, toFields(draft));
        } else if (!draft.id) {
          current = await createCampaign({
            ...toFields(draft),
            title: draft.title && !draft.title.endsWith('(Draft)') ? `${draft.title} (Draft)` : draft.title,
          });
        }
        setDraft(current);
        setDirty(false);
      }
      if (fn) setDraft(await fn(current.id));
      onChanged();
      return true;
    } catch (e) {
      setError(errorMessage(e));
      return false;
    } finally {
      setBusy(null);
    }
  };

  const handleClose = async () => {
    if (dirty && draft) {
      await run('Saving…');
    }
    onClose();
  };

  const goTo = async (next: StudioSection) => {
    if (next === step) return;
    if (dirty && !(await run('Saving…'))) return;
    setStep(next);
  };

  const onSearch = (q: string) => {
    setQuery(q);
    clearTimeout(timer.current);
    if (!q.trim()) return setResults([]);
    timer.current = setTimeout(() => searchInterests(q.trim()).then(setResults).catch(() => setResults([])), 300);
  };

  const onCitySearch = (q: string) => {
    setCityQuery(q);
    setCityError(null);
    clearTimeout(cityTimer.current);
    if (!q.trim()) return setCityResults([]);
    const country = draft.audience.countries[0] || cityCountry;
    cityTimer.current = setTimeout(
      () =>
        searchLocations(q.trim(), country)
          .then(setCityResults)
          .catch((e) => {
            setCityResults([]);
            setCityError(
              e instanceof ApiError && e.code === 'META_NOT_CONNECTED'
                ? 'Connect Meta to search cities'
                : errorMessage(e)
            );
          }),
      300
    );
  };

  const addCity = (loc: MetaLocation) => {
    setCityCountry(loc.country_code);
    setCityQuery('');
    setCityResults([]);
    editAudience({
      cities: [...draft.audience.cities, { key: loc.key, name: loc.name }],
      countries: draft.audience.countries.filter((c) => c !== loc.country_code),
    });
  };

  if (result) {
    return (
      <Shell onClose={onClose} title={draft.title || 'Campaign'} statusBadge={draft.status}>
        <div className="p-10 text-center space-y-4 text-sm">
          <p
            role="status"
            className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-800 dark:text-emerald-300 font-semibold"
          >
            {result === 'DONE'
              ? 'Submitted and activated on Meta. Meta review and delivery availability still apply.'
              : 'Publishing was discarded. Anything created on Meta was deleted and your draft is kept.'}
          </p>
          <button type="button" className={btnPrimary} onClick={onClose}>
            Done
          </button>
        </div>
      </Shell>
    );
  }

  const { audience } = draft;
  const chosenCities = new Set(audience.cities.map((c) => c.key));
  const cityFull = audience.cities.length >= MAX_CITIES;
  const chosenIds = new Set(audience.interests.map((i) => i.id));
  const publishReason = publishBlockReason(draft);
  const lowBudget = draft.daily_budget !== null && draft.daily_budget < 50;

  const destinationStatuses: Partial<Record<PostTarget, DestinationState>> = {};
  if (draft.posted) {
    for (const [target, info] of Object.entries(draft.posted)) {
      destinationStatuses[target as PostTarget] = {
        status: 'PUBLISHED',
        media_id: info.media_id,
        at: info.at,
      };
    }
  }

  // Validation status helpers for each section
  const isSectionComplete = (sec: StudioSection): boolean => {
    switch (sec) {
      case 1:
        return Boolean(draft.title?.trim() && (draft.objective !== 'TRAFFIC' || draft.landing_url?.trim()));
      case 2:
        return draft.audience.countries.length > 0 || draft.audience.cities.length > 0;
      case 3:
        return draft.daily_budget !== null && draft.daily_budget >= 50;
      case 4:
        return Boolean(
          (draft.image_id || draft.image_url) &&
            draft.variants?.[draft.selected_variant]?.headline &&
            draft.variants?.[draft.selected_variant]?.primary_text
        );
      case 5:
        return (draft.selected_hashtags ?? []).length > 0;
      case 6:
        return Boolean(draft.can_publish || Object.values(draft.publishing_destinations ?? {}).some(Boolean));
      default:
        return false;
    }
  };

  const hasSectionError = (sec: StudioSection): boolean => {
    const missing = draft.missing_fields ?? [];
    switch (sec) {
      case 1:
        return missing.includes('title') || missing.includes('landing_url');
      case 2:
        return missing.includes('audience');
      case 3:
        return Boolean(lowBudget || missing.includes('daily_budget'));
      case 4:
        return missing.includes('image_id') || missing.includes('variants');
      case 6:
        return Boolean(publishReason);
      default:
        return false;
    }
  };

  const selectedVariantObj = draft.variants?.[draft.selected_variant] ?? draft.variants?.[0];
  const activeDestinationsCount = Object.values(draft.publishing_destinations ?? {}).filter(Boolean).length;

  return (
    <Shell onClose={handleClose} title="AdCraft Studio" statusBadge={draft.status === 'DRAFT' ? 'Draft' : draft.status}>
      <div className="flex flex-col md:flex-row flex-1 overflow-hidden min-h-[580px]">
        {/* ========================================================================= */}
        {/* LEFT SIDEBAR NAVIGATION */}
        {/* ========================================================================= */}
        <nav
          aria-label="Studio sections"
          className="w-full md:w-64 lg:w-72 bg-[#FAF8F5] dark:bg-[#0B0F19] border-b md:border-b-0 md:border-r border-[#EDE6DD] dark:border-white/10 p-3 sm:p-4 flex md:flex-col gap-1.5 overflow-x-auto md:overflow-y-auto shrink-0"
        >
          {SECTIONS.map((sec) => {
            const isActive = step === sec.id;
            const complete = isSectionComplete(sec.id);
            const errorInSec = hasSectionError(sec.id);

            return (
              <button
                key={sec.id}
                type="button"
                aria-current={isActive ? 'step' : undefined}
                onClick={() => goTo(sec.id)}
                disabled={!!busy}
                className={`w-full flex items-center justify-between p-3 rounded-2xl text-left transition-all cursor-pointer whitespace-nowrap md:whitespace-normal ${
                  isActive
                    ? 'bg-[#FEECE7] dark:bg-[#F26D5B]/15 border border-[#FAD6CD] dark:border-[#F26D5B]/30 text-[#F26D5B] font-bold shadow-2xs'
                    : 'text-[#5C5047] dark:text-slate-300 hover:bg-white dark:hover:bg-white/5 border border-transparent'
                }`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div
                    className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 ${
                      isActive
                        ? 'bg-[#F26D5B] text-white'
                        : 'bg-white dark:bg-white/5 text-[#7A6C63] dark:text-slate-400 border border-[#EDE6DD] dark:border-white/10'
                    }`}
                  >
                    <sec.icon className="w-4 h-4" />
                  </div>
                  <div className="min-w-0 pr-1">
                    <span className="block text-xs font-bold leading-tight truncate">{sec.title}</span>
                    <span className="hidden md:block text-[10px] text-[#8C7E74] dark:text-slate-400 leading-tight mt-0.5 truncate">
                      {sec.subtitle}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-1.5 shrink-0 ml-1">
                  {errorInSec ? (
                    <AlertCircle className="w-3.5 h-3.5 text-amber-500 dark:text-amber-400 shrink-0" />
                  ) : complete ? (
                    <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
                  ) : null}
                  {isActive && <ChevronRight className="w-3.5 h-3.5 text-[#F26D5B] hidden md:block shrink-0" />}
                </div>
              </button>
            );
          })}
        </nav>

        {/* ========================================================================= */}
        {/* RIGHT CONTENT PANEL */}
        {/* ========================================================================= */}
        <div className="flex-1 overflow-y-auto p-5 sm:p-7 space-y-6 bg-white dark:bg-[#0B0F19]">
          {/* Section Heading Header */}
          <div className="pb-3 border-b border-[#EDE6DD] dark:border-white/10 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h4 className="text-base font-bold text-[#1F1A18] dark:text-white">
                {SECTIONS.find((s) => s.id === step)?.title}
              </h4>
              <p className="text-xs text-[#7A6C63] dark:text-slate-400">
                {SECTIONS.find((s) => s.id === step)?.subtitle}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => run(`Saving ${SECTIONS.find((s) => s.id === step)?.title || 'section'}…`)}
                disabled={!!busy}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-[#1F1A18] dark:text-white hover:border-[#F26D5B]/40 hover:text-[#F26D5B] transition-colors cursor-pointer"
                title={`Save ${SECTIONS.find((s) => s.id === step)?.title}`}
              >
                <Save className="w-3.5 h-3.5 text-[#F26D5B]" />
                <span>Save Section</span>
              </button>
              <span className="text-[11px] font-semibold text-[#8C7E74] dark:text-slate-400">
                <span className="text-rose-500 font-bold">*</span> Required for publishing
              </span>
            </div>
          </div>

          {/* Missing Fields Banner */}
          {draft.missing_fields?.length > 0 && (
            <div className="p-3.5 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-900 dark:text-amber-200 text-xs font-semibold flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400" />
                <span>
                  Missing before you can publish:{' '}
                  <strong>{draft.missing_fields.map(fieldLabel).join(', ')}</strong>
                </span>
              </div>
            </div>
          )}

          {draft.warnings?.length > 0 && (
            <ul
              className="p-3.5 rounded-2xl bg-blue-500/10 border border-blue-500/20 text-blue-900 dark:text-blue-200 text-xs space-y-1 list-disc list-inside"
              aria-label="Warnings"
            >
              {draft.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}

          <ErrorBox message={error} />
          {busy && (
            <p role="status" className="text-xs font-semibold text-[#F26D5B] animate-pulse">
              {busy}
            </p>
          )}

          {/* --------------------------------------------------------------------- */}
          {/* SECTION 1: OBJECTIVE & IDEA */}
          {/* --------------------------------------------------------------------- */}
          {step === 1 && (
            <div className="space-y-5">
              {draft.idea && (
                <div className="p-3.5 rounded-2xl bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-xs text-[#7A6C63] dark:text-slate-400">
                  <strong className="text-[#1F1A18] dark:text-white">Your idea / prompt:</strong> {draft.idea}
                </div>
              )}
              <div>
                <label htmlFor="title" className={labelCls}>
                  Campaign title <span className="text-rose-500 font-bold">*</span>
                </label>
                <input
                  id="title"
                  value={draft.title}
                  onChange={(e) => edit({ title: e.target.value })}
                  placeholder="e.g. Python Course Launch"
                  className={inputCls}
                />
              </div>
              <div>
                <span className={labelCls}>
                  Campaign objective <span className="text-rose-500 font-bold">*</span>
                </span>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {(
                    [
                      ['TRAFFIC', '🚀 Traffic', 'Send people to your website or landing page.'],
                      ['AWARENESS', '📢 Awareness', 'Show the ad to as many interested people as possible.'],
                    ] as const
                  ).map(([id, t, d]) => (
                    <button
                      key={id}
                      type="button"
                      aria-pressed={draft.objective === id}
                      onClick={() => edit({ objective: id })}
                      className={toggle(draft.objective === id)}
                    >
                      <span className="block text-sm font-bold text-[#1F1A18] dark:text-white">{t}</span>
                      <span className="block text-[11px] text-[#7A6C63] dark:text-slate-400 mt-0.5">{d}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label htmlFor="landing" className={labelCls}>
                  Landing URL (https){' '}
                  {draft.objective === 'TRAFFIC' && <span className="text-rose-500 font-bold">*</span>}
                </label>
                <div className="relative">
                  <Globe className="w-4 h-4 text-[#9C8F85] absolute left-3.5 top-1/2 -translate-y-1/2" />
                  <input
                    id="landing"
                    type="url"
                    value={draft.landing_url}
                    onChange={(e) => edit({ landing_url: e.target.value })}
                    placeholder="https://yourwebsite.com"
                    className={`${inputCls} pl-10`}
                  />
                </div>
                <p className="text-[11px] text-[#9C8F85] mt-1">
                  Required when campaign objective is set to Traffic.
                </p>
              </div>

              <SectionSaveBar
                sectionTitle="Objective & Idea"
                dirty={dirty}
                busy={!!busy}
                onSave={() => run('Saving Objective & Idea…')}
                onNext={() => goTo(2)}
              />
            </div>
          )}

          {/* --------------------------------------------------------------------- */}
          {/* SECTION 2: TARGET AUDIENCE */}
          {/* --------------------------------------------------------------------- */}
          {step === 2 && (
            <div className="space-y-5">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="country" className={labelCls}>
                    Country {draft.audience.cities.length === 0 && <span className="text-rose-500 font-bold">*</span>}
                  </label>
                  <select
                    id="country"
                    value={audience.countries[0] ?? ''}
                    onChange={(e) => editAudience({ countries: e.target.value ? [e.target.value] : [] })}
                    className={inputCls}
                  >
                    {COUNTRIES.map(([code, name]) => (
                      <option key={code} value={code}>
                        {name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <span className={labelCls}>Gender</span>
                  <div className="flex gap-1">
                    {(['ALL', 'MEN', 'WOMEN'] as const).map((g) => (
                      <button
                        key={g}
                        type="button"
                        aria-pressed={audience.genders === g}
                        onClick={() => editAudience({ genders: g })}
                        className={`flex-1 ${toggle(audience.genders === g)} py-1.5 text-xs font-bold text-center`}
                      >
                        {g === 'ALL' ? 'All' : g === 'MEN' ? 'Men' : 'Women'}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label htmlFor="age-min" className={labelCls}>
                    Minimum age
                  </label>
                  <input
                    id="age-min"
                    type="number"
                    min={18}
                    max={65}
                    value={audience.age_min}
                    onChange={(e) => editAudience({ age_min: Number(e.target.value) })}
                    className={inputCls}
                  />
                </div>
                <div>
                  <label htmlFor="age-max" className={labelCls}>
                    Maximum age
                  </label>
                  <input
                    id="age-max"
                    type="number"
                    min={18}
                    max={65}
                    value={audience.age_max}
                    onChange={(e) => editAudience({ age_max: Number(e.target.value) })}
                    className={inputCls}
                  />
                </div>
              </div>

              <div>
                <span className={labelCls}>Cities</span>
                <div className="flex flex-wrap gap-2">
                  {audience.cities.length === 0 && (
                    <span className="text-[11px] text-[#9C8F85]">
                      Targeting whole country. Search below to narrow down to specific cities.
                    </span>
                  )}
                  {audience.cities.map((c) => (
                    <span key={c.key} className={chip}>
                      <span>{c.name}</span>
                      <button
                        type="button"
                        aria-label={`Remove city ${c.name}`}
                        onClick={() => editAudience({ cities: audience.cities.filter((x) => x.key !== c.key) })}
                        className="cursor-pointer"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
                <div className="relative mt-2">
                  <Search className="w-4 h-4 text-[#9C8F85] absolute left-3.5 top-1/2 -translate-y-1/2" />
                  <input
                    id="city-search"
                    aria-label="Search cities"
                    value={cityQuery}
                    disabled={cityFull}
                    onChange={(e) => onCitySearch(e.target.value)}
                    placeholder={cityFull ? 'City limit reached' : 'e.g. Mumbai, Pune'}
                    className={`${inputCls} pl-10`}
                    aria-describedby="city-help"
                  />
                </div>
                <p
                  id="city-help"
                  className={`text-[11px] mt-1 ${cityError ? 'text-rose-600 font-bold' : 'text-[#9C8F85]'}`}
                >
                  {cityError ?? `Up to ${MAX_CITIES} cities.`}
                </p>
                {!cityFull && cityResults.some((r) => !chosenCities.has(r.key)) && (
                  <div className="flex flex-wrap gap-1.5 p-2.5 mt-1 bg-[#FAF8F5] dark:bg-[#0F172A] rounded-xl border border-[#EDE6DD] dark:border-white/10">
                    {cityResults
                      .filter((r) => !chosenCities.has(r.key))
                      .map((r) => (
                        <button
                          key={r.key}
                          type="button"
                          aria-label={`Add city ${r.name}`}
                          onClick={() => addCity(r)}
                          className="px-2.5 py-1 bg-white dark:bg-white/10 border border-[#EDE6DD] dark:border-white/10 hover:border-[#F26D5B] text-xs font-semibold rounded-full flex items-center gap-1 cursor-pointer"
                        >
                          <Plus className="w-3 h-3 text-[#F26D5B]" />
                          <span>{r.name}</span>
                        </button>
                      ))}
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <label htmlFor="interest-search" className={labelCls}>
                  Search Meta interests (up to {MAX_INTERESTS})
                </label>
                <div className="relative">
                  <Search className="w-4 h-4 text-[#9C8F85] absolute left-3.5 top-1/2 -translate-y-1/2" />
                  <input
                    id="interest-search"
                    value={query}
                    onChange={(e) => onSearch(e.target.value)}
                    placeholder="e.g. Python, Baking, Fitness"
                    className={`${inputCls} pl-10`}
                  />
                </div>
                {results.some((r) => !chosenIds.has(r.id)) && (
                  <div className="flex flex-wrap gap-1.5 p-2.5 bg-[#FAF8F5] dark:bg-[#0F172A] rounded-xl border border-[#EDE6DD] dark:border-white/10">
                    {results
                      .filter((r) => !chosenIds.has(r.id))
                      .map((r) => (
                        <button
                          key={r.id}
                          type="button"
                          disabled={audience.interests.length >= MAX_INTERESTS}
                          aria-label={`Add interest ${r.name}`}
                          onClick={() =>
                            editAudience({ interests: [...audience.interests, { id: r.id, name: r.name }] })
                          }
                          className="px-2.5 py-1 bg-white dark:bg-white/10 border border-[#EDE6DD] dark:border-white/10 hover:border-[#F26D5B] text-xs font-semibold rounded-full flex items-center gap-1 cursor-pointer"
                        >
                          <Plus className="w-3 h-3 text-[#F26D5B]" />
                          <span>{r.name}</span>
                        </button>
                      ))}
                  </div>
                )}
                <div className="flex flex-wrap gap-2">
                  {audience.interests.map((i) => (
                    <span key={i.id} className={chip}>
                      <span>{i.name}</span>
                      <button
                        type="button"
                        aria-label={`Remove interest ${i.name}`}
                        onClick={() => editAudience({ interests: audience.interests.filter((x) => x.id !== i.id) })}
                        className="cursor-pointer"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              </div>

              <SectionSaveBar
                sectionTitle="Target Audience"
                dirty={dirty}
                busy={!!busy}
                onSave={() => run('Saving Target Audience…')}
                onNext={() => goTo(3)}
              />
            </div>
          )}

          {/* --------------------------------------------------------------------- */}
          {/* SECTION 3: BUDGET & SCHEDULE */}
          {/* --------------------------------------------------------------------- */}
          {step === 3 && (
            <div className="space-y-5">
              <div>
                <label htmlFor="budget" className={labelCls}>
                  Daily budget (₹) <span className="text-rose-500 font-bold">*</span>
                </label>
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    id="budget"
                    type="number"
                    min={50}
                    step={10}
                    value={draft.daily_budget ?? ''}
                    aria-invalid={lowBudget}
                    aria-describedby="budget-help"
                    onChange={(e) =>
                      edit({ daily_budget: e.target.value === '' ? null : Number(e.target.value) })
                    }
                    className={`${inputCls} max-w-40`}
                  />
                  {[50, 100, 300, 500].map((b) => (
                    <button
                      key={b}
                      type="button"
                      aria-pressed={draft.daily_budget === b}
                      onClick={() => edit({ daily_budget: b })}
                      className={`${toggle(draft.daily_budget === b)} px-3.5 py-1.5 text-xs font-bold`}
                    >
                      ₹{b}
                    </button>
                  ))}
                </div>
                <p
                  id="budget-help"
                  className={`text-[11px] mt-1 ${lowBudget ? 'text-rose-600 font-bold' : 'text-[#9C8F85]'}`}
                >
                  {lowBudget ? 'Minimum is ₹50/day.' : 'Minimum ₹50/day for paid Meta delivery.'}
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="start" className={labelCls}>
                    Start date
                  </label>
                  <input
                    id="start"
                    type="date"
                    value={draft.start_date ?? ''}
                    onChange={(e) => edit({ start_date: e.target.value || null })}
                    className={inputCls}
                  />
                </div>
                <div>
                  <label htmlFor="end" className={labelCls}>
                    End date
                  </label>
                  <input
                    id="end"
                    type="date"
                    value={draft.end_date ?? ''}
                    min={draft.start_date ?? undefined}
                    onChange={(e) => edit({ end_date: e.target.value || null })}
                    className={inputCls}
                  />
                </div>
              </div>

              <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-900 dark:text-emerald-200 text-xs flex gap-2.5">
                <ShieldCheck className="w-5 h-5 shrink-0 text-emerald-600 dark:text-emerald-400 mt-0.5" />
                <p className="leading-relaxed">
                  Publishing starts delivery on the connected Instagram and Facebook accounts after Meta approves the ad.
                  The connected ad account pays up to the specified daily budget. Safe mode limits unexpected spend.
                </p>
              </div>

              <SectionSaveBar
                sectionTitle="Budget & Schedule"
                dirty={dirty}
                busy={!!busy}
                onSave={() => run('Saving Budget & Schedule…')}
                onNext={() => goTo(4)}
              />
            </div>
          )}

          {/* --------------------------------------------------------------------- */}
          {/* SECTION 4: CREATIVE & PREVIEW */}
          {/* --------------------------------------------------------------------- */}
          {step === 4 && (
            <div className="space-y-6">
              <StudioCreativeStep
                draft={draft}
                busy={!!busy}
                onVariant={editVariant}
                onSelectVariant={(i) => edit({ selected_variant: i })}
                run={run}
                onOpenMedia={() => setModal('media')}
                onPublishingDestinationsChange={(destinations) => edit({ publishing_destinations: destinations })}
                onHashtagsChange={(hashtags) => edit({ selected_hashtags: hashtags })}
                onAiRecommendedChange={(tags) => edit({ ai_recommended_hashtags: tags })}
              />

              <SectionSaveBar
                sectionTitle="Creative & Preview"
                dirty={dirty}
                busy={!!busy}
                onSave={() => run('Saving Creative & Preview…')}
                onNext={() => goTo(5)}
              />
            </div>
          )}

          {/* --------------------------------------------------------------------- */}
          {/* SECTION 5: HASHTAGS */}
          {/* --------------------------------------------------------------------- */}
          {step === 5 && (
            <div className="space-y-4">
              <HashtagSelector
                selectedHashtags={draft.selected_hashtags ?? []}
                onChange={(tags) => edit({ selected_hashtags: tags })}
                contextText={`${draft.idea || ''} ${draft.title || ''} ${selectedVariantObj?.headline || ''} ${
                  selectedVariantObj?.primary_text || ''
                } ${draft.image_prompt || ''}`}
                headline={selectedVariantObj?.headline}
                primaryText={selectedVariantObj?.primary_text}
                description={selectedVariantObj?.description}
                businessCategory={draft.idea || draft.title || ''}
                imagePrompt={draft.image_prompt}
                objective={draft.objective}
                audience={draft.audience}
                aiRecommendedHashtags={draft.ai_recommended_hashtags ?? []}
                onAiRecommendedChange={(tags) => edit({ ai_recommended_hashtags: tags })}
                customHashtags={draft.custom_hashtags ?? []}
                disabled={!!busy}
                title="Hashtag Selection"
              />

              <div className="p-3.5 rounded-2xl bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-xs text-[#7A6C63] dark:text-slate-400">
                <p>
                  Hashtags are included in the caption when publishing to supported platforms (Instagram &amp; Facebook Feed).
                  You can choose up to 5 hashtags combining AI recommendations, explored business tags, and custom hashtags.
                </p>
              </div>

              <SectionSaveBar
                sectionTitle="Hashtags"
                dirty={dirty}
                busy={!!busy}
                onSave={() => run('Saving Hashtags…')}
                onNext={() => goTo(6)}
              />
            </div>
          )}

          {/* --------------------------------------------------------------------- */}
          {/* SECTION 6: PUBLISHING */}
          {/* --------------------------------------------------------------------- */}
          {step === 6 && (
            <div className="space-y-6">
              <PublishingDestinations
                destinations={{
                  facebook_feed: Boolean(draft.publishing_destinations?.facebook_feed),
                  facebook_story: Boolean(draft.publishing_destinations?.facebook_story),
                  instagram_feed: Boolean(draft.publishing_destinations?.instagram_feed),
                  instagram_story: Boolean(draft.publishing_destinations?.instagram_story),
                }}
                onChange={(target: PostTarget, enabled: boolean) =>
                  edit({
                    publishing_destinations: {
                      ...(draft.publishing_destinations || {
                        facebook_feed: false,
                        facebook_story: false,
                        instagram_feed: false,
                        instagram_story: false,
                      }),
                      [target]: enabled,
                    },
                  })
                }
                statuses={destinationStatuses}
                disabled={!!busy}
                title="Social Publishing Destinations"
              />

              {/* Summary Review Card */}
              <div className="p-4 rounded-2xl bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 space-y-3">
                <h5 className="text-xs font-bold uppercase tracking-wider text-[#7A6C63] dark:text-slate-300">
                  Pre-Publishing Review Summary
                </h5>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div>
                    <span className="text-[#8C7E74] dark:text-slate-400 block text-[11px]">Headline</span>
                    <span className="font-semibold text-[#1F1A18] dark:text-white">
                      {selectedVariantObj?.headline || '(No headline configured)'}
                    </span>
                  </div>
                  <div>
                    <span className="text-[#8C7E74] dark:text-slate-400 block text-[11px]">Active Destinations</span>
                    <span className="font-semibold text-[#1F1A18] dark:text-white">
                      {activeDestinationsCount > 0
                        ? `${activeDestinationsCount} destination(s) enabled`
                        : 'Sponsored Ad only (No profile post)'}
                    </span>
                  </div>
                  <div>
                    <span className="text-[#8C7E74] dark:text-slate-400 block text-[11px]">Selected Hashtags</span>
                    <span className="font-semibold text-[#F26D5B]">
                      {(draft.selected_hashtags ?? []).length > 0
                        ? draft.selected_hashtags?.join(' ')
                        : 'No hashtags selected'}
                    </span>
                  </div>
                  <div>
                    <span className="text-[#8C7E74] dark:text-slate-400 block text-[11px]">Daily Budget</span>
                    <span className="font-semibold text-[#1F1A18] dark:text-white">
                      ₹{draft.daily_budget ?? '—'} / day
                    </span>
                  </div>
                </div>
              </div>

              {publishReason && (
                <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-900 dark:text-amber-200 text-xs space-y-2">
                  <div className="flex items-center gap-2 font-bold text-amber-800 dark:text-amber-300">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    <span>Action Required Before Launching:</span>
                  </div>
                  <p>{publishReason}</p>
                  <div className="flex flex-wrap gap-2 pt-1">
                    {draft.missing_fields?.includes('title') && (
                      <button
                        type="button"
                        onClick={() => goTo(1)}
                        className="px-2.5 py-1 rounded-lg bg-amber-500/20 text-amber-900 dark:text-amber-200 font-semibold cursor-pointer text-[11px]"
                      >
                        Go to Objective &amp; Idea
                      </button>
                    )}
                    {draft.missing_fields?.includes('image_id') && (
                      <button
                        type="button"
                        onClick={() => goTo(4)}
                        className="px-2.5 py-1 rounded-lg bg-amber-500/20 text-amber-900 dark:text-amber-200 font-semibold cursor-pointer text-[11px]"
                      >
                        Go to Creative &amp; Preview
                      </button>
                    )}
                  </div>
                </div>
              )}

              <SectionSaveBar
                sectionTitle="Publishing"
                dirty={dirty}
                busy={!!busy}
                onSave={() => run('Saving Publishing…')}
                isLast
              />
            </div>
          )}
        </div>
      </div>

      {/* ========================================================================= */}
      {/* FOOTER ACTIONS BAR */}
      {/* ========================================================================= */}
      <div className="px-6 py-4 bg-[#FAF8F5] dark:bg-[#111827] border-t border-[#EDE6DD] dark:border-white/10 flex flex-wrap items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-2">
          {busy ? (
            <span role="status" className="text-xs text-[#F26D5B] font-medium flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#F26D5B] animate-ping" />
              {busy}
            </span>
          ) : dirty ? (
            <span className="text-xs text-amber-600 dark:text-amber-400 font-medium">Unsaved changes</span>
          ) : (
            <span className="text-xs text-emerald-700 dark:text-emerald-400 font-medium flex items-center gap-1">
              <Check className="w-3.5 h-3.5" />
              Changes saved to draft
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {step > 1 ? (
            <button
              type="button"
              className={btnSecondary}
              disabled={!!busy}
              onClick={() => goTo((step - 1) as StudioSection)}
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back</span>
            </button>
          ) : (
            <button
              type="button"
              className={btnSecondary}
              disabled={!!busy}
              onClick={handleClose}
              title="Back to campaigns"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back</span>
            </button>
          )}

          <button type="button" className={btnSecondary} disabled={!!busy} onClick={() => run('Saving…')}>
            <Save className="w-3.5 h-3.5" />
            <span>{draft.status === 'DRAFT' ? 'Save draft' : 'Save as new draft'}</span>
          </button>

          {step < 6 && (
            <button
              type="button"
              className={btnSecondary}
              disabled={!!busy}
              onClick={() => goTo((step + 1) as StudioSection)}
            >
              <span>Continue</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}

          {publishReason && (
            <span id="studio-publish-reason" className="text-[11px] text-amber-700 dark:text-amber-400 max-w-64 text-right hidden sm:inline-block">
              {publishReason}
            </span>
          )}

          <button
            type="button"
            className={btnPrimary}
            disabled={!!busy || !!publishReason}
            aria-describedby={publishReason ? 'studio-publish-reason' : undefined}
            onClick={async () => {
              if (dirty || !draft.id) {
                const ok = await run('Saving…');
                if (!ok) return;
              }
              setModal('publish');
            }}
          >
            <Send className="w-3.5 h-3.5" />
            <span>Publish and start Instagram ad</span>
          </button>
        </div>
      </div>

      {modal === 'media' && (
        <MediaPicker
          onClose={() => setModal(null)}
          onPick={async (imageId) => {
            if (await run('Using the image…', (id) => setCampaignImage(id, imageId))) setModal(null);
          }}
        />
      )}
      {modal === 'publish' && (
        <PublishFlow
          campaign={draft}
          showDestinationSelector={false}
          onFinished={(outcome) => {
            setModal(null);
            setResult(outcome);
            onChanged();
          }}
          onClose={() => setModal(null)}
        />
      )}
    </Shell>
  );
}

function Shell({
  onClose,
  title = 'Campaign Studio',
  statusBadge,
  children,
}: {
  onClose: () => void;
  title?: string;
  statusBadge?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 md:p-6 bg-black/60 dark:bg-black/80 backdrop-blur-md text-[#1F1A18] dark:text-white">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Campaign Studio"
        className="bg-white dark:bg-[#0B0F19] w-full max-w-5xl max-h-[94vh] rounded-3xl border border-[#EDE6DD] dark:border-white/10 shadow-2xl flex flex-col overflow-hidden"
      >
        <div className="px-6 py-4 bg-[#FAF8F5] dark:bg-[#111827] border-b border-[#EDE6DD] dark:border-white/10 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <button
              type="button"
              aria-label="Back"
              onClick={onClose}
              className="w-8 h-8 rounded-full bg-white dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 flex items-center justify-center text-[#7A6C63] dark:text-slate-400 hover:text-[#1F1A18] dark:hover:text-white hover:bg-[#F26D5B]/10 hover:border-[#F26D5B]/30 cursor-pointer transition-colors shrink-0"
              title="Back"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-[#F26D5B] to-[#FF8E53] flex items-center justify-center text-white shadow-xs">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold leading-tight text-[#1F1A18] dark:text-white">
                  {title}
                </h3>
                {statusBadge && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#EDE6DD] dark:bg-white/10 text-[#7A6C63] dark:text-slate-300">
                    {statusBadge}
                  </span>
                )}
              </div>
              <p className="text-xs text-[#7A6C63] dark:text-slate-400">
                Create, customize, and publish your campaign. Drafts are saved on AdCraft.
              </p>
            </div>
          </div>
          <button
            type="button"
            aria-label="Close studio"
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-white dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 flex items-center justify-center text-[#7A6C63] dark:text-slate-400 hover:text-[#1F1A18] dark:hover:text-white cursor-pointer transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export default CampaignStudioModal;
