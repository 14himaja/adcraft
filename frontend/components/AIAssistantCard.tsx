'use client';

import React, { useState } from 'react';
import { Sparkles, PenLine } from 'lucide-react';
import { Campaign, createDraftFromIdea } from '../lib/api';
import { ErrorBox, errorMessage } from './Dialog';

// Ideas from the user guide §9 test scenarios.
export const EXAMPLE_IDEAS = [
  { label: 'Python course', idea: 'Promote my online Python course for college students in India. ₹999 for 8 weeks of live classes. Website https://synxa.ai/python' },
  { label: 'Hyderabad bakery', idea: "Make people in Hyderabad aware of my new bakery 'Sweet Crumbs' in Gachibowli. Fresh cakes and cookies." },
  { label: 'Fitness app', idea: 'Get downloads for my fitness app FitStreak. Track workouts and build a daily streak.' },
  { label: 'SaaS free trial', idea: 'Free 14-day trial of ReviewBot, an AI code-review tool for software teams. https://reviewbot.example.com' },
  { label: 'Telugu restaurant', idea: "Write the ad in Telugu for my Andhra meals restaurant 'Ruchulu' in Vijayawada. Website https://example-ruchulu.in" },
  { label: 'Weekend workshop', idea: 'Get sign-ups for my free 2-day AI workshop this Saturday and Sunday in Chennai. Register at https://example.org/workshop' },
];

interface AIAssistantCardProps {
  onDraftReady: (campaign: Campaign) => void;
  onStartFromScratch: () => void;
  userName?: string | null;
  idea?: string;
  onIdeaChange?: (idea: string) => void;
}

export function AIAssistantCard({ onDraftReady, onStartFromScratch, userName, idea: controlled, onIdeaChange }: AIAssistantCardProps) {
  const [local, setLocal] = useState('');
  const idea = controlled ?? local;
  const setIdea = onIdeaChange ?? setLocal;
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = async () => {
    setGenerating(true);
    setError(null);
    try {
      onDraftReady(await createDraftFromIdea(idea.trim()));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setGenerating(false);
    }
  };

  const greetingName = userName ? userName.split(' ')[0] : 'Creator';

  return (
    <div className="border-b border-[#EDE6DD] dark:border-white/10 py-5 space-y-4 text-[#1F1A18] dark:text-white transition-colors duration-200">
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-xl bg-[#FEECE7] dark:bg-purple-500/15 border border-[#FAD6CD] dark:border-purple-500/25 text-[#F26D5B] dark:text-purple-400 flex items-center justify-center shadow-2xs">
          <Sparkles className="w-4 h-4" />
        </div>
        <h4 className="text-sm font-bold">AI Ad Studio</h4>
      </div>

      <p className="text-xs text-[#6A5A53] dark:text-slate-300 leading-relaxed">
        Hi {greetingName}! Describe what you want to promote. I&apos;ll write three ad versions, pick an audience and
        create the image. Nothing is published until you say so.
      </p>

      <div>
        <label htmlFor="ad-idea" className="block text-xs font-bold text-[#5C5047] dark:text-slate-300 mb-1.5">
          Describe your ad idea
        </label>
        <textarea
          id="ad-idea"
          rows={4}
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder="e.g. Promote my bakery in Hyderabad to people nearby. Website https://…"
          className="w-full px-3.5 py-2.5 bg-[#FAF8F5] dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 rounded-xl text-xs text-[#1F1A18] dark:text-white placeholder-[#9C8F85] focus:outline-none focus:ring-2 focus:ring-[#F26D5B]/30"
        />
      </div>

      <div className="flex flex-wrap gap-1.5" aria-label="Example ideas">
        {EXAMPLE_IDEAS.map((ex) => (
          <button
            key={ex.label}
            type="button"
            onClick={() => setIdea(ex.idea)}
            className="px-2.5 py-1 rounded-full bg-[#FAF8F5] dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 hover:border-[#F26D5B] text-[11px] font-semibold text-[#5C5047] dark:text-slate-300 cursor-pointer"
          >
            {ex.label}
          </button>
        ))}
      </div>

      <ErrorBox message={error} />

      <button
        type="button"
        onClick={generate}
        disabled={generating || !idea.trim()}
        className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-[#F26D5B] hover:bg-[#E05C4A] text-white text-xs font-bold transition-all shadow-md shadow-[#F26D5B]/20 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {generating ? (
          <>
            <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            <span role="status">Writing your ad and creating the image… (about 20 s)</span>
          </>
        ) : (
          <>
            <Sparkles className="w-4 h-4" />
            <span>Generate ad</span>
          </>
        )}
      </button>

      <button
        type="button"
        onClick={onStartFromScratch}
        className="w-full inline-flex items-center justify-center gap-1.5 text-[11px] font-semibold text-[#7A6C63] dark:text-slate-400 hover:text-[#F26D5B] cursor-pointer"
      >
        <PenLine className="w-3.5 h-3.5" />
        <span>Start from scratch (no AI)</span>
      </button>
    </div>
  );
}

export default AIAssistantCard;
