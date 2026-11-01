import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MetaConnectCard } from './MetaConnectCard';
import * as metaHooks from '../lib/meta';
import * as api from '../lib/api';

describe('MetaConnectCard', () => {
  const mockMutateConn = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders "Connect" button when not connected', () => {
    vi.spyOn(metaHooks, 'useMetaConnection').mockReturnValue({
      connection: { status: 'NOT_CONNECTED' },
      isLoading: false,
      isError: false,
      error: undefined,
      mutate: mockMutateConn,
    });
    vi.spyOn(metaHooks, 'useMetaAssets').mockReturnValue({
      assets: undefined,
      isLoading: false,
      isError: false,
      error: undefined,
      mutate: vi.fn(),
    });

    render(<MetaConnectCard />);

    expect(screen.getByTestId('not-connected-view')).toBeInTheDocument();
    expect(screen.getByTestId('btn-connect-meta')).toBeInTheDocument();
    expect(screen.getByText(/Connect with Facebook/i)).toBeInTheDocument();
  });

  it('renders assets and selection dropdowns when connected', () => {
    vi.spyOn(metaHooks, 'useMetaConnection').mockReturnValue({
      connection: {
        status: 'ACTIVE',
        mode: 'fake',
        expires_at: '2026-12-01T00:00:00Z',
        ad_account_id: 'act_123',
        ad_account_name: 'Main Ad Account',
        page_id: 'page_456',
        page_name: 'Test Brand Page',
        instagram_username: 'testbrand',
      },
      isLoading: false,
      isError: false,
      error: undefined,
      mutate: mockMutateConn,
    });
    vi.spyOn(metaHooks, 'useMetaAssets').mockReturnValue({
      assets: {
        ad_accounts: [{ id: 'act_123', name: 'Main Ad Account', currency: 'USD' }],
        pages: [{ id: 'page_456', name: 'Test Brand Page', instagram: { id: 'ig_789', username: 'testbrand' } }],
      },
      isLoading: false,
      isError: false,
      error: undefined,
      mutate: vi.fn(),
    });

    render(<MetaConnectCard />);

    expect(screen.getByTestId('connected-view')).toBeInTheDocument();
    expect(screen.getByTestId('select-ad-account')).toBeInTheDocument();
    expect(screen.getByTestId('select-page')).toBeInTheDocument();
    expect(screen.getByTestId('selected-ad-account-display')).toHaveTextContent('Main Ad Account');
    expect(screen.getByTestId('selected-ig-display')).toHaveTextContent('@testbrand');
  });

  it('submits asset selection and calls updateConnection', async () => {
    const user = userEvent.setup();
    const updateSpy = vi.spyOn(api, 'updateConnection').mockResolvedValueOnce({
      status: 'ACTIVE',
      ad_account_id: 'act_123',
      page_id: 'page_456',
    });

    vi.spyOn(metaHooks, 'useMetaConnection').mockReturnValue({
      connection: {
        status: 'ACTIVE',
        mode: 'fake',
        expires_at: '2026-12-01T00:00:00Z',
      },
      isLoading: false,
      isError: false,
      error: undefined,
      mutate: mockMutateConn,
    });
    vi.spyOn(metaHooks, 'useMetaAssets').mockReturnValue({
      assets: {
        ad_accounts: [{ id: 'act_123', name: 'Main Ad Account', currency: 'USD' }],
        pages: [{ id: 'page_456', name: 'Test Brand Page', instagram: { id: 'ig_789', username: 'testbrand' } }],
      },
      isLoading: false,
      isError: false,
      error: undefined,
      mutate: vi.fn(),
    });

    render(<MetaConnectCard />);

    // The card never picks an asset silently: nothing is saved until the user chooses.
    await user.selectOptions(screen.getByTestId('select-ad-account'), 'act_123');
    await user.selectOptions(screen.getByTestId('select-page'), 'page_456');
    const saveBtn = screen.getByTestId('btn-save-selection');
    await user.click(saveBtn);

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith({
        ad_account_id: 'act_123',
        page_id: 'page_456',
      });
      expect(mockMutateConn).toHaveBeenCalled();
      expect(screen.getByTestId('selection-success')).toBeInTheDocument();
    });
  });

  it('renders expired banner when status is EXPIRED', () => {
    vi.spyOn(metaHooks, 'useMetaConnection').mockReturnValue({
      connection: {
        status: 'EXPIRED',
        mode: 'fake',
        expires_at: '2026-09-01T00:00:00Z',
      },
      isLoading: false,
      isError: false,
      error: undefined,
      mutate: mockMutateConn,
    });
    vi.spyOn(metaHooks, 'useMetaAssets').mockReturnValue({
      assets: {
        ad_accounts: [],
        pages: [],
      },
      isLoading: false,
      isError: false,
      error: undefined,
      mutate: vi.fn(),
    });

    render(<MetaConnectCard />);

    expect(screen.getByTestId('expired-banner')).toBeInTheDocument();
    expect(screen.getByText(/Meta session expired/i)).toBeInTheDocument();
    expect(screen.getByTestId('btn-reconnect')).toBeInTheDocument();
  });

  it('defaults to the saved selection and saves a different choice', async () => {
    const user = userEvent.setup();
    const updateSpy = vi.spyOn(api, 'updateConnection').mockResolvedValueOnce({ status: 'ACTIVE' });
    vi.spyOn(metaHooks, 'useMetaConnection').mockReturnValue({
      connection: { status: 'ACTIVE', ad_account_id: 'act_2', page_id: 'page_2' },
      isLoading: false,
      isError: false,
      error: undefined,
      mutate: mockMutateConn,
    });
    vi.spyOn(metaHooks, 'useMetaAssets').mockReturnValue({
      assets: {
        ad_accounts: [{ id: 'act_1', name: 'One', currency: 'INR' }, { id: 'act_2', name: 'Two', currency: 'INR' }],
        pages: [
          { id: 'page_1', name: 'P1', instagram: { id: 'ig_1', username: 'p1' } },
          { id: 'page_2', name: 'P2', instagram: { id: 'ig_2', username: 'p2' } },
        ],
      },
      isLoading: false,
      isError: false,
      error: undefined,
      mutate: vi.fn(),
    });

    render(<MetaConnectCard />);
    expect(screen.getByTestId('select-ad-account')).toHaveValue('act_2');
    expect(screen.getByTestId('select-page')).toHaveValue('page_2');

    await user.selectOptions(screen.getByTestId('select-ad-account'), 'act_1');
    await user.click(screen.getByTestId('btn-save-selection'));
    await waitFor(() => expect(updateSpy).toHaveBeenCalledWith({ ad_account_id: 'act_1', page_id: 'page_2' }));
  });
});
