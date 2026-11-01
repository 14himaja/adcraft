import { fireEvent, render, screen } from '@testing-library/react';
import type { ImgHTMLAttributes } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { AdImage } from './AdImage';

vi.mock('next/image', () => ({
  default: (props: ImgHTMLAttributes<HTMLImageElement>) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img {...props} alt={props.alt} />
  ),
}));

describe('AdImage', () => {
  it('shows a clear fallback when the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 404 }));
    render(<div className="relative"><AdImage src="/api/v1/images/x" alt="Ad" fill /></div>);
    fireEvent.error(screen.getByAltText('Ad'));
    expect(await screen.findByText('Image unavailable')).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it('shows sign in again fallback when the request fails with 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 401 }));
    render(<div className="relative"><AdImage src="/api/v1/images/auth-needed" alt="Ad Auth" fill /></div>);
    fireEvent.error(screen.getByAltText('Ad Auth'));
    expect(await screen.findByText('Sign in again')).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
