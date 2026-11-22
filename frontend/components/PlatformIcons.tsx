import React from 'react';
import { SocialPlatformId } from '../lib/types';

export function InstagramLogo({ className = 'w-6 h-6' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <defs>
        <radialGradient id="igBrandGrad" cx="30%" cy="107%" r="130%">
          <stop offset="0%" stopColor="#fdf497" />
          <stop offset="10%" stopColor="#fdf497" />
          <stop offset="45%" stopColor="#fd5949" />
          <stop offset="68%" stopColor="#d6249f" />
          <stop offset="92%" stopColor="#285AEB" />
        </radialGradient>
      </defs>
      <rect width="48" height="48" rx="13" fill="url(#igBrandGrad)" />
      <rect x="11.5" y="11.5" width="25" height="25" rx="7.5" stroke="#FFFFFF" strokeWidth="2.8" />
      <circle cx="24" cy="24" r="6" stroke="#FFFFFF" strokeWidth="2.8" />
      <circle cx="31.2" cy="16.8" r="1.7" fill="#FFFFFF" />
    </svg>
  );
}

export function FacebookLogo({ className = 'w-6 h-6' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <circle cx="24" cy="24" r="24" fill="#1877F2" />
      <path
        d="M29.6 24.4H25.7V38.5H20V24.4H17.2V19.6H20V16.5C20 12.6 22.1 10.3 26.5 10.3C28.5 10.3 30 10.6 30 10.6L29.5 15.2C29.5 15.2 28.2 15 26.8 15C25.3 15 24.8 15.7 24.8 17.1V19.6H29.3L28.7 24.4H29.6Z"
        fill="#FFFFFF"
      />
    </svg>
  );
}

export function LinkedInLogo({ className = 'w-6 h-6' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <rect width="48" height="48" rx="10" fill="#0A66C2" />
      <path
        d="M15.2 19.6H10.5V35.2H15.2V19.6ZM12.85 11.8C11.35 11.8 10.1 13.05 10.1 14.55C10.1 16.05 11.35 17.3 12.85 17.3C14.35 17.3 15.6 16.05 15.6 14.55C15.6 13.05 14.35 11.8 12.85 11.8ZM37.5 26.4C37.5 21.8 34.95 19.2 31.3 19.2C28.35 19.2 26.75 20.85 26.05 22.05V19.6H21.55C21.6 21.2 21.55 35.2 21.55 35.2H26.25V26.6C26.25 26.15 26.3 25.7 26.45 25.35C26.85 24.45 27.7 23.5 29.25 23.5C31.25 23.5 32.15 25 32.15 27.2V35.2H37.5V26.4Z"
        fill="#FFFFFF"
      />
    </svg>
  );
}

export function XLogo({ className = 'w-6 h-6' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <rect width="48" height="48" rx="12" fill="#0F1419" />
      <path
        d="M26.9 21.8L36.2 11H34L25.9 20.4L19.4 11H12L21.8 25.2L12 36.5H14.2L22.7 26.6L29.6 36.5H37L26.9 21.8ZM23.9 25.3L22.9 23.9L15 12.7H18.4L24.8 21.8L25.8 23.2L34.1 35H30.7L23.9 25.3Z"
        fill="#FFFFFF"
      />
    </svg>
  );
}

export function PinterestLogo({ className = 'w-6 h-6' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <circle cx="24" cy="24" r="24" fill="#E60023" />
      <path
        d="M24.3 11.2C16.7 11.2 12.6 16.4 12.6 21.3C12.6 24.1 14 26.7 16.2 27.6C16.6 27.8 16.8 27.7 16.9 27.3C17 27 17.3 25.7 17.4 25.2C17.5 24.9 17.4 24.7 17.2 24.4C16.5 23.6 16.1 22.4 16.1 21C16.1 17.3 18.9 14.3 23.5 14.3C27.4 14.3 29.8 16.8 29.8 20.4C29.8 24.7 27.7 28.1 24.8 28.1C23.2 28.1 22.1 26.8 22.4 25.2C22.8 23.4 23.6 21.4 23.6 20.1C23.6 18.9 22.9 17.9 21.6 17.9C20 17.9 18.7 19.6 18.7 21.8C18.7 23.2 19.2 24.1 19.2 24.1L17.3 32.1C16.9 33.9 17.1 36.2 17.2 36.6C17.2 36.8 17.5 36.9 17.6 36.7C17.8 36.4 20.1 33.5 20.8 30.8C21 30 22 26.4 22 26.4C22.6 27.6 24.4 28.6 26.2 28.6C31.7 28.6 35.4 23.6 35.4 17.4C35.4 13.1 31.1 11.2 24.3 11.2Z"
        fill="#FFFFFF"
      />
    </svg>
  );
}

export function RedditLogo({ className = 'w-6 h-6' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <circle cx="24" cy="24" r="24" fill="#FF4500" />
      <path
        d="M36.5 24.2C36.5 22.6 35.2 21.3 33.6 21.3C32.8 21.3 32.1 21.6 31.6 22.1C29.6 20.7 26.9 19.8 24 19.7L25.3 13.7L29.5 14.6C29.6 15.7 30.5 16.6 31.6 16.6C32.8 16.6 33.8 15.6 33.8 14.4C33.8 13.2 32.8 12.2 31.6 12.2C30.7 12.2 29.9 12.8 29.6 13.5L24.8 12.5C24.5 12.4 24.2 12.6 24.1 12.9L22.6 19.7C19.6 19.8 16.9 20.7 14.9 22.1C14.4 21.6 13.7 21.3 12.9 21.3C11.3 21.3 10 22.6 10 24.2C10 25.4 10.7 26.4 11.7 26.8C11.7 27.1 11.6 27.4 11.6 27.7C11.6 32.1 17 35.7 23.6 35.7C30.2 35.7 35.6 32.1 35.6 27.7C35.6 27.4 35.6 27.1 35.5 26.8C36 26.4 36.5 25.4 36.5 24.2ZM17.8 26.2C17.8 25 18.8 24.1 19.9 24.1C21.1 24.1 22 25 22 26.2C22 27.4 21.1 28.3 19.9 28.3C18.8 28.3 17.8 27.4 17.8 26.2ZM29.4 31.5C28 32.9 25.3 33 24 33C22.7 33 20 32.9 18.6 31.5C18.4 31.3 18.4 30.9 18.6 30.7C18.8 30.5 19.2 30.5 19.4 30.7C20.3 31.6 22.1 31.9 24 31.9C25.9 31.9 27.7 31.6 28.6 30.7C28.8 30.5 29.2 30.5 29.4 30.7C29.6 30.9 29.6 31.3 29.4 31.5ZM28.1 28.3C26.9 28.3 26 27.4 26 26.2C26 25 26.9 24.1 28.1 24.1C29.2 24.1 30.2 25 30.2 26.2C30.2 27.4 29.2 28.3 28.1 28.3Z"
        fill="#FFFFFF"
      />
    </svg>
  );
}

export function PlatformLogo({
  platform,
  className = 'w-8 h-8',
}: {
  platform: SocialPlatformId | string;
  className?: string;
}) {
  switch (platform) {
    case 'instagram':
      return <InstagramLogo className={className} />;
    case 'facebook':
      return <FacebookLogo className={className} />;
    case 'linkedin':
      return <LinkedInLogo className={className} />;
    case 'x':
      return <XLogo className={className} />;
    case 'pinterest':
      return <PinterestLogo className={className} />;
    case 'reddit':
      return <RedditLogo className={className} />;
    default:
      return <FacebookLogo className={className} />;
  }
}

