'use client';

import React, { useState } from 'react';
import {
  Check,
  AlertTriangle,
  RefreshCw,
  ExternalLink,
  ShieldCheck,
  Trash2,
  CreditCard,
  Layers,
  Sparkles,
  Info,
} from 'lucide-react';
import { useMetaConnection, useMetaAssets } from '../lib/meta';
import {
  updateConnection,
  getMe,
  disconnectMeta,
  disconnectAdAccount,
  disconnectPage,
  disconnectInstagram,
  ApiError,
} from '../lib/api';

function FacebookIcon({ className = 'w-5 h-5' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
    </svg>
  );
}

function InstagramIcon({ className = 'w-5 h-5' }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect width="20" height="20" x="2" y="2" rx="5" ry="5" />
      <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
      <line x1="17.5" x2="17.51" y1="6.5" y2="6.5" />
    </svg>
  );
}

export function MetaConnectCard() {
  const { connection, error, isLoading: isConnLoading, mutate: mutateConnection } = useMetaConnection();
  const isUnauthenticated = error instanceof ApiError && error.code === 'UNAUTHENTICATED';
  const isConnected = connection?.status === 'ACTIVE' || connection?.status === 'EXPIRED';
  const { assets, isLoading: isAssetsLoading, mutate: mutateAssets } = useMetaAssets(isConnected);

  // User asset choices
  const [adAccountChoice, setSelectedAdAccount] = useState('');
  const [pageChoice, setSelectedPage] = useState('');
  const [igChoice, setSelectedIg] = useState('');

  const selectedAdAccount = adAccountChoice || connection?.ad_account_id || '';
  const selectedPage = pageChoice || connection?.page_id || '';
  const selectedIg = igChoice || connection?.instagram_user_id || '';

  const eligiblePages = assets?.pages?.filter((page) => page.instagram) ?? [];
  const allPages = assets?.pages ?? [];
  const instagramAccounts = assets?.instagram_accounts ?? [];

  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [syncingAssets, setSyncingAssets] = useState(false);
  const [assetError, setAssetError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  const handleConnect = async () => {
    try {
      await getMe();
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full-page redirect into the Meta OAuth flow
      window.location.href = '/api/v1/meta/connect';
    } catch {
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full-page navigation to sign in
      window.location.href = '/login';
    }
  };

  const handleSyncAssets = async () => {
    setSyncingAssets(true);
    setAssetError(null);
    try {
      await mutateAssets();
    } catch (err: unknown) {
      setAssetError(err instanceof Error ? err.message : 'Could not refresh Meta assets. Reconnect and try again.');
    } finally {
      setSyncingAssets(false);
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm('Are you sure you want to disconnect all Meta accounts?')) return;
    try {
      await disconnectMeta();
      await mutateConnection();
      await mutateAssets();
    } catch (err: unknown) {
      console.error('Failed to disconnect', err);
    }
  };

  const handleDisconnectSpecific = async (type: 'ad_account' | 'page' | 'instagram') => {
    setActionBusy(type);
    try {
      if (type === 'ad_account') await disconnectAdAccount();
      else if (type === 'page') await disconnectPage();
      else if (type === 'instagram') await disconnectInstagram();
      await mutateConnection();
      await mutateAssets();
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : `Failed to disconnect ${type}`);
    } finally {
      setActionBusy(null);
    }
  };

  const handleSaveSelection = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAdAccount && !selectedPage && !selectedIg) return;

    setSaving(true);
    setSaveError(null);
    setSaveSuccess(false);

    try {
      await updateConnection({
        ad_account_id: selectedAdAccount || undefined,
        page_id: selectedPage || undefined,
        instagram_user_id: selectedIg || undefined,
      });
      await mutateConnection();
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 4000);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setSaveError(err.message);
      } else {
        setSaveError('Failed to save selected assets');
      }
    } finally {
      setSaving(false);
    }
  };

  if (isConnLoading) {
    return (
      <div className="w-full max-w-3xl p-8 bg-[#FAF8F5] dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 rounded-3xl shadow-xl animate-pulse space-y-4">
        <div className="h-6 bg-slate-300 dark:bg-slate-800 rounded w-1/3 mb-4"></div>
        <div className="h-4 bg-slate-200 dark:bg-slate-800/60 rounded w-2/3 mb-6"></div>
        <div className="h-10 bg-slate-200 dark:bg-slate-800 rounded w-40"></div>
      </div>
    );
  }

  const isNotConnected = !connection || connection.status === 'NOT_CONNECTED';
  const isExpired = connection?.status === 'EXPIRED';
  const isActive = connection?.status === 'ACTIVE';

  return (
    <div
      className="w-full max-w-3xl border-b border-[#EDE6DD] dark:border-white/10 text-[#1F1A18] dark:text-white transition-colors duration-200"
      data-testid="meta-connect-card"
    >
      {/* Header */}
      <div className="p-6 border-b border-[#EDE6DD] dark:border-white/10 bg-[#FAF8F5] dark:bg-gradient-to-r dark:from-blue-900/30 dark:via-indigo-900/20 dark:to-purple-900/30 flex items-center justify-between">
        <div>
          <h3 className="text-xl font-extrabold text-[#1F1A18] dark:text-white flex items-center gap-2.5">
            Connected Accounts &amp; Integrations
            {isActive && (
              <span
                className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-800 dark:text-emerald-400 border border-emerald-500/30"
                data-testid="status-badge"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 dark:bg-emerald-400 animate-pulse" />
                Active
              </span>
            )}
            {isExpired && (
              <span
                className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/20 text-amber-800 dark:text-amber-300 border border-amber-500/30"
                data-testid="status-badge"
              >
                Expired
              </span>
            )}
            {isNotConnected && (
              <span
                className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#F5EFE6] dark:bg-slate-800 text-[#7A6C63] dark:text-slate-400 border border-[#EDE6DD] dark:border-white/5"
                data-testid="status-badge"
              >
                Not Connected
              </span>
            )}
          </h3>
          <p className="text-xs sm:text-sm text-[#7A6C63] dark:text-slate-400 mt-1">
            Connect your Facebook Pages, Instagram Professional Accounts, and Meta Ad Accounts independently.
          </p>
        </div>

        {connection?.mode && (
          <span className="text-[10px] uppercase font-mono tracking-wider px-2.5 py-1 bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 rounded-lg text-[#7A6C63] dark:text-slate-300">
            {connection.mode} mode
          </span>
        )}
      </div>

      <div className="p-6 space-y-6">
        {/* Expired Warning Banner */}
        {isExpired && (
          <div
            role="alert"
            className="flex items-start gap-3 p-4 bg-amber-500/10 border border-amber-500/30 rounded-2xl text-amber-900 dark:text-amber-200"
            data-testid="expired-banner"
          >
            <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <div className="flex-1 text-xs sm:text-sm">
              <p className="font-semibold text-amber-800 dark:text-amber-300">Meta session expired</p>
              <p className="text-amber-700/80 dark:text-amber-200/80 mt-0.5">
                Your authorization has expired or was revoked. Please reconnect to restore publishing and ad services.
              </p>
            </div>
            <button
              onClick={handleConnect}
              className="px-3.5 py-1.5 bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold rounded-xl shadow-md transition-all shrink-0 cursor-pointer"
              data-testid="btn-reconnect"
            >
              Reconnect
            </button>
          </div>
        )}

        {/* Not Connected State */}
        {isNotConnected && (
          <div className="text-center py-8 px-4" data-testid="not-connected-view">
            <div className="w-16 h-16 mx-auto mb-4 bg-[#FEECE7] dark:bg-gradient-to-tr dark:from-blue-600/20 dark:to-indigo-600/20 border border-[#FAD6CD] dark:border-blue-500/30 text-[#F26D5B] dark:text-blue-400 rounded-2xl flex items-center justify-center shadow-xs dark:shadow-lg dark:shadow-blue-500/10">
              <ShieldCheck className="w-8 h-8" />
            </div>
            <h4 className="text-lg font-bold text-[#1F1A18] dark:text-white mb-1.5">Connect Your Meta Business Assets</h4>
            <p className="text-xs sm:text-sm text-[#7A6C63] dark:text-slate-400 max-w-md mx-auto mb-6 leading-relaxed">
              Sign in with your Meta account. We’ll securely discover and authorize only the Facebook Pages, Instagram accounts, and ad accounts you have access to.
            </p>

            {isUnauthenticated && (
              <div className="mb-5 p-3.5 bg-amber-500/10 border border-amber-500/30 text-amber-800 dark:text-amber-300 rounded-xl text-xs max-w-md mx-auto text-center flex items-center justify-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" />
                <span>Please sign in or register to connect your accounts.</span>
              </div>
            )}

            <div className="flex justify-center">
              <button
                onClick={handleConnect}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-3 bg-[#1877F2] hover:bg-[#166fe5] text-white font-bold text-xs sm:text-sm rounded-xl shadow-lg shadow-[#1877F2]/20 transition-all cursor-pointer"
                data-testid="btn-connect-meta"
              >
                <span>Connect with Facebook</span>
                <ExternalLink className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* Connected Details & 3-Card Asset Section */}
        {(isActive || isExpired) && (
          <div className="space-y-6" data-testid="connected-view">
            {/* Top Overview Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 p-4 bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 rounded-2xl text-xs">
              <div>
                <span className="text-[#7A6C63] dark:text-slate-400 block text-[11px] mb-0.5">Authorization Token</span>
                <span className="font-semibold text-[#1F1A18] dark:text-white" data-testid="token-expiry">
                  {connection?.expires_at ? new Date(connection.expires_at).toLocaleDateString() : 'Active (No expiry)'}
                  {connection?.expiring_soon && (
                    <span className="ml-1 text-[11px] text-amber-600 dark:text-amber-400 font-bold">(Expiring soon)</span>
                  )}
                </span>
              </div>
              <div>
                <span className="text-[#7A6C63] dark:text-slate-400 block text-[11px] mb-0.5">Active Ad Account</span>
                <span className="font-semibold text-[#1F1A18] dark:text-white truncate block" data-testid="selected-ad-account-display">
                  {connection?.ad_account_name || connection?.ad_account_id || 'None (Paid Ads Inactive)'}
                  {connection?.currency && ` (${connection.currency})`}
                </span>
              </div>
              <div>
                <span className="text-[#7A6C63] dark:text-slate-400 block text-[11px] mb-0.5">Active Facebook Page</span>
                <span className="font-semibold text-[#1F1A18] dark:text-white truncate block" data-testid="selected-page-display">
                  {connection?.page_name || connection?.page_id || 'None selected'}
                </span>
              </div>
              <div>
                <span className="text-[#7A6C63] dark:text-slate-400 block text-[11px] mb-0.5">Active Instagram</span>
                <span className="font-semibold text-[#1F1A18] dark:text-white flex items-center gap-1.5" data-testid="selected-ig-display">
                  {connection?.instagram_username ? `@${connection.instagram_username}` : connection?.instagram_user_id || 'None linked'}
                  {connection?.instagram_username && (
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 dark:bg-emerald-400" />
                  )}
                </span>
              </div>
            </div>

            {/* Quick Actions Bar */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
              <button
                type="button"
                onClick={handleDisconnect}
                className="inline-flex items-center gap-1.5 text-xs text-rose-600 dark:text-rose-400 hover:text-rose-700 dark:hover:text-rose-300 font-medium py-1.5 px-3 rounded-xl border border-rose-200 dark:border-rose-500/20 hover:bg-rose-50 dark:hover:bg-rose-500/10 transition-colors cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Disconnect All</span>
              </button>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleSyncAssets}
                  disabled={syncingAssets || isExpired}
                  className="inline-flex items-center gap-1.5 text-xs text-[#5C5047] dark:text-slate-300 hover:text-[#1F1A18] dark:hover:text-white font-medium py-1.5 px-3 rounded-xl border border-[#EDE6DD] dark:border-white/10 hover:bg-[#FAF8F5] dark:hover:bg-white/5 transition-colors cursor-pointer shadow-2xs"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${syncingAssets ? 'animate-spin' : ''}`} />
                  <span>{syncingAssets ? 'Syncing…' : 'Sync Assets'}</span>
                </button>
                <button
                  type="button"
                  onClick={handleConnect}
                  className="inline-flex items-center gap-1.5 text-xs text-[#5C5047] dark:text-slate-300 hover:text-[#1F1A18] dark:hover:text-white font-medium py-1.5 px-3 rounded-xl border border-[#EDE6DD] dark:border-white/10 hover:bg-[#FAF8F5] dark:hover:bg-white/5 transition-colors cursor-pointer shadow-2xs"
                  data-testid="btn-reconnect-secondary"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>Reconnect Account</span>
                </button>
              </div>
            </div>

            {assetError && (
              <div role="alert" className="p-3 bg-rose-500/10 border border-rose-500/30 text-rose-700 dark:text-rose-300 text-xs rounded-xl">
                {assetError}
              </div>
            )}

            {saveError && (
              <div role="alert" className="p-3 bg-rose-500/10 border border-rose-500/30 text-rose-700 dark:text-rose-300 text-xs rounded-xl" data-testid="selection-error">
                {saveError}
              </div>
            )}

            {saveSuccess && (
              <div role="status" className="p-3 bg-emerald-500/10 border border-emerald-500/30 text-emerald-800 dark:text-emerald-300 text-xs rounded-xl flex items-center gap-2" data-testid="selection-success">
                <Check className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                <span>Asset selection updated successfully!</span>
              </div>
            )}

            {/* ========================================================================= */}
            {/* SEPARATE INTEGRATION CARDS ARCHITECTURE */}
            {/* ========================================================================= */}
            <form onSubmit={handleSaveSelection} className="space-y-5">
              {/* CARD 1: FACEBOOK PAGES */}
              <div className="p-5 bg-white dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 rounded-2xl shadow-xs space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="w-9 h-9 rounded-xl bg-[#1877F2]/10 text-[#1877F2] flex items-center justify-center font-bold">
                      <FacebookIcon className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-[#1F1A18] dark:text-white flex items-center gap-2">
                        Facebook Pages
                        {connection?.page_id ? (
                          <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold bg-emerald-500/15 text-emerald-700 dark:text-emerald-400">
                            Active
                          </span>
                        ) : (
                          <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold bg-amber-500/15 text-amber-700 dark:text-amber-400">
                            None Selected
                          </span>
                        )}
                      </h4>
                      <p className="text-[11px] text-[#7A6C63] dark:text-slate-400">
                        Required for organic Facebook Feed posts, Facebook Stories, and ad creative attribution.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 text-[11px]">
                    <span className="px-2 py-0.5 rounded-md bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-[#5C5047] dark:text-slate-300 font-medium">
                      Feed Posts
                    </span>
                    <span className="px-2 py-0.5 rounded-md bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-[#5C5047] dark:text-slate-300 font-medium">
                      Stories
                    </span>
                  </div>
                </div>

                <div className="space-y-2">
                  <label htmlFor="page-select" className="block text-xs font-semibold text-[#7A6C63] dark:text-slate-300 uppercase tracking-wider">
                    Facebook Page &amp; Instagram
                  </label>
                  <select
                    id="page-select"
                    value={selectedPage}
                    onChange={(e) => setSelectedPage(e.target.value)}
                    disabled={isAssetsLoading || saving}
                    className="w-full px-3 py-2.5 bg-[#FAF8F5] dark:bg-[#0B1120] border border-[#EDE6DD] dark:border-white/10 rounded-xl text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-[#F26D5B] text-[#1F1A18] dark:text-white"
                    data-testid="select-page"
                  >
                    <option value="" disabled className="bg-white dark:bg-[#0F172A]">
                      {isAssetsLoading ? 'Loading eligible Pages…' : 'Choose a Page with Instagram'}
                    </option>
                    {eligiblePages.length ? (
                      eligiblePages.map((p) => (
                        <option key={p.id} value={p.id} className="bg-white dark:bg-[#0F172A] text-[#1F1A18] dark:text-white">
                          {p.name} {p.instagram ? `(@${p.instagram.username})` : '(No Instagram)'}
                        </option>
                      ))
                    ) : allPages.length ? (
                      allPages.map((p) => (
                        <option key={p.id} value={p.id} className="bg-white dark:bg-[#0F172A] text-[#1F1A18] dark:text-white">
                          {p.name} {p.instagram ? `(@${p.instagram.username})` : '(No Instagram)'}
                        </option>
                      ))
                    ) : (
                      !isAssetsLoading && <option value="" disabled className="bg-white dark:bg-[#0F172A]">No eligible linked Instagram Pages found</option>
                    )}
                  </select>
                </div>

                {connection?.page_id && (
                  <div className="flex items-center justify-between pt-2 border-t border-[#EDE6DD] dark:border-white/5 text-xs">
                    <span className="text-[#7A6C63] dark:text-slate-400">
                      Currently using: <strong>{connection.page_name || connection.page_id}</strong>
                    </span>
                    <button
                      type="button"
                      onClick={() => handleDisconnectSpecific('page')}
                      disabled={actionBusy === 'page'}
                      className="text-rose-600 dark:text-rose-400 hover:underline text-[11px] font-semibold cursor-pointer"
                    >
                      {actionBusy === 'page' ? 'Disconnecting…' : 'Disconnect Page'}
                    </button>
                  </div>
                )}
              </div>

              {/* CARD 2: INSTAGRAM PROFESSIONAL ACCOUNTS */}
              <div className="p-5 bg-white dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 rounded-2xl shadow-xs space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#f09433] via-[#dc2743] to-[#bc1888] text-white flex items-center justify-center font-bold shadow-xs">
                      <InstagramIcon className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-[#1F1A18] dark:text-white flex items-center gap-2">
                        Instagram Professional Accounts
                        {connection?.instagram_username ? (
                          <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold bg-emerald-500/15 text-emerald-700 dark:text-emerald-400">
                            Active
                          </span>
                        ) : (
                          <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold bg-slate-500/15 text-slate-700 dark:text-slate-400">
                            Not Linked
                          </span>
                        )}
                      </h4>
                      <p className="text-[11px] text-[#7A6C63] dark:text-slate-400">
                        Publishes Instagram Feed photos, Instagram Stories, and powers automated DM interactions.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 text-[11px]">
                    <span className="px-2 py-0.5 rounded-md bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-[#5C5047] dark:text-slate-300 font-medium">
                      Feed Photos
                    </span>
                    <span className="px-2 py-0.5 rounded-md bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-[#5C5047] dark:text-slate-300 font-medium">
                      Stories
                    </span>
                    <span className="px-2 py-0.5 rounded-md bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-[#5C5047] dark:text-slate-300 font-medium">
                      DMs
                    </span>
                  </div>
                </div>

                <div className="space-y-2">
                  <label htmlFor="instagram-select" className="block text-xs font-semibold text-[#7A6C63] dark:text-slate-300 uppercase tracking-wider">
                    Select Active Instagram Account
                  </label>
                  <select
                    id="instagram-select"
                    value={selectedIg}
                    onChange={(e) => setSelectedIg(e.target.value)}
                    disabled={isAssetsLoading || saving}
                    className="w-full px-3 py-2.5 bg-[#FAF8F5] dark:bg-[#0B1120] border border-[#EDE6DD] dark:border-white/10 rounded-xl text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-[#F26D5B] text-[#1F1A18] dark:text-white"
                  >
                    <option value="" className="bg-white dark:bg-[#0F172A]">
                      {connection?.instagram_username
                        ? `@${connection.instagram_username} (Default from Page)`
                        : 'Auto-link from selected Facebook Page'}
                    </option>
                    {instagramAccounts.map((ig) => (
                      <option key={ig.id} value={ig.id} className="bg-white dark:bg-[#0F172A] text-[#1F1A18] dark:text-white">
                        @{ig.username} — linked to {ig.page_name}
                      </option>
                    ))}
                  </select>
                </div>

                {connection?.instagram_username ? (
                  <div className="flex items-center justify-between pt-2 border-t border-[#EDE6DD] dark:border-white/5 text-xs">
                    <span className="text-[#7A6C63] dark:text-slate-400">
                      Active: <strong>@{connection.instagram_username}</strong>
                    </span>
                    <button
                      type="button"
                      onClick={() => handleDisconnectSpecific('instagram')}
                      disabled={actionBusy === 'instagram'}
                      className="text-rose-600 dark:text-rose-400 hover:underline text-[11px] font-semibold cursor-pointer"
                    >
                      {actionBusy === 'instagram' ? 'Disconnecting…' : 'Disconnect Instagram'}
                    </button>
                  </div>
                ) : (
                  <div className="p-3 bg-amber-500/10 border border-amber-500/20 text-amber-800 dark:text-amber-300 rounded-xl text-xs flex items-center gap-2">
                    <Info className="w-4 h-4 shrink-0" />
                    <span>
                      To publish to Instagram, ensure your Instagram Professional account is linked to your Facebook Page in Meta Business Suite.
                    </span>
                  </div>
                )}
              </div>

              {/* CARD 3: META AD ACCOUNTS */}
              <div className="p-5 bg-white dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 rounded-2xl shadow-xs space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="w-9 h-9 rounded-xl bg-purple-500/10 text-purple-600 dark:text-purple-400 flex items-center justify-center font-bold">
                      <CreditCard className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-[#1F1A18] dark:text-white flex items-center gap-2">
                        Meta Ad Accounts
                        {connection?.ad_account_id ? (
                          <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold bg-emerald-500/15 text-emerald-700 dark:text-emerald-400">
                            Active
                          </span>
                        ) : (
                          <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold bg-slate-500/15 text-slate-700 dark:text-slate-400">
                            Optional (Not Configured)
                          </span>
                        )}
                      </h4>
                      <p className="text-[11px] text-[#7A6C63] dark:text-slate-400">
                        Optional for organic social media posting. Only required if you create paid sponsored ad campaigns.
                      </p>
                    </div>
                  </div>

                  <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded-md bg-purple-500/10 text-purple-700 dark:text-purple-300 border border-purple-500/20">
                    Paid Campaigns Only
                  </span>
                </div>

                <div className="space-y-2">
                  <label htmlFor="ad-account-select" className="block text-xs font-semibold text-[#7A6C63] dark:text-slate-300 uppercase tracking-wider">
                    Ad Account
                  </label>
                  <select
                    id="ad-account-select"
                    value={selectedAdAccount}
                    onChange={(e) => setSelectedAdAccount(e.target.value)}
                    disabled={isAssetsLoading || saving}
                    className="w-full px-3 py-2.5 bg-[#FAF8F5] dark:bg-[#0B1120] border border-[#EDE6DD] dark:border-white/10 rounded-xl text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-[#F26D5B] text-[#1F1A18] dark:text-white"
                    data-testid="select-ad-account"
                  >
                    <option value="" disabled className="bg-white dark:bg-[#0F172A]">
                      {isAssetsLoading ? 'Loading accounts…' : 'Choose an ad account'}
                    </option>
                    {assets?.ad_accounts?.length ? (
                      assets.ad_accounts.map((acc) => (
                        <option key={acc.id} value={acc.id} className="bg-white dark:bg-[#0F172A] text-[#1F1A18] dark:text-white">
                          {acc.name} ({acc.currency || 'INR'}) — {acc.id}
                        </option>
                      ))
                    ) : (
                      !isAssetsLoading && <option value="" disabled className="bg-white dark:bg-[#0F172A]">No ad accounts found</option>
                    )}
                  </select>
                </div>

                {connection?.ad_account_id && (
                  <div className="flex items-center justify-between pt-2 border-t border-[#EDE6DD] dark:border-white/5 text-xs">
                    <span className="text-[#7A6C63] dark:text-slate-400">
                      Using: <strong>{connection.ad_account_name || connection.ad_account_id}</strong>
                      {connection.currency && ` · ${connection.currency}`}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleDisconnectSpecific('ad_account')}
                      disabled={actionBusy === 'ad_account'}
                      className="text-rose-600 dark:text-rose-400 hover:underline text-[11px] font-semibold cursor-pointer"
                    >
                      {actionBusy === 'ad_account' ? 'Disconnecting…' : 'Disconnect Ad Account'}
                    </button>
                  </div>
                )}
              </div>

              {/* SAVE / APPLY SELECTION BUTTON */}
              <div className="flex items-center justify-between pt-3">
                <p className="text-[11px] text-[#7A6C63] dark:text-slate-400">
                  Switching active accounts immediately directs subsequent publishing actions to the selected assets.
                </p>
                <button
                  type="submit"
                  disabled={saving || !selectedAdAccount || !selectedPage}
                  className="inline-flex items-center gap-2 px-6 py-2.5 bg-gradient-to-r from-[#F26D5B] to-[#FF8E53] hover:from-[#E05947] hover:to-[#F26D5B] text-white font-bold text-xs sm:text-sm rounded-xl shadow-lg shadow-[#F26D5B]/25 transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer shrink-0"
                  data-testid="btn-save-selection"
                >
                  {saving ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Saving…</span>
                    </>
                  ) : saveSuccess ? (
                    <>
                      <Check className="w-4 h-4" />
                      <span>Saved</span>
                    </>
                  ) : (
                    <span>Save Selection</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}

export default MetaConnectCard;
