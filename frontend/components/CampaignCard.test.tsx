import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CampaignCard } from './CampaignCard';
import type { Campaign } from '../lib/api';
import { apiError, bodyOf, calls, makeCampaign, mockApi, renderSWR } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

const card = (over: Partial<Campaign>, props: { onEdit?: () => void; onChanged?: () => void } = {}) =>
  renderSWR(<CampaignCard campaign={makeCampaign(over)} onEdit={props.onEdit ?? vi.fn()} onChanged={props.onChanged ?? vi.fn()} />);

const btn = (name: RegExp) => screen.queryByRole('button', { name });

describe('CampaignCard', () => {
  it.each([
    ['DRAFT', 'Draft', ['Edit', 'Publish']],
    ['PUBLISHING', 'Publishing', ['View progress']],
    ['PUBLISH_FAILED', 'Publish failed', ['View progress']],
    ['PAUSED_ON_META', 'Paused on Meta', ['Activate']],
    ['ACTIVE', 'Active', ['Pause']],
    ['PAUSED', 'Paused', ['Resume']],
    ['COMPLETED', 'Completed', []],
  ] as const)('%s shows its badge and actions', (status, label, actions) => {
    card({ status, can_activate: true });
    expect(screen.getByText(label, { selector: '[data-testid="status-badge"]' })).toBeInTheDocument();
    for (const name of ['Edit', 'Publish', 'View progress', 'Activate', 'Pause', 'Resume']) {
      const present = (actions as readonly string[]).includes(name);
      expect(Boolean(btn(new RegExp(`^${name}$`, 'i')))).toBe(present);
    }
    expect(btn(/^delete$/i)).toBeInTheDocument();
  });

  it('shows what Meta reports and lets the agent fix it, listing what is left for the user', async () => {
    const fetchMock = mockApi({
      'POST /v1/campaigns/c1/fix': { fixed: ['Changed the button to Learn More on the ad.'], manual: ['Add a profile photo.'] },
    });
    card({ status: 'ACTIVE', meta: { issues: ['Web feed CTA not supported'] } });
    expect(screen.getByText('Web feed CTA not supported')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /fix with ai/i }));
    await waitFor(() => expect(calls(fetchMock, 'POST /v1/campaigns/c1/fix')).toHaveLength(1));
    expect(await screen.findByText(/Fixed: Changed the button to Learn More/)).toBeInTheDocument();
    expect(screen.getByText(/You need to do this: Add a profile photo/)).toBeInTheDocument();
  });

  it('posts the ad as a normal post to only the target you press, and asks before repeating one', async () => {
    const fetchMock = mockApi({
      'POST /v1/campaigns/c1/post': { results: { instagram_feed: { status: 'PUBLISHED', media_id: 'm1' } } },
    });
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    card({ status: 'ACTIVE', image_url: '/img.jpg', posted: { instagram_story: { media_id: 'x', at: '2026-10-26' } } });
    await userEvent.click(screen.getByRole('button', { name: 'Instagram Feed' }));
    await waitFor(() => expect(calls(fetchMock, 'POST /v1/campaigns/c1/post')).toHaveLength(1));
    expect(bodyOf(fetchMock, 'POST /v1/campaigns/c1/post')).toEqual({ targets: ['instagram_feed'] });
    expect(await screen.findByText(/Instagram Feed: posted/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /✓ Instagram Story/ })); // already posted: asks first
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(calls(fetchMock, 'POST /v1/campaigns/c1/post')).toHaveLength(1); // declined, so nothing was sent
    expect(screen.getAllByRole('button', { name: /Facebook (Feed|Story)|Instagram (Feed|Story)/ })).toHaveLength(4);
  });

  it('shows no post buttons for a draft', () => {
    card({ status: 'DRAFT', image_url: '/img.jpg' });
    expect(screen.queryByRole('button', { name: 'Instagram Feed' })).not.toBeInTheDocument();
  });

  it('disables Activate with a tooltip when real spend is off', () => {
    card({ status: 'PAUSED_ON_META', can_activate: false });
    const activate = btn(/^activate$/i)!;
    expect(activate).toBeDisabled();
    expect(activate).toHaveAttribute('title', 'Real spend is off (SAFE_MODE_NO_SPEND / ALLOW_REAL_AD_SPEND)');
  });

  it('disables Publish with the reason when the draft is incomplete', () => {
    card({ status: 'DRAFT', can_publish: false, missing_fields: ['landing_url'] });
    expect(btn(/^publish$/i)).toBeDisabled();
    expect(btn(/^publish$/i)).toHaveAccessibleDescription(/landing url/i);
  });

  it('activates only after the spend checkbox is ticked', async () => {
    const onChanged = vi.fn();
    const fetchMock = mockApi({ 'POST /v1/campaigns/c1/activate': makeCampaign({ status: 'ACTIVE' }) });
    card({ status: 'PAUSED_ON_META', can_activate: true }, { onChanged });
    await userEvent.click(btn(/^activate$/i)!);
    const dialog = screen.getByRole('dialog', { name: /activate campaign/i });
    expect(dialog).toHaveTextContent('₹100/day');
    const confirm = within(dialog).getByRole('button', { name: /activate and spend/i });
    expect(confirm).toBeDisabled();
    await userEvent.click(within(dialog).getByLabelText(/i understand this spends money/i));
    await userEvent.click(confirm);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(bodyOf(fetchMock, 'POST /v1/campaigns/c1/activate')).toEqual({ confirm: true });
  });

  it.each([
    ['ACTIVE', /^pause$/i, 'POST /v1/campaigns/c1/pause'],
    ['PAUSED', /^resume$/i, 'POST /v1/campaigns/c1/resume'],
  ] as const)('%s → %s', async (status, name, route) => {
    const onChanged = vi.fn();
    const fetchMock = mockApi({ [route]: makeCampaign() });
    card({ status, can_activate: true }, { onChanged });
    await userEvent.click(btn(name)!);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(calls(fetchMock, route)).toHaveLength(1);
  });

  it('deletes after confirming and explains Meta deletion', async () => {
    const onChanged = vi.fn();
    const fetchMock = mockApi({ 'DELETE /v1/campaigns/c1': { status: 'DELETED' } });
    card({ status: 'PAUSED_ON_META' }, { onChanged });
    await userEvent.click(btn(/^delete$/i)!);
    const dialog = screen.getByRole('dialog', { name: /delete campaign/i });
    expect(dialog).toHaveTextContent(/deleted on meta/i);
    await userEvent.click(within(dialog).getByRole('button', { name: /delete permanently/i }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(calls(fetchMock, 'DELETE /v1/campaigns/c1')).toHaveLength(1);
  });

  it('calls onEdit for drafts', async () => {
    const onEdit = vi.fn();
    card({ status: 'DRAFT' }, { onEdit });
    await userEvent.click(btn(/^edit$/i)!);
    expect(onEdit).toHaveBeenCalledWith('c1', expect.objectContaining({ id: 'c1' }));
  });

  it('shows insights and refreshes them', async () => {
    const onChanged = vi.fn();
    const fetchMock = mockApi({
      'POST /v1/campaigns/c1/insights/refresh': { impressions: 2000, reach: 1500, clicks: 40, spend_minor: 9950, ctr: 2 },
    });
    card(
      { status: 'ACTIVE', insights: { impressions: 1000, reach: 800, clicks: 25, spend_minor: 4550, ctr: 2.5, cpc_minor: 182, updated_at: '2026-10-14T10:00:00Z' } },
      { onChanged },
    );
    expect(screen.getByText('1,000')).toBeInTheDocument();
    expect(screen.getByText('800')).toBeInTheDocument();
    expect(screen.getByText('25')).toBeInTheDocument();
    expect(screen.getByText('2.50%')).toBeInTheDocument();
    expect(screen.getByText('₹45.50')).toBeInTheDocument();
    await userEvent.click(btn(/refresh insights/i)!);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(calls(fetchMock, 'POST /v1/campaigns/c1/insights/refresh')).toHaveLength(1);
  });

  it('shows the error message when an action fails', async () => {
    mockApi({ 'POST /v1/campaigns/c1/insights/refresh': apiError(429, 'Refresh at most once every 5 minutes') });
    card({ status: 'ACTIVE' });
    await userEvent.click(btn(/refresh insights/i)!);
    expect(await screen.findByRole('alert')).toHaveTextContent('Refresh at most once every 5 minutes');
  });
});
