import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PublishingDestinations } from './PublishingDestinations';
import { CONNECTION, mockApi, renderSWR } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

describe('PublishingDestinations', () => {
  const defaultDestinations = {
    facebook_feed: false,
    facebook_story: false,
    instagram_feed: false,
    instagram_story: false,
  };

  it('renders all four publishing destinations with titles, descriptions and icons', async () => {
    renderSWR(
      <PublishingDestinations
        destinations={defaultDestinations}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByRole('heading', { name: /publishing destinations/i })).toBeInTheDocument();
    expect(screen.getByText(/0 of 4 selected/i)).toBeInTheDocument();

    const expectedTitles = [
      'Facebook Feed',
      'Facebook Story',
      'Instagram Feed',
      'Instagram Story',
    ];

    for (const title of expectedTitles) {
      expect(screen.getByText(title)).toBeInTheDocument();
      expect(screen.getByRole('checkbox', { name: title })).not.toBeChecked();
    }

    expect(
      screen.getByText(/publish the ad as a regular post on your connected facebook page/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/share the same creative as a facebook story/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/publish the generated image and caption as an instagram feed post/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/share the generated creative to instagram stories/i)
    ).toBeInTheDocument();
  });

  it('reflects active toggle states and calls onChange on toggle click', async () => {
    const onChange = vi.fn();
    renderSWR(
      <PublishingDestinations
        destinations={{
          ...defaultDestinations,
          facebook_feed: true,
          instagram_feed: true,
        }}
        onChange={onChange}
      />
    );

    expect(screen.getByText(/2 of 4 selected/i)).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Facebook Feed' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Instagram Feed' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Facebook Story' })).not.toBeChecked();

    await userEvent.click(screen.getByRole('checkbox', { name: 'Facebook Story' }));
    expect(onChange).toHaveBeenCalledWith('facebook_story', true);

    await userEvent.click(screen.getByRole('checkbox', { name: 'Facebook Feed' }));
    expect(onChange).toHaveBeenCalledWith('facebook_feed', false);
  });

  it('displays connected Facebook Page and Instagram accounts', async () => {
    mockApi({
      'GET /v1/meta/connection': CONNECTION,
    });
    renderSWR(
      <PublishingDestinations
        destinations={defaultDestinations}
        onChange={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getAllByText(/Page: Synxa Page/i)).toHaveLength(2);
      expect(screen.getAllByText(/Account: @synxait/i)).toHaveLength(2);
    });
  });

  it('renders live per-destination statuses: Publishing, Published, and Failed with Retry', async () => {
    const onRetry = vi.fn();
    renderSWR(
      <PublishingDestinations
        destinations={{
          facebook_feed: true,
          facebook_story: true,
          instagram_feed: true,
          instagram_story: false,
        }}
        onChange={vi.fn()}
        onRetry={onRetry}
        statuses={{
          facebook_feed: { status: 'PUBLISHED', media_id: 'fb_123' },
          facebook_story: { status: 'FAILED', error: 'Stories require page admin permissions' },
          instagram_feed: { status: 'PUBLISHING' },
        }}
      />
    );

    // Instagram Feed shows publishing in progress
    expect(screen.getByText(/publishing to instagram feed…/i)).toBeInTheDocument();

    // Facebook Feed shows published with media id
    expect(screen.getByText(/published successfully/i)).toBeInTheDocument();
    expect(screen.getByText('(fb_123)')).toBeInTheDocument();

    // Facebook Story shows failed with error message
    expect(screen.getByText(/failed to publish/i)).toBeInTheDocument();
    expect(screen.getByText(/stories require page admin permissions/i)).toBeInTheDocument();

    // Retry button on failed destination
    const retryBtn = screen.getByRole('button', { name: /retry/i });
    expect(retryBtn).toBeInTheDocument();
    await userEvent.click(retryBtn);
    expect(onRetry).toHaveBeenCalledWith('facebook_story');
  });

  it('locks already published destinations against accidental duplicate posting', async () => {
    renderSWR(
      <PublishingDestinations
        destinations={{
          facebook_feed: true,
          facebook_story: false,
          instagram_feed: false,
          instagram_story: false,
        }}
        onChange={vi.fn()}
        statuses={{
          facebook_feed: { status: 'PUBLISHED', media_id: 'fb_999' },
        }}
      />
    );

    const publishedCheckbox = screen.getByRole('checkbox', { name: 'Facebook Feed' });
    expect(publishedCheckbox).toBeDisabled();
    expect(publishedCheckbox).toBeChecked();
  });
});
