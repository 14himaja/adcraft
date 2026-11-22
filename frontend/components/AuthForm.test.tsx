import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuthForm } from './AuthForm';
import * as api from '../lib/api';

const mockPush = vi.fn();
let mockSearchParams = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
  useSearchParams: () => mockSearchParams,
}));

describe('AuthForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSearchParams = new URLSearchParams();
  });

  it('renders login form and submits successfully', async () => {
    const user = userEvent.setup();
    const loginSpy = vi.spyOn(api, 'login').mockResolvedValueOnce({
      id: 'u1',
      email: 'test@example.com',
      name: 'Test',
      workspace: 'W',
    });

    render(<AuthForm initialMode="login" />);

    await user.type(screen.getByLabelText(/email address/i), 'test@example.com');
    await user.type(screen.getByLabelText(/^password/i), 'SecretPass123!');
    await user.click(screen.getByTestId('auth-submit'));

    await waitFor(() => {
      expect(loginSpy).toHaveBeenCalledWith('test@example.com', 'SecretPass123!');
      expect(mockPush).toHaveBeenCalledWith('/settings/meta');
    });
  });

  it('displays error message when login fails', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'login').mockRejectedValueOnce(new Error('Invalid email or password'));

    render(<AuthForm initialMode="login" />);

    await user.type(screen.getByLabelText(/email address/i), 'wrong@example.com');
    await user.type(screen.getByLabelText(/^password/i), 'wrongpass');
    await user.click(screen.getByTestId('auth-submit'));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Invalid email or password');
    });
  });

  it('switches to registration mode and displays workspace input', async () => {
    const user = userEvent.setup();
    render(<AuthForm initialMode="login" />);

    expect(screen.queryByLabelText(/workspace name/i)).not.toBeInTheDocument();

    await user.click(screen.getByTestId('tab-register'));

    expect(screen.getByLabelText(/workspace name/i)).toBeInTheDocument();
  });

  it('toggles password visibility when the eye button is clicked', async () => {
    const user = userEvent.setup();
    render(<AuthForm initialMode="login" />);

    const passwordInput = screen.getByLabelText(/^password/i);
    const toggleButton = screen.getByTestId('toggle-password-visibility');

    // Initially password is hidden
    expect(passwordInput).toHaveAttribute('type', 'password');
    expect(toggleButton).toHaveAttribute('aria-label', 'Show password');

    // Click to view password
    await user.click(toggleButton);
    expect(passwordInput).toHaveAttribute('type', 'text');
    expect(toggleButton).toHaveAttribute('aria-label', 'Hide password');

    // Click again to hide password
    await user.click(toggleButton);
    expect(passwordInput).toHaveAttribute('type', 'password');
    expect(toggleButton).toHaveAttribute('aria-label', 'Show password');
  });

  it('preserves and navigates to the redirect destination when query param is present', async () => {
    mockSearchParams = new URLSearchParams('redirect=%2Fsettings%2Fconnections');
    const user = userEvent.setup();
    vi.spyOn(api, 'login').mockResolvedValueOnce({
      id: 'u1',
      email: 'test@example.com',
      name: 'Test',
      workspace: 'W',
    });

    render(<AuthForm initialMode="login" />);

    await user.type(screen.getByLabelText(/email address/i), 'test@example.com');
    await user.type(screen.getByLabelText(/^password/i), 'SecretPass123!');
    await user.click(screen.getByTestId('auth-submit'));

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/settings/connections');
      expect(mockPush).not.toHaveBeenCalledWith('/settings/meta');
    });
  });

  it('navigates via window.location when redirect points to an API OAuth route', async () => {
    mockSearchParams = new URLSearchParams('redirect=%2Fapi%2Fv1%2Fintegrations%2Flinkedin%2Fconnect%3Freturn_to%3D%252Fsettings%252Fconnections');
    const user = userEvent.setup();
    vi.spyOn(api, 'login').mockResolvedValueOnce({
      id: 'u1',
      email: 'test@example.com',
      name: 'Test',
      workspace: 'W',
    });

    const mockLoc = { href: '', assign: vi.fn(), replace: vi.fn() };
    vi.stubGlobal('location', mockLoc);

    render(<AuthForm initialMode="login" />);

    await user.type(screen.getByLabelText(/email address/i), 'test@example.com');
    await user.type(screen.getByLabelText(/^password/i), 'SecretPass123!');
    await user.click(screen.getByTestId('auth-submit'));

    await waitFor(() => {
      expect(mockLoc.href).toBe('/api/v1/integrations/linkedin/connect?return_to=%2Fsettings%2Fconnections');
      expect(mockPush).not.toHaveBeenCalled();
    });
  });

  it('blocks unsafe open redirects and safely falls back', async () => {
    mockSearchParams = new URLSearchParams('redirect=https%3A%2F%2Fevil.com');
    const user = userEvent.setup();
    vi.spyOn(api, 'login').mockResolvedValueOnce({
      id: 'u1',
      email: 'test@example.com',
      name: 'Test',
      workspace: 'W',
    });

    render(<AuthForm initialMode="login" />);

    await user.type(screen.getByLabelText(/email address/i), 'test@example.com');
    await user.type(screen.getByLabelText(/^password/i), 'SecretPass123!');
    await user.click(screen.getByTestId('auth-submit'));

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/settings/meta');
    });
  });
});
