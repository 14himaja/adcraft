'use client';

import React from 'react';
import useSWR from 'swr';
import { fetcher } from '../lib/api';
import {
  Bot,
  FolderKanban,
  ImageIcon,
  Users,
  BarChart3,
  Settings,
  Link2,
  Home,
  MessageCircle,
  Send,
} from 'lucide-react';

export type SidebarSection = 'dashboard' | 'campaigns' | 'audience' | 'media' | 'insights' | 'dm' | 'posts' | 'connections';

interface SidebarProps {
  activeSection?: SidebarSection;
  onSelectSection?: (section: SidebarSection) => void;
  onOpenAssistant?: () => void;
  onOpenSettings?: (tab?: 'meta' | 'account' | 'ai') => void;
}

export function Sidebar({
  activeSection = 'dashboard',
  onSelectSection,
  onOpenAssistant,
  onOpenSettings,
}: SidebarProps) {
  const { data: dmSummary } = useSWR<{ needs_human: number }>('/v1/dm/summary', fetcher, { refreshInterval: 30_000 });
  const navItems = [
    {
      id: 'dashboard',
      label: 'Home',
      icon: Home,
      onClick: () => onSelectSection && onSelectSection('dashboard'),
    },
    {
      id: 'assistant',
      label: 'AI Assistant',
      icon: Bot,
      isAction: true,
      onClick: () => onOpenAssistant && onOpenAssistant(),
    },
    {
      id: 'campaigns',
      label: 'Campaigns',
      icon: FolderKanban,
      onClick: () => onSelectSection && onSelectSection('campaigns'),
    },
    {
      id: 'audience',
      label: 'Audience & Targeting',
      icon: Users,
      onClick: () => onSelectSection && onSelectSection('audience'),
    },
    {
      id: 'media',
      label: 'Media Library',
      icon: ImageIcon,
      onClick: () => onSelectSection && onSelectSection('media'),
    },
    {
      id: 'dm',
      label: 'DM Agent',
      icon: MessageCircle,
      onClick: () => onSelectSection && onSelectSection('dm'),
    },
    {
      id: 'posts',
      label: 'Publish Posts',
      icon: Send,
      onClick: () => onSelectSection && onSelectSection('posts'),
    },
    {
      id: 'insights',
      label: 'Analytics',
      icon: BarChart3,
      onClick: () => onSelectSection && onSelectSection('insights'),
    },
    {
      id: 'connections',
      label: 'Social Accounts',
      icon: Link2,
      onClick: () =>
        onSelectSection ? onSelectSection('connections') : onOpenSettings && onOpenSettings('meta'),
    },
    {
      id: 'settings',
      label: 'Settings',
      icon: Settings,
      onClick: () => onOpenSettings && onOpenSettings('account'),
    },
  ];

  return (
    <aside className="sticky top-0 h-screen w-64 bg-[#FAF8F5] dark:bg-[#0B0F19] border-r border-[#EDE6DD] dark:border-white/10 flex flex-col justify-between p-5 shrink-0 select-none text-[#2A1E1B] dark:text-white transition-colors duration-200">
      {/* Top Branding & Navigation */}
      <div className="space-y-6">
        {/* Logo */}
        <div
          onClick={() => onSelectSection && onSelectSection('dashboard')}
          className="flex items-center gap-3 px-2 group cursor-pointer"
        >
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#F26D5B] via-[#FF8E53] to-[#A855F7] flex items-center justify-center shadow-lg shadow-[#F26D5B]/20 group-hover:scale-105 transition-transform">
            <svg
              className="w-5 h-5 text-white"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 3v18" />
              <path d="M12 8c-4-4-9-2-9 4s5 8 9 4" />
              <path d="M12 8c4-4 9-2 9 4s-5 8-9 4" />
            </svg>
          </div>
          <div>
            <h1 className="text-xl font-extrabold text-[#2A1E1B] dark:text-white tracking-tight leading-none">
              AdCraft
            </h1>
            <p className="text-[10px] uppercase font-bold tracking-wider text-[#8C7E74] dark:text-slate-400 mt-1">
              Create · Grow · Inspire
            </p>
          </div>
        </div>

        {/* Navigation Links */}
        <nav className="space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeSection === item.id;

            return (
              <button
                key={item.label}
                type="button"
                onClick={item.onClick}
                className={`w-full flex items-center gap-3.5 px-3.5 py-2.5 rounded-xl text-sm font-semibold transition-all text-left cursor-pointer ${
                  isActive
                    ? 'bg-[#FEECE7] dark:bg-[#F26D5B]/20 text-[#F26D5B] border border-[#FAD6CD] dark:border-[#F26D5B]/30 shadow-2xs'
                    : 'text-[#6A5A53] dark:text-slate-300 hover:bg-white/80 dark:hover:bg-white/5 hover:text-[#2A1E1B] dark:hover:text-white'
                }`}
              >
                <Icon
                  className={`w-4 h-4 ${
                    isActive ? 'text-[#F26D5B]' : 'text-[#9C8F85] dark:text-slate-400'
                  }`}
                />
                <span>{item.id === 'dm' && (dmSummary?.needs_human ?? 0) > 0 ? `DM Agent (${dmSummary?.needs_human})` : item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

    </aside>
  );
}

export default Sidebar;
