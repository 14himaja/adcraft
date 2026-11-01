'use client';

import React, { useEffect, useMemo, useState } from 'react';
import useSWR from 'swr';
import {
  Check,
  Hash,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  X,
  AlertCircle,
  Info,
} from 'lucide-react';
import {
  HashtagsData,
  RecommendedHashtagItem,
  addCustomHashtag,
  deleteCustomHashtag,
  fetcher,
  recommendHashtags,
} from '../lib/api';
import { btnPrimary, btnSecondary, inputCls, labelCls } from './Dialog';

export const MAX_HASHTAGS_ALLOWED = 5;

export const DEFAULT_PREDEFINED_CATEGORIES: Record<string, string[]> = {
  'Trending & Discovery': ['#FYP', '#ForYou', '#Trending', '#Viral'],
  'Business & Branding': ['#SmallBusiness', '#BusinessGrowth', '#BrandAwareness', '#Entrepreneur'],
  'Marketing & Advertising': ['#DigitalMarketing', '#SocialMediaMarketing', '#MarketingTips', '#AdCampaign'],
  'Shopping & Products': ['#ShopNow', '#NewArrival', '#ProductLaunch', '#BestDeals'],
  'Food & Restaurants': ['#FoodLovers', '#Foodie', '#RestaurantMarketing', '#FoodBusiness'],
  'Fashion & Beauty': ['#FashionTrends', '#StyleInspiration', '#BeautyTips', '#FashionBusiness'],
  'Technology & Startups': ['#TechInnovation', '#StartupLife', '#AI', '#TechBusiness'],
};

export interface HashtagSelectorProps {
  /** Currently selected hashtags (e.g. ['#SmallBusiness', '#Trending']) */
  selectedHashtags: string[];
  /** Callback when the selected hashtags array changes */
  onChange: (hashtags: string[]) => void;
  /** Context text from campaign/post (idea, title, primary text, prompt) for smart recommendations */
  contextText?: string;
  headline?: string;
  primaryText?: string;
  description?: string;
  businessCategory?: string;
  productService?: string;
  imagePrompt?: string;
  objective?: string;
  audience?: unknown;
  /** Pre-existing or draft AI recommended hashtags */
  aiRecommendedHashtags?: string[];
  /** Callback when AI recommended hashtags are refreshed */
  onAiRecommendedChange?: (tags: string[]) => void;
  /** Custom hashtags saved on the campaign level or user level */
  customHashtags?: string[];
  /** Callback when user adds a custom hashtag (for campaign-level persistence) */
  onCustomHashtagsChange?: (customTags: string[]) => void;
  /** Whether the component inputs are disabled */
  disabled?: boolean;
  /** Custom section title */
  title?: string;
  /** Show publishing destination compatibility notice below selector */
  showDestinationNotice?: boolean;
}

export function normalizeTagInput(raw: string): { tag: string | null; error: string | null } {
  if (!raw || !raw.trim()) {
    return { tag: null, error: 'Please enter a hashtag' };
  }
  const trimmed = raw.trim();
  if (trimmed === '#') {
    return { tag: null, error: 'Please enter a hashtag name' };
  }
  if (/\s/.test(trimmed)) {
    return { tag: null, error: 'Hashtags cannot contain spaces' };
  }
  const withHash = trimmed.startsWith('#') ? trimmed : `#${trimmed}`;
  if (withHash.length > 50) {
    return { tag: null, error: 'Hashtag cannot exceed 50 characters' };
  }
  if (!/^#[A-Za-z0-9_]+$/.test(withHash)) {
    return { tag: null, error: 'Hashtags can only contain letters, numbers, and underscores' };
  }
  return { tag: withHash, error: null };
}

export function HashtagSelector({
  selectedHashtags = [],
  onChange,
  contextText = '',
  headline = '',
  primaryText = '',
  description = '',
  businessCategory = '',
  productService = '',
  imagePrompt = '',
  objective = '',
  audience,
  aiRecommendedHashtags: initialAiRecommended,
  onAiRecommendedChange,
  customHashtags: propCustomHashtags,
  onCustomHashtagsChange,
  disabled = false,
  title = 'Hashtags',
  showDestinationNotice = true,
}: HashtagSelectorProps) {
  const { data: serverData, mutate: mutateServerData } = useSWR<HashtagsData>(
    `/v1/hashtags`,
    fetcher,
    { revalidateOnFocus: false }
  );

  const [activeCategory, setActiveCategory] = useState<string>('All');
  const [searchQuery, setSearchQuery] = useState('');
  const [customInput, setCustomInput] = useState('');
  const [customError, setCustomError] = useState<string | null>(null);
  const [limitNotice, setLimitNotice] = useState<string | null>(null);
  const [isAddingCustom, setIsAddingCustom] = useState(false);
  const [isGeneratingAi, setIsGeneratingAi] = useState(false);
  const [aiItems, setAiItems] = useState<RecommendedHashtagItem[]>([]);
  const [aiAlternatives, setAiAlternatives] = useState<string[]>([]);
  const [expandedReasonTag, setExpandedReasonTag] = useState<string | null>(null);

  // Maintain dynamic AI recommended hashtags state
  const [aiRecommended, setAiRecommended] = useState<string[]>(() => {
    if (initialAiRecommended && initialAiRecommended.length > 0) {
      return initialAiRecommended;
    }
    return [];
  });

  // Combine predefined categories from server or fallback
  const categories = serverData?.categories ?? DEFAULT_PREDEFINED_CATEGORIES;
  const userCustomHashtags = serverData?.custom ?? propCustomHashtags ?? [];

  // Initial load of AI recommendations if empty
  useEffect(() => {
    if (initialAiRecommended && initialAiRecommended.length > 0) {
      setAiRecommended(initialAiRecommended);
      return;
    }

    const combined = `${contextText} ${headline} ${primaryText} ${description} ${businessCategory} ${productService} ${imagePrompt}`.trim();
    if (!combined) {
      // Fallback default starter recommendation if no context at all
      setAiRecommended(['#SmallBusiness', '#BrandAwareness', '#Trending', '#DigitalMarketing', '#ShopNow']);
      return;
    }

    let isMounted = true;
    setIsGeneratingAi(true);
    recommendHashtags({
      text: contextText,
      headline,
      primary_text: primaryText,
      description,
      business_category: businessCategory,
      product_service: productService,
      image_prompt: imagePrompt,
      objective,
      audience,
    })
      .then((res) => {
        if (isMounted) {
          if (res.ai_recommended && res.ai_recommended.length > 0) {
            setAiRecommended(res.ai_recommended);
            onAiRecommendedChange?.(res.ai_recommended);
          }
          if (res.recommended_hashtags && res.recommended_hashtags.length > 0) {
            setAiItems(res.recommended_hashtags);
          } else if (res.ai_recommended) {
            setAiItems(res.ai_recommended.map((t) => ({ tag: t })));
          }
          if (res.alternative_hashtags && res.alternative_hashtags.length > 0) {
            setAiAlternatives(res.alternative_hashtags);
          }
        }
      })
      .catch(() => {
        // Fallback dynamic heuristic based on text
        const lower = combined.toLowerCase();
        let fallback: { tag: string; reason: string }[] = [];
        let alts: string[] = [];
        if (/burger|fast food|fries/i.test(lower)) {
          fallback = [
            { tag: '#BurgerLovers', reason: 'Directly relevant to the advertised burger product' },
            { tag: '#Foodie', reason: 'Relevant to the food-loving audience' },
            { tag: '#FoodDelivery', reason: 'Relevant when the advertisement promotes delivery' },
            { tag: '#RestaurantMarketing', reason: 'Relevant to the restaurant business' },
            { tag: '#FoodLovers', reason: 'Connects with foodies and meal discovery' },
          ];
          alts = ['#BurgerCombo', '#LocalEats', '#RestaurantDeals'];
        } else if (/pizza|cafe|coffee|bakery|food|restaurant|dining/i.test(lower)) {
          fallback = [
            { tag: '#FoodLovers', reason: 'Broad discovery for food enthusiasts' },
            { tag: '#Foodie', reason: 'Engages diners and food critics' },
            { tag: '#RestaurantMarketing', reason: 'Connects with local restaurant foot traffic' },
            { tag: '#FoodDelivery', reason: 'Promotes takeaway and home dining' },
            { tag: '#DeliciousEats', reason: 'Highlights appetizing meal offerings' },
          ];
          alts = ['#LocalEats', '#DinnerPlans', '#FoodCravings'];
        } else if (/fashion|cloth|wear|dress|beauty|style|outfit/i.test(lower)) {
          fallback = [
            { tag: '#FashionTrends', reason: 'Targets shoppers following latest trends' },
            { tag: '#StyleInspiration', reason: 'Provides visual outfit styling ideas' },
            { tag: '#OOTD', reason: 'High-volume outfit of the day discovery tag' },
            { tag: '#NewCollection', reason: 'Highlights freshly launched apparel' },
            { tag: '#ShopNow', reason: 'Direct call-to-action for shoppers' },
          ];
          alts = ['#BoutiqueStyle', '#FashionInspo', '#WardrobeEssentials'];
        } else if (/ai|tech|software|app|startup|saas|cloud|data/i.test(lower)) {
          fallback = [
            { tag: '#ArtificialIntelligence', reason: 'Primary category for AI solutions' },
            { tag: '#TechInnovation', reason: 'Attracts innovators and tech enthusiasts' },
            { tag: '#AIProducts', reason: 'Directly relevant to AI-powered tooling' },
            { tag: '#StartupLife', reason: 'Engages startup founders and tech leaders' },
            { tag: '#TechBusiness', reason: 'Reaches B2B software decision-makers' },
          ];
          alts = ['#SaaSProduct', '#MachineLearning', '#FutureOfWork'];
        } else if (/python|code|program|developer|course/i.test(lower)) {
          fallback = [
            { tag: '#LearnPython', reason: 'Directly relevant to Python coding course' },
            { tag: '#PythonCourse', reason: 'Specific to educational enrollment' },
            { tag: '#CodingCareer', reason: 'Appeals to students aiming for tech jobs' },
            { tag: '#TechEducation', reason: 'Category tag for professional upskilling' },
            { tag: '#LearnCoding', reason: 'Broader discovery for beginners' },
          ];
          alts = ['#CodeNewbie', '#SoftwareDeveloper', '#TechSkills'];
        } else {
          fallback = [
            { tag: '#SmallBusiness', reason: 'Connects with local and independent business supporters' },
            { tag: '#BrandAwareness', reason: 'Increases reach and brand discovery' },
            { tag: '#Trending', reason: 'High-visibility discovery tag' },
            { tag: '#DigitalMarketing', reason: 'Engages social media marketing audience' },
            { tag: '#ShopNow', reason: 'Encourages immediate purchase action' },
          ];
          alts = ['#TrendingNow', '#DiscoverMore', '#BestOffer'];
        }
        if (isMounted) {
          setAiItems(fallback);
          setAiRecommended(fallback.map((f) => f.tag));
          setAiAlternatives(alts);
        }
      })
      .finally(() => {
        if (isMounted) setIsGeneratingAi(false);
      });

    return () => {
      isMounted = false;
    };
  }, [contextText, headline, primaryText, description, businessCategory, productService, imagePrompt, objective]);

  // Handler to explicitly regenerate AI hashtags
  const handleRegenerateAi = async () => {
    if (disabled || isGeneratingAi) return;
    setIsGeneratingAi(true);
    try {
      const res = await recommendHashtags({
        text: contextText,
        headline,
        primary_text: primaryText,
        description,
        business_category: businessCategory,
        product_service: productService,
        image_prompt: imagePrompt,
        objective,
        audience,
      });
      if (res.ai_recommended && res.ai_recommended.length > 0) {
        setAiRecommended(res.ai_recommended);
        onAiRecommendedChange?.(res.ai_recommended);
      }
      if (res.recommended_hashtags && res.recommended_hashtags.length > 0) {
        setAiItems(res.recommended_hashtags);
      } else if (res.ai_recommended) {
        setAiItems(res.ai_recommended.map((t) => ({ tag: t })));
      }
      if (res.alternative_hashtags && res.alternative_hashtags.length > 0) {
        setAiAlternatives(res.alternative_hashtags);
      }
    } catch {
      // Keep existing recommendations
    } finally {
      setIsGeneratingAi(false);
    }
  };

  // Predefined Explore library tags (filtered by category and search)
  const exploreLibraryTags = useMemo(() => {
    let list: { tag: string; category: string }[] = [];
    if (activeCategory === 'All') {
      Object.entries(categories).forEach(([cat, tags]) => {
        tags.forEach((t) => list.push({ tag: t, category: cat }));
      });
    } else if (categories[activeCategory]) {
      categories[activeCategory].forEach((t) => list.push({ tag: t, category: activeCategory }));
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().replace(/^#/, '');
      list = list.filter((item) => item.tag.toLowerCase().includes(q));
    }

    // Deduplicate
    const seen = new Set<string>();
    const unique: { tag: string; category: string }[] = [];
    list.forEach((item) => {
      const lower = item.tag.toLowerCase();
      if (!seen.has(lower)) {
        seen.add(lower);
        unique.push(item);
      }
    });
    return unique;
  }, [activeCategory, categories, searchQuery]);

  const selectedCount = selectedHashtags.length;
  const isLimitReached = selectedCount >= MAX_HASHTAGS_ALLOWED;

  // Selection toggle handler
  const handleToggle = (tag: string) => {
    if (disabled) return;
    const lower = tag.toLowerCase();
    const isSelected = selectedHashtags.some((t) => t.toLowerCase() === lower);

    if (isSelected) {
      const updated = selectedHashtags.filter((t) => t.toLowerCase() !== lower);
      onChange(updated);
      setLimitNotice(null);
    } else {
      if (selectedCount >= MAX_HASHTAGS_ALLOWED) {
        setLimitNotice(`Maximum of ${MAX_HASHTAGS_ALLOWED} hashtags reached. Deselect one to choose another.`);
        return;
      }
      onChange([...selectedHashtags, tag]);
      setLimitNotice(null);
    }
  };

  // Add custom hashtag handler
  const handleAddCustom = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (disabled || isAddingCustom) return;

    setCustomError(null);
    setLimitNotice(null);

    const { tag: normalized, error } = normalizeTagInput(customInput);
    if (error || !normalized) {
      setCustomError(error);
      return;
    }

    // Check duplicate in selected
    const lower = normalized.toLowerCase();
    if (selectedHashtags.some((t) => t.toLowerCase() === lower)) {
      setCustomError(`Hashtag ${normalized} is already selected`);
      return;
    }

    setIsAddingCustom(true);
    try {
      const res = await addCustomHashtag(normalized);
      if (res.custom) {
        onCustomHashtagsChange?.(res.custom);
        await mutateServerData();
      }

      setCustomInput('');

      // Auto-select if slot available
      if (selectedCount < MAX_HASHTAGS_ALLOWED) {
        onChange([...selectedHashtags, normalized]);
      } else {
        setLimitNotice(
          `Added ${normalized} to your hashtags library. Deselect an existing hashtag to add it to your post.`
        );
      }
    } catch (err: any) {
      setCustomError(err.message || 'Failed to add custom hashtag');
    } finally {
      setIsAddingCustom(false);
    }
  };

  // Delete custom hashtag from user library
  const handleDeleteCustom = async (tag: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const res = await deleteCustomHashtag(tag);
      if (res.custom) {
        onCustomHashtagsChange?.(res.custom);
        await mutateServerData();
      }
      if (selectedHashtags.some((t) => t.toLowerCase() === tag.toLowerCase())) {
        onChange(selectedHashtags.filter((t) => t.toLowerCase() !== tag.toLowerCase()));
      }
    } catch {
      // Best effort
    }
  };

  // Helper to determine the origin of a selected hashtag
  const getTagOrigin = (tag: string): 'AI' | 'Library' | 'Custom' => {
    const lower = tag.toLowerCase();
    if (aiRecommended.some((t) => t.toLowerCase() === lower)) return 'AI';
    if (userCustomHashtags.some((t) => t.toLowerCase() === lower)) return 'Custom';
    return 'Library';
  };

  const categoryTabNames = ['All', ...Object.keys(categories)];

  return (
    <div
      className="space-y-5 rounded-3xl p-4 sm:p-6 bg-white dark:bg-[#0B0F19] border border-[#EDE6DD] dark:border-white/10 shadow-sm"
      aria-label="Hashtag Selector"
    >
      {/* 1. Header with title, subtitle, and live counter badge */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-3 border-b border-[#EDE6DD] dark:border-white/10">
        <div>
          <div className="flex items-center gap-2">
            <Hash className="w-4 h-4 text-[#F26D5B]" />
            <h3 className="text-sm font-bold text-[#1F1A18] dark:text-white tracking-tight">
              {title}
            </h3>
            <span
              className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full transition-colors ${
                selectedCount === MAX_HASHTAGS_ALLOWED
                  ? 'bg-[#FEECE7] text-[#F26D5B] dark:bg-[#F26D5B]/20 dark:text-[#F26D5B] border border-[#FAD6CD] dark:border-[#F26D5B]/30'
                  : selectedCount > 0
                  ? 'bg-slate-100 text-slate-700 dark:bg-white/10 dark:text-slate-200'
                  : 'bg-slate-100 text-slate-500 dark:bg-white/5 dark:text-slate-400'
              }`}
              aria-live="polite"
              id="hashtag-counter-badge"
            >
              {`${selectedCount}/${MAX_HASHTAGS_ALLOWED} selected`}
            </span>
          </div>
          <p className="text-xs text-[#7A6C63] dark:text-slate-400 mt-0.5">
            Choose up to 5 hashtags dynamically recommended by AI or from the predefined library.
          </p>
        </div>

        {selectedCount > 0 && (
          <button
            type="button"
            onClick={() => {
              onChange([]);
              setLimitNotice(null);
            }}
            disabled={disabled}
            className="text-[11px] text-[#7A6C63] dark:text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 self-start sm:self-auto cursor-pointer"
          >
            Clear selection
          </button>
        )}
      </div>

      {/* Limit reached warning banner */}
      {limitNotice && (
        <div
          role="alert"
          className="p-3 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-800 dark:text-amber-300 text-xs flex items-center justify-between gap-2"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400" />
            <span>{limitNotice}</span>
          </div>
          <button
            type="button"
            onClick={() => setLimitNotice(null)}
            className="text-amber-600 dark:text-amber-400 hover:text-amber-800"
            aria-label="Dismiss notice"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* ============================================================== */}
      {/* GROUP 1: AI RECOMMENDED HASHTAGS                               */}
      {/* ============================================================== */}
      <div className="p-4 rounded-2xl bg-gradient-to-br from-indigo-50/50 via-purple-50/30 to-rose-50/20 dark:from-indigo-950/20 dark:via-purple-950/15 dark:to-rose-950/10 border border-indigo-100/80 dark:border-indigo-500/20 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 flex items-center justify-center">
              <Sparkles className="w-3.5 h-3.5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-xs font-bold text-indigo-950 dark:text-indigo-200">
                  AI Recommended
                </h4>
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-indigo-100/70 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 border border-indigo-200/60 dark:border-indigo-700/40">
                  Generated for this ad
                </span>
              </div>
              <p className="text-[10px] text-indigo-700/70 dark:text-indigo-300/70">
                Dynamically generated by HashtagRecommendationAgent based on ad title, caption, category, and objective
              </p>
            </div>
          </div>

          <button
            type="button"
            aria-label="Refresh AI recommendations"
            onClick={handleRegenerateAi}
            disabled={disabled || isGeneratingAi}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl text-[11px] font-semibold text-indigo-600 dark:text-indigo-300 bg-white/80 dark:bg-white/5 border border-indigo-200 dark:border-indigo-500/30 hover:bg-indigo-50 dark:hover:bg-white/10 transition-colors disabled:opacity-50 cursor-pointer shadow-xs self-start sm:self-auto"
            title="Regenerate suggestions for this ad"
          >
            <RefreshCw className={`w-3 h-3 ${isGeneratingAi ? 'animate-spin' : ''}`} />
            <span>{isGeneratingAi ? 'Regenerating…' : 'Regenerate Suggestions'}</span>
          </button>
        </div>

        <div className="flex flex-wrap gap-2 pt-1" role="group" aria-label="AI Recommended Hashtags">
          {aiRecommended.map((tag) => {
            const isSelected = selectedHashtags.some((t) => t.toLowerCase() === tag.toLowerCase());
            const isDisabled = disabled || (isLimitReached && !isSelected);
            const item = aiItems.find((i) => i.tag.toLowerCase() === tag.toLowerCase());
            const reason = item?.reason;
            const isExpanded = expandedReasonTag === tag.toLowerCase();

            return (
              <div key={`ai-wrap-${tag}`} className="inline-flex flex-col">
                <div className="inline-flex items-center gap-1">
                  <button
                    key={`ai-${tag}`}
                    type="button"
                    aria-pressed={isSelected}
                    disabled={isDisabled}
                    onClick={() => handleToggle(tag)}
                    className={`group inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all select-none ${
                      isSelected
                        ? 'bg-indigo-600 text-white shadow-xs scale-[1.02]'
                        : isDisabled
                        ? 'opacity-40 cursor-not-allowed bg-white dark:bg-white/5 text-slate-400 border border-slate-200 dark:border-white/10'
                        : 'bg-white dark:bg-[#131927] text-indigo-900 dark:text-indigo-200 border border-indigo-200/70 dark:border-indigo-500/30 hover:border-indigo-400 hover:bg-indigo-50/50 dark:hover:bg-indigo-950/40 cursor-pointer'
                    }`}
                  >
                    <Sparkles className={`w-3 h-3 ${isSelected ? 'text-indigo-200' : 'text-indigo-500'}`} />
                    <span>{tag}</span>
                    {isSelected ? (
                      <Check className="w-3.5 h-3.5 text-white stroke-[2.5]" />
                    ) : (
                      <Plus className="w-3 h-3 text-indigo-400 opacity-60 group-hover:opacity-100" />
                    )}
                  </button>

                  {reason && (
                    <button
                      type="button"
                      aria-label={`Why ${tag}?`}
                      aria-expanded={isExpanded}
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpandedReasonTag(isExpanded ? null : tag.toLowerCase());
                      }}
                      className="p-1 rounded-full text-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-200 hover:bg-indigo-100/60 dark:hover:bg-indigo-950/50 transition-colors cursor-pointer"
                      title={isExpanded ? 'Hide explanation' : 'Show explanation'}
                    >
                      <Info className="w-3 h-3" />
                    </button>
                  )}
                </div>

                {isExpanded && reason && (
                  <div className="mt-1 text-[11px] text-indigo-900 dark:text-indigo-200 bg-white/95 dark:bg-[#161F32] border border-indigo-200/80 dark:border-indigo-700/50 rounded-xl px-2.5 py-1.5 shadow-xs max-w-xs animate-in fade-in duration-150">
                    <span className="font-semibold">{tag}:</span> {reason}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Alternative Suggestions */}
        {aiAlternatives.length > 0 && (
          <div className="pt-2 border-t border-indigo-100/70 dark:border-indigo-500/10 space-y-1.5">
            <span className="text-[10px] font-bold text-indigo-900/70 dark:text-indigo-300/70 uppercase tracking-wider">
              Alternative Suggestions
            </span>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Alternative Hashtags">
              {aiAlternatives.map((altTag) => {
                const isSelected = selectedHashtags.some((t) => t.toLowerCase() === altTag.toLowerCase());
                const isDisabled = disabled || (isLimitReached && !isSelected);
                return (
                  <button
                    key={`alt-${altTag}`}
                    type="button"
                    aria-pressed={isSelected}
                    disabled={isDisabled}
                    onClick={() => handleToggle(altTag)}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium transition-colors cursor-pointer ${
                      isSelected
                        ? 'bg-indigo-600 text-white'
                        : isDisabled
                        ? 'opacity-40 cursor-not-allowed bg-white/50 text-slate-400'
                        : 'bg-white/70 dark:bg-white/5 text-indigo-800 dark:text-indigo-300 hover:bg-indigo-100/50 dark:hover:bg-indigo-900/30 border border-indigo-200/50 dark:border-indigo-700/30'
                    }`}
                  >
                    <span>{altTag}</span>
                    {isSelected ? <Check className="w-3 h-3" /> : <Plus className="w-2.5 h-2.5 opacity-60" />}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* ============================================================== */}
      {/* GROUP 2: EXPLORE PREDEFINED LIBRARY                            */}
      {/* ============================================================== */}
      <div className="space-y-3 pt-2">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h4 className="text-xs font-bold text-[#1F1A18] dark:text-white">
              Explore Hashtags
            </h4>
            <p className="text-[10px] text-[#7A6C63] dark:text-slate-400">
              Browse predefined business starter hashtags by category or search
            </p>
          </div>

          <div className="relative w-full sm:w-64">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
            <input
              id="hashtag-search-input"
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search library..."
              disabled={disabled}
              className={`${inputCls} pl-8 text-xs py-1.5`}
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                aria-label="Clear search"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Category Tabs */}
        <div
          className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none"
          role="tablist"
          aria-label="Hashtag Categories"
        >
          {categoryTabNames.map((catName) => {
            const isActive = activeCategory === catName;
            return (
              <button
                key={catName}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setActiveCategory(catName)}
                disabled={disabled}
                className={`text-xs px-2.5 py-1 rounded-xl whitespace-nowrap transition-colors font-medium cursor-pointer ${
                  isActive
                    ? 'bg-[#1F1A18] text-white dark:bg-white dark:text-[#1F1A18]'
                    : 'bg-[#FAF8F5] text-[#7A6C63] dark:bg-white/5 dark:text-slate-300 hover:bg-slate-200/60 dark:hover:bg-white/10'
                }`}
              >
                {catName}
              </button>
            );
          })}
        </div>

        {/* Predefined Chips Grid */}
        <div
          className="flex flex-wrap gap-2 max-h-48 overflow-y-auto p-3 rounded-2xl bg-[#FAF8F5] dark:bg-[#070A12] border border-[#EDE6DD] dark:border-white/5"
          role="group"
          aria-label="Predefined Hashtags"
        >
          {exploreLibraryTags.length === 0 ? (
            <p className="text-xs text-slate-400 p-2 italic">
              No predefined hashtags matched your search. Try another keyword or create a custom hashtag below.
            </p>
          ) : (
            exploreLibraryTags.map(({ tag }) => {
              const isSelected = selectedHashtags.some((t) => t.toLowerCase() === tag.toLowerCase());
              const isDisabled = disabled || (isLimitReached && !isSelected);

              return (
                <button
                  key={`explore-${tag}`}
                  type="button"
                  aria-pressed={isSelected}
                  disabled={isDisabled}
                  onClick={() => handleToggle(tag)}
                  className={`group inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold transition-all select-none ${
                    isSelected
                      ? 'bg-[#F26D5B] text-white shadow-xs'
                      : isDisabled
                      ? 'opacity-40 cursor-not-allowed bg-white dark:bg-white/5 text-slate-400 border border-slate-200 dark:border-white/10'
                      : 'bg-white dark:bg-white/5 text-[#4D423A] dark:text-slate-200 border border-[#EDE6DD] dark:border-white/10 hover:border-[#F26D5B] hover:text-[#F26D5B] cursor-pointer'
                  }`}
                >
                  <span>{tag}</span>
                  {isSelected ? (
                    <Check className="w-3.5 h-3.5 text-white stroke-[2.5]" />
                  ) : (
                    <Plus className="w-3 h-3 text-slate-400 group-hover:text-[#F26D5B]" />
                  )}
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* ============================================================== */}
      {/* GROUP 3: CREATE CUSTOM HASHTAG                                 */}
      {/* ============================================================== */}
      <div className="space-y-2 pt-2 border-t border-[#EDE6DD] dark:border-white/10">
        <label htmlFor="custom-hashtag-input" className={labelCls}>
          Create custom hashtag
        </label>
        <form onSubmit={handleAddCustom} className="flex gap-2">
          <div className="relative flex-1">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-xs font-bold select-none">
              #
            </span>
            <input
              id="custom-hashtag-input"
              type="text"
              value={customInput}
              onChange={(e) => {
                setCustomInput(e.target.value);
                if (customError) setCustomError(null);
              }}
              placeholder="e.g. MyBrand2026"
              disabled={disabled || isAddingCustom}
              maxLength={50}
              className={`${inputCls} pl-7 text-xs`}
            />
          </div>
          <button
            type="submit"
            disabled={disabled || !customInput.trim() || isAddingCustom}
            className={`${btnPrimary} text-xs px-3.5 py-2 shrink-0 flex items-center gap-1`}
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add Hashtag</span>
          </button>
        </form>

        {customError && (
          <p role="alert" className="text-xs text-rose-600 dark:text-rose-400 font-medium flex items-center gap-1">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            <span>{customError}</span>
          </p>
        )}

        {/* User saved custom hashtags */}
        {userCustomHashtags.length > 0 && (
          <div className="pt-1">
            <p className="text-[10px] text-[#7A6C63] dark:text-slate-400 mb-1.5">
              Your saved custom hashtags:
            </p>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Custom Hashtags">
              {userCustomHashtags.map((tag) => {
                const isSelected = selectedHashtags.some((t) => t.toLowerCase() === tag.toLowerCase());
                const isDisabled = disabled || (isLimitReached && !isSelected);

                return (
                  <div
                    key={`custom-${tag}`}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs transition-colors ${
                      isSelected
                        ? 'bg-purple-600 text-white'
                        : 'bg-purple-50 dark:bg-purple-950/30 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-800'
                    }`}
                  >
                    <button
                      type="button"
                      disabled={isDisabled}
                      onClick={() => handleToggle(tag)}
                      aria-pressed={isSelected}
                      className="cursor-pointer font-medium flex items-center gap-1"
                    >
                      <span>{tag}</span>
                      {isSelected && <Check className="w-3 h-3 text-white" />}
                    </button>
                    <button
                      type="button"
                      aria-label={`Delete custom hashtag ${tag}`}
                      onClick={(e) => handleDeleteCustom(tag, e)}
                      className="text-purple-400 hover:text-rose-600 p-0.5 cursor-pointer ml-0.5"
                    >
                      <Trash2 className="w-2.5 h-2.5" />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* ============================================================== */}
      {/* GROUP 4: SELECTED HASHTAGS PREVIEW                             */}
      {/* ============================================================== */}
      <div className="pt-3 border-t border-[#EDE6DD] dark:border-white/10 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-[#1F1A18] dark:text-white">
            Selected hashtags preview
          </span>
          <span className="text-[11px] text-[#7A6C63] dark:text-slate-400">
            {selectedCount === 0 ? 'No hashtags selected yet' : `${selectedCount} of 5 chosen`}
          </span>
        </div>

        {selectedCount === 0 ? (
          <p className="text-xs text-slate-400 italic bg-[#FAF8F5] dark:bg-white/5 p-3 rounded-2xl border border-dashed border-[#EDE6DD] dark:border-white/10">
            Select up to 5 hashtags above from AI recommendations, the explore library, or custom tags.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2 p-3 rounded-2xl bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10">
            {selectedHashtags.map((tag) => {
              const origin = getTagOrigin(tag);
              return (
                <span
                  key={`selected-${tag}`}
                  className="inline-flex items-center gap-1.5 pl-2.5 pr-1.5 py-1 rounded-full text-xs font-semibold bg-[#1F1A18] text-white dark:bg-white dark:text-[#1F1A18] shadow-xs"
                >
                  <span
                    className={`text-[9px] uppercase px-1 py-0.2 rounded font-extrabold tracking-wider ${
                      origin === 'AI'
                        ? 'bg-indigo-500 text-white'
                        : origin === 'Custom'
                        ? 'bg-purple-500 text-white'
                        : 'bg-emerald-500 text-white'
                    }`}
                  >
                    {origin}
                  </span>
                  <span>{tag}</span>
                  <button
                    type="button"
                    onClick={() => handleToggle(tag)}
                    aria-label={`Remove ${tag}`}
                    className="p-0.5 rounded-full hover:bg-white/20 dark:hover:bg-black/10 cursor-pointer"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              );
            })}
          </div>
        )}
      </div>

      {/* ============================================================== */}
      {/* 5. PUBLISHING DESTINATION COMPATIBILITY NOTICE                  */}
      {/* ============================================================== */}
      {showDestinationNotice && (
        <div className="p-3 rounded-2xl bg-slate-50 dark:bg-white/5 border border-slate-200/70 dark:border-white/5 text-[11px] text-[#7A6C63] dark:text-slate-400 flex items-start gap-2">
          <Info className="w-4 h-4 shrink-0 text-slate-500 dark:text-slate-400 mt-0.5" />
          <div className="space-y-0.5">
            <p className="font-semibold text-slate-700 dark:text-slate-300">
              Publishing Compatibility
            </p>
            <p>
              Selected hashtags are appended to <strong>Instagram Feed</strong> and <strong>Facebook Feed</strong> post captions.
              Stories on Instagram and Facebook publish visual media only (standard post hashtags are not supported on Meta Story feeds).
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
