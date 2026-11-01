import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PublishFlow } from './PublishFlow';
import { apiError, bodyOf, calls, CONNECTION, makeCampaign, mockApi, renderSWR, seq } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

const step = (name: string, status: string, meta_object_id: string | null = null) => ({
  name, status, meta_object_id, attempts: 1, last_error: null,
});
const running = { status: 'RUNNING', steps: [step('CAMPAIGN', 'DONE', '111'), step('ADSET', 'RUNNING')], error: null };
const done = {
  status: 'DONE',
  steps: [step('CAMPAIGN', 'DONE', '111'), step('ADSET', 'DONE', '222'), step('IMAGE', 'DONE', 'abc'), step('CREATIVE', 'DONE', '333'), step('AD', 'DONE', '444')],
  error: null,
};
const failed = {
  status: 'FAILED',
  steps: [step('CAMPAIGN', 'DONE', '111'), step('ADSET', 'FAILED')],
  error: { step: 'ADSET', message: 'Daily budget is below the Meta minimum', meta_code: 100 },
};

describe('PublishFlow', () => {
  it('confirms with account, Page, Instagram, budget, dates, text and image', async () => {
    const fetchMock = mockApi({
      'GET /v1/meta/connection': CONNECTION,
      'POST /v1/campaigns/c1/publish': { status: 'PUBLISHING' },
      'GET /v1/campaigns/c1/publish': seq(running, done),
    });
    const onFinished = vi.fn();
    renderSWR(<PublishFlow campaign={makeCampaign()} onClose={vi.fn()} onFinished={onFinished} />);
    const dialog = screen.getByRole('dialog', { name: /publish and start instagram ad/i });
    expect(await within(dialog).findByText(/Main Ad Account/)).toBeInTheDocument();
    for (const text of ['Synxa Page', '@synxait', '₹100/day', '2026-10-20 → 2026-10-22', 'Learn Python fast', 'Live classes for students.']) {
      expect(within(dialog).getByText(text)).toBeInTheDocument();
    }
    expect(within(dialog).getByAltText(/ad image/i)).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole('button', { name: /publish and start ad/i }));
    expect(bodyOf(fetchMock, 'POST /v1/campaigns/c1/publish')).toEqual({ confirm: true });

    expect(await screen.findByText(/111/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/444/)).toBeInTheDocument(), { timeout: 4000 });
    expect(screen.getAllByText('✓')).toHaveLength(5);
    expect(screen.getByText(/submitted and activated on meta/i)).toBeInTheDocument();
    expect(onFinished).toHaveBeenCalled();
  });

  it('posts nothing extra unless a post switch is on', async () => {
    const fetchMock = mockApi({
      'GET /v1/meta/connection': CONNECTION,
      'POST /v1/campaigns/c1/publish': { status: 'PUBLISHING' },
      'GET /v1/campaigns/c1/publish': seq(running, done),
    });
    renderSWR(<PublishFlow campaign={makeCampaign()} onClose={vi.fn()} onFinished={vi.fn()} />);
    for (const name of ['Facebook Feed', 'Facebook Story', 'Instagram Feed', 'Instagram Story']) {
      expect(screen.getByRole('checkbox', { name })).not.toBeChecked();
    }
    await userEvent.click(await screen.findByRole('button', { name: /publish and start ad/i }));
    await waitFor(() => expect(calls(fetchMock, 'POST /v1/campaigns/c1/publish')).toHaveLength(1));
    expect(calls(fetchMock, 'POST /v1/campaigns/c1/post')).toHaveLength(0);
  });

  it('posts to exactly the switched-on targets when publishing and shows what each did', async () => {
    const fetchMock = mockApi({
      'GET /v1/meta/connection': CONNECTION,
      'POST /v1/campaigns/c1/publish': { status: 'PUBLISHING' },
      'POST /v1/campaigns/c1/post': {
        results: {
          instagram_story: { status: 'PUBLISHED', media_id: 'm1' },
          facebook_feed: { status: 'FAILED', error: 'Facebook posting needs the pages_manage_posts permission.' },
        },
      },
      'GET /v1/campaigns/c1/publish': seq(running, done),
    });
    renderSWR(<PublishFlow campaign={makeCampaign()} onClose={vi.fn()} onFinished={vi.fn()} />);
    await userEvent.click(screen.getByRole('checkbox', { name: 'Instagram Story' }));
    await userEvent.click(screen.getByRole('checkbox', { name: 'Facebook Feed' }));
    await userEvent.click(await screen.findByRole('button', { name: /publish and start ad/i }));
    await waitFor(() => expect(calls(fetchMock, 'POST /v1/campaigns/c1/post')).toHaveLength(1));
    expect(bodyOf(fetchMock, 'POST /v1/campaigns/c1/post')).toEqual({ targets: ['instagram_story', 'facebook_feed'] });
    expect(await screen.findByText(/Instagram Story: posted/)).toBeInTheDocument();
    expect(screen.getByText(/Facebook Feed: Facebook posting needs the pages_manage_posts/)).toBeInTheDocument();
  });

  it('blocks publishing when Meta is not connected', async () => {
    mockApi({ 'GET /v1/meta/connection': { status: 'NOT_CONNECTED' } });
    renderSWR(<PublishFlow campaign={makeCampaign()} onClose={vi.fn()} onFinished={vi.fn()} />);
    const btn = await screen.findByRole('button', { name: /publish and start ad/i });
    await waitFor(() => expect(btn).toBeDisabled());
    expect(btn).toHaveAccessibleDescription(/connect meta first/i);
  });

  it('shows the failure with Resume and Discard', async () => {
    const fetchMock = mockApi({
      'GET /v1/meta/connection': CONNECTION,
      'GET /v1/campaigns/c1/publish': seq(failed, done),
      'POST /v1/campaigns/c1/publish/resume': { status: 'PUBLISHING' },
      'POST /v1/campaigns/c1/publish/discard': { status: 'DRAFT' },
    });
    const onFinished = vi.fn();
    renderSWR(
      <PublishFlow campaign={makeCampaign({ status: 'PUBLISH_FAILED' })} onClose={vi.fn()} onFinished={onFinished} />,
    );
    expect(await screen.findByText('Daily budget is below the Meta minimum')).toBeInTheDocument();
    expect(screen.getByText('✗')).toBeInTheDocument();
    expect(screen.getAllByText('○')).toHaveLength(3);

    await userEvent.click(screen.getByRole('button', { name: /^resume/i }));
    expect(calls(fetchMock, 'POST /v1/campaigns/c1/publish/resume')).toHaveLength(1);
    expect(await screen.findByText(/444/)).toBeInTheDocument();
  });

  it('discards a failed publish', async () => {
    const fetchMock = mockApi({
      'GET /v1/meta/connection': CONNECTION,
      'GET /v1/campaigns/c1/publish': failed,
      'POST /v1/campaigns/c1/publish/discard': { status: 'DRAFT' },
    });
    const onFinished = vi.fn();
    const onClose = vi.fn();
    renderSWR(<PublishFlow campaign={makeCampaign({ status: 'PUBLISH_FAILED' })} onClose={onClose} onFinished={onFinished} />);
    await userEvent.click(await screen.findByRole('button', { name: /discard/i }));
    await waitFor(() => expect(calls(fetchMock, 'POST /v1/campaigns/c1/publish/discard')).toHaveLength(1));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(onFinished).toHaveBeenCalled();
  });

  it('shows the publish error message from the backend', async () => {
    mockApi({
      'GET /v1/meta/connection': CONNECTION,
      'POST /v1/campaigns/c1/publish': apiError(409, 'Draft is incomplete', 'DRAFT_INCOMPLETE'),
    });
    renderSWR(<PublishFlow campaign={makeCampaign()} onClose={vi.fn()} onFinished={vi.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: /publish and start ad/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Draft is incomplete');
  });
  it('omits destination selector when showDestinationSelector is false', async () => {
    mockApi({
      'GET /v1/meta/connection': CONNECTION,
    });
    renderSWR(<PublishFlow campaign={makeCampaign()} showDestinationSelector={false} onClose={vi.fn()} onFinished={vi.fn()} />);
    const dialog = screen.getByRole('dialog', { name: /publish and start instagram ad/i });
    expect(await within(dialog).findByText(/Main Ad Account/)).toBeInTheDocument();
    expect(within(dialog).queryByText(/Publishing Destinations/i)).not.toBeInTheDocument();
  });
});
