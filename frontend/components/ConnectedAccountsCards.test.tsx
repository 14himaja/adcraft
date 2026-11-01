import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MetaConnectCard } from './MetaConnectCard';
import * as metaHooks from '../lib/meta';
import * as api from '../lib/api';

describe('Connected Accounts Settings Architecture', () => {
  const mockMutateConn = vi.fn();
  const mockMutateAssets = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders separate integration cards for Facebook Pages, Instagram, and Meta Ad Accounts', () => {
    vi.spyOn(metaHooks, 'useMetaConnection').mockReturnValue({
      connection: {
        status: 'ACTIVE',
        mode: 'real',
        expires_at: '2026-12-31T00:00:00Z',
        ad_account_id: 'act_101',
        ad_account_name: 'Alpha Growth Ads',
        currency: 'USD',
        page_id: 'page_202',
        page_name: 'Alpha Brand Page',
        instagram_user_id: 'ig_303',
        instagram_username: 'alphabrand',
      },
      isLoading: false,
      isError: false,
      error: undefined,
      mutate: mockMutateConn,
    });

    vi.spyOn(metaHooks, 'useMetaAssets').mockReturnValue({
      assets: {
        ad_accounts: [{ id: 'act_101', name: 'Alpha Growth Ads', currency: 'USD' }],
        pages: [{ id: 'page_202', name: 'Alpha Brand Page', instagram: { id: 'ig_303', username: 'alphabrand' } }],
        instagram_accounts: [
          { id: 'ig_303', username: 'alphabrand', page_id: 'page_202', page_name: 'Alpha Brand Page' },
        ],
      },
      isLoading: false,
      isError: false,
      error: undefined,
      mutate: mockMutateAssets,
    });

    render(<MetaConnectCard />);

    // 1. Facebook Pages Card
    expect(screen.getByRole('heading', { name: /Facebook Pages/i })).toBeInTheDocument();
    expect(screen.getAllByText(/Feed Posts/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Stories/i).length).toBeGreaterThan(0);

    // 2. Instagram Professional Accounts Card
    expect(screen.getByRole('heading', { name: /Instagram Professional Accounts/i })).toBeInTheDocument();
    expect(screen.getAllByText(/Feed Photos/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/DMs/i).length).toBeGreaterThan(0);

    // 3. Meta Ad Accounts Card (with optional note for organic posting)
    expect(screen.getByRole('heading', { name: /Meta Ad Accounts/i })).toBeInTheDocument();
    expect(screen.getByText(/Paid Campaigns Only/i)).toBeInTheDocument();
    expect(screen.getByText(/Optional for organic social media posting/i)).toBeInTheDocument();
  });

  it('allows disconnecting ad account independently while keeping organic social posting active', async () => {
    const user = userEvent.setup();
    const disconnectAdSpy = vi.spyOn(api, 'disconnectAdAccount').mockResolvedValueOnce({
      status: 'ACTIVE',
      page_id: 'page_202',
      instagram_username: 'alphabrand',
    });

    vi.spyOn(metaHooks, 'useMetaConnection').mockReturnValue({
      connection: {
        status: 'ACTIVE',
        mode: 'real',
        ad_account_id: 'act_101',
        ad_account_name: 'Alpha Ads',
        page_id: 'page_202',
        page_name: 'Alpha Page',
        instagram_username: 'alphabrand',
      },
      isLoading: false,
      isError: false,
      error: undefined,
      mutate: mockMutateConn,
    });

    vi.spyOn(metaHooks, 'useMetaAssets').mockReturnValue({
      assets: {
        ad_accounts: [{ id: 'act_101', name: 'Alpha Ads', currency: 'INR' }],
        pages: [{ id: 'page_202', name: 'Alpha Page', instagram: { id: 'ig_303', username: 'alphabrand' } }],
      },
      isLoading: false,
      isError: false,
      error: undefined,
      mutate: mockMutateAssets,
    });

    render(<MetaConnectCard />);

    const disconnectAdBtn = screen.getByRole('button', { name: /Disconnect Ad Account/i });
    expect(disconnectAdBtn).toBeInTheDocument();

    await user.click(disconnectAdBtn);

    await waitFor(() => {
      expect(disconnectAdSpy).toHaveBeenCalled();
      expect(mockMutateConn).toHaveBeenCalled();
    });
  });

  it('allows disconnecting Facebook Page independently', async () => {
    const user = userEvent.setup();
    const disconnectPageSpy = vi.spyOn(api, 'disconnectPage').mockResolvedValueOnce({
      status: 'ACTIVE',
      ad_account_id: 'act_101',
    });

    vi.spyOn(metaHooks, 'useMetaConnection').mockReturnValue({
      connection: {
        status: 'ACTIVE',
        mode: 'real',
        ad_account_id: 'act_101',
        page_id: 'page_202',
        page_name: 'Alpha Page',
      },
      isLoading: false,
      isError: false,
      error: undefined,
      mutate: mockMutateConn,
    });

    vi.spyOn(metaHooks, 'useMetaAssets').mockReturnValue({
      assets: {
        ad_accounts: [{ id: 'act_101', name: 'Alpha Ads', currency: 'INR' }],
        pages: [{ id: 'page_202', name: 'Alpha Page', instagram: null }],
      },
      isLoading: false,
      isError: false,
      error: undefined,
      mutate: mockMutateAssets,
    });

    render(<MetaConnectCard />);

    const disconnectPageBtn = screen.getByRole('button', { name: /Disconnect Page/i });
    expect(disconnectPageBtn).toBeInTheDocument();

    await user.click(disconnectPageBtn);

    await waitFor(() => {
      expect(disconnectPageSpy).toHaveBeenCalled();
      expect(mockMutateConn).toHaveBeenCalled();
    });
  });
});
