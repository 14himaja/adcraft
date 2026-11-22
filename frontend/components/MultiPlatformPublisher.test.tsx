import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MultiPlatformPublisher } from './MultiPlatformPublisher';
import { bodyOf, calls, mockApi, renderSWR } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

const INTEGRATIONS = {
  organization_id: 'synxait',
  connected_count: 2,
  total_platforms: 3,
  platforms: [
    {
      platform: 'instagram',
      name: 'Instagram',
      description: 'IG',
      configured: true,
      required_env_vars: [],
      required_scopes: [],
      capabilities: {
        supports_oauth: true,
        supports_refresh: false,
        supports_account_selection: true,
        supports_text_post: false,
        supports_image_post: true,
        supports_link_post: false,
        supports_title: false,
        requires_image: true,
        requires_target_selection: true,
        max_text_length: 2200,
        target_label: 'Instagram Business Account',
      },
      advertising: { supported: true, status: 'ACTIVE', note: '' },
      status: 'NOT_CONNECTED',
      connected: false,
    },
    {
      platform: 'facebook',
      name: 'Facebook',
      description: 'Facebook',
      configured: true,
      required_env_vars: [],
      required_scopes: [],
      capabilities: {
        supports_oauth: true,
        supports_refresh: false,
        supports_account_selection: true,
        supports_text_post: true,
        supports_image_post: true,
        supports_link_post: true,
        supports_title: false,
        requires_image: false,
        requires_target_selection: true,
        max_text_length: 63206,
        target_label: 'Facebook Page',
      },
      advertising: { supported: true, status: 'ACTIVE', note: '' },
      status: 'ACTIVE',
      connected: true,
      selected_target_id: 'page_123',
      selected_target_name: 'Synxait Facebook Page',
    },
    {
      platform: 'linkedin',
      name: 'LinkedIn',
      description: 'LinkedIn',
      configured: true,
      required_env_vars: [],
      required_scopes: [],
      capabilities: {
        supports_oauth: true,
        supports_refresh: true,
        supports_account_selection: true,
        supports_text_post: true,
        supports_image_post: true,
        supports_link_post: true,
        supports_title: false,
        requires_image: false,
        requires_target_selection: true,
        max_text_length: 3000,
        target_label: 'LinkedIn Organization Page',
      },
      advertising: { supported: false, status: 'REQUIRES_API_APPROVAL', note: '' },
      status: 'ACTIVE',
      connected: true,
      selected_target_id: 'urn:li:organization:555',
      selected_target_name: 'Synxait Corp',
    },
  ],
};

describe('MultiPlatformPublisher', () => {
  it('validates, previews, and publishes independently across connected platforms', async () => {
    const fetchMock = mockApi({
      'GET /v1/integrations': INTEGRATIONS,
      'GET /v1/media': [],
      'GET /v1/integrations/publish/history': [],
      'GET /v1/hashtags': { categories: {}, custom: [], max_limit: 5 },
      'POST /v1/integrations/publish/preview': {
        previews: {
          linkedin: {
            platform: 'linkedin',
            name: 'LinkedIn',
            connection_status: 'ACTIVE',
            target_id: 'urn:li:organization:555',
            target_name: 'Synxait Corp',
            formatted_text: 'Launching today!',
            character_count: 16,
            max_text_length: 3000,
            valid: true,
            errors: [],
          },
          facebook: {
            platform: 'facebook',
            name: 'Facebook',
            connection_status: 'ACTIVE',
            target_id: 'page_123',
            target_name: 'Synxait Facebook Page',
            formatted_text: 'Launching today!',
            character_count: 16,
            max_text_length: 63206,
            valid: true,
            errors: [],
          },
        },
      },
      'POST /v1/integrations/publish': {
        results: {
          linkedin: {
            platform: 'linkedin',
            status: 'PUBLISHED',
            platform_post_id: 'urn:li:share:1',
            post_url: 'https://linkedin.com/feed/update/1',
          },
          facebook: {
            platform: 'facebook',
            status: 'FAILED',
            error: 'Rate limit reached',
          },
        },
      },
    });

    renderSWR(<MultiPlatformPublisher />);

    // Instagram is disconnected so its selector button is disabled
    expect(await screen.findByTestId('select-platform-instagram')).toBeDisabled();
    await userEvent.click(screen.getByTestId('select-platform-linkedin'));
    await userEvent.click(screen.getByTestId('select-platform-facebook'));

    await userEvent.type(screen.getByLabelText(/post text \/ caption/i), 'Launching today!');
    await userEvent.click(screen.getByTestId('btn-preview-multi'));

    expect(await screen.findByTestId('multi-previews')).toBeInTheDocument();
    expect(screen.getByText('16/3000')).toBeInTheDocument();

    await userEvent.click(screen.getByTestId('btn-publish-multi'));
    await waitFor(() => expect(calls(fetchMock, 'POST /v1/integrations/publish')).toHaveLength(1));
    expect(bodyOf(fetchMock, 'POST /v1/integrations/publish').platforms).toEqual(['linkedin', 'facebook']);

    const results = await screen.findByTestId('multi-publish-results');
    expect(results).toHaveTextContent(/linkedin: PUBLISHED/i);
    expect(results).toHaveTextContent(/facebook: FAILED/i);
    expect(results).toHaveTextContent(/Rate limit reached/i);
  });
});
