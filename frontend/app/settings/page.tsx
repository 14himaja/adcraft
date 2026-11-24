'use client';

import React, { Suspense, useState, useEffect } from 'react';
import Link from 'next/link';
import { Home } from 'lucide-react';
import { SocialMediaConnections } from '../../components/SocialMediaConnections';
import { getMe, UserProfile } from '../../lib/api';

function SettingsPageContent() {
  const [user, setUser] = useState<UserProfile | null>(null);

  useEffect(() => {
    getMe().then(setUser).catch(() => setUser(null));
  }, []);

  return (
    <div className="min-h-screen bg-[#FAF8F5] dark:bg-[#090D16] text-[#1F1A18] dark:text-[#F8FAFC] py-10 px-4 sm:px-6 lg:px-8 transition-colors duration-200">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-center text-xs sm:text-sm text-[#7A6C63] dark:text-slate-400 gap-2">
          <Link href="/" className="hover:text-[#1F1A18] dark:hover:text-white transition-colors flex items-center gap-1.5">
            <Home className="w-3.5 h-3.5" />
            <span>Dashboard</span>
          </Link>
          <span>/</span>
          <span className="text-[#F26D5B] font-semibold">Social Media Connections</span>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 rounded-3xl shadow-2xs dark:shadow-xl">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-[#1F1A18] dark:text-white tracking-tight">
              Settings &amp; Integrations
            </h1>
            <p className="mt-1 text-xs sm:text-sm text-[#7A6C63] dark:text-slate-400">
              Connect and manage Facebook, Instagram, and LinkedIn accounts independently.
            </p>
          </div>
          {user && (
            <div className="flex items-center gap-3 px-4 py-2 bg-[#FAF8F5] dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 rounded-2xl">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#F26D5B] to-[#FF8E53] flex items-center justify-center font-bold text-white text-sm">
                {user.name ? user.name.charAt(0).toUpperCase() : 'U'}
              </div>
              <div>
                <p className="text-xs font-bold text-[#1F1A18] dark:text-white">{user.name}</p>
                <p className="text-[10px] text-[#7A6C63] dark:text-slate-400">{user.email}</p>
              </div>
            </div>
          )}
        </div>

        <SocialMediaConnections returnTo="/settings/connections" />
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<div className="p-12 text-center text-slate-500">Loading settings...</div>}>
      <SettingsPageContent />
    </Suspense>
  );
}
