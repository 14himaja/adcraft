'use client';

import React, { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { CheckCircle2, AlertCircle, Home } from 'lucide-react';
import Link from 'next/link';
import { MetaConnectCard } from '../../../components/MetaConnectCard';

function SettingsMetaContent() {
  const searchParams = useSearchParams();
  const connected = searchParams.get('connected');
  const error = searchParams.get('error');

  return (
    <div className="min-h-screen bg-[#FAF8F5] dark:bg-[#090D16] text-[#1F1A18] dark:text-[#F8FAFC] py-10 px-4 sm:px-6 lg:px-8 transition-colors duration-200">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Navigation Breadcrumb */}
        <div className="flex items-center text-xs sm:text-sm text-[#7A6C63] dark:text-slate-400 gap-2">
          <Link href="/" className="hover:text-[#1F1A18] dark:hover:text-white transition-colors flex items-center gap-1.5">
            <Home className="w-3.5 h-3.5" />
            <span>Dashboard</span>
          </Link>
          <span>/</span>
          <Link href="/settings" className="hover:text-[#1F1A18] dark:hover:text-white transition-colors">
            Settings
          </Link>
          <span>/</span>
          <span className="text-[#F26D5B] font-semibold">Meta & Instagram</span>
        </div>

        {/* Page Title */}
        <div className="p-6 bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 rounded-3xl shadow-2xs dark:shadow-xl">
          <h1 className="text-2xl sm:text-3xl font-extrabold text-[#1F1A18] dark:text-white tracking-tight">
            Integration Settings
          </h1>
          <p className="mt-1 text-xs sm:text-sm text-[#7A6C63] dark:text-slate-400">
            Configure your Meta Marketing API credentials, Ad Accounts, and Instagram assets.
          </p>
        </div>

        {/* Feedback Banners */}
        {connected && (
          <div
            role="status"
            className="flex items-center gap-3 p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-2xl text-emerald-800 dark:text-emerald-300 text-xs sm:text-sm shadow-xs"
            data-testid="connected-banner"
          >
            <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 shrink-0" />
            <div>
              <span className="font-semibold text-[#1F1A18] dark:text-white">Meta account connected successfully!</span>{' '}
              Select your active ad account and Instagram page below to complete setup.
            </div>
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="flex items-center gap-3 p-4 bg-rose-500/10 border border-rose-500/30 rounded-2xl text-rose-800 dark:text-rose-300 text-xs sm:text-sm shadow-xs"
            data-testid="error-banner"
          >
            <AlertCircle className="w-5 h-5 text-rose-600 dark:text-rose-400 shrink-0" />
            <div>
              <span className="font-semibold text-[#1F1A18] dark:text-white">Authorization failed or denied.</span>{' '}
              {error === 'denied'
                ? 'Meta permissions were declined during login.'
                : `Error code: ${error}`}
            </div>
          </div>
        )}

        {/* Main Connection Card */}
        <div className="flex justify-center pt-2">
          <MetaConnectCard />
        </div>
      </div>
    </div>
  );
}

export default function SettingsMetaPage() {
  return (
    <Suspense fallback={<div className="p-12 text-center text-slate-500">Loading settings...</div>}>
      <SettingsMetaContent />
    </Suspense>
  );
}
