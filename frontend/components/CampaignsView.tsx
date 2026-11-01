'use client';

import React, { useState } from 'react';
import useSWR from 'swr';
import { FolderKanban, Plus, Search, RefreshCw, Sparkles } from 'lucide-react';
import { Campaign, fetcher } from '../lib/api';
import { CampaignCard } from './CampaignCard';
import { ErrorBox, errorMessage } from './Dialog';

interface CampaignsViewProps {
  onCreateCampaign: () => void;
  onEditCampaign: (id: string, campaign?: Campaign) => void;
}

export function CampaignsView({ onCreateCampaign, onEditCampaign }: CampaignsViewProps) {
  const { data, error, isLoading, mutate } = useSWR<Campaign[]>('/v1/campaigns', fetcher);
  const campaigns = data ?? [];
  const loading = isLoading;
  const [search, setSearch] = useState('');

  const filtered = campaigns.filter((c) =>
    `${c.title} ${c.objective} ${c.status}`.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 py-6 border-b border-[#EDE6DD] dark:border-white/10">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-extrabold text-[#1F1A18] dark:text-white tracking-tight">
              All Instagram Campaigns
            </h2>
          </div>
          <p className="text-xs text-[#7A6C63] dark:text-slate-400 mt-1">
            Drafts and live campaigns. Publishing submits the ad for Meta review and starts delivery when it is approved.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => mutate()}
            title="Refresh campaigns"
            aria-label="Refresh campaigns"
            className="p-2.5 rounded-xl bg-white dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 hover:bg-[#FAF8F5] dark:hover:bg-white/10 text-[#7A6C63] dark:text-slate-300 transition-colors cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>

          <button
            type="button"
            onClick={onCreateCampaign}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#F26D5B] hover:bg-[#E05C4A] text-white text-xs font-bold transition-all shadow-md shadow-[#F26D5B]/20 cursor-pointer hover:scale-105 active:scale-95"
          >
            <Plus className="w-4 h-4" />
            <span>Create Campaign</span>
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-[#9C8F85] absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search campaigns by title, objective or status..."
            aria-label="Search campaigns"
            className="w-full pl-10 pr-4 py-2 bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 rounded-xl text-xs sm:text-sm text-[#1F1A18] dark:text-white placeholder-[#9C8F85] focus:outline-none focus:ring-2 focus:ring-[#F26D5B]/30"
          />
        </div>
      </div>

      <ErrorBox message={error ? errorMessage(error) : null} />

      {loading ? (
        <div className="p-12 text-center border-b border-[#EDE6DD] dark:border-white/10">
          <div className="w-6 h-6 border-2 border-[#F26D5B] border-t-transparent rounded-full animate-spin mx-auto mb-2" />
          <p className="text-xs text-[#7A6C63] dark:text-slate-400">Loading your campaigns from database...</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="p-12 text-center border-b border-[#EDE6DD] dark:border-white/10">
          <div className="w-14 h-14 rounded-2xl bg-[#FEECE7] dark:bg-[#F26D5B]/15 text-[#F26D5B] flex items-center justify-center mx-auto mb-3">
            <FolderKanban className="w-7 h-7" />
          </div>
          <h4 className="text-base font-bold text-[#1F1A18] dark:text-white">
            {campaigns.length === 0 ? 'No campaigns created yet' : 'No matching campaigns'}
          </h4>
          <p className="text-xs text-[#7A6C63] dark:text-slate-400 max-w-sm mx-auto mt-1 leading-relaxed">
            {campaigns.length === 0
              ? 'Describe your idea in the AI Ad Studio on the dashboard, or start a draft from scratch.'
              : 'Try adjusting your search query.'}
          </p>

          {campaigns.length === 0 && (
            <button
              type="button"
              onClick={onCreateCampaign}
              className="mt-5 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#F26D5B] hover:bg-[#E05C4A] text-white text-xs font-bold transition-all shadow-md shadow-[#F26D5B]/20 cursor-pointer"
            >
              <Sparkles className="w-4 h-4" />
              <span>Launch Campaign Studio</span>
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-col">
          {filtered.map((c) => (
            <CampaignCard key={c.id} campaign={c} onEdit={onEditCampaign} onChanged={() => mutate()} />
          ))}
        </div>
      )}
    </div>
  );
}

export default CampaignsView;
