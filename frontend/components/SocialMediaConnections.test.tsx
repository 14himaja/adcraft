import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SocialMediaConnections } from './SocialMediaConnections';
import { bodyOf, calls, mockApi, renderSWR } from '../test/mockApi';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const makePlatform = (
  platform: string,
  name: string,
  over: Record<string, unknown> = {}
) => ({
  platform,
  name,
  description: `${name} integration description`,
  configured: true,
  required_env_vars: [`${platform.toUpperCase()}_CLIENT_ID`],
  required_scopes: ['read', 'write'],
  capabilities: {
    supports_oauth: true,
    supports_refresh: platform === 'linkedin',
    supports_account_selection: true,
    supports_text_post: true,
    supports_image_post: true,
    supports_link_post: true,
    supports_title: false,
    requires_image: platform === 'instagram',
    requires_target_selection: true,
    max_text_length: platform === 'facebook' ? 63206 : 3000,
    target_label:
      platform === 'linkedin'
        ? 'LinkedIn Organization Page or Profile'
        : platform === 'facebook'
        ? 'Facebook Page'
        : `${name} Account`,
  },
  advertising: { supported: platform === 'facebook' || platform === 'instagram', status: 'FUTURE_PHASE', note: '' },
  status: 'NOT_CONNECTED',
  connected: false,
  ...over,
});

const ALL_THREE_NOT_CONNECTED = {
  organization_id: 'synxait',
  connected_count: 0,
  total_platforms: 3,
  platforms: [
    makePlatform('facebook', 'Facebook'),
    makePlatform('instagram', 'Instagram'),
    makePlatform('linkedin', 'LinkedIn'),
  ],
};

describe('SocialMediaConnections', () => {
  it('renders all 3 social media platforms with Connect buttons when disconnected', async () => {
    mockApi({
      'GET /v1/integrations': ALL_THREE_NOT_CONNECTED,
      'GET /v1/integrations/advertising/platforms': { organization_id: 'synxait', note: '', platforms: [] },
    });
    renderSWR(<SocialMediaConnections />);

    expect(await screen.findByText('Social Media Connections')).toBeInTheDocument();
    expect(screen.getByTestId('connected-count-badge')).toHaveTextContent('0 of 3 connected');

    for (const pid of ['facebook', 'instagram', 'linkedin']) {
      expect(screen.getByTestId(`platform-card-${pid}`)).toBeInTheDocument();
      expect(screen.getByTestId(`btn-connect-${pid}`)).toBeInTheDocument();
      expect(screen.getByTestId(`status-${pid}`)).toHaveTextContent(/not connected/i);
    }
  });

  it('redirects to /login preserving LinkedIn OAuth destination when not authenticated', async () => {
    mockApi({
      'GET /v1/integrations': ALL_THREE_NOT_CONNECTED,
      'GET /v1/integrations/advertising/platforms': { organization_id: 'synxait', note: '', platforms: [] },
      'GET /v1/auth/me': () => {
        throw new Error('Not logged in');
      },
    });

    const mockLoc = { href: '', assign: vi.fn(), replace: vi.fn() };
    vi.stubGlobal('location', mockLoc);

    renderSWR(<SocialMediaConnections returnTo="/settings/connections" />);
    await userEvent.click(await screen.findByTestId('btn-connect-linkedin'));

    await waitFor(() => {
      expect(mockLoc.href).toBe(
        `/login?redirect=${encodeURIComponent(
          '/api/v1/integrations/linkedin/connect?return_to=%2Fsettings%2Fconnections'
        )}`
      );
    });
  });

  it('initiates LinkedIn OAuth directly when user is authenticated', async () => {
    mockApi({
      'GET /v1/integrations': ALL_THREE_NOT_CONNECTED,
      'GET /v1/integrations/advertising/platforms': { organization_id: 'synxait', note: '', platforms: [] },
      'GET /v1/auth/me': { id: 'u1', email: 'test@example.com', name: 'User', workspace: 'W' },
    });

    const mockLoc = { href: '', assign: vi.fn(), replace: vi.fn() };
    vi.stubGlobal('location', mockLoc);

    renderSWR(<SocialMediaConnections returnTo="/settings/connections" />);
    await userEvent.click(await screen.findByTestId('btn-connect-linkedin'));

    await waitFor(() => {
      expect(mockLoc.href).toBe(
        '/api/v1/integrations/linkedin/connect?return_to=%2Fsettings%2Fconnections'
      );
    });
  });

  it('allows managing a connected LinkedIn account and separating Organization Pages from Personal Profile', async () => {
    const fetchMock = mockApi({
      'GET /v1/integrations': {
        organization_id: 'synxait',
        connected_count: 1,
        total_platforms: 3,
        platforms: [
          makePlatform('facebook', 'Facebook'),
          makePlatform('instagram', 'Instagram'),
          makePlatform('linkedin', 'LinkedIn', {
            status: 'ACTIVE',
            connected: true,
            account_display_name: 'Alice Smith',
            selected_target_id: 'urn:li:person:1',
            selected_target_name: 'Alice Smith',
            account_type: 'personal',
          }),
        ],
      },
      'GET /v1/integrations/advertising/platforms': { organization_id: 'synxait', note: '', platforms: [] },
      'GET /v1/integrations/linkedin/accounts': {
        platform: 'linkedin',
        selected_target_id: 'urn:li:person:1',
        accounts: [
          {
            account_id: 'urn:li:organization:555',
            display_name: 'Synxait Corp (Organization Page)',
            account_type: 'organization',
            target_id: 'urn:li:organization:555',
            target_name: 'Synxait Corp',
            target_type: 'linkedin_organization',
            can_publish: true,
            permission_note: 'Organization Page administrator.',
          },
          {
            account_id: 'urn:li:person:1',
            display_name: 'Alice Smith (Personal Profile)',
            account_type: 'personal',
            target_id: 'urn:li:person:1',
            target_name: 'Alice Smith',
            target_type: 'linkedin_personal',
            can_publish: true,
            permission_note: 'Personal profile.',
          },
        ],
      },
      'PUT /v1/integrations/linkedin/account': makePlatform('linkedin', 'LinkedIn', {
        status: 'ACTIVE',
        connected: true,
        selected_target_id: 'urn:li:organization:555',
        selected_target_name: 'Synxait Corp',
      }),
    });

    renderSWR(<SocialMediaConnections />);
    await userEvent.click(await screen.findByTestId('btn-manage-linkedin'));

    const dialog = await screen.findByRole('dialog', { name: /manage linkedin account/i });
    expect(await within(dialog).findByText(/Organization Pages/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/Synxait Corp \(Organization Page\)/i)).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole('radio', { name: /Synxait Corp/i }));
    await userEvent.click(within(dialog).getByRole('button', { name: /save selection/i }));

    await waitFor(() => expect(calls(fetchMock, 'PUT /v1/integrations/linkedin/account')).toHaveLength(1));
    expect(bodyOf(fetchMock, 'PUT /v1/integrations/linkedin/account')).toEqual({
      target_id: 'urn:li:organization:555',
    });
  });

  it('disconnects a connected platform independently after confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const fetchMock = mockApi({
      'GET /v1/integrations': {
        organization_id: 'synxait',
        connected_count: 1,
        total_platforms: 3,
        platforms: [
          makePlatform('facebook', 'Facebook'),
          makePlatform('instagram', 'Instagram'),
          makePlatform('linkedin', 'LinkedIn', {
            status: 'ACTIVE',
            connected: true,
            account_username: 'synxait_li',
            selected_target_name: 'Synxait Corp',
          }),
        ],
      },
      'GET /v1/integrations/advertising/platforms': { organization_id: 'synxait', note: '', platforms: [] },
      'POST /v1/integrations/linkedin/disconnect': makePlatform('linkedin', 'LinkedIn'),
    });

    renderSWR(<SocialMediaConnections />);
    await userEvent.click(await screen.findByTestId('btn-disconnect-linkedin'));

    await waitFor(() => expect(calls(fetchMock, 'POST /v1/integrations/linkedin/disconnect')).toHaveLength(1));
    expect(await screen.findByText(/linkedin disconnected\./i)).toBeInTheDocument();
  });

  it('shows OAuth success, cancellation, and missing credentials banners', async () => {
    mockApi({
      'GET /v1/integrations': ALL_THREE_NOT_CONNECTED,
      'GET /v1/integrations/advertising/platforms': { organization_id: 'synxait', note: '', platforms: [] },
    });
    const { rerender } = renderSWR(
      <SocialMediaConnections oauthConnected="1" oauthPlatform="linkedin" />
    );
    expect(await screen.findByTestId('oauth-connected-banner')).toHaveTextContent(/linkedin connected successfully/i);

    rerender(<SocialMediaConnections oauthError="denied" oauthPlatform="linkedin" />);
    expect(screen.getByTestId('oauth-error-banner')).toHaveTextContent(/authorization was cancelled/i);

    rerender(<SocialMediaConnections oauthError="not_configured" oauthPlatform="linkedin" />);
    expect(screen.getByTestId('oauth-error-banner')).toHaveTextContent(/LINKEDIN_CLIENT_ID/i);
  });

  it('shows separate Paid Advertising Readiness panel with gated platforms', async () => {
    mockApi({
      'GET /v1/integrations': ALL_THREE_NOT_CONNECTED,
      'GET /v1/integrations/advertising/platforms': {
        organization_id: 'synxait',
        note: 'Paid ads separate',
        platforms: [
          {
            id: 'linkedin_ads',
            social_platform: 'linkedin',
            name: 'LinkedIn Ads',
            status: 'REQUIRES_API_APPROVAL',
            organic_connected: false,
            api_approved: false,
            billing_supported_india: 'International Card · 18% GST',
            min_daily_budget: '$10 USD/day',
            available_features: [],
            gated_features: ['campaign_creation'],
            requirements_note: 'Requires separate LinkedIn Advertising API approval.',
          },
        ],
      },
    });
    renderSWR(<SocialMediaConnections />);
    await userEvent.click(await screen.findByRole('button', { name: /view ad readiness/i }));
    expect(await screen.findByText('LinkedIn Ads')).toBeInTheDocument();
    expect(screen.getByText(/REQUIRES API APPROVAL/i)).toBeInTheDocument();
  });
});
