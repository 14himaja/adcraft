import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AIProviderSettings } from './AIProviderSettings';
import { bodyOf, calls, mockApi } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

const SETTINGS = {
  provider: 'openai',
  model_family: 'gemini',
  configured: false,
  key_source: 'missing',
  masked_key: null,
  connection_status: 'NOT_TESTED',
  tested_at: null,
};

describe('AIProviderSettings', () => {
  it('shows the model family choice only for OpenRouter', async () => {
    mockApi({ 'GET /v1/settings/ai': SETTINGS });
    render(<AIProviderSettings />);
    const provider = await screen.findByLabelText(/^AI provider/i);
    expect(screen.queryByLabelText(/models served through openrouter/i)).not.toBeInTheDocument();
    await userEvent.selectOptions(provider, 'openrouter');
    expect(screen.getByLabelText(/models served through openrouter/i)).toBeInTheDocument();
    await userEvent.selectOptions(provider, 'gemini');
    expect(screen.queryByLabelText(/models served through openrouter/i)).not.toBeInTheDocument();
  });

  it('saves OpenRouter with the chosen model family and the key', async () => {
    const fetchMock = mockApi({
      'GET /v1/settings/ai': SETTINGS,
      'PUT /v1/settings/ai': { ...SETTINGS, provider: 'openrouter', model_family: 'openai', configured: true },
    });
    render(<AIProviderSettings />);
    await userEvent.selectOptions(await screen.findByLabelText(/^AI provider/i), 'openrouter');
    await userEvent.selectOptions(screen.getByLabelText(/models served through openrouter/i), 'openai');
    await userEvent.type(screen.getByLabelText(/^API key/i), 'or-key-123456');
    await userEvent.click(screen.getByRole('button', { name: /save api key/i }));
    await waitFor(() => expect(calls(fetchMock, 'PUT /v1/settings/ai')).toHaveLength(1));
    expect(bodyOf(fetchMock, 'PUT /v1/settings/ai')).toEqual({
      provider: 'openrouter',
      api_key: 'or-key-123456',
      model_family: 'openai',
    });
  });

  it('does not send a model family for a direct provider', async () => {
    const fetchMock = mockApi({
      'GET /v1/settings/ai': SETTINGS,
      'PUT /v1/settings/ai': { ...SETTINGS, provider: 'gemini', configured: true },
    });
    render(<AIProviderSettings />);
    await userEvent.selectOptions(await screen.findByLabelText(/^AI provider/i), 'gemini');
    await userEvent.type(screen.getByLabelText(/^API key/i), 'gm-key-123456');
    await userEvent.click(screen.getByRole('button', { name: /save api key/i }));
    await waitFor(() => expect(calls(fetchMock, 'PUT /v1/settings/ai')).toHaveLength(1));
    expect(bodyOf(fetchMock, 'PUT /v1/settings/ai')).toEqual({ provider: 'gemini', api_key: 'gm-key-123456' });
  });

  it('loads the saved provider and family', async () => {
    mockApi({ 'GET /v1/settings/ai': { ...SETTINGS, provider: 'openrouter', model_family: 'openai', configured: true } });
    render(<AIProviderSettings />);
    expect(await screen.findByLabelText(/models served through openrouter/i)).toHaveValue('openai');
    expect(screen.getByLabelText(/^AI provider/i)).toHaveValue('openrouter');
  });
});
