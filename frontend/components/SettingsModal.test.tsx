import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SettingsModal } from './SettingsModal';
import { mockApi, renderSWR } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

const props = { onClose: vi.fn(), user: null };

describe('SettingsModal', () => {
  it('opens on initialTab, resets to it on reopen and follows initialTab changes', async () => {
    mockApi({ 'GET /v1/meta/connection': { status: 'NOT_CONNECTED' } });
    const { rerender } = renderSWR(<SettingsModal {...props} isOpen initialTab="appearance" />);
    expect(screen.getByText('Color Palette & Theme')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /^account$/i }));
    expect(screen.queryByText('Color Palette & Theme')).not.toBeInTheDocument();

    rerender(<SettingsModal {...props} isOpen={false} initialTab="appearance" />);
    expect(screen.queryByText('Platform Settings')).not.toBeInTheDocument();
    rerender(<SettingsModal {...props} isOpen initialTab="appearance" />);
    expect(screen.getByText('Color Palette & Theme')).toBeInTheDocument();

    rerender(<SettingsModal {...props} isOpen initialTab="account" />);
    expect(screen.queryByText('Color Palette & Theme')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });
});
