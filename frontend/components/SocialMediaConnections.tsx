'use client';

import React, { useMemo, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  Check,
  CheckCircle2,
  ExternalLink,
  Loader2,
  Lock,
  RefreshCw,
  Send,
  Settings2,
  Sparkles,
  Trash2,
  X as CloseIcon,
} from 'lucide-react';
import {
  disconnectSocialPlatform,
  getPlatformConnectUrl,
  refreshPlatformConnection,
  selectPlatformAccount,
  useAdvertisingPlatforms,
  usePlatformAccounts,
  useSocialConnections,
} from '../lib/integrations';
import { getMe } from '../lib/api';
import { SocialPlatformConnection, SocialPlatformId } from '../lib/types';
import { PlatformLogo } from './PlatformIcons';
import { MetaConnectCard } from './MetaConnectCard';

interface SocialMediaConnectionsProps {
  /** Path the backend should redirect back to after OAuth finishes. */
  returnTo?: string;
  /** Optional callback to open the multi-platform publisher. */
  onOpenPublisher?: () => void;
  /** Optional compact display inside modals. */
  compact?: boolean;
  /** Optional OAuth callback status overrides (otherwise read from URL query string). */
  oauthConnected?: string | null;
  oauthError?: string | null;
  oauthPlatform?: string | null;
}

const DEFAULT_CARDS: { id: SocialPlatformId; name: string; description: string }[] = [
  {
    id: 'facebook',
    name: 'Facebook',
    description: 'Connect Facebook Pages for organic Page posts, media, and Meta business management.',
  },
  {
    id: 'instagram',
    name: 'Instagram',
    description: 'Publish feed photos and manage Instagram Business & Creator accounts via Meta.',
  },
  {
    id: 'linkedin',
    name: 'LinkedIn',
    description: 'Connect LinkedIn Organization Pages and profiles for text and image publishing.',
  },
];

function StatusBadge({ platform }: { platform: SocialPlatformConnection }) {
  if (platform.status === 'ACTIVE') {
    return (
      <span
        className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30"
        data-testid={`status-${platform.platform}`}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 dark:bg-emerald-400 animate-pulse" />
        Connected
      </span>
    );
  }
  if (platform.status === 'EXPIRED') {
    return (
      <span
        className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-500/15 text-amber-800 dark:text-amber-300 border border-amber-500/30"
        data-testid={`status-${platform.platform}`}
      >
        Expired
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-[#F5EFE6] dark:bg-white/5 text-[#7A6C63] dark:text-slate-400 border border-[#EDE6DD] dark:border-white/10"
      data-testid={`status-${platform.platform}`}
    >
      Not connected
    </span>
  );
}

function ManageAccountModal({
  platform,
  onClose,
  onUpdated,
}: {
  platform: SocialPlatformConnection;
  onClose: () => void;
  onUpdated: (msg: string) => Promise<void> | void;
}) {
  const { accounts, selectedTargetId, isLoading, error, mutate } = usePlatformAccounts(
    platform.platform,
    platform.status === 'ACTIVE'
  );
  const [choice, setChoice] = useState(
    platform.selected_target_id || selectedTargetId || ''
  );
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [showMetaAdvanced, setShowMetaAdvanced] = useState(false);

  const effectiveChoice = choice || selectedTargetId || platform.selected_target_id || '';
  const isMeta = platform.platform === 'instagram' || platform.platform === 'facebook';

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!effectiveChoice) return;
    setSaving(true);
    setActionErr(null);
    try {
      await selectPlatformAccount(platform.platform, effectiveChoice);
      await onUpdated(`${platform.name} active account updated.`);
      onClose();
    } catch (err: unknown) {
      setActionErr(err instanceof Error ? err.message : 'Failed to update account selection.');
    } finally {
      setSaving(false);
    }
  };

  const handleRefreshToken = async () => {
    setRefreshing(true);
    setActionErr(null);
    try {
      await refreshPlatformConnection(platform.platform);
      await mutate();
      await onUpdated(`${platform.name} connection refreshed.`);
    } catch (err: unknown) {
      setActionErr(err instanceof Error ? err.message : 'Could not refresh connection.');
    } finally {
      setRefreshing(false);
    }
  };

  const orgAccounts = accounts.filter((a) => a.account_type === 'organization');
  const otherAccounts = accounts.filter((a) => a.account_type !== 'organization');

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 dark:bg-black/80 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`Manage ${platform.name} Account`}
    >
      <div className="w-full max-w-2xl max-h-[90vh] bg-white dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 rounded-3xl shadow-2xl flex flex-col overflow-hidden text-[#1F1A18] dark:text-white">
        <div className="flex items-center justify-between p-5 border-b border-[#EDE6DD] dark:border-white/10">
          <div className="flex items-center gap-3">
            <PlatformLogo platform={platform.platform} className="w-9 h-9" />
            <div>
              <h3 className="text-base font-extrabold">{platform.name} Account Settings</h3>
              <p className="text-xs text-[#7A6C63] dark:text-slate-400">
                Select which {platform.capabilities.target_label.toLowerCase()} AdCraft should use.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close manage account"
            className="w-8 h-8 rounded-full bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 flex items-center justify-center cursor-pointer"
          >
            <CloseIcon className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 overflow-y-auto space-y-5">
          {actionErr && (
            <div role="alert" className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-700 dark:text-rose-300">
              {actionErr}
            </div>
          )}
          {error && (
            <div role="alert" className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-700 dark:text-rose-300">
              {error instanceof Error ? error.message : 'Could not fetch authorized accounts.'}
            </div>
          )}

          {/* Connection summary */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-3.5 rounded-2xl bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-xs">
            <div>
              <span className="text-[11px] text-[#7A6C63] dark:text-slate-400 block">Status</span>
              <span className="font-bold text-emerald-700 dark:text-emerald-400">{platform.status}</span>
            </div>
            <div>
              <span className="text-[11px] text-[#7A6C63] dark:text-slate-400 block">Active Target</span>
              <span className="font-semibold truncate block">
                {platform.selected_target_name || platform.account_display_name || 'None selected'}
              </span>
            </div>
            <div>
              <span className="text-[11px] text-[#7A6C63] dark:text-slate-400 block">Token Expires</span>
              <span className="font-semibold">
                {platform.expires_at ? new Date(platform.expires_at).toLocaleDateString() : 'Active'}
              </span>
            </div>
          </div>

          {platform.platform === 'linkedin' && (
            <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/20 text-xs text-blue-900 dark:text-blue-200">
              LinkedIn personal profiles and Organization (Company) Pages are managed separately. Organization Page publishing requires an approved administrator role and the{' '}
              <code className="font-mono">w_organization_social</code> permission.
            </div>
          )}

          {/* Account / Target Selector */}
          <form onSubmit={handleSave} className="space-y-4">
            <div className="flex items-center justify-between">
              <label htmlFor="target-select" className="text-xs font-bold uppercase tracking-wider text-[#7A6C63] dark:text-slate-400">
                Authorized {platform.capabilities.target_label}s
              </label>
              <button
                type="button"
                onClick={() => mutate()}
                disabled={isLoading}
                className="inline-flex items-center gap-1 text-xs font-semibold text-[#F26D5B] hover:underline cursor-pointer"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
                <span>Refresh List</span>
              </button>
            </div>

            {isLoading ? (
              <div className="flex items-center gap-2 text-xs text-[#7A6C63] dark:text-slate-400 py-4">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Discovering authorized {platform.name} assets…</span>
              </div>
            ) : accounts.length === 0 ? (
              <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-800 dark:text-amber-300">
                No authorized {platform.capabilities.target_label.toLowerCase()}s were returned for this account. Ensure your account has the required Page or Organization administrator permissions.
              </div>
            ) : (
              <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                {orgAccounts.length > 0 && (
                  <p className="text-[10px] font-bold uppercase tracking-wider text-[#7A6C63] dark:text-slate-400 pt-1">
                    Organization Pages
                  </p>
                )}
                {[...orgAccounts, ...otherAccounts].map((acc) => {
                  const isSelected = effectiveChoice === acc.target_id;
                  return (
                    <label
                      key={`${acc.account_id}-${acc.target_id}`}
                      className={`flex items-start gap-3 p-3 rounded-2xl border cursor-pointer transition-all ${
                        isSelected
                          ? 'border-[#F26D5B] bg-[#FEECE7]/40 dark:bg-[#F26D5B]/10'
                          : 'border-[#EDE6DD] dark:border-white/10 hover:border-[#F26D5B]/40'
                      } ${!acc.can_publish ? 'opacity-65' : ''}`}
                    >
                      <input
                        type="radio"
                        name="target_id"
                        value={acc.target_id}
                        checked={isSelected}
                        disabled={!acc.can_publish}
                        onChange={() => setChoice(acc.target_id)}
                        className="mt-1 accent-[#F26D5B]"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-bold truncate">{acc.display_name}</span>
                          <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full bg-black/5 dark:bg-white/10 text-[#7A6C63] dark:text-slate-300 shrink-0">
                            {acc.account_type}
                          </span>
                        </div>
                        {acc.permission_note && (
                          <p className="text-[11px] text-[#7A6C63] dark:text-slate-400 mt-0.5">
                            {acc.permission_note}
                          </p>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>
            )}

            <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-[#EDE6DD] dark:border-white/10">
              <div className="flex items-center gap-2">
                {platform.capabilities.supports_refresh && (
                  <button
                    type="button"
                    onClick={handleRefreshToken}
                    disabled={refreshing}
                    className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-[#EDE6DD] dark:border-white/10 text-xs font-semibold hover:bg-[#FAF8F5] dark:hover:bg-white/5 cursor-pointer"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
                    <span>{refreshing ? 'Refreshing…' : 'Refresh Token'}</span>
                  </button>
                )}
                {isMeta && (
                  <button
                    type="button"
                    onClick={() => setShowMetaAdvanced((s) => !s)}
                    className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-[#EDE6DD] dark:border-white/10 text-xs font-semibold hover:bg-[#FAF8F5] dark:hover:bg-white/5 cursor-pointer"
                  >
                    <Settings2 className="w-3.5 h-3.5" />
                    <span>{showMetaAdvanced ? 'Hide Meta Ad Assets' : 'Manage Meta Ad Accounts'}</span>
                  </button>
                )}
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-[#7A6C63] dark:text-slate-300 hover:bg-black/5 dark:hover:bg-white/5 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving || !effectiveChoice}
                  className="inline-flex items-center gap-1.5 px-5 py-2 rounded-xl bg-gradient-to-r from-[#F26D5B] to-[#FF8E53] text-white text-xs font-bold shadow-md disabled:opacity-50 cursor-pointer"
                >
                  {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  <span>Save Selection</span>
                </button>
              </div>
            </div>
          </form>

          {isMeta && showMetaAdvanced && (
            <div className="pt-4 border-t border-[#EDE6DD] dark:border-white/10">
              <MetaConnectCard />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function SocialMediaConnections({
  returnTo = '/?section=connections',
  onOpenPublisher,
  compact = false,
  oauthConnected,
  oauthError,
  oauthPlatform,
}: SocialMediaConnectionsProps) {
  const { platforms, connectedCount, isLoading, error, mutate } = useSocialConnections();
  const { adPlatforms } = useAdvertisingPlatforms();

  const [connectingId, setConnectingId] = useState<SocialPlatformId | null>(null);
  const [disconnectingId, setDisconnectingId] = useState<SocialPlatformId | null>(null);
  const [managingPlatform, setManagingPlatform] = useState<SocialPlatformId | null>(null);
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showAdsPanel, setShowAdsPanel] = useState(false);

  const urlParams = useMemo(() => {
    if (typeof window === 'undefined') return null;
    return new URLSearchParams(window.location.search);
  }, []);
  const queryConnected = oauthConnected !== undefined ? oauthConnected : urlParams?.get('connected') ?? null;
  const queryError = oauthError !== undefined ? oauthError : urlParams?.get('error') ?? null;
  const queryPlatform = oauthPlatform !== undefined ? oauthPlatform : urlParams?.get('platform') ?? null;

  const cards: SocialPlatformConnection[] = useMemo(() => {
    if (platforms.length > 0) return platforms;
    return DEFAULT_CARDS.map((d) => ({
      platform: d.id,
      name: d.name,
      description: d.description,
      configured: true,
      required_env_vars: [],
      required_scopes: [],
      capabilities: {
        supports_oauth: true,
        supports_refresh: false,
        supports_account_selection: true,
        supports_text_post: true,
        supports_image_post: true,
        supports_link_post: false,
        supports_title: false,
        requires_image: false,
        requires_target_selection: true,
        max_text_length: 2000,
        target_label: 'Account',
      },
      advertising: { supported: false, status: 'FUTURE_PHASE', note: '' },
      status: 'NOT_CONNECTED',
      connected: false,
    }));
  }, [platforms]);

  const activeManageObj = useMemo(
    () => cards.find((c) => c.platform === managingPlatform) ?? null,
    [cards, managingPlatform]
  );

  const handleConnect = async (platform: SocialPlatformId) => {
    setConnectingId(platform);
    setNotice(null);
    const connectUrl = getPlatformConnectUrl(platform, returnTo);
    try {
      await getMe();
      window.location.href = connectUrl;
    } catch {
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- sign in then resume OAuth
      window.location.href = `/login?redirect=${encodeURIComponent(connectUrl)}`;
    }
  };

  const handleDisconnect = async (platform: SocialPlatformConnection) => {
    if (!window.confirm(`Disconnect ${platform.name} from this workspace?`)) return;
    setDisconnectingId(platform.platform);
    setNotice(null);
    try {
      await disconnectSocialPlatform(platform.platform);
      await mutate();
      setNotice({ type: 'success', text: `${platform.name} disconnected.` });
    } catch (err: unknown) {
      setNotice({
        type: 'error',
        text: err instanceof Error ? err.message : `Failed to disconnect ${platform.name}.`,
      });
    } finally {
      setDisconnectingId(null);
    }
  };

  return (
    <div className="space-y-6" data-testid="social-media-connections">
      {/* Section Header */}
      <div className="rounded-3xl bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 p-6 shadow-2xs dark:shadow-xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h2 className="text-xl sm:text-2xl font-extrabold text-[#1F1A18] dark:text-white tracking-tight">
                Social Media Connections
              </h2>
              <span
                className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#FEECE7] dark:bg-[#F26D5B]/15 text-[#F26D5B] border border-[#FAD6CD] dark:border-[#F26D5B]/30"
                data-testid="connected-count-badge"
              >
                {connectedCount} of {cards.length} connected
              </span>
            </div>
            <p className="text-xs sm:text-sm text-[#7A6C63] dark:text-slate-400 mt-1">
              Connect and manage all your social media accounts from one place.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => mutate()}
              disabled={isLoading}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-[#EDE6DD] dark:border-white/10 text-xs font-semibold text-[#5C5047] dark:text-slate-300 hover:bg-[#FAF8F5] dark:hover:bg-white/5 transition-colors cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>
            {onOpenPublisher && connectedCount > 0 && (
              <button
                type="button"
                onClick={onOpenPublisher}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-gradient-to-r from-[#F26D5B] to-[#FF8E53] text-white text-xs font-bold shadow-md shadow-[#F26D5B]/20 hover:opacity-95 transition-opacity cursor-pointer"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Publish Content</span>
              </button>
            )}
          </div>
        </div>

        {/* OAuth & Action Feedback Banners */}
        <div className="space-y-3 mt-4 empty:hidden">
          {queryConnected && (
            <div
              role="status"
              data-testid="oauth-connected-banner"
              className="flex items-center gap-2.5 p-3.5 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-800 dark:text-emerald-300"
            >
              <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
              <span>
                <strong className="capitalize">{queryPlatform || 'Account'}</strong> connected successfully! You can manage your active account or Page below.
              </span>
            </div>
          )}

          {queryError && (
            <div
              role="alert"
              data-testid="oauth-error-banner"
              className="flex items-start gap-2.5 p-3.5 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-800 dark:text-rose-300"
            >
              <AlertCircle className="w-4 h-4 text-rose-600 dark:text-rose-400 shrink-0 mt-0.5" />
              <div>
                <p className="font-bold">
                  {queryError === 'denied'
                    ? `${queryPlatform ? queryPlatform.toUpperCase() : 'Platform'} authorization was cancelled.`
                    : queryError === 'not_configured'
                    ? `${queryPlatform ? queryPlatform.toUpperCase() : 'Platform'} OAuth credentials are not configured.`
                    : 'Connection could not be completed.'}
                </p>
                {queryError === 'not_configured' && queryPlatform && (
                  <p className="mt-1 opacity-90">
                    Configure{' '}
                    <code className="font-mono">
                      {(cards.find((c) => c.platform === queryPlatform)?.required_env_vars ?? []).join(', ') ||
                        `${queryPlatform.toUpperCase()}_CLIENT_ID`}
                    </code>{' '}
                    in your backend <code className="font-mono">.env</code> file to enable OAuth login.
                  </p>
                )}
              </div>
            </div>
          )}

          {notice && (
            <div
              role={notice.type === 'error' ? 'alert' : 'status'}
              className={`flex items-center gap-2.5 p-3.5 rounded-2xl border text-xs ${
                notice.type === 'success'
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-800 dark:text-emerald-300'
                  : 'bg-rose-500/10 border-rose-500/30 text-rose-800 dark:text-rose-300'
              }`}
            >
              {notice.type === 'success' ? (
                <Check className="w-4 h-4 shrink-0" />
              ) : (
                <AlertTriangle className="w-4 h-4 shrink-0" />
              )}
              <span>{notice.text}</span>
            </div>
          )}

          {error && (
            <div
              role="alert"
              className="flex items-center gap-2.5 p-3.5 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-800 dark:text-amber-300"
            >
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>Sign in to view and manage your workspace&apos;s connected social media accounts.</span>
            </div>
          )}
        </div>
      </div>

      {/* 6 Platform Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="platform-cards-grid">
        {cards.map((p) => {
          const isConnecting = connectingId === p.platform;
          const isDisconnecting = disconnectingId === p.platform;
          const isConnected = p.status === 'ACTIVE';
          const isExpired = p.status === 'EXPIRED';

          return (
            <div
              key={p.platform}
              data-testid={`platform-card-${p.platform}`}
              className={`rounded-2xl p-5 bg-white dark:bg-[#111827] border transition-all flex flex-col justify-between gap-4 shadow-2xs ${
                isConnected
                  ? 'border-emerald-500/35 dark:border-emerald-500/30'
                  : isExpired
                  ? 'border-amber-500/40'
                  : 'border-[#EDE6DD] dark:border-white/10 hover:border-[#F26D5B]/40'
              }`}
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <PlatformLogo platform={p.platform} className="w-10 h-10 shrink-0" />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-base font-bold text-[#1F1A18] dark:text-white">
                          {p.name}
                        </h3>
                        <StatusBadge platform={p} />
                        {!p.configured && (
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-500/20">
                            Env Setup Needed
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-[#7A6C63] dark:text-slate-400 mt-1 leading-relaxed">
                        {p.description}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Connected account details */}
                {(isConnected || isExpired) && (
                  <div className="p-3 rounded-xl bg-[#FAF8F5] dark:bg-[#0B1120] border border-[#EDE6DD] dark:border-white/10 text-xs space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-bold text-[#1F1A18] dark:text-white truncate">
                        {p.selected_target_name ||
                          p.account_display_name ||
                          (p.account_username ? `@${p.account_username}` : `${p.name} Account`)}
                      </span>
                      {p.account_type && (
                        <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded-md bg-white dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-[#7A6C63] dark:text-slate-300 shrink-0">
                          {p.account_type}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-[#7A6C63] dark:text-slate-400">
                      <span>
                        {p.expires_at
                          ? `Expires ${new Date(p.expires_at).toLocaleDateString()}`
                          : 'Authorized via OAuth'}
                        {p.expiring_soon && (
                          <span className="ml-1 text-amber-600 dark:text-amber-400 font-semibold">
                            (Expiring soon)
                          </span>
                        )}
                      </span>
                      {p.mode === 'fake' && <span className="font-mono uppercase text-[10px]">sandbox</span>}
                    </div>
                  </div>
                )}
              </div>

              {/* Card Action Buttons */}
              <div className="flex items-center gap-2 pt-1">
                {!isConnected && !isExpired && (
                  <button
                    type="button"
                    onClick={() => handleConnect(p.platform)}
                    disabled={isConnecting}
                    data-testid={`btn-connect-${p.platform}`}
                    className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-[#1F1A18] hover:bg-[#332B28] dark:bg-white/10 dark:hover:bg-white/15 text-white text-xs font-bold border border-transparent dark:border-white/10 transition-all disabled:opacity-60 cursor-pointer"
                  >
                    {isConnecting ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Connecting…</span>
                      </>
                    ) : (
                      <>
                        <span>Connect</span>
                        <ExternalLink className="w-3.5 h-3.5 opacity-75" />
                      </>
                    )}
                  </button>
                )}

                {isExpired && (
                  <>
                    <button
                      type="button"
                      onClick={() => handleConnect(p.platform)}
                      disabled={isConnecting}
                      data-testid={`btn-reconnect-${p.platform}`}
                      className="flex-1 inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold transition-colors cursor-pointer"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${isConnecting ? 'animate-spin' : ''}`} />
                      <span>Reconnect</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDisconnect(p)}
                      disabled={isDisconnecting}
                      data-testid={`btn-disconnect-${p.platform}`}
                      className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2.5 rounded-xl border border-rose-200 dark:border-rose-500/30 text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-500/10 text-xs font-semibold transition-colors cursor-pointer"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      <span>Disconnect</span>
                    </button>
                  </>
                )}

                {isConnected && (
                  <>
                    <button
                      type="button"
                      onClick={() => setManagingPlatform(p.platform)}
                      data-testid={`btn-manage-${p.platform}`}
                      className="flex-1 inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl bg-[#FAF8F5] hover:bg-[#F3EDE4] dark:bg-white/10 dark:hover:bg-white/15 text-[#1F1A18] dark:text-white border border-[#EDE6DD] dark:border-white/10 text-xs font-bold transition-colors cursor-pointer"
                    >
                      <Settings2 className="w-3.5 h-3.5" />
                      <span>Manage Account</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDisconnect(p)}
                      disabled={isDisconnecting}
                      data-testid={`btn-disconnect-${p.platform}`}
                      className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2.5 rounded-xl border border-rose-200 dark:border-rose-500/30 text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-500/10 text-xs font-semibold transition-colors cursor-pointer"
                    >
                      {isDisconnecting ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="w-3.5 h-3.5" />
                      )}
                      <span>Disconnect</span>
                    </button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Future Phase: Paid Advertising Integrations Separation Notice */}
      {!compact && adPlatforms.length > 0 && (
        <div className="rounded-3xl bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 p-5 shadow-2xs">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-purple-500/10 text-purple-600 dark:text-purple-400 flex items-center justify-center">
                <Sparkles className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-[#1F1A18] dark:text-white">
                  Paid Advertising Integrations (Separate from Organic)
                </h3>
                <p className="text-[11px] text-[#7A6C63] dark:text-slate-400">
                  Paid ad campaigns require dedicated Ads API approval, an eligible Ad Account, and platform billing setup.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setShowAdsPanel((s) => !s)}
              className="text-xs font-bold text-[#F26D5B] hover:underline self-start sm:self-center cursor-pointer"
            >
              {showAdsPanel ? 'Hide Ad Readiness' : 'View Ad Readiness'}
            </button>
          </div>

          {showAdsPanel && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4 pt-4 border-t border-[#EDE6DD] dark:border-white/10">
              {adPlatforms.map((ad) => (
                <div
                  key={ad.id}
                  className="p-3.5 rounded-2xl bg-[#FAF8F5] dark:bg-[#0B1120] border border-[#EDE6DD] dark:border-white/10 space-y-1.5 text-xs"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-[#1F1A18] dark:text-white">{ad.name}</span>
                    <span
                      className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full ${
                        ad.status === 'READY'
                          ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
                          : 'bg-slate-500/15 text-slate-700 dark:text-slate-300'
                      }`}
                    >
                      {ad.status !== 'READY' && <Lock className="w-2.5 h-2.5" />}
                      {ad.status.replace(/_/g, ' ')}
                    </span>
                  </div>
                  <p className="text-[11px] text-[#7A6C63] dark:text-slate-400">{ad.requirements_note}</p>
                  <p className="text-[10px] text-[#9C8F85] dark:text-slate-500">
                    Min Budget: {ad.min_daily_budget} · {ad.billing_supported_india}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeManageObj && (
        <ManageAccountModal
          platform={activeManageObj}
          onClose={() => setManagingPlatform(null)}
          onUpdated={async (msg) => {
            setNotice({ type: 'success', text: msg });
            await mutate();
          }}
        />
      )}
    </div>
  );
}

export default SocialMediaConnections;
