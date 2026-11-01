import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen } from '@testing-library/react';
import { CampaignPerformanceCard } from './CampaignPerformanceCard';
import { mockApi, renderSWR } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

const KEY = 'GET /v1/meta/insights?timeframe=7d';

describe('CampaignPerformanceCard', () => {
  it('shows real totals from Meta insights', async () => {
    mockApi({
      [KEY]: { impressions: 12345, reach: 6789, clicks: 321, spend: 1234.5, currency: 'INR', timeframe: '7d', status: 'ACTIVE' },
    });
    renderSWR(<CampaignPerformanceCard />);
    expect(await screen.findByText('12,345')).toBeInTheDocument();
    expect(screen.getByText('6,789')).toBeInTheDocument();
    expect(screen.getByText('321')).toBeInTheDocument();
    expect(screen.getByText('₹1,234.50')).toBeInTheDocument();
    expect(screen.queryByText(/no live campaigns yet/i)).not.toBeInTheDocument();
  });

  it('shows an empty state when nothing is spending', async () => {
    mockApi({
      [KEY]: { impressions: 0, reach: 0, clicks: 0, spend: 0, currency: 'INR', timeframe: '7d', status: 'NO_ACTIVE_SPEND' },
    });
    renderSWR(<CampaignPerformanceCard />);
    expect(await screen.findByText(/no live campaigns yet/i)).toBeInTheDocument();
  });
});
