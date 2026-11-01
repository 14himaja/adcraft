'use client';

import React from 'react';
import useSWR from 'swr';
import { Plus, Sparkles, FolderKanban } from 'lucide-react';
import { Campaign, fetcher } from '../lib/api';
import { CampaignCard } from './CampaignCard';

interface RecentCampaignsProps {
  onEditCampaign: (id: string, campaign?: Campaign) => void;
  onCreateNew?: () => void;
}

export function RecentCampaigns({ onEditCampaign, onCreateNew }: RecentCampaignsProps) {
  const { data, isLoading, mutate } = useSWR<Campaign[]>('/v1/campaigns', fetcher);
  const campaigns = (data ?? []).slice(0, 4);

  return (
    <div id="campaigns" className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-extrabold text-[#1F1A18] dark:text-white tracking-tight">Recent Campaigns</h3>
          <p className="text-xs text-[#7A6C63] dark:text-slate-400">Status, actions and delivery numbers from Meta</p>
        </div>
        <button
          type="button"
          onClick={() => onCreateNew && onCreateNew()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#F26D5B] hover:bg-[#E05C4A] text-white text-xs font-bold transition-all shadow-xs cursor-pointer hover:scale-105 active:scale-95"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>New Campaign</span>
        </button>
      </div>

      {isLoading ? (
        <div className="py-8 text-center border-b border-[#EDE6DD] dark:border-white/10">
          <div className="w-6 h-6 border-2 border-[#F26D5B] border-t-transparent rounded-full animate-spin mx-auto mb-2" />
          <p className="text-xs text-[#7A6C63] dark:text-slate-400">Loading campaigns...</p>
        </div>
      ) : campaigns.length === 0 ? (
        <div className="border-b border-[#EDE6DD] dark:border-white/10 py-8 sm:p-10 text-center">
          <div className="w-14 h-14 rounded-2xl bg-[#FEECE7] dark:bg-[#F26D5B]/15 text-[#F26D5B] flex items-center justify-center mx-auto mb-4">
            <FolderKanban className="w-7 h-7" />
          </div>
          <h4 className="text-base font-bold text-[#1F1A18] dark:text-white">No Campaigns Created Yet</h4>
          <p className="text-xs text-[#7A6C63] dark:text-slate-400 max-w-md mx-auto mt-1.5 leading-relaxed">
            Describe your idea in the AI Ad Studio and press Generate ad. Drafts stay on AdCraft until you publish them.
          </p>
          <button
            type="button"
            onClick={() => onCreateNew && onCreateNew()}
            className="mt-5 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#F26D5B] hover:bg-[#E05C4A] text-white text-xs font-bold transition-all shadow-md shadow-[#F26D5B]/20 cursor-pointer"
          >
            <Sparkles className="w-4 h-4" />
            <span>Start from scratch</span>
          </button>
        </div>
      ) : (
        <div className="flex flex-col">
          {campaigns.map((c) => (
            <CampaignCard key={c.id} campaign={c} onEdit={onEditCampaign} onChanged={() => mutate()} />
          ))}
        </div>
      )}
    </div>
  );
}

export default RecentCampaigns;
