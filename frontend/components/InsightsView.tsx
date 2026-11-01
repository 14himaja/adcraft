'use client';

import React from 'react';
import useSWR from 'swr';
import { BarChart3 } from 'lucide-react';
import { Campaign, PerformanceInsights, fetcher } from '../lib/api';
import { useMetaConnection } from '../lib/meta';
import { StatusBadge } from './CampaignCard';
import { rupees } from './PublishFlow';

const DELIVERED: Campaign['status'][] = ['ACTIVE', 'PAUSED', 'COMPLETED', 'PAUSED_ON_META'];
const num = (n: number | undefined) => (n ?? 0).toLocaleString('en-IN');

export function InsightsView() {
  const { connection } = useMetaConnection();
  const { data: totals } = useSWR<PerformanceInsights>('/v1/meta/insights?timeframe=7d', fetcher);
  const { data: campaigns } = useSWR<Campaign[]>('/v1/campaigns', fetcher);
  const published = (campaigns ?? []).filter((c) => DELIVERED.includes(c.status));

  const cards: [string, string, string?][] = [
    ['Total spend', rupees(totals?.spend), 'text-emerald-600 dark:text-emerald-400'],
    ['Reach', num(totals?.reach)],
    ['Impressions', num(totals?.impressions)],
    ['Link clicks', num(totals?.clicks)],
  ];

  return (
    <div className="space-y-6">
      <div className="py-6 border-b border-[#EDE6DD] dark:border-white/10">
        <h2 className="text-xl font-extrabold text-[#1F1A18] dark:text-white tracking-tight">Insights & Analytics</h2>
        <p className="text-xs text-[#7A6C63] dark:text-slate-400 mt-1">
          {connection?.status === 'ACTIVE'
            ? `Numbers stored from Meta for ${connection.ad_account_name ?? connection.ad_account_id ?? 'your ad account'}${connection.instagram_username ? ` (@${connection.instagram_username})` : ''}. Use Refresh insights on a campaign card for the latest numbers.`
            : 'Connect Meta to see delivery numbers.'}
        </p>
        {totals?.message && <p className="text-[11px] text-[#9C8F85] dark:text-slate-500 mt-1">{totals.message}</p>}
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map(([label, value, cls]) => (
          <div key={label} className="py-5 border-b border-[#EDE6DD] dark:border-white/10">
            <span className="text-xs font-bold text-[#7A6C63] dark:text-slate-400">{label}</span>
            <p className={`text-2xl font-extrabold mt-1 ${cls ?? 'text-[#1F1A18] dark:text-white'}`}>{value}</p>
          </div>
        ))}
      </div>

      {published.length === 0 ? (
        <div className="p-10 text-center border-b border-[#EDE6DD] dark:border-white/10">
          <BarChart3 className="w-7 h-7 text-[#F26D5B] mx-auto mb-2" />
          <h4 className="text-sm font-bold text-[#1F1A18] dark:text-white">No published campaigns yet</h4>
          <p className="text-xs text-[#7A6C63] dark:text-slate-400 mt-1">
            Publish a draft and wait for Meta approval and delivery to start collecting reach, clicks and spend.
          </p>
        </div>
      ) : (
        <div className="border-b border-[#EDE6DD] dark:border-white/10 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#FAF8F5] dark:bg-[#0F172A] text-[#7A6C63] dark:text-slate-400 uppercase font-bold text-[10px] tracking-wider">
              <tr>
                {['Campaign', 'Status', 'Impressions', 'Reach', 'Clicks', 'CTR', 'Spend', 'Updated'].map((h) => (
                  <th key={h} className="py-3 px-4">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[#EDE6DD]/60 dark:divide-white/5 text-[#1F1A18] dark:text-white">
              {published.map((c) => {
                const i = c.insights;
                return (
                  <tr key={c.id}>
                    <td className="py-3 px-4 font-bold">{c.title}</td>
                    <td className="py-3 px-4"><StatusBadge status={c.status} /></td>
                    <td className="py-3 px-4">{num(i?.impressions)}</td>
                    <td className="py-3 px-4">{num(i?.reach)}</td>
                    <td className="py-3 px-4">{num(i?.clicks)}</td>
                    <td className="py-3 px-4">{`${(i?.ctr ?? 0).toFixed(2)}%`}</td>
                    <td className="py-3 px-4 font-bold">{rupees((i?.spend_minor ?? 0) / 100)}</td>
                    <td className="py-3 px-4 text-[#7A6C63] dark:text-slate-400">
                      {i?.updated_at ? new Date(i.updated_at).toLocaleString() : 'never'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default InsightsView;
