import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MediaView, MediaPicker } from './MediaView';
import { apiError, calls, makeCampaign, mockApi, renderSWR } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

const MEDIA = [
  { id: 'm1', filename: 'cake.jpg', source: 'generated', prompt: 'cakes in a bakery window', created_at: '2026-10-10T10:00:00Z' },
  { id: 'm2', filename: 'shop.jpg', source: 'uploaded', prompt: null, created_at: '2026-10-11T10:00:00Z' },
];

describe('MediaView', () => {
  it('lists real media served from /api/v1/images', async () => {
    mockApi({ 'GET /v1/media': MEDIA, 'GET /v1/campaigns': [] });
    renderSWR(<MediaView />);
    const img = await screen.findByAltText('cake.jpg');
    expect(img.getAttribute('src')).toContain('/api/v1/images/m1');
    expect(screen.getByText('cakes in a bakery window')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /^uploaded$/i }));
    expect(screen.queryByAltText('cake.jpg')).not.toBeInTheDocument();
    expect(screen.getByAltText('shop.jpg')).toBeInTheDocument();
  });

  it('keeps upload disabled with an explanation until a draft is chosen, then uploads into it', async () => {
    const fetchMock = mockApi({
      'GET /v1/media': [],
      'GET /v1/campaigns': [makeCampaign({ id: 'd1', title: 'Bakery' }), makeCampaign({ id: 'a1', status: 'ACTIVE' })],
      'POST /v1/campaigns/d1/image': makeCampaign({ id: 'd1' }),
    });
    renderSWR(<MediaView />);
    expect(await screen.findByText(/no images yet/i)).toBeInTheDocument();
    const input = screen.getByLabelText(/upload image/i);
    expect(input).toBeDisabled();
    expect(screen.getByText(/uploads are attached to a draft campaign/i)).toBeInTheDocument();
    const select = screen.getByLabelText(/use in campaign/i);
    await waitFor(() => expect(screen.getByRole('option', { name: 'Bakery' })).toBeInTheDocument());
    expect(screen.queryAllByRole('option')).toHaveLength(2); // placeholder + the one DRAFT
    await userEvent.selectOptions(select, 'd1');
    const file = new File(['x'], 'p.png', { type: 'image/png' });
    await userEvent.upload(input, file);
    await waitFor(() => expect(calls(fetchMock, 'POST /v1/campaigns/d1/image')).toHaveLength(1));
  });

  it('shows the upload rejection message', async () => {
    mockApi({
      'GET /v1/media': [],
      'GET /v1/campaigns': [makeCampaign({ id: 'd1', title: 'Bakery' })],
      'POST /v1/campaigns/d1/image': apiError(422, 'Image is 9:16; use 1:1 or 4:5'),
    });
    renderSWR(<MediaView />);
    await waitFor(() => expect(screen.getByRole('option', { name: 'Bakery' })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText(/use in campaign/i), 'd1');
    await userEvent.upload(screen.getByLabelText(/upload image/i), new File(['x'], 'p.png', { type: 'image/png' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Image is 9:16; use 1:1 or 4:5');
  });
});

describe('MediaPicker', () => {
  it('returns the chosen media item', async () => {
    mockApi({ 'GET /v1/media': MEDIA });
    const onPick = vi.fn();
    renderSWR(<MediaPicker onPick={onPick} onClose={vi.fn()} />);
    expect(screen.getByRole('dialog', { name: /media library/i })).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: /use shop\.jpg/i }));
    expect(onPick).toHaveBeenCalledWith('m2');
  });
});
