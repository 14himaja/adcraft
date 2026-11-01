'use client';

import Image, { ImageProps } from 'next/image';
import { useState } from 'react';

export function AdImage(props: ImageProps) {
  const [failure, setFailure] = useState<string | null>(null);
  const handleError = async () => {
    let message = 'Image unavailable';
    try {
      const response = await fetch(typeof props.src === 'string' ? props.src : '', { credentials: 'include' });
      if (response.status === 401) message = 'Sign in again';
    } catch { /* Keep generic fallback for network errors. */ }
    setFailure(message);
  };
  if (failure) return <div role="img" aria-label={failure} className="absolute inset-0 flex items-center justify-center bg-slate-100 dark:bg-slate-900 text-xs text-[#7A6C63]">{failure}</div>;
  return <Image {...props} alt={props.alt} unoptimized onError={handleError} />;
}
