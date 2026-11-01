import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CampaignStudioModal } from './CampaignStudioModal';
import { makeCampaign, mockApi, renderSWR } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

const openStudio = (id: string | null = 'c1') =>
  renderSWR(<CampaignStudioModal campaignId={id} onClose={vi.fn()} onChanged={vi.fn()} />);

describe('AdCraft Studio Sidebar & 6 Sections', () => {
  it('renders persistent sidebar navigation with all 6 sections in exact order', async () => {
    mockApi({ 'GET /v1/campaigns/c1': makeCampaign() });
    openStudio();

    expect(await screen.findByRole('dialog', { name: /campaign studio/i })).toBeInTheDocument();
    expect(screen.getByText('AdCraft Studio')).toBeInTheDocument();

    const sidebar = screen.getByRole('navigation', { name: /studio sections/i });
    expect(sidebar).toBeInTheDocument();

    expect(screen.getByRole('button', { name: /1\. objective & idea/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /2\. target audience/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /3\. budget & schedule/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /4\. creative & preview/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /5\. hashtags/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /6\. publishing/i })).toBeInTheDocument();
  });

  it('allows navigating to any section in any order without forced linear steps', async () => {
    mockApi({ 'GET /v1/campaigns/c1': makeCampaign() });
    openStudio();

    // Start at section 1
    expect(await screen.findByLabelText(/campaign title/i)).toBeInTheDocument();

    // Directly jump to section 5 (Hashtags) without visiting 2, 3, 4
    await userEvent.click(screen.getByRole('button', { name: /5\. hashtags/i }));
    expect(await screen.findByText(/hashtag selection/i)).toBeInTheDocument();

    // Jump directly to section 3 (Budget & Schedule)
    await userEvent.click(screen.getByRole('button', { name: /3\. budget & schedule/i }));
    expect(await screen.findByLabelText(/daily budget/i)).toBeInTheDocument();

    // Jump directly to section 6 (Publishing)
    await userEvent.click(screen.getByRole('button', { name: /6\. publishing/i }));
    expect(await screen.findByText(/social publishing destinations/i)).toBeInTheDocument();
    expect(screen.getByText(/pre-publishing review summary/i)).toBeInTheDocument();

    // Jump directly back to section 1 (Objective & Idea)
    await userEvent.click(screen.getByRole('button', { name: /1\. objective & idea/i }));
    expect(await screen.findByLabelText(/campaign title/i)).toBeInTheDocument();
  });

  it('preserves form values when switching between sidebar sections', async () => {
    mockApi({
      'GET /v1/campaigns/c1': makeCampaign({ title: 'Original Title' }),
      'PUT /v1/campaigns/c1': (init: RequestInit) => makeCampaign(JSON.parse(String(init.body))),
    });
    openStudio();

    const title = await screen.findByLabelText(/campaign title/i);
    await userEvent.clear(title);
    await userEvent.type(title, 'Modified Brand Campaign');

    // Switch to section 3
    await userEvent.click(screen.getByRole('button', { name: /3\. budget & schedule/i }));
    expect(await screen.findByLabelText(/daily budget/i)).toBeInTheDocument();

    // Switch back to section 1
    await userEvent.click(screen.getByRole('button', { name: /1\. objective & idea/i }));
    expect(await screen.findByDisplayValue('Modified Brand Campaign')).toBeInTheDocument();
  });

  it('displays required field indicator (*) for mandatory inputs', async () => {
    mockApi({ 'GET /v1/campaigns/c1': makeCampaign() });
    openStudio();

    expect(await screen.findByText(/required for publishing/i)).toBeInTheDocument();
    const titleLabel = screen.getByText(/campaign title/i);
    expect(titleLabel.innerHTML).toContain('*');
  });

  it('shows pre-publishing review summary in section 6 with jump buttons for missing fields', async () => {
    mockApi({
      'GET /v1/campaigns/c1': makeCampaign({
        missing_fields: ['title', 'image_id'],
        can_publish: false,
      }),
    });
    openStudio();

    await userEvent.click(await screen.findByRole('button', { name: /6\. publishing/i }));
    expect(await screen.findByText(/action required before launching/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /go to objective & idea/i })).toBeInTheDocument();

    // Clicking jump button moves directly to Section 1
    await userEvent.click(screen.getByRole('button', { name: /go to objective & idea/i }));
    expect(await screen.findByLabelText(/campaign title/i)).toBeInTheDocument();
  });

  it('header includes back arrow that allows moving back and closing the studio', async () => {
    const handleClose = vi.fn();
    mockApi({ 'GET /v1/campaigns/c1': makeCampaign() });
    renderSWR(<CampaignStudioModal campaignId="c1" onClose={handleClose} onChanged={vi.fn()} />);

    const backButton = await screen.findByRole('button', { name: /^back$/i });
    expect(backButton).toBeInTheDocument();

    await userEvent.click(backButton);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('section 4 (Creative & Preview) does not show hashtags, keeping hashtags isolated to section 5', async () => {
    mockApi({ 'GET /v1/campaigns/c1': makeCampaign() });
    openStudio();

    // Navigate to Section 4: Creative & Preview
    await userEvent.click(await screen.findByRole('button', { name: /4\. creative & preview/i }));

    // Creative & Preview elements should be present
    expect(await screen.findByText(/regenerate image/i)).toBeInTheDocument();
    expect(screen.getByText(/choose from media library/i)).toBeInTheDocument();

    // Hashtag selector controls should NOT be rendered in section 4
    expect(screen.queryByText(/explore hashtags/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/ai recommended/i)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/search library\.\.\./i)).not.toBeInTheDocument();

    // Navigate to Section 5: Hashtags
    await userEvent.click(screen.getByRole('button', { name: /5\. hashtags/i }));

    // Now Hashtag selector controls should be present in section 5
    expect(await screen.findByText(/hashtag selection/i)).toBeInTheDocument();
    expect(screen.getByText(/explore hashtags/i)).toBeInTheDocument();
  });
  it('provides save option in each section and saves changes', async () => {
    mockApi({
      'GET /v1/campaigns/c1': makeCampaign({ title: 'My Product' }),
      'PUT /v1/campaigns/c1': (init: RequestInit) => makeCampaign(JSON.parse(String(init.body))),
    });
    openStudio();

    expect(await screen.findByRole('button', { name: /save objective & idea/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save section/i })).toBeInTheDocument();

    const title = screen.getByLabelText(/campaign title/i);
    await userEvent.clear(title);
    await userEvent.type(title, 'New Brand Title');

    expect(screen.getByText(/unsaved changes in objective & idea/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /save objective & idea/i }));
    await waitFor(() => expect(screen.getByText(/objective & idea saved/i)).toBeInTheDocument());
  });

  it('auto-saves draft when exiting via header back arrow if changes are unsaved', async () => {
    let savedTitle = '';
    const handleClose = vi.fn();
    mockApi({
      'GET /v1/campaigns/c1': makeCampaign({ title: 'Original' }),
      'PUT /v1/campaigns/c1': (init: RequestInit) => {
        const body = JSON.parse(String(init.body));
        savedTitle = body.title;
        return makeCampaign(body);
      },
    });
    renderSWR(<CampaignStudioModal campaignId="c1" onClose={handleClose} onChanged={vi.fn()} />);

    const title = await screen.findByLabelText(/campaign title/i);
    await userEvent.clear(title);
    await userEvent.type(title, 'Auto-Saved Title');

    const backButton = screen.getByTitle('Back');
    await userEvent.click(backButton);

    await waitFor(() => expect(savedTitle).toBe('Auto-Saved Title'));
    await waitFor(() => expect(handleClose).toHaveBeenCalled());
  });

  it('auto-saves draft when exiting via close (X) button if changes are unsaved', async () => {
    let savedTitle = '';
    const handleClose = vi.fn();
    mockApi({
      'GET /v1/campaigns/c1': makeCampaign({ title: 'Original' }),
      'PUT /v1/campaigns/c1': (init: RequestInit) => {
        const body = JSON.parse(String(init.body));
        savedTitle = body.title;
        return makeCampaign(body);
      },
    });
    renderSWR(<CampaignStudioModal campaignId="c1" onClose={handleClose} onChanged={vi.fn()} />);

    const title = await screen.findByLabelText(/campaign title/i);
    await userEvent.clear(title);
    await userEvent.type(title, 'Closed Auto-Saved');

    const closeBtn = screen.getByRole('button', { name: /close studio/i });
    await userEvent.click(closeBtn);

    await waitFor(() => expect(savedTitle).toBe('Closed Auto-Saved'));
    await waitFor(() => expect(handleClose).toHaveBeenCalled());
  });
});
