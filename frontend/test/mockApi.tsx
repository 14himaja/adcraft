import React from 'react';
import { render } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { vi } from 'vitest';
import type { Campaign } from '../lib/api';

type Handler = unknown | ((init: RequestInit) => unknown);

/** Stub global fetch with a route table keyed "METHOD /v1/path". Unknown routes return 404. */
export function mockApi(routes: Record<string, Handler>) {
  const fn = vi.fn(async (url: string, init: RequestInit = {}) => {
    const key = `${init.method ?? 'GET'} ${url.replace(/^\/api/, '')}`;
    if (!(key in routes)) return json(404, { error: { code: 'NOT_MOCKED', message: key, details: {} } });
    const value = await (typeof routes[key] === 'function' ? (routes[key] as (i: RequestInit) => unknown)(init) : routes[key]);
    return value instanceof Response ? value : json(200, value);
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

export const apiError = (status: number, message: string, code = 'ERROR') => () =>
  json(status, { error: { code, message, details: {} } });

/** Returns each value in turn, repeating the last one. */
export function seq(...values: unknown[]) {
  let i = 0;
  return () => values[Math.min(i++, values.length - 1)];
}

export function calls(fn: ReturnType<typeof mockApi>, key: string) {
  return fn.mock.calls.filter(([url, init]) => `${init?.method ?? 'GET'} ${String(url).replace(/^\/api/, '')}` === key);
}

export function bodyOf(fn: ReturnType<typeof mockApi>, key: string, n = 0) {
  return JSON.parse(String(calls(fn, key)[n][1]?.body));
}

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

export function renderSWR(ui: React.ReactElement) {
  return render(<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>{ui}</SWRConfig>);
}

export function makeCampaign(over: Partial<Campaign> = {}): Campaign {
  return {
    id: 'c1',
    status: 'DRAFT',
    idea: 'Promote my Python course',
    title: 'Python Course Launch',
    objective: 'TRAFFIC',
    landing_url: 'https://synxa.ai/python',
    audience: {
      countries: ['IN'],
      cities: [{ key: '1017930', name: 'Bangalore' }],
      age_min: 18,
      age_max: 24,
      genders: 'ALL',
      interests: [{ id: '6003682002118', name: 'Python (programming language)' }],
    },
    daily_budget: 100,
    currency: 'INR',
    start_date: '2026-10-20',
    end_date: '2026-10-22',
    variants: [
      { headline: 'Learn Python fast', primary_text: 'Live classes for students.', description: '8 weeks', call_to_action: 'LEARN_MORE' },
      { headline: 'Code in 8 weeks', primary_text: 'Join live Python classes.', description: 'Only ₹999', call_to_action: 'SIGN_UP' },
    ],
    selected_variant: 0,
    image_prompt: 'student coding',
    image_id: 'img1',
    image_url: '/api/v1/images/img1',
    missing_fields: [],
    warnings: [],
    publish: null,
    insights: null,
    can_publish: true,
    can_activate: false,
    created_at: '2026-10-14T10:00:00Z',
    updated_at: '2026-10-14T10:00:00Z',
    ...over,
  };
}

export const CONNECTION = {
  status: 'ACTIVE',
  ad_account_id: 'act_123',
  ad_account_name: 'Main Ad Account',
  page_id: 'p1',
  page_name: 'Synxa Page',
  instagram_username: 'synxait',
};
