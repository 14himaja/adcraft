'use client';

import React, { useState } from 'react';
import { X, Link2, User, Sun, Moon, Palette, Check, Key, CreditCard, ExternalLink } from 'lucide-react';
import { SocialMediaConnections } from './SocialMediaConnections';
import { UserProfile } from '../lib/api';
import { useTheme } from '../lib/theme';
import { useMetaConnection } from '../lib/meta';
import { AIProviderSettings } from './AIProviderSettings';
import { changePassword } from '../lib/api';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  user: UserProfile | null;
  initialTab?: 'meta' | 'account' | 'ai' | 'appearance';
  onOpenAuth?: (mode: 'login' | 'register') => void;
  onLogout?: () => void;
  onOpenMetaConnection?: () => void;
}

/** Mounted only while open (keyed by initialTab), so each open starts on initialTab. */
export function SettingsModal(props: SettingsModalProps) {
  return props.isOpen ? <SettingsPanel key={props.initialTab ?? 'meta'} {...props} /> : null;
}

function SettingsPanel({
  onClose,
  user,
  initialTab = 'meta',
  onOpenAuth,
  onLogout,
  onOpenMetaConnection,
}: SettingsModalProps) {
  const [activeTab, setActiveTab] = useState<'meta' | 'account' | 'ai' | 'appearance' | 'billing' | 'ad-account'>(initialTab);
  const { theme, setTheme } = useTheme();
  const [themeDraft, setThemeDraft] = useState(theme);
  const { connection } = useMetaConnection();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [passwordMessage, setPasswordMessage] = useState('');
  const [passwordBusy, setPasswordBusy] = useState(false);
  const metaConnectionOnly = initialTab === 'meta';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 dark:bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-3xl max-h-[90vh] bg-white dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 rounded-lg shadow-xl flex flex-col overflow-hidden text-[#1F1A18] dark:text-white transition-colors duration-200">
        {/* Modal Top Bar */}
        <div className="flex items-center justify-between p-6 border-b border-[#EDE6DD] dark:border-white/10">
          <div className="flex items-center gap-3">
            <div>
              <h2 className="text-xl font-extrabold text-[#1F1A18] dark:text-white tracking-tight leading-none">
                {metaConnectionOnly ? 'Social Media Connections' : 'Settings'}
              </h2>
              <p className="text-xs text-[#7A6C63] dark:text-slate-400 mt-1">
                {metaConnectionOnly
                  ? 'Connect and manage all your social media accounts from one place.'
                  : 'Manage your account, AI provider, appearance, ad account, and billing.'}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="w-9 h-9 rounded-full bg-black/5 hover:bg-black/10 dark:bg-white/5 dark:hover:bg-white/10 flex items-center justify-center text-[#7A6C63] dark:text-slate-400 hover:text-[#1F1A18] dark:hover:text-white transition-colors cursor-pointer"
            aria-label="Close settings"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-2 px-6 pt-4 border-b border-[#EDE6DD] dark:border-white/5 text-xs font-semibold overflow-x-auto">
          {metaConnectionOnly && <button
            type="button"
            onClick={() => setActiveTab('meta')}
            className={`flex items-center gap-2 px-4 py-2.5 transition-all cursor-pointer ${
              activeTab === 'meta'
                ? 'text-[#F26D5B] border-b-2 border-[#F26D5B] font-bold'
                : 'text-[#7A6C63] dark:text-slate-400 hover:text-[#1F1A18] dark:hover:text-white'
            }`}
          >
            <Link2 className="w-4 h-4" />
            <span>Social Connections</span>
          </button>}

          {!metaConnectionOnly && <button
            type="button"
            onClick={() => setActiveTab('ai')}
            className={`flex items-center gap-2 px-4 py-2.5 transition-all cursor-pointer ${
              activeTab === 'ai'
                ? 'text-[#F26D5B] border-b-2 border-[#F26D5B] font-bold'
                : 'text-[#7A6C63] dark:text-slate-400 hover:text-[#1F1A18] dark:hover:text-white'
            }`}
          >
            <Key className="w-4 h-4" />
            <span>API Keys & AI</span>
          </button>}

          {!metaConnectionOnly && <button
            type="button"
              onClick={() => setActiveTab('account')}
            className={`flex items-center gap-2 px-4 py-2.5 transition-all cursor-pointer ${
              activeTab === 'account'
                ? 'text-[#F26D5B] border-b-2 border-[#F26D5B] font-bold'
                : 'text-[#7A6C63] dark:text-slate-400 hover:text-[#1F1A18] dark:hover:text-white'
            }`}
          >
            <User className="w-4 h-4" />
            <span>Account</span>
          </button>}

          {!metaConnectionOnly && <button
            type="button"
            onClick={() => setActiveTab('ad-account')}
            className={`flex items-center gap-2 px-4 py-2.5 transition-all cursor-pointer ${activeTab === 'ad-account' ? 'text-[#F26D5B] border-b-2 border-[#F26D5B] font-bold' : 'text-[#7A6C63] dark:text-slate-400 hover:text-[#1F1A18] dark:hover:text-white'}`}
          ><Link2 className="w-4 h-4" /><span>Ad Account</span></button>}

          {!metaConnectionOnly && <button
            type="button"
            onClick={() => setActiveTab('appearance')}
            className={`flex items-center gap-2 px-4 py-2.5 transition-all cursor-pointer ${
              activeTab === 'appearance'
                ? 'text-[#F26D5B] border-b-2 border-[#F26D5B] font-bold'
                : 'text-[#7A6C63] dark:text-slate-400 hover:text-[#1F1A18] dark:hover:text-white'
            }`}
          >
            <Palette className="w-4 h-4" />
            <span>Appearance</span>
          </button>}

          {!metaConnectionOnly && <button
            type="button"
            onClick={() => setActiveTab('billing')}
            className={`flex items-center gap-2 px-4 py-2.5 transition-all cursor-pointer ${
              activeTab === 'billing'
                ? 'text-[#F26D5B] border-b-2 border-[#F26D5B] font-bold'
                : 'text-[#7A6C63] dark:text-slate-400 hover:text-[#1F1A18] dark:hover:text-white'
            }`}
          >
            <CreditCard className="w-4 h-4" />
            <span>Billing</span>
          </button>}
        </div>

        {/* Tab Content Body */}
        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === 'meta' && (
            <div>
              <SocialMediaConnections compact />
            </div>
          )}

          {activeTab === 'ai' && (
            <div className="max-w-xl mx-auto space-y-5">
              <AIProviderSettings />
            </div>
          )}

          {activeTab === 'appearance' && (
            <div className="max-w-xl mx-auto space-y-6">
              <div className="space-y-3">
                <h3 className="text-sm font-bold text-[#1F1A18] dark:text-white">Color Palette & Theme</h3>
                <p className="text-xs text-[#7A6C63] dark:text-slate-400">
                  Switch between the original signature Light Pink & Cream palette or the Obsidian Dark palette.
                </p>

                <div className="grid grid-cols-2 gap-4 pt-2">
                  <div
                    onClick={() => setThemeDraft('light')}
                    className={`p-4 rounded-2xl border-2 cursor-pointer transition-all ${
                      themeDraft === 'light'
                        ? 'border-[#F26D5B] bg-[#FEECE7]/50 shadow-md'
                        : 'border-[#EDE6DD] dark:border-white/10 hover:border-[#F26D5B]/40'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <Sun className="w-4 h-4 text-[#F26D5B]" />
                        <span className="text-xs font-bold text-[#1F1A18] dark:text-white">Signature Light Pink</span>
                      </div>
                      {themeDraft === 'light' && <Check className="w-4 h-4 text-[#F26D5B]" />}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="w-4 h-4 rounded-full bg-[#FAF8F5] border border-[#EDE6DD]" />
                      <span className="w-4 h-4 rounded-full bg-[#FEECE7]" />
                      <span className="w-4 h-4 rounded-full bg-[#F26D5B]" />
                      <span className="text-[10px] font-semibold text-[#7A6C63] ml-1">Pink & Cream</span>
                    </div>
                  </div>

                  <div
                    onClick={() => setThemeDraft('dark')}
                    className={`p-4 rounded-2xl border-2 cursor-pointer transition-all ${
                      themeDraft === 'dark'
                        ? 'border-[#F26D5B] bg-[#F26D5B]/10 shadow-md'
                        : 'border-[#EDE6DD] dark:border-white/10 hover:border-[#F26D5B]/40'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <Moon className="w-4 h-4 text-purple-400" />
                        <span className="text-xs font-bold text-[#1F1A18] dark:text-white">Obsidian Dark</span>
                      </div>
                      {themeDraft === 'dark' && <Check className="w-4 h-4 text-[#F26D5B]" />}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="w-4 h-4 rounded-full bg-[#090D16] border border-white/20" />
                      <span className="w-4 h-4 rounded-full bg-[#111827]" />
                      <span className="w-4 h-4 rounded-full bg-[#F26D5B]" />
                      <span className="text-[10px] font-semibold text-slate-400 ml-1">Night Mode</span>
                    </div>
                  </div>
                </div>
                <p className="text-xs text-[#7A6C63] dark:text-slate-400">Default theme: Light</p>
                <button type="button" onClick={() => setTheme(themeDraft)} className="rounded-xl bg-[#F26D5B] px-4 py-2.5 text-xs font-bold text-white">Save appearance</button>
              </div>
            </div>
          )}

          {activeTab === 'billing' && (
            <div className="max-w-xl mx-auto space-y-5">
              <div className="py-6 border-b border-[#EDE6DD] dark:border-white/10 space-y-4">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 flex items-center justify-center">
                    <CreditCard className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-[#1F1A18] dark:text-white">Meta ad account billing</h3>
                    <p className="text-xs text-[#7A6C63] dark:text-slate-400">Payment methods are managed by Meta.</p>
                  </div>
                </div>
                {connection?.ad_account_id ? (
                  <div className="rounded-xl bg-white dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/5 p-4 text-xs space-y-1">
                    <p className="font-bold text-[#1F1A18] dark:text-white">{connection.ad_account_name || 'Connected ad account'}</p>
                    <p className="font-mono text-[#7A6C63] dark:text-slate-400">{connection.ad_account_id}</p>
                  </div>
                ) : (
                  <p className="rounded-xl bg-amber-500/10 border border-amber-500/20 p-4 text-xs text-amber-800 dark:text-amber-300">
                    Connect and select an ad account under Meta Connection to manage its billing.
                  </p>
                )}
                <p className="text-xs text-[#6A5A53] dark:text-slate-300 leading-relaxed">
                  Add or update a payment method in Meta Ads Manager under Billing &amp; payments. Select the ad account shown above. Meta verifies billing before it delivers ads.
                </p>
                <a
                  href="https://www.facebook.com/ads/manager/"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-xl bg-[#1877F2] hover:bg-[#166FE5] px-4 py-2.5 text-xs font-bold text-white transition-colors"
                >
                  <span>Open Meta Ads Manager</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </div>
            </div>
          )}

          {activeTab === 'ad-account' && (
            <div className="max-w-xl mx-auto p-6 bg-[#FAF8F5] dark:bg-[#111827] rounded-2xl border border-[#EDE6DD] dark:border-white/10 space-y-4">
              <h3 className="text-sm font-bold">Connected Meta account</h3>
              <p className="text-xs text-[#7A6C63] dark:text-slate-400">{connection?.status === 'ACTIVE' ? `Connected${connection.ad_account_name ? ` · ${connection.ad_account_name}` : ''}` : 'No active Meta account connection.'}</p>
              <button type="button" onClick={() => { onClose(); onOpenMetaConnection?.(); }} className="rounded-xl bg-[#1877F2] px-4 py-2.5 text-xs font-bold text-white">{connection?.status === 'ACTIVE' ? 'Manage Meta Connection' : 'Connect Meta Account'}</button>
            </div>
          )}

          {activeTab === 'account' && (
            <div className="max-w-xl mx-auto space-y-6">
              {user ? (
                <div className="py-6 border-b border-[#EDE6DD] dark:border-white/10 space-y-4">
                  <div className="flex items-center gap-4">
                    <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-[#F26D5B] to-[#FF8E53] flex items-center justify-center text-xl font-extrabold text-white shadow-lg shadow-[#F26D5B]/25">
                      {user.name ? user.name.charAt(0).toUpperCase() : 'U'}
                    </div>
                    <div>
                      <h4 className="text-lg font-bold text-[#1F1A18] dark:text-white">{user.name}</h4>
                      <p className="text-xs text-[#7A6C63] dark:text-slate-400">{user.email}</p>
                      <span className="inline-block mt-1 text-[10px] font-semibold tracking-wider uppercase px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30">
                        Authenticated
                      </span>
                    </div>
                  </div>

                  <div className="pt-3 border-t border-[#EDE6DD] dark:border-white/10 space-y-3 text-xs sm:text-sm">
                    <form onSubmit={async (e) => { e.preventDefault(); setPasswordBusy(true); setPasswordMessage(''); try { await changePassword(currentPassword, newPassword); setCurrentPassword(''); setNewPassword(''); setPasswordMessage('Password changed.'); } catch (err) { setPasswordMessage(err instanceof Error ? err.message : 'Password update failed.'); } finally { setPasswordBusy(false); } }} className="space-y-2">
                      <label className="block">Current password<input type="password" required value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} className="mt-1 w-full rounded-lg border border-[#EDE6DD] dark:border-white/10 bg-white dark:bg-[#0F172A] p-2" /></label>
                      <label className="block">New password<input type="password" required minLength={6} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} className="mt-1 w-full rounded-lg border border-[#EDE6DD] dark:border-white/10 bg-white dark:bg-[#0F172A] p-2" /></label>
                      <button disabled={passwordBusy} className="rounded-lg bg-[#F26D5B] px-3 py-2 font-bold text-white disabled:opacity-50">Change password</button>
                      {passwordMessage && <p role="status">{passwordMessage}</p>}
                    </form>
                  </div>

                  {onLogout && (
                    <div className="pt-4 border-t border-[#EDE6DD] dark:border-white/10 flex justify-end">
                      <button
                        type="button"
                        onClick={onLogout}
                        className="px-4 py-2 bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 dark:text-rose-300 border border-rose-500/30 rounded-xl text-xs font-bold transition-colors cursor-pointer"
                      >
                        Sign Out
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="py-8 text-center border-b border-[#EDE6DD] dark:border-white/10 space-y-4">
                  <div className="w-12 h-12 mx-auto rounded-full bg-black/5 dark:bg-white/5 flex items-center justify-center text-[#7A6C63] dark:text-slate-400">
                    <User className="w-6 h-6" />
                  </div>
                  <h4 className="text-base font-bold text-[#1F1A18] dark:text-white">Not Signed In</h4>
                  <p className="text-xs text-[#7A6C63] dark:text-slate-400 max-w-sm mx-auto">
                    Sign in or register an account to sync your Meta assets and save your generated ad campaigns.
                  </p>
                  <div className="flex justify-center gap-3 pt-2">
                    <button
                      type="button"
                      onClick={() => {
                        onClose();
                        onOpenAuth?.('login');
                      }}
                      className="px-4 py-2 bg-black/5 hover:bg-black/10 dark:bg-white/10 dark:hover:bg-white/20 text-[#1F1A18] dark:text-white border border-[#EDE6DD] dark:border-transparent rounded-xl text-xs font-bold transition-colors cursor-pointer"
                    >
                      Sign In
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        onClose();
                        onOpenAuth?.('register');
                      }}
                      className="px-4 py-2 bg-gradient-to-r from-[#F26D5B] to-[#FF8E53] text-white rounded-xl text-xs font-bold transition-all shadow-md shadow-[#F26D5B]/20 cursor-pointer"
                    >
                      Create Account
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default SettingsModal;
