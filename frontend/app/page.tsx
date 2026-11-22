'use client';

import React, { useState, useEffect, useSyncExternalStore } from 'react';
import { useSWRConfig } from 'swr';
import { Sidebar, SidebarSection } from '../components/Sidebar';
import { TopHeader } from '../components/TopHeader';
import { HeroBanner } from '../components/HeroBanner';
import { WorkflowSteps } from '../components/WorkflowSteps';
import { RecentCampaigns } from '../components/RecentCampaigns';
import { CampaignPerformanceCard } from '../components/CampaignPerformanceCard';
import { CampaignStudioModal } from '../components/CampaignStudioModal';
import { ChatStudio } from '../components/ChatStudio';
import { SettingsModal } from '../components/SettingsModal';
import { AuthModal } from '../components/AuthModal';
import { AudienceView } from '../components/AudienceView';
import { CampaignsView } from '../components/CampaignsView';
import { MediaView } from '../components/MediaView';
import { InsightsView } from '../components/InsightsView';
import { DmAgentView } from '../components/DmAgentView';
import { OrganicPostView } from '../components/OrganicPostView';
import { SocialMediaConnections } from '../components/SocialMediaConnections';
import { MultiPlatformPublisher } from '../components/MultiPlatformPublisher';
import { Campaign, getMe, logout, UserProfile, MetaInterest, MetaLocation } from '../lib/api';
import { useMetaConnection } from '../lib/meta';
import { useSocialConnections } from '../lib/integrations';

const VALID_SECTIONS: SidebarSection[] = [
  'dashboard',
  'campaigns',
  'audience',
  'media',
  'insights',
  'dm',
  'posts',
  'connections',
];

function subscribeNoop() {
  return () => {};
}

export default function Home() {
  const urlSection = useSyncExternalStore(
    subscribeNoop,
    () => {
      const sec = new URLSearchParams(window.location.search).get('section') as SidebarSection | null;
      return sec && VALID_SECTIONS.includes(sec) ? sec : 'dashboard';
    },
    () => 'dashboard' as SidebarSection
  );
  const [selectedSection, setSelectedSection] = useState<SidebarSection | null>(null);
  const activeSection = selectedSection ?? urlSection;
  const setActiveSection = (sec: SidebarSection) => setSelectedSection(sec);
  const [publishMode, setPublishMode] = useState<'instagram' | 'multi'>('multi');
  // null = closed; { id: null } = new draft from scratch; { id, campaign } = edit saved draft
  const [studio, setStudio] = useState<{ id: string | null; campaign?: Campaign | null } | null>(null);
  // null = closed; { campaign: null } = new chat; { campaign } = continue a draft in the chat
  const [chat, setChat] = useState<{ campaign: Campaign | null } | null>(null);
  const [idea, setIdea] = useState('');
  const { mutate } = useSWRConfig();
  const refreshCampaigns = () => mutate('/v1/campaigns');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<'meta' | 'account' | 'ai' | 'appearance'>('account');
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');

  // User Authentication State
  const [user, setUser] = useState<UserProfile | null>(null);

  // Meta & Multi-Platform Connection State via SWR
  const { connection, mutate: mutateMeta } = useMetaConnection();
  const { connectedCount, mutate: mutateSocial } = useSocialConnections();
  const isMetaConnected = connection?.status === 'ACTIVE';

  useEffect(() => {
    getMe()
      .then((profile) => setUser(profile))
      .catch(() => setUser(null));
  }, []);

  // Prompts typed anywhere on the dashboard land in the AI Ad Studio box; the user then presses Generate ad.
  const handleIdea = (prompt?: string) => {
    if (prompt) setIdea(prompt);
    setActiveSection('dashboard');
    setTimeout(() => document.getElementById('ad-idea')?.focus(), 0);
  };
  const openScratch = () => setStudio({ id: null, campaign: null });
  const openWizard = (id: string, campaign?: Campaign) => setStudio({ id, campaign });
  const openChat = (campaign: Campaign | null = null) => setChat({ campaign });
  // Drafts continue in the chat; published campaigns open the full editor.
  const openDraft = (id: string, campaign?: Campaign) =>
    campaign?.status === 'DRAFT' ? openChat(campaign) : openWizard(id, campaign);

  const handleOpenSettings = (tab?: 'meta' | 'account' | 'ai' | 'appearance') => {
    if (tab) {
      setSettingsTab(tab);
    }
    setSettingsOpen(true);
  };

  const handleOpenAuth = (mode: 'login' | 'register') => {
    setAuthMode(mode);
    setAuthOpen(true);
  };

  const handleAuthSuccess = (profile?: UserProfile) => {
    if (profile) {
      setUser(profile);
    } else {
      getMe().then(setUser).catch(() => {});
    }
    mutateMeta();
    mutateSocial();
    setAuthOpen(false);

    if (!isMetaConnected && connectedCount === 0) {
      setActiveSection('connections');
    }
  };

  const handleLogout = async () => {
    try {
      await logout();
      setUser(null);
      mutateMeta(undefined, false);
      mutateSocial(undefined, false);
    } catch {
      setUser(null);
      mutateMeta(undefined, false);
      mutateSocial(undefined, false);
    }
  };

  const handleApplyAudience = (audienceData: {
    country: string;
    cities: MetaLocation[];
    age_min: number;
    age_max: number;
    gender: 'ALL' | 'MEN' | 'WOMEN';
    interests: MetaInterest[];
  }) => {
    const campaign: Campaign = {
      id: '', status: 'DRAFT', idea: '', title: '', objective: 'TRAFFIC', landing_url: '',
      audience: {
        countries: [audienceData.country],
        cities: audienceData.cities.map(({ key, name }) => ({ key, name })),
        age_min: audienceData.age_min,
        age_max: audienceData.age_max,
        genders: audienceData.gender,
        interests: audienceData.interests.map(({ id, name }) => ({ id, name })),
      },
      daily_budget: 100, currency: 'INR', start_date: null, end_date: null,
      variants: [{ headline: '', primary_text: '', description: '', call_to_action: 'LEARN_MORE' }],
      selected_variant: 0, image_prompt: '', image_id: null, image_url: null,
      missing_fields: [], warnings: [], can_publish: false, can_activate: false,
    };
    setStudio({ id: null, campaign });
  };

  return (
    <div className="min-h-screen bg-[#FAF8F5] dark:bg-[#090D16] text-[#1F1A18] dark:text-[#F8FAFC] flex font-sans transition-colors duration-200">
      {/* 1. Left Navigation Sidebar */}
      <Sidebar
        activeSection={activeSection}
        onSelectSection={(sec) => setActiveSection(sec)}
        onOpenAssistant={() => handleIdea()}
        onOpenSettings={handleOpenSettings}
      />

      {/* 2. Main Center & Right Content Container */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Sticky Header with live user & Meta connection */}
        <TopHeader
          onSearch={(q) => handleIdea(q)}
          user={user}
          metaConnected={isMetaConnected}
          metaUsername={connection?.instagram_username}
          connectedCount={connectedCount}
          onOpenAuth={handleOpenAuth}
          onOpenConnections={() => setActiveSection('connections')}
          onOpenSettings={() => handleOpenSettings('meta')}
          onLogout={handleLogout}
        />

        {/* Dynamic Section Rendering */}
        <main className="flex-1 p-6 sm:p-8 space-y-8 max-w-[1560px] mx-auto w-full">
          {activeSection === 'dashboard' && (
            <div className="space-y-8">
              {/* Redesigned Hero Banner with integrated idea generator */}
              <HeroBanner
                onDraftReady={(draft) => {
                  refreshCampaigns();
                  openChat(draft);
                }}
                onSubmitPrompt={handleIdea}
                initialPrompt={idea}
                onPromptChange={setIdea}
              />

              {/* Remaining dashboard content: Workflow, Recent Campaigns and Performance */}
              <div className="grid grid-cols-1 xl:grid-cols-12 gap-8 items-start">
                <div className="xl:col-span-8 space-y-6">
                  {/* 4-Stage Horizontal Workflow Strip */}
                  <WorkflowSteps onStepClick={() => handleIdea()} />

                  {/* Recent Campaigns Section */}
                  <RecentCampaigns onEditCampaign={openDraft} onCreateNew={() => openChat()} />
                </div>

                <div className="xl:col-span-4 space-y-6">
                  {/* Campaign Performance Multi-Line Area Chart Card */}
                  <CampaignPerformanceCard />
                </div>
              </div>
            </div>
          )}

          {activeSection === 'campaigns' && (
            <CampaignsView onCreateCampaign={() => openChat()} onEditCampaign={openDraft} />
          )}

          {activeSection === 'audience' && (
            <AudienceView onApplyToCampaign={handleApplyAudience} />
          )}

          {activeSection === 'media' && (
            <MediaView />
          )}

          {activeSection === 'dm' && <DmAgentView />}

          {activeSection === 'posts' && (
            <div className="space-y-6">
              <div className="inline-flex p-1 rounded-2xl bg-white dark:bg-[#111827] border border-[#EDE6DD] dark:border-white/10 text-xs font-bold">
                <button
                  type="button"
                  onClick={() => setPublishMode('instagram')}
                  className={`px-4 py-2 rounded-xl transition-colors cursor-pointer ${
                    publishMode === 'instagram'
                      ? 'bg-[#F26D5B] text-white shadow-xs'
                      : 'text-[#7A6C63] dark:text-slate-400 hover:text-[#1F1A18] dark:hover:text-white'
                  }`}
                >
                  Post to Instagram
                </button>
                <button
                  type="button"
                  onClick={() => setPublishMode('multi')}
                  className={`px-4 py-2 rounded-xl transition-colors cursor-pointer ${
                    publishMode === 'multi'
                      ? 'bg-[#F26D5B] text-white shadow-xs'
                      : 'text-[#7A6C63] dark:text-slate-400 hover:text-[#1F1A18] dark:hover:text-white'
                  }`}
                >
                  Multi-Platform Publisher
                </button>
              </div>
              {publishMode === 'instagram' ? (
                <OrganicPostView />
              ) : (
                <MultiPlatformPublisher onOpenConnections={() => setActiveSection('connections')} />
              )}
            </div>
          )}

          {activeSection === 'connections' && (
            <SocialMediaConnections
              returnTo="/?section=connections"
              onOpenPublisher={() => {
                setPublishMode('multi');
                setActiveSection('posts');
              }}
            />
          )}

          {activeSection === 'insights' && (
            <InsightsView />
          )}
        </main>
      </div>

      {/* 3. Production Campaign Creation Studio Modal */}
      {studio && (
        <CampaignStudioModal
          key={studio.id ?? 'new'}
          campaignId={studio.id}
          initialCampaign={studio.campaign}
          onClose={() => setStudio(null)}
          onChanged={refreshCampaigns}
        />
      )}

      {chat && (
        <ChatStudio
          key={chat.campaign?.id ?? 'new'}
          campaign={chat.campaign}
          onClose={() => setChat(null)}
          onChanged={refreshCampaigns}
          onAdvanced={(campaign) => {
            setChat(null);
            openWizard(campaign.id, campaign);
          }}
        />
      )}

      {/* 4. Full Platform & Meta Connection Settings Modal */}
      <SettingsModal
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onOpenMetaConnection={() => handleOpenSettings('meta')}
        user={user}
        initialTab={settingsTab}
        onOpenAuth={handleOpenAuth}
        onLogout={handleLogout}
      />

      {/* 5. In-Page Auth Modal (Login / Register) */}
      <AuthModal
        isOpen={authOpen}
        onClose={() => setAuthOpen(false)}
        initialMode={authMode}
        onSuccess={handleAuthSuccess}
      />
    </div>
  );
}
