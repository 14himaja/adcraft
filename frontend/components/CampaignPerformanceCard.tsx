'use client';

import React from 'react';
import useSWR from 'swr';
import { ShieldCheck } from 'lucide-react';
import { PerformanceInsights, fetcher } from '../lib/api';
import { rupees } from './PublishFlow';

const num = (n: number | undefined) => (n ?? 0).toLocaleString('en-IN');

/** Dashboard totals from GET /meta/insights (same SWR key as InsightsView, so they share the cache). */
export function CampaignPerformanceCard() {
  const { data, error } = useSWR<PerformanceInsights>('/v1/meta/insights?timeframe=7d', fetcher);
  const empty = data?.status === 'NO_ACTIVE_SPEND';

  const metrics: [string, string, string?][] = [
    ['Impressions', num(data?.impressions)],
    ['Reach', num(data?.reach)],
    ['Clicks', num(data?.clicks)],
    ['Spend', rupees(data?.spend), 'text-emerald-600 dark:text-emerald-400'],
  ];

  return (
    <div className="border-b border-[#EDE6DD] dark:border-white/10 py-5 space-y-4 text-[#1F1A18] dark:text-white transition-colors duration-200">
      <h4 className="text-sm font-bold text-[#1F1A18] dark:text-white">Campaign Performance</h4>

      {error && <p className="text-xs text-rose-600">Could not load performance.</p>}
      {!data && !error && <p role="status" className="text-xs text-[#7A6C63] dark:text-slate-400">Loading…</p>}

      {empty && (
        <div className="py-6 flex flex-col items-center justify-center text-center">
          <div className="w-7 h-7 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-600 dark:text-emerald-400 mb-1.5">
            <ShieldCheck className="w-4 h-4" />
          </div>
          <p className="text-xs font-semibold">No live campaigns yet</p>
          <p className="text-[10px] text-[#7A6C63] dark:text-slate-400 max-w-xs mt-0.5">
            Totals appear here after an ad is approved and starts delivering.
          </p>
        </div>
      )}

      {data && !empty && (
        <div className="grid grid-cols-2 gap-2 text-left">
          {metrics.map(([label, value, color]) => (
            <div key={label} className="p-2.5 border-b border-[#EDE6DD] dark:border-white/5">
              <span className="block text-[11px] font-medium text-[#7A6C63] dark:text-slate-400">{label}</span>
              <p className={`text-sm sm:text-base font-extrabold mt-0.5 ${color ?? 'text-[#1F1A18] dark:text-white'}`}>{value}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default CampaignPerformanceCard;
