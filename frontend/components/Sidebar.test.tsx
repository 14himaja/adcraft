import { screen } from '@testing-library/react';
import { describe, expect, it, afterEach, vi } from 'vitest';
import { Sidebar } from './Sidebar';
import { mockApi, renderSWR } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

describe('Sidebar', () => {
  it('shows the current needs-human conversation count', async () => {
    mockApi({ 'GET /v1/dm/summary': { enabled: true, needs_human: 3, last_inbound_at: null } });
    renderSWR(<Sidebar />);
    expect(await screen.findByRole('button', { name: /DM Agent \(3\)/i })).toBeInTheDocument();
  });
});
