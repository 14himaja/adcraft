import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AIAssistantCard } from './AIAssistantCard';
import { apiError, bodyOf, makeCampaign, mockApi } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

describe('AIAssistantCard', () => {
  it('fills the idea from an example chip and posts it to /campaigns/draft', async () => {
    let resolve!: (v: unknown) => void;
    const fetchMock = mockApi({ 'POST /v1/campaigns/draft': () => new Promise((r) => (resolve = r)) });
    const onDraftReady = vi.fn();
    render(<AIAssistantCard onDraftReady={onDraftReady} onStartFromScratch={vi.fn()} />);

    const generate = screen.getByRole('button', { name: /generate ad/i });
    expect(generate).toBeDisabled();

    await userEvent.click(screen.getByRole('button', { name: /hyderabad bakery/i }));
    const box = screen.getByLabelText(/describe your ad idea/i) as HTMLTextAreaElement;
    expect(box.value).toMatch(/Hyderabad/);

    await userEvent.click(generate);
    expect(screen.getByText(/writing your ad and creating the image/i)).toBeInTheDocument();
    expect(bodyOf(fetchMock, 'POST /v1/campaigns/draft')).toEqual({ idea: box.value });

    const draft = makeCampaign({ id: 'new1' });
    resolve(new Response(JSON.stringify(draft), { status: 200 }));
    await waitFor(() => expect(onDraftReady).toHaveBeenCalledWith(draft));
  });

  it('shows the backend error message', async () => {
    mockApi({ 'POST /v1/campaigns/draft': apiError(503, 'The AI is busy, try again') });
    render(<AIAssistantCard onDraftReady={vi.fn()} onStartFromScratch={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(/describe your ad idea/i), 'Ads for my phone repair shop');
    await userEvent.click(screen.getByRole('button', { name: /generate ad/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The AI is busy, try again');
  });

  it('offers manual creation', async () => {
    const onStart = vi.fn();
    render(<AIAssistantCard onDraftReady={vi.fn()} onStartFromScratch={onStart} />);
    await userEvent.click(screen.getByRole('button', { name: /start from scratch/i }));
    expect(onStart).toHaveBeenCalled();
  });
});
