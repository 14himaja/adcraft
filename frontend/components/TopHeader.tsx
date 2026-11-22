'use client';

import React, { useState, useRef, useEffect } from 'react';
import {
  Search,
  Bell,
  ChevronDown,
  Settings,
  LogOut,
  Link2,
  Sun,
  Moon,
  ShieldCheck,
  CheckCircle2,
  Zap,
  Info,
  Check,
} from 'lucide-react';
import { UserProfile, switchWorkspace } from '../lib/api';
import { useTheme } from '../lib/theme';

interface TopHeaderProps {
  onSearch?: (query: string) => void;
  user?: UserProfile | null;
  onOpenAuth?: (mode: 'login' | 'register') => void;
  onOpenSettings?: () => void;
  onOpenConnections?: () => void;
  onLogout?: () => void;
  metaConnected?: boolean;
  metaUsername?: string | null;
  connectedCount?: number;
}

export function TopHeader({
  onSearch,
  user,
  onOpenAuth,
  onOpenSettings,
  onOpenConnections,
  onLogout,
  metaConnected,
  metaUsername,
  connectedCount,
}: TopHeaderProps) {
  const [searchVal, setSearchVal] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);
  const { theme, toggleTheme, isMounted } = useTheme();

  // Status notes derived from real state (no canned history).
  const [allRead, setAllRead] = useState(false);
  const effectiveConnectedCount = connectedCount ?? (metaConnected ? 1 : 0);
  const notifications = [
    {
      id: 'delivery',
      title: 'Live ad delivery',
      desc: 'Ads enter delivery after Meta review. Billing is handled by the connected ad account.',
      type: 'shield',
    },
    {
      id: 'meta',
      title: effectiveConnectedCount > 0 ? `${effectiveConnectedCount} social platform${effectiveConnectedCount === 1 ? '' : 's'} connected` : 'No social accounts connected',
      desc: effectiveConnectedCount > 0
        ? `Manage your connected platforms${metaUsername ? ` (Instagram @${metaUsername})` : ''} in Social Connections.`
        : 'Connect Facebook, Instagram, or LinkedIn in Social Connections.',
      type: 'meta',
    },
    ...(user ? [{ id: 'user', title: 'Signed in', desc: `Logged in as ${user.name} (${user.workspace}).`, type: 'user' }] : []),
  ].map((n) => ({ ...n, unread: !allRead }));

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
      if (notifRef.current && !notifRef.current.contains(event.target as Node)) {
        setNotifOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && onSearch) {
      onSearch(searchVal);
    }
  };

  const handleMarkAllRead = () => setAllRead(true);

  const unreadCount = notifications.filter((n) => n.unread).length;
  const displayName = user?.name || (user?.email ? user.email.split('@')[0] : null);
  const initials = displayName ? displayName.slice(0, 2).toUpperCase() : 'U';

  return (
    <header className="h-16 px-6 sm:px-8 flex items-center justify-between border-b border-[#EDE6DD] dark:border-white/10 bg-[#FAF8F5]/85 dark:bg-[#0B0F19]/80 backdrop-blur-md sticky top-0 z-30 text-[#1F1A18] dark:text-white transition-colors duration-200">
      {/* Search Input Bar */}
      <div className="relative w-full max-w-xl">
        <Search className="w-4 h-4 text-[#9C8F85] dark:text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
        <input
          type="text"
          value={searchVal}
          onChange={(e) => setSearchVal(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search campaigns, target audiences, or ask anything..."
          className="w-full pl-10 pr-16 py-2 bg-white/80 hover:bg-white focus:bg-white dark:bg-[#111827] dark:hover:bg-[#162032] dark:focus:bg-[#162032] border border-[#E5DDD2] dark:border-white/10 rounded-full text-xs sm:text-sm text-[#1F1A18] dark:text-white placeholder-[#9C8F85] dark:placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-[#F26D5B]/30 focus:border-[#F26D5B] transition-all shadow-2xs"
        />
        <div className="absolute right-3.5 top-1/2 -translate-y-1/2 pointer-events-none flex items-center gap-1 bg-[#F5EFE6] dark:bg-white/5 px-2 py-0.5 rounded-md text-[10px] font-semibold text-[#8A7C73] dark:text-slate-400 border border-[#E8DFC2]/50 dark:border-white/10">
          <span>Ctrl K</span>
        </div>
      </div>

      {/* Right Controls: Theme Toggle, Meta Badge, Notifications & Profile */}
      <div className="flex items-center gap-2.5 sm:gap-3.5 ml-4">
        {/* Theme Switcher Button (Single clean source of truth) */}
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          title={theme === 'dark' ? 'Switch to Light Pink Theme' : 'Switch to Dark Theme'}
          className="relative w-9 h-9 rounded-full bg-white dark:bg-[#111827] hover:bg-[#F3EDE4] dark:hover:bg-white/10 border border-[#E5DDD2] dark:border-white/10 flex items-center justify-center text-[#5C5047] dark:text-slate-300 transition-all shadow-2xs cursor-pointer hover:scale-105 active:scale-95"
        >
          {isMounted && theme === 'dark' ? (
            <Sun className="w-4 h-4 text-amber-400" />
          ) : (
            <Moon className="w-4 h-4 text-[#5C5047] dark:text-slate-300" />
          )}
        </button>

        {/* Social Media Connections Status Badge */}
        {effectiveConnectedCount > 0 ? (
          <button
            type="button"
            onClick={() => (onOpenConnections ? onOpenConnections() : onOpenSettings?.())}
            data-testid="header-connections-btn"
            className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 hover:bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 text-xs font-semibold transition-all cursor-pointer shadow-xs"
          >
            <span className="w-2 h-2 rounded-full bg-emerald-500 dark:bg-emerald-400 animate-pulse" />
            <span>
              {effectiveConnectedCount === 1 && metaUsername
                ? `Connected: @${metaUsername}`
                : `${effectiveConnectedCount} Social Connected`}
            </span>
          </button>
        ) : (
          <button
            type="button"
            onClick={() => (onOpenConnections ? onOpenConnections() : onOpenSettings?.())}
            data-testid="header-connections-btn"
            className="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/80 dark:bg-white/5 hover:bg-white dark:hover:bg-white/10 border border-[#E5DDD2] dark:border-white/10 text-[#5C5047] dark:text-slate-300 text-xs font-semibold transition-all cursor-pointer shadow-2xs"
          >
            <Link2 className="w-3.5 h-3.5 text-[#9C8F85] dark:text-slate-400" />
            <span>Social Connections</span>
          </button>
        )}

        {/* Interactive Notification Bell Popover */}
        <div className="relative" ref={notifRef}>
          <button
            type="button"
            onClick={() => setNotifOpen(!notifOpen)}
            aria-label="Notifications"
            className="relative w-9 h-9 rounded-full bg-white dark:bg-[#111827] hover:bg-[#F3EDE4] dark:hover:bg-white/10 border border-[#E5DDD2] dark:border-white/10 flex items-center justify-center text-[#5C5047] dark:text-slate-300 transition-colors shadow-2xs cursor-pointer"
          >
            <Bell className="w-4 h-4" />
            {unreadCount > 0 && (
              <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-[#F26D5B] ring-2 ring-white dark:ring-[#0B0F19]" />
            )}
          </button>

          {/* Notification Dropdown Panel */}
          {notifOpen && (
            <div className="absolute right-0 mt-2 w-80 sm:w-96 rounded-2xl bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 shadow-2xl p-4 z-50 text-[#1F1A18] dark:text-white animate-in fade-in duration-150">
              <div className="flex items-center justify-between pb-3 border-b border-[#EDE6DD] dark:border-white/10">
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-bold">Notification Center</h4>
                  {unreadCount > 0 && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#FEECE7] dark:bg-[#F26D5B]/20 text-[#F26D5B]">
                      {unreadCount} new
                    </span>
                  )}
                </div>
                {unreadCount > 0 && (
                  <button
                    type="button"
                    onClick={handleMarkAllRead}
                    className="text-[11px] font-semibold text-[#F26D5B] hover:underline cursor-pointer"
                  >
                    Mark all read
                  </button>
                )}
              </div>

              <div className="divide-y divide-[#EDE6DD]/60 dark:divide-white/5 max-h-80 overflow-y-auto">
                {notifications.map((n) => (
                  <div key={n.id} className="py-3 flex items-start gap-3">
                    <div className="w-7 h-7 rounded-lg bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 flex items-center justify-center shrink-0 mt-0.5">
                      {n.type === 'shield' && <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />}
                      {n.type === 'meta' && <Zap className="w-3.5 h-3.5 text-blue-500" />}
                      {n.type === 'system' && <CheckCircle2 className="w-3.5 h-3.5 text-purple-500" />}
                      {n.type === 'user' && <Info className="w-3.5 h-3.5 text-amber-500" />}
                    </div>
                    <div className="flex-1 text-left">
                      <div className="flex items-center justify-between">
                        <p className={`text-xs font-bold ${n.unread ? 'text-[#1F1A18] dark:text-white' : 'text-[#7A6C63] dark:text-slate-400'}`}>
                          {n.title}
                        </p>
                      </div>
                      <p className="text-[11px] text-[#7A6C63] dark:text-slate-400 mt-0.5 leading-relaxed">
                        {n.desc}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* User Profile or Sign In Buttons */}
        {user ? (
          <div className="relative" ref={menuRef}>
            <div
              onClick={() => setMenuOpen(!menuOpen)}
              className="flex items-center gap-2.5 pl-2 py-1 pr-2 rounded-full hover:bg-white/80 dark:hover:bg-white/5 border border-transparent hover:border-[#E5DDD2] dark:hover:border-white/10 transition-colors cursor-pointer select-none"
            >
              <div className="relative w-8 h-8 rounded-full bg-gradient-to-tr from-[#F26D5B] via-[#FF8E53] to-[#A855F7] flex items-center justify-center text-white text-xs font-extrabold shadow-md shadow-[#F26D5B]/20 shrink-0">
                {initials}
              </div>
              <div className="text-left hidden sm:block">
                <p className="text-xs font-bold text-[#1F1A18] dark:text-white leading-tight">
                  {displayName}
                </p>
                <div className="flex items-center gap-1 mt-0.5">
                  {user.is_dev_workspace ? (
                    <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-amber-500/15 text-amber-800 dark:text-amber-300 border border-amber-500/30">
                      Synxait (Dev/Test)
                    </span>
                  ) : (
                    <span className="text-[10px] font-medium text-[#8C7E74] dark:text-slate-400 leading-tight">
                      {user.workspace || 'Workspace'}
                    </span>
                  )}
                </div>
              </div>
              <ChevronDown className="w-3.5 h-3.5 text-[#9C8F85] dark:text-slate-400 ml-0.5" />
            </div>

            {/* Profile Dropdown Menu */}
            {menuOpen && (
              <div className="absolute right-0 mt-2 w-56 rounded-2xl bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 shadow-2xl p-2 z-50 text-[#1F1A18] dark:text-white animate-in fade-in duration-150">
                <div className="px-3 py-2 border-b border-[#EDE6DD] dark:border-white/10 mb-1">
                  <p className="text-xs font-bold text-[#1F1A18] dark:text-white">{displayName}</p>
                  <p className="text-[11px] text-[#8C7E74] dark:text-slate-400 truncate">{user.email}</p>
                </div>

                {/* Workspace Switcher */}
                <div className="py-2 border-b border-[#EDE6DD] dark:border-white/10 px-2 space-y-1">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-[#9C8F85] dark:text-slate-400 block px-1">
                    Workspace
                  </span>
                  {(user.workspaces || [
                    { id: 'synxait', name: 'Synxait', label: 'Synxait (Dev/Test)', type: 'development' },
                    { id: 'personal', name: user.workspace || 'Customer Workspace', label: user.workspace || 'Customer Workspace', type: 'customer' },
                  ]).map((ws) => {
                    const isActive = (user.workspace_id || (user.is_dev_workspace ? 'synxait' : 'personal')) === ws.id;
                    return (
                      <button
                        key={ws.id}
                        type="button"
                        onClick={async () => {
                          try {
                            await switchWorkspace(ws.id);
                            window.location.reload();
                          } catch (err) {
                            console.error('Failed to switch workspace', err);
                          }
                        }}
                        className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer text-left ${
                          isActive
                            ? 'bg-[#F26D5B]/10 text-[#F26D5B] font-bold'
                            : 'text-[#2A1E1B] dark:text-slate-300 hover:bg-[#FAF8F5] dark:hover:bg-white/5'
                        }`}
                      >
                        <span className="truncate">{ws.label || ws.name}</span>
                        {isActive && <Check className="w-3.5 h-3.5 text-[#F26D5B] shrink-0" />}
                      </button>
                    );
                  })}
                </div>

                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    onOpenSettings?.();
                  }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold text-[#2A1E1B] dark:text-slate-200 hover:bg-[#FAF8F5] dark:hover:bg-white/10 transition-colors cursor-pointer text-left"
                >
                  <Settings className="w-4 h-4 text-[#F26D5B]" />
                  <span>Settings</span>
                </button>

                {onLogout && (
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      onLogout();
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-500/10 transition-colors cursor-pointer text-left mt-1"
                  >
                    <LogOut className="w-4 h-4" />
                    <span>Sign Out</span>
                  </button>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onOpenAuth && onOpenAuth('login')}
              className="px-3 py-1.5 rounded-xl text-xs font-semibold text-[#5C5047] dark:text-slate-300 hover:text-[#1F1A18] dark:hover:text-white hover:bg-white/80 dark:hover:bg-white/5 border border-[#E5DDD2] dark:border-transparent transition-colors cursor-pointer shadow-2xs"
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => onOpenAuth && onOpenAuth('register')}
              className="px-3.5 py-1.5 rounded-xl text-xs font-bold bg-gradient-to-r from-[#F26D5B] to-[#FF8E53] hover:from-[#E05947] hover:to-[#F26D5B] text-white shadow-md shadow-[#F26D5B]/20 transition-all cursor-pointer"
            >
              Register
            </button>
          </div>
        )}
      </div>
    </header>
  );
}

export default TopHeader;
