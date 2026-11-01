import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { InsightsView } from './InsightsView';
import { CONNECTION, makeCampaign, mockApi, renderSWR } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

const TOTALS = { reach: 2300, impressions: 5100, clicks: 77, spend: 123.5, currency: 'INR', timeframe: '7d', status: 'ACTIVE' };

describe('InsightsView', () => {
  it('shows account totals and per-campaign numbers', async () => {
    mockApi({
      'GET /v1/meta/connection': CONNECTION,
      'GET /v1/meta/insights?timeframe=7d': TOTALS,
      'GET /v1/campaigns': [
        makeCampaign({ title: 'Bakery', status: 'ACTIVE', insights: { impressions: 5100, reach: 2300, clicks: 77, spend_minor: 12350, ctr: 1.51, cpc_minor: 160, updated_at: '2026-10-14T10:00:00Z' } }),
        makeCampaign({ id: 'c2', title: 'Draft only', status: 'DRAFT' }),
      ],
    });
    renderSWR(<InsightsView />);
    await waitFor(() => expect(screen.getAllByText('₹123.50')).toHaveLength(2)); // account total + campaign row
    expect(screen.getAllByText('2,300').length).toBeGreaterThan(0);
    expect(screen.getAllByText('5,100').length).toBeGreaterThan(0);
    expect(await screen.findByRole('cell', { name: 'Bakery' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '1.51%' })).toBeInTheDocument();
    expect(screen.queryByRole('cell', { name: 'Draft only' })).not.toBeInTheDocument();
    expect(screen.getByText(/Main Ad Account/)).toBeInTheDocument();
    expect(screen.queryByText(/test meta connection/i)).not.toBeInTheDocument();
  });

  it('shows an empty state when nothing has been published', async () => {
    mockApi({
      'GET /v1/meta/connection': CONNECTION,
      'GET /v1/meta/insights?timeframe=7d': { ...TOTALS, reach: 0, impressions: 0, clicks: 0, spend: 0, status: 'NO_ACTIVE_SPEND' },
      'GET /v1/campaigns': [makeCampaign()],
    });
    renderSWR(<InsightsView />);
    expect(await screen.findByText(/no published campaigns yet/i)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
});
