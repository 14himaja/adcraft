'use client';

import React, { useState, useRef } from 'react';
import Image from 'next/image';
import { ArrowRight, Sparkles, ShieldCheck } from 'lucide-react';
import { Campaign, createDraftFromIdea } from '../lib/api';
import { ErrorBox, errorMessage } from './Dialog';

export interface HeroBannerProps {
  onSubmitPrompt?: (prompt?: string) => void;
  onDraftReady?: (campaign: Campaign) => void;
  initialPrompt?: string;
  onPromptChange?: (prompt: string) => void;
}

const EXAMPLES = [
  'Launch a new product',
  'Promote an event',
  'Get more website visits',
  'Increase brand awareness',
];

export function HeroBanner({
  onSubmitPrompt,
  onDraftReady,
  initialPrompt = '',
  onPromptChange,
}: HeroBannerProps) {
  const [prompt, setPrompt] = useState(initialPrompt);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Follow the parent's prompt when it changes (adjusting state while rendering, not in an effect).
  const [seenInitial, setSeenInitial] = useState(initialPrompt);
  if (initialPrompt !== seenInitial) {
    setSeenInitial(initialPrompt);
    setPrompt(initialPrompt);
  }

  const handleChange = (val: string) => {
    setPrompt(val);
    if (onPromptChange) {
      onPromptChange(val);
    }
  };

  const handleGenerate = async (textToUse?: string) => {
    const text = (textToUse ?? prompt).trim();
    if (!text) {
      inputRef.current?.focus();
      return;
    }

    if (onDraftReady) {
      setGenerating(true);
      setError(null);
      try {
        const draft = await createDraftFromIdea(text);
        onDraftReady(draft);
      } catch (e) {
        setError(errorMessage(e));
      } finally {
        setGenerating(false);
      }
    } else if (onSubmitPrompt) {
      onSubmitPrompt(text);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !generating) {
      e.preventDefault();
      handleGenerate();
    }
  };

  const handleExampleClick = (ex: string) => {
    handleChange(ex);
    if (onSubmitPrompt) {
      onSubmitPrompt(ex);
    }
    setTimeout(() => {
      inputRef.current?.focus();
    }, 0);
  };

  return (
    <section className="relative overflow-hidden rounded-3xl bg-[#FAF3EC] dark:bg-[#141A26] border border-[#EDE3D7] dark:border-white/10 p-6 sm:p-8 lg:p-10 shadow-xs transition-colors duration-200">
      <div className="flex flex-col lg:flex-row items-center justify-between gap-8 lg:gap-10">
        {/* Left Column: Badges, Title, Subtitle, Input, Examples */}
        <div className="flex-1 min-w-0 w-full space-y-5 sm:space-y-6">
          {/* Top Badges */}
          <div className="flex flex-wrap items-center gap-2.5 sm:gap-3">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 sm:px-3.5 sm:py-1.5 rounded-full bg-[#FDEEE7] dark:bg-[#38231C] border border-[#FAD9CD] dark:border-[#523328] text-[#9E3922] dark:text-[#FFA08C] text-[10px] sm:text-[11px] font-bold tracking-wider uppercase shadow-2xs">
              <Sparkles className="w-3.5 h-3.5 text-[#EB6044] dark:text-[#FFA08C]" />
              <span>Turn Ideas into Instagram Ads</span>
            </div>

            <div className="inline-flex items-center gap-1.5 px-3 py-1 sm:px-3.5 sm:py-1.5 rounded-full bg-[#EAF7EE] dark:bg-[#122A1D] border border-[#C2EBCE] dark:border-[#1E4D33] text-[#1A733D] dark:text-[#6EE7B7] text-xs font-semibold shadow-2xs">
              <ShieldCheck className="w-4 h-4 text-[#1C7E43] dark:text-[#6EE7B7]" />
              <span>Zero-Spend Safe Mode (Paused by Default)</span>
            </div>
          </div>

          {/* Heading */}
          <h1 className="text-3xl sm:text-4xl lg:text-[44px] font-extrabold text-[#1E1815] dark:text-white tracking-tight leading-[1.14]">
            What do you <br className="hidden sm:inline" />
            want to <span className="font-serif-accent italic font-normal text-[#E85D3F]">promote</span> <br className="hidden sm:inline" />
            today?
          </h1>

          {/* Subtitle */}
          <p className="text-sm sm:text-[15px] text-[#6E6058] dark:text-slate-300 leading-relaxed max-w-xl">
            Describe your product, service, or goal. Our multi-agent AI generates strategy, copy variations, and targets high-intent audiences on Instagram.
          </p>

          {/* Input Box Bar */}
          <div className="space-y-2 max-w-xl">
            <div className="relative flex items-center bg-white dark:bg-[#1E293B] rounded-2xl border border-[#EDE3D7] dark:border-white/10 shadow-sm p-1.5 sm:p-2 pl-4 sm:pl-5 gap-3 transition-all focus-within:ring-2 focus-within:ring-[#F26549]/30 focus-within:border-[#F26549]">
              <Sparkles className="w-5 h-5 text-[#EB6044] flex-shrink-0" />
              <input
                ref={inputRef}
                id="ad-idea"
                type="text"
                value={prompt}
                onChange={(e) => handleChange(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="e.g. Promote my handmade leather bags to..."
                disabled={generating}
                className="w-full bg-transparent border-none outline-none text-sm sm:text-base text-[#1E1815] dark:text-white placeholder-[#9D9086] dark:placeholder-slate-400 font-normal"
              />
              <button
                type="button"
                onClick={() => handleGenerate()}
                disabled={generating || !prompt.trim()}
                aria-label="Generate ad"
                className="w-10 h-10 sm:w-11 sm:h-11 rounded-xl sm:rounded-2xl bg-gradient-to-br from-[#F26549] to-[#F57758] hover:from-[#E2563A] hover:to-[#E86747] text-white flex items-center justify-center flex-shrink-0 shadow-md shadow-[#F26549]/25 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed active:scale-95"
              >
                {generating ? (
                  <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <ArrowRight className="w-5 h-5" />
                )}
              </button>
            </div>

            {generating && (
              <div className="flex items-center gap-2 text-xs font-semibold text-[#EB6044] animate-pulse px-1 pt-1">
                <span className="w-2 h-2 rounded-full bg-[#EB6044] animate-ping" />
                <span>Writing your ad and creating the image… (about 20 s)</span>
              </div>
            )}

            <ErrorBox message={error} />
          </div>

          {/* Try examples pills */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 pt-1 text-xs">
            <span className="text-[#7A6C64] dark:text-slate-400 font-medium whitespace-nowrap">
              Try examples:
            </span>
            <div className="flex flex-wrap items-center gap-2">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => handleExampleClick(ex)}
                  className="px-3.5 py-1.5 rounded-full bg-white dark:bg-[#1E293B] border border-[#EDE3D7] dark:border-white/10 hover:border-[#F26549] hover:text-[#F26549] text-[#4F413B] dark:text-slate-200 font-medium shadow-2xs transition-all cursor-pointer text-xs"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right Column: Moodboard Creator Image */}
        <div className="w-full lg:w-[360px] xl:w-[420px] aspect-[4/3] sm:aspect-[16/11] lg:aspect-square xl:aspect-[4/3] relative rounded-2xl sm:rounded-3xl overflow-hidden shadow-xs flex-shrink-0 border border-[#EDE3D7]/60 dark:border-white/10">
          <Image
            src="/hero-creator.jpg"
            alt="Creator designing campaign moodboard and Instagram ads"
            fill
            sizes="(max-width: 1024px) 100vw, 420px"
            className="object-cover object-center"
            priority
          />
        </div>
      </div>
    </section>
  );
}
