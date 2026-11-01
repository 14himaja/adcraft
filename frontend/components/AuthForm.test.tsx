import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuthForm } from './AuthForm';
import * as api from '../lib/api';

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

describe('AuthForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
});
