import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatStudio } from './ChatStudio';
import { apiError, bodyOf, makeCampaign, mockApi, renderSWR } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

const open = (campaign = makeCampaign()) =>
  renderSWR(<ChatStudio campaign={campaign} onClose={vi.fn()} onChanged={vi.fn()} onAdvanced={vi.fn()} />);

describe('ChatStudio', () => {
  it('turns the first message into a draft and shows tappable options', async () => {
    const fetchMock = mockApi({ 'POST /v1/campaigns/draft': makeCampaign() });
    renderSWR(<ChatStudio campaign={null} onClose={vi.fn()} onChanged={vi.fn()} onAdvanced={vi.fn()} />);
    await userEvent.type(screen.getByLabelText('Message'), 'Tiffins 50% off in Hyderabad{Enter}');
    expect(await screen.findByRole('group', { name: 'Daily budget' })).toBeInTheDocument();
    expect(bodyOf(fetchMock, 'POST /v1/campaigns/draft')).toEqual({ idea: 'Tiffins 50% off in Hyderabad' });
    expect(screen.getByText('Tiffins 50% off in Hyderabad')).toBeInTheDocument();
  });

  it('saves a tapped option straight away', async () => {
    const fetchMock = mockApi({ 'PUT /v1/campaigns/c1': makeCampaign({ daily_budget: 200 }) });
    open();
    await userEvent.click(within(screen.getByRole('group', { name: 'Daily budget' })).getByRole('button', { name: '₹200/day' }));
    expect(bodyOf(fetchMock, 'PUT /v1/campaigns/c1')).toEqual({ daily_budget: 200 });
    expect(await screen.findByRole('button', { name: '₹200/day', pressed: true })).toBeInTheDocument();
  });

  it('sends follow-up messages to the chat endpoint and shows the reply', async () => {
    const fetchMock = mockApi({
      'POST /v1/campaigns/c1/chat': {
        campaign: makeCampaign({ audience: { ...makeCampaign().audience, cities: [] } }),
        reply: 'Removed Bangalore.',
        warnings: ['Connect your Meta account to add cities or interests'],
      },
    });
    open();
    expect(screen.getByRole('button', { name: 'Remove city Bangalore' })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Message'), 'drop Bangalore{Enter}');
    expect(await screen.findByText('Removed Bangalore.')).toBeInTheDocument();
    expect(screen.getByText('Connect your Meta account to add cities or interests')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Remove city Bangalore' })).not.toBeInTheDocument();
    expect(bodyOf(fetchMock, 'POST /v1/campaigns/c1/chat')).toEqual({ message: 'drop Bangalore' });
  });

  it('New image asks the AI for a fresh concept instead of re-rendering the same brief', async () => {
    const fetchMock = mockApi({
      'POST /v1/campaigns/c1/chat': { campaign: makeCampaign({ image_id: 'img2' }), reply: 'Done: new image.', warnings: [] },
    });
    open();
    await userEvent.click(screen.getByRole('button', { name: /new image/i }));
    expect(await screen.findByText('Done: new image.')).toBeInTheDocument();
    expect(bodyOf(fetchMock, 'POST /v1/campaigns/c1/chat').message).toMatch(/completely different concept/);
  });

  it('shows backend errors and keeps the draft', async () => {
    mockApi({ 'POST /v1/campaigns/c1/chat': apiError(503, 'The AI is busy, try again') });
    open();
    await userEvent.type(screen.getByLabelText('Message'), 'cheaper{Enter}');
    expect(await screen.findByRole('alert')).toHaveTextContent('The AI is busy, try again');
    expect(screen.getByRole('group', { name: 'Daily budget' })).toBeInTheDocument();
  });

  it('shows the saved conversation when a draft is reopened', () => {
    mockApi({});
    open(makeCampaign({
      chat: [
        { role: 'user', text: 'Promote my Python course' },
        { role: 'user', text: 'make it cheaper' },
        { role: 'assistant', text: 'Done: budget ₹50/day.' },
      ],
    }));
    expect(screen.getByText('make it cheaper')).toBeInTheDocument();
    expect(screen.getByText('Done: budget ₹50/day.')).toBeInTheDocument();
  });

  it('lets the advertiser confirm an ad is not a special category', async () => {
    const fetchMock = mockApi({ 'PUT /v1/campaigns/c1': makeCampaign({ special_category_reason: null, not_special_category: true }) });
    open(makeCampaign({ can_publish: false, special_category_reason: "mentions 'hiring'" }));
    await userEvent.click(screen.getByRole('button', { name: /not a job, housing, credit or political ad/i }));
    expect(bodyOf(fetchMock, 'PUT /v1/campaigns/c1')).toEqual({ not_special_category: true });
    expect(await screen.findByRole('button', { name: /publish and start instagram ad/i })).toBeEnabled();
  });

  it('blocks publishing until required fields are filled', () => {
    mockApi({});
    open(makeCampaign({ can_publish: false, missing_fields: ['landing_url'] }));
    expect(screen.getByRole('button', { name: /publish and start instagram ad/i })).toBeDisabled();
    expect(screen.getByText(/still needed: landing url/i)).toBeInTheDocument();
  });
});
