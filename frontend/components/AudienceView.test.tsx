import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AudienceView } from './AudienceView';
import { mockApi } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

describe('AudienceView', () => {
  it('starts empty (no demo cities, interests or reach numbers) and applies the chosen country code', async () => {
    const onApply = vi.fn();
    render(<AudienceView onApplyToCampaign={onApply} />);
    expect(screen.queryByText('Bengaluru')).not.toBeInTheDocument();
    expect(screen.getAllByText('0 selected').length).toBeGreaterThan(0);
    expect(screen.queryByText(/\dM – \d/)).not.toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText(/target country/i), 'US');
    await userEvent.click(screen.getByRole('button', { name: /apply to new campaign/i }));
    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ country: 'US', cities: [], interests: [] }));
  });

  it('clears interest results when the search is emptied', async () => {
    mockApi({ 'GET /v1/meta/interests?q=py': [{ id: '1', name: 'Python', audience_size_lower: 1000000 }] });
    render(<AudienceView />);
    const box = screen.getByPlaceholderText(/search meta interests/i);
    await userEvent.type(box, 'py');
    expect(await screen.findByText('Python')).toBeInTheDocument();
    await userEvent.clear(box);
    expect(screen.queryByText('Python')).not.toBeInTheDocument();
  });
});
