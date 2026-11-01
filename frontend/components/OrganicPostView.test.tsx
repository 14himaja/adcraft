import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { OrganicPostView } from './OrganicPostView';
import { apiError, bodyOf, calls, mockApi, renderSWR } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

const MEDIA = [
  { id: 'm1', filename: 'cake.jpg', source: 'generated', prompt: 'cake', created_at: '2026-10-10T10:00:00Z' },
  { id: 'm2', filename: 'shop.jpg', source: 'uploaded', prompt: null, created_at: '2026-10-11T10:00:00Z' },
];
const ACCOUNTS = {
  default: 'ig_1',
  accounts: [
    { instagram_user_id: 'ig_1', username: 'main_brand', page_id: 'p1', page_name: 'Main Page' },
    { instagram_user_id: 'ig_2', username: 'client_brand', page_id: 'p2', page_name: 'Client Page' },
  ],
  unavailable: [{ page_id: 'p3', page_name: 'Old Page', reason: 'No Instagram professional account is linked' }],
};
const POST = {
  id: 'p1',
  image_id: 'm1',
  caption: 'Fresh bake!',
  status: 'PUBLISHED',
  media_id: 'fake_media_1',
  error: null,
  ig_user_id: 'ig_1',
  created_at: '2026-10-18T10:00:00Z',
};
const base = { 'GET /v1/organic/accounts': ACCOUNTS, 'GET /v1/media': MEDIA, 'GET /v1/organic/posts': [] };

describe('OrganicPostView', () => {
  it('states what the account needs and why a Page cannot be used', async () => {
    mockApi(base);
    renderSWR(<OrganicPostView />);
    expect(await screen.findByText(/business or creator account/i)).toBeInTheDocument();
    expect(screen.getByText(/linked to a facebook page/i)).toBeInTheDocument();
    expect(await screen.findByText(/old page: no instagram professional account is linked/i)).toBeInTheDocument();
  });

  it('keeps posting disabled until a picture is chosen, then posts to the default account after confirming', async () => {
    const fetchMock = mockApi({ ...base, 'POST /v1/organic/posts': POST });
    renderSWR(<OrganicPostView />);
    const post = await screen.findByRole('button', { name: /^post to instagram$/i });
    expect(post).toBeDisabled();
    await userEvent.click(await screen.findByRole('button', { name: /use cake\.jpg/i }));
    await userEvent.type(screen.getByLabelText(/caption/i), 'Fresh bake!');
    await userEvent.click(post);
    expect(calls(fetchMock, 'POST /v1/organic/posts')).toHaveLength(0); // nothing is published before confirming
    await userEvent.click(await screen.findByRole('button', { name: /post now/i }));
    expect(await screen.findByText('Posted to @main_brand.')).toBeInTheDocument();
    expect(bodyOf(fetchMock, 'POST /v1/organic/posts')).toEqual({
      image_id: 'm1',
      caption: 'Fresh bake!',
      instagram_user_id: 'ig_1',
    });
  });

  it('posts to another account when it is chosen', async () => {
    const fetchMock = mockApi({ ...base, 'POST /v1/organic/posts': { ...POST, ig_user_id: 'ig_2' } });
    renderSWR(<OrganicPostView />);
    await userEvent.selectOptions(await screen.findByLabelText(/post as/i), 'ig_2');
    await userEvent.click(await screen.findByRole('button', { name: /use cake\.jpg/i }));
    await userEvent.click(screen.getByRole('button', { name: /^post to instagram$/i }));
    expect(await screen.findByText(/publicly on @client_brand/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /post now/i }));
    await waitFor(() => expect(calls(fetchMock, 'POST /v1/organic/posts')).toHaveLength(1));
    expect(bodyOf(fetchMock, 'POST /v1/organic/posts').instagram_user_id).toBe('ig_2');
  });

  it('generates a picture with AI and selects it', async () => {
    const fetchMock = mockApi({
      ...base,
      'POST /v1/organic/images/generate': { id: 'm3', filename: 'post.jpg', source: 'generated', prompt: 'a cake', created_at: '2026-10-18T10:00:00Z' },
    });
    renderSWR(<OrganicPostView />);
    await userEvent.type(await screen.findByLabelText(/generate a picture with ai/i), 'A cake on a table');
    await userEvent.click(screen.getByRole('button', { name: /^generate$/i }));
    await waitFor(() => expect(calls(fetchMock, 'POST /v1/organic/images/generate')).toHaveLength(1));
    expect(bodyOf(fetchMock, 'POST /v1/organic/images/generate')).toEqual({ prompt: 'A cake on a table' });
    await waitFor(() => expect(screen.getByRole('button', { name: /^post to instagram$/i })).toBeEnabled());
  });

  it('uploads a picture', async () => {
    const fetchMock = mockApi({
      ...base,
      'GET /v1/media': [],
      'POST /v1/organic/images': { id: 'm9', filename: 'p.png', source: 'uploaded', prompt: null, created_at: '2026-10-18T10:00:00Z' },
    });
    renderSWR(<OrganicPostView />);
    await userEvent.upload(await screen.findByLabelText(/upload image/i), new File(['x'], 'p.png', { type: 'image/png' }));
    await waitFor(() => expect(calls(fetchMock, 'POST /v1/organic/images')).toHaveLength(1));
  });

  it('shows Instagram rejections and refreshes the post list', async () => {
    const fetchMock = mockApi({
      ...base,
      'POST /v1/organic/posts': apiError(502, 'Instagram did not accept the post: bad image', 'INSTAGRAM_POST_FAILED'),
    });
    renderSWR(<OrganicPostView />);
    await userEvent.click(await screen.findByRole('button', { name: /use cake\.jpg/i }));
    await userEvent.click(screen.getByRole('button', { name: /^post to instagram$/i }));
    await userEvent.click(await screen.findByRole('button', { name: /post now/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Instagram did not accept the post');
    await waitFor(() => expect(calls(fetchMock, 'GET /v1/organic/posts').length).toBeGreaterThan(1));
  });

  it('explains when Meta is not connected yet', async () => {
    mockApi({
      'GET /v1/organic/accounts': apiError(409, 'Connect your Instagram ads account in Settings first', 'META_NOT_CONNECTED'),
      'GET /v1/media': [],
      'GET /v1/organic/posts': [],
    });
    renderSWR(<OrganicPostView />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Connect your Instagram ads account');
    expect(screen.getByRole('button', { name: /^post to instagram$/i })).toBeDisabled();
  });

  it('lists recent posts with the account they went to', async () => {
    mockApi({ ...base, 'GET /v1/organic/posts': [POST] });
    renderSWR(<OrganicPostView />);
    expect(await screen.findByText(/@main_brand · fresh bake!/i)).toBeInTheDocument();
  });

  it('deletes a recent post from the list', async () => {
    const fetchMock = mockApi({
      ...base,
      'GET /v1/organic/posts': [POST],
      'DELETE /v1/organic/posts/p1': { status: 'DELETED', id: 'p1' },
    });
    renderSWR(<OrganicPostView />);
    const deleteBtn = await screen.findByRole('button', { name: /delete post p1/i });
    await userEvent.click(deleteBtn);
    await waitFor(() => expect(calls(fetchMock, 'DELETE /v1/organic/posts/p1')).toHaveLength(1));
  });

  it('keeps button enabled after posting so user can post again', async () => {
    mockApi({ ...base, 'POST /v1/organic/posts': POST });
    renderSWR(<OrganicPostView />);
    await userEvent.click(await screen.findByRole('button', { name: /use cake\.jpg/i }));
    const post = screen.getByRole('button', { name: /^post to instagram$/i });
    expect(post).toBeEnabled();
    await userEvent.click(post);
    await userEvent.click(await screen.findByRole('button', { name: /post now/i }));
    expect(await screen.findByText('Posted to @main_brand.')).toBeInTheDocument();
    // After posting, button is NOT disabled - picture remains selected
    expect(screen.getByRole('button', { name: /^post to instagram$/i })).toBeEnabled();
  });
});

