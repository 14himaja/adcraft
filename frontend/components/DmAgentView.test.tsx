import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DmAgentView } from './DmAgentView';
import { apiError, bodyOf, calls, mockApi, renderSWR } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

const CONFIG = {
  enabled: false,
  business_name: 'Priya Bakery',
  tone: 'Warm and short',
  knowledge: 'Open 9am-6pm Mon-Sat.',
  handoff_message: 'Priya will reply soon.',
};
const THREAD = (over = {}) => ({
  id: 't1',
  customer_id: 'cust_123456',
  status: 'NEEDS_HUMAN',
  last_inbound_at: '2026-10-18T10:00:00Z',
  updated_at: '2026-10-18T10:00:00Z',
  messages: [
    { role: 'customer', text: 'I want a refund', at: '2026-10-18T10:00:00Z' },
    { role: 'agent', text: 'Priya will reply soon.', at: '2026-10-18T10:00:05Z' },
  ],
  ...over,
});

describe('DmAgentView', () => {
  it('loads the saved block and saves edits with auto-reply switched on', async () => {
    const fetchMock = mockApi({
      'GET /v1/dm/config': CONFIG,
      'GET /v1/dm/threads': [],
      'PUT /v1/dm/config': (init: RequestInit) => JSON.parse(String(init.body)),
    });
    renderSWR(<DmAgentView />);
    const knowledge = await screen.findByLabelText(/what the ai knows/i);
    expect(knowledge).toHaveValue('Open 9am-6pm Mon-Sat.');
    await userEvent.clear(knowledge);
    await userEvent.type(knowledge, 'Cakes from Rs 800.');
    await userEvent.click(screen.getByLabelText(/auto-reply to instagram dms/i));
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));
    expect(await screen.findByText(/the ai is answering dms/i)).toBeInTheDocument();
    expect(bodyOf(fetchMock, 'PUT /v1/dm/config')).toMatchObject({
      enabled: true,
      knowledge: 'Cakes from Rs 800.',
      business_name: 'Priya Bakery',
    });
  });

  it('shows why enabling failed', async () => {
    mockApi({
      'GET /v1/dm/config': CONFIG,
      'GET /v1/dm/threads': [],
      'PUT /v1/dm/config': apiError(409, 'Connect your Instagram ads account in Settings first'),
    });
    renderSWR(<DmAgentView />);
    await userEvent.click(await screen.findByLabelText(/auto-reply to instagram dms/i));
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Connect your Instagram ads account');
  });

  it('previews an answer without sending anything', async () => {
    mockApi({
      'GET /v1/dm/config': CONFIG,
      'GET /v1/dm/threads': [],
      'POST /v1/dm/preview': { reply: 'We open at 9am.', needs_human: false },
    });
    renderSWR(<DmAgentView />);
    await userEvent.type(await screen.findByLabelText(/test question/i), 'When do you open?');
    await userEvent.click(screen.getByRole('button', { name: /^ask$/i }));
    expect(await screen.findByText('We open at 9am.')).toBeInTheDocument();
  });

  it('lets the owner reply to a thread that needs them, then hand it back to the AI', async () => {
    const fetchMock = mockApi({
      'GET /v1/dm/config': CONFIG,
      'GET /v1/dm/threads': [THREAD()],
      'POST /v1/dm/threads/t1/reply': THREAD({ status: 'HUMAN' }),
      'POST /v1/dm/threads/t1/resume': THREAD({ status: 'BOT' }),
    });
    renderSWR(<DmAgentView />);
    expect(await screen.findByText('I want a refund')).toBeInTheDocument();
    expect(screen.getByText('Needs you')).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/reply to customer 123456/i), 'Sorry about that, sorting it now');
    await userEvent.click(screen.getByRole('button', { name: /^send$/i }));
    await waitFor(() => expect(calls(fetchMock, 'POST /v1/dm/threads/t1/reply')).toHaveLength(1));
    expect(bodyOf(fetchMock, 'POST /v1/dm/threads/t1/reply')).toEqual({ message: 'Sorry about that, sorting it now' });
    await userEvent.click(screen.getByRole('button', { name: /hand back to ai/i }));
    await waitFor(() => expect(calls(fetchMock, 'POST /v1/dm/threads/t1/resume')).toHaveLength(1));
  });

  it('lists chats by customer name and opens the one you select like a chat', async () => {
    mockApi({
      'GET /v1/dm/config': CONFIG,
      'GET /v1/dm/threads': [
        THREAD({ customer_name: 'Ravi Kumar' }),
        THREAD({
          id: 't2',
          customer_id: 'cust_999999',
          customer_name: 'Asha Rao',
          messages: [{ role: 'customer', text: 'Do you deliver to Madhapur?', at: '2026-10-18T11:00:00Z' }],
        }),
      ],
    });
    renderSWR(<DmAgentView />);
    expect(await screen.findByRole('button', { name: /ravi kumar/i })).toBeInTheDocument();
    expect(screen.queryByText(/customer 123456/i)).not.toBeInTheDocument(); // the name replaces the id
    expect(screen.getByText('I want a refund')).toBeInTheDocument(); // first chat is open by default
    await userEvent.click(screen.getByRole('button', { name: /asha rao/i }));
    expect(await screen.findAllByText('Do you deliver to Madhapur?')).toHaveLength(2); // list preview + chat bubble
    expect(screen.queryByText('I want a refund')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Reply to Asha Rao')).toBeInTheDocument();
  });

  it('falls back to a short id when the name is unknown', async () => {
    mockApi({ 'GET /v1/dm/config': CONFIG, 'GET /v1/dm/threads': [THREAD({ customer_name: '' })] });
    renderSWR(<DmAgentView />);
    expect(await screen.findByRole('button', { name: /customer 123456/i })).toBeInTheDocument();
  });

  it('hides the hand-back button while the AI is already replying', async () => {
    mockApi({ 'GET /v1/dm/config': CONFIG, 'GET /v1/dm/threads': [THREAD({ status: 'BOT' })] });
    renderSWR(<DmAgentView />);
    expect(await screen.findByText('AI replying')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /hand back to ai/i })).not.toBeInTheDocument();
  });

  it('shows the 24 hour rule when a manual reply is refused', async () => {
    mockApi({
      'GET /v1/dm/config': CONFIG,
      'GET /v1/dm/threads': [THREAD()],
      'POST /v1/dm/threads/t1/reply': apiError(409, 'Instagram only allows replies within 24 hours'),
    });
    renderSWR(<DmAgentView />);
    await userEvent.type(await screen.findByLabelText(/reply to customer/i), 'hello');
    await userEvent.click(screen.getByRole('button', { name: /^send$/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('within 24 hours');
  });

  it('renders status line: Agent is off, Webhook not verified, and Webhook subscribed', async () => {
    mockApi({
      'GET /v1/dm/config': CONFIG,
      'GET /v1/dm/threads': [],
      'GET /v1/dm/status': { agent_enabled: false, webhook_verified: true, webhook_subscribed: false, last_inbound_at: null, last_error: null },
    });
    const { unmount } = renderSWR(<DmAgentView />);
    expect(await screen.findByText('Agent is off')).toBeInTheDocument();
    unmount();

    mockApi({
      'GET /v1/dm/config': { ...CONFIG, enabled: true },
      'GET /v1/dm/threads': [],
      'GET /v1/dm/status': { agent_enabled: true, webhook_verified: false, webhook_subscribed: false, last_inbound_at: null, last_error: null },
    });
    const { unmount: unmount2 } = renderSWR(<DmAgentView />);
    expect(await screen.findByText('Webhook not verified')).toBeInTheDocument();
    unmount2();

    mockApi({
      'GET /v1/dm/config': { ...CONFIG, enabled: true },
      'GET /v1/dm/threads': [],
      'GET /v1/dm/status': { agent_enabled: true, webhook_verified: true, webhook_subscribed: true, last_inbound_at: null, last_error: null },
    });
    renderSWR(<DmAgentView />);
    expect(await screen.findByText(/Webhook subscribed/i)).toBeInTheDocument();
  });

  it('allows filling the knowledge block with the provided example', async () => {
    mockApi({
      'GET /v1/dm/config': { ...CONFIG, knowledge: '' },
      'GET /v1/dm/threads': [],
    });
    renderSWR(<DmAgentView />);
    const useBtn = await screen.findByRole('button', { name: /use this example/i });
    await userEvent.click(useBtn);
    const textarea = screen.getByLabelText(/what the ai knows/i) as HTMLTextAreaElement;
    expect(textarea.value).toContain('Priya Bakery');
  });

  it('lets the owner delete a conversation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const fetchMock = mockApi({
      'GET /v1/dm/config': CONFIG,
      'GET /v1/dm/threads': [THREAD()],
      'DELETE /v1/dm/threads/t1': { status: 'DELETED' },
    });
    renderSWR(<DmAgentView />);
    expect(await screen.findByText('I want a refund')).toBeInTheDocument();
    const deleteBtn = screen.getByRole('button', { name: /delete conversation/i });
    await userEvent.click(deleteBtn);
    await waitFor(() => expect(calls(fetchMock, 'DELETE /v1/dm/threads/t1')).toHaveLength(1));
  });
});
