import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeProvider, useTheme } from './theme';

function Probe() {
  const { theme, toggleTheme, setTheme, isMounted } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="mounted">{String(isMounted)}</span>
      <button onClick={toggleTheme}>toggle</button>
      <button onClick={() => setTheme('light')}>light</button>
    </div>
  );
}

const root = document.documentElement;

describe('ThemeProvider', () => {
  beforeEach(() => {
    localStorage.clear();
    root.classList.remove('dark', 'light');
  });

  it('starts light by default and applies the class', () => {
    render(<ThemeProvider><Probe /></ThemeProvider>);
    expect(screen.getByTestId('theme')).toHaveTextContent('light');
    expect(screen.getByTestId('mounted')).toHaveTextContent('true');
    expect(root).toHaveClass('light');
    expect(root).not.toHaveClass('dark');
  });

  it('restores dark from localStorage, toggles and persists', async () => {
    localStorage.setItem('adcraft_theme', 'dark');
    render(<ThemeProvider><Probe /></ThemeProvider>);
    expect(screen.getByTestId('theme')).toHaveTextContent('dark');
    expect(root).toHaveClass('dark');

    await userEvent.click(screen.getByText('toggle'));
    expect(screen.getByTestId('theme')).toHaveTextContent('light');
    expect(root).toHaveClass('light');
    expect(root).not.toHaveClass('dark');
    expect(localStorage.getItem('adcraft_theme')).toBe('light');

    await userEvent.click(screen.getByText('toggle'));
    expect(screen.getByTestId('theme')).toHaveTextContent('dark');
    expect(localStorage.getItem('adcraft_theme')).toBe('dark');
  });
});
