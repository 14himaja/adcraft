'use client';

import React, { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Home } from 'lucide-react';
import { SocialMediaConnections } from '../../../components/SocialMediaConnections';

function ConnectionsPageContent() {
  const searchParams = useSearchParams();
  return (
    <div className="min-h-screen bg-[#FAF8F5] dark:bg-[#090D16] text-[#1F1A18] dark:text-[#F8FAFC] py-10 px-4 sm:px-6 lg:px-8 transition-colors duration-200">
      <div className="max-w-5xl mx-auto space-y-6">
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
          <span className="text-[#F26D5B] font-semibold">Social Media Connections</span>
        </div>

        <SocialMediaConnections
          returnTo="/settings/connections"
          oauthConnected={searchParams.get('connected')}
          oauthError={searchParams.get('error')}
          oauthPlatform={searchParams.get('platform')}
        />
      </div>
    </div>
  );
}

export default function SettingsConnectionsPage() {
  return (
    <Suspense fallback={<div className="p-12 text-center text-slate-500">Loading connections...</div>}>
      <ConnectionsPageContent />
    </Suspense>
  );
}

