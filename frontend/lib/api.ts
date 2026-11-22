export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function api<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const jsonBody = init.body !== undefined && !(init.body instanceof FormData);
  const response = await fetch(`/api${path}`, {
    ...init,
    credentials: "include",
    headers: { ...(jsonBody ? { "Content-Type": "application/json" } : {}), ...init.headers },
  });
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = body.error ?? {};
    throw new ApiError(response.status, error.code ?? "UNKNOWN", error.message ?? response.statusText, error.details);
  }
  return body as T;
}

export const fetchApi = api;
export const fetcher = <T,>(path: string) => api<T>(path);

export type WorkspaceItem = {
  id: string;
  name: string;
  label: string;
  type: 'development' | 'customer';
  description: string;
  is_default: boolean;
};

export type UserProfile = {
  id: string;
  email: string;
  name: string;
  workspace: string;
  workspace_id?: string;
  workspaces?: WorkspaceItem[];
  is_dev_workspace?: boolean;
};

export async function login(email: string, password: string): Promise<UserProfile> {
  return api<UserProfile>(
    '/v1/auth/login',
    {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }
  );
}

export async function register(
  email: string,
  password: string,
  name?: string,
  workspace_name?: string
): Promise<UserProfile> {
  return api<UserProfile>(
    '/v1/auth/register',
    {
      method: 'POST',
      body: JSON.stringify({
        email,
        password,
        ...(name ? { name } : {}),
        ...(workspace_name ? { workspace_name } : {}),
      }),
    }
  );
}

export async function logout() {
  return api<void>('/v1/auth/logout', { method: 'POST' });
}

export async function getMe(): Promise<UserProfile> {
  return api<UserProfile>('/v1/auth/me');
}

export async function changePassword(current_password: string, new_password: string) {
  return api<void>('/v1/auth/password', { method: 'PUT', body: JSON.stringify({ current_password, new_password }) });
}

export async function switchWorkspace(workspace_id: string): Promise<UserProfile> {
  return api<UserProfile>('/v1/auth/workspace/switch', {
    method: 'POST',
    body: JSON.stringify({ workspace_id }),
  });
}

export type ModelFamily = 'gemini' | 'openai'; // which models OpenRouter serves
export type AISettings = { provider: 'openai' | 'gemini' | 'openrouter'; model_family?: ModelFamily; configured: boolean; key_source: 'user' | 'workspace' | 'missing'; masked_key: string | null; connection_status: string; tested_at: string | null };
export const getAISettings = () => api<AISettings>('/v1/settings/ai');
export const saveAISettings = (provider: AISettings['provider'], api_key?: string, model_family?: ModelFamily) =>
  api<AISettings>('/v1/settings/ai', {
    method: 'PUT',
    body: JSON.stringify({ provider, ...(api_key ? { api_key } : {}), ...(provider === 'openrouter' && model_family ? { model_family } : {}) }),
  });
export const testAIConnection = () => api<{ provider: string; connection_status: string; message: string }>('/v1/settings/ai/test', { method: 'POST' });

export async function getConnection() {
  return api<import('./types').MetaConnection>('/v1/meta/connection');
}

export async function getAssets() {
  return api<import('./types').MetaAssets>('/v1/meta/assets');
}

export async function updateConnection(selection: {
  ad_account_id?: string | null;
  page_id?: string | null;
  instagram_user_id?: string | null;
}) {
  return api<import('./types').MetaConnection>('/v1/meta/connection', {
    method: 'PUT',
    body: JSON.stringify(selection),
  });
}

export async function disconnectMeta() {
  return api<{ status: string }>('/v1/meta/disconnect', {
    method: 'POST',
  });
}

export async function disconnectAdAccount() {
  return api<import('./types').MetaConnection>('/v1/meta/disconnect-ad-account', {
    method: 'POST',
  });
}

export async function disconnectPage() {
  return api<import('./types').MetaConnection>('/v1/meta/disconnect-page', {
    method: 'POST',
  });
}

export async function disconnectInstagram() {
  return api<import('./types').MetaConnection>('/v1/meta/disconnect-instagram', {
    method: 'POST',
  });
}

export type CampaignStatus =
  | 'DRAFT'
  | 'PUBLISHING'
  | 'PUBLISH_FAILED'
  | 'PAUSED_ON_META'
  | 'ACTIVE'
  | 'PAUSED'
  | 'COMPLETED';

export const CTA_OPTIONS = ['LEARN_MORE', 'SIGN_UP', 'DOWNLOAD', 'GET_QUOTE', 'CONTACT_US', 'SUBSCRIBE'] as const;

export type AdVariant = { headline: string; primary_text: string; description: string; call_to_action: string };

export type Audience = {
  countries: string[];
  cities: { key: string; name: string }[];
  age_min: number;
  age_max: number;
  genders: 'ALL' | 'MEN' | 'WOMEN';
  interests: { id: string; name: string }[];
};

export type PublishStep = {
  name: string;
  status: string; // PENDING | RUNNING | DONE | FAILED
  meta_object_id?: string | null;
  attempts?: number;
  last_error?: string | null;
};

export type PublishBlock = {
  status: 'RUNNING' | 'FAILED' | 'DONE';
  steps: PublishStep[];
  error: { step: string; message: string; meta_code?: number | null } | null;
};

export type CampaignInsights = {
  impressions: number;
  reach: number;
  clicks: number;
  spend_minor: number;
  ctr: number; // percent, as Meta reports it
  cpc_minor?: number | null;
  updated_at?: string | null;
};

/** Spec 07 §1/§5: campaign JSON as returned by the backend. */
export type Campaign = {
  id: string;
  status: CampaignStatus;
  idea: string;
  title: string;
  objective: 'TRAFFIC' | 'AWARENESS';
  landing_url: string;
  audience: Audience;
  daily_budget: number | null;
  currency: string;
  start_date: string | null;
  end_date: string | null;
  variants: AdVariant[];
  selected_variant: number;
  /** Saved AI chat for this draft, oldest first. */
  chat?: { role: 'user' | 'assistant'; text: string }[] | null;
  image_prompt: string;
  image_id: string | null;
  image_url: string | null;
  missing_fields: string[];
  warnings: string[];
  meta?: (Record<string, string | string[] | null | undefined> & { issues?: string[] }) | null;
  publish?: PublishBlock | null;
  insights?: CampaignInsights | null;
  posted?: Record<string, { media_id: string; at: string }> | null;
  publishing_destinations?: Record<PostTarget, boolean> | null;
  selected_hashtags?: string[] | null;
  custom_hashtags?: string[] | null;
  ai_recommended_hashtags?: string[] | null;
  can_publish: boolean;
  live_delivery_enabled?: boolean;
  /** Why the text looks like a Meta special ad category (jobs, housing, credit, politics), or null. */
  special_category_reason?: string | null;
  not_special_category?: boolean | null;
  can_activate: boolean;
  created_at?: string;
  updated_at?: string;
};

export type CampaignFields = Partial<
  Pick<
    Campaign,
    | 'title'
    | 'objective'
    | 'landing_url'
    | 'audience'
    | 'daily_budget'
    | 'start_date'
    | 'end_date'
    | 'variants'
    | 'selected_variant'
    | 'not_special_category'
    | 'publishing_destinations'
    | 'selected_hashtags'
    | 'custom_hashtags'
    | 'ai_recommended_hashtags'
  >
>;

export type MediaItem = {
  id: string;
  filename: string;
  source: 'generated' | 'uploaded';
  prompt?: string | null;
  source_campaign?: string | null;
  created_at: string;
};

export const imageUrl = (imageId: string) => `/api/v1/images/${imageId}`;
export const duplicateCampaign = (id: string) => api<Campaign>(`/v1/campaigns/${id}/duplicate`, { method: 'POST' });
export const deleteMedia = (id: string) => api<{ status: string; id: string }>(`/v1/media/${id}`, { method: 'DELETE' });
export const deleteDmThread = (id: string) => api<{ status: string }>(`/v1/dm/threads/${id}`, { method: 'DELETE' });

const post = <T,>(path: string, body: unknown = {}) => api<T>(path, { method: 'POST', body: JSON.stringify(body) });
const put = <T,>(path: string, body: unknown) => api<T>(path, { method: 'PUT', body: JSON.stringify(body) });
const c = (id: string) => `/v1/campaigns/${encodeURIComponent(id)}`;

export const getCampaigns = () => api<Campaign[]>('/v1/campaigns');
export const getCampaign = (id: string) => api<Campaign>(c(id));
export const createDraftFromIdea = (idea: string) => post<Campaign>('/v1/campaigns/draft', { idea });
export const createCampaign = (fields: CampaignFields) => post<Campaign>('/v1/campaigns', fields);
export const updateCampaign = (id: string, fields: CampaignFields) => put<Campaign>(c(id), fields);
export type ChatTurn = { campaign: Campaign; reply: string; warnings: string[] };
export const chatCampaign = (id: string, message: string) => post<ChatTurn>(`${c(id)}/chat`, { message });
export const improveCopy = (id: string, instruction: string) => post<Campaign>(`${c(id)}/copy/improve`, { instruction });
export const regenerateImage = (id: string, prompt?: string) =>
  post<Campaign>(`${c(id)}/image/generate`, prompt ? { prompt } : {});
export const setCampaignImage = (id: string, image_id: string) => put<Campaign>(`${c(id)}/image`, { image_id });
export function uploadCampaignImage(id: string, file: File) {
  const form = new FormData();
  form.append('file', file);
  return api<Campaign>(`${c(id)}/image`, { method: 'POST', body: form });
}
export const getMedia = () => api<MediaItem[]>('/v1/media');

export const publishCampaign = (id: string) => post<{ status: string }>(`${c(id)}/publish`, { confirm: true });

/** Normal free posts of the ad's picture and text, separate from the paid ad. */
export const POST_TARGETS = [
  ['facebook_feed', 'Facebook Feed'],
  ['facebook_story', 'Facebook Story'],
  ['instagram_feed', 'Instagram Feed'],
  ['instagram_story', 'Instagram Story'],
] as const;
export type PostTarget = (typeof POST_TARGETS)[number][0];
export type PostResults = Record<string, { status: 'PUBLISHED' | 'FAILED'; media_id?: string; error?: string }>;
export const postCampaign = (id: string, targets: PostTarget[]) =>
  post<{ results: PostResults }>(`${c(id)}/post`, { targets });
export const publishPath = (id: string) => `${c(id)}/publish`;
export const resumePublish = (id: string) => post<{ status: string }>(`${c(id)}/publish/resume`);
export const discardPublish = (id: string) => post<{ status: string }>(`${c(id)}/publish/discard`);

export const activateCampaign = (id: string) => post<Campaign>(`${c(id)}/activate`, { confirm: true });
export const pauseCampaign = (id: string) => post<Campaign>(`${c(id)}/pause`);
export const resumeCampaign = (id: string) => post<Campaign>(`${c(id)}/resume`);
export const deleteCampaign = (id: string) => api<{ status: string }>(c(id), { method: 'DELETE' });
export const fixIssues = (id: string) => post<{ fixed: string[]; manual: string[] }>(`${c(id)}/fix`);
export const refreshInsights = (id: string) => post<CampaignInsights>(`${c(id)}/insights/refresh`);

export type MetaInterest = {
  id: string;
  name: string;
  audience_size_lower: number;
};

export async function searchInterests(query: string = 'technology'): Promise<MetaInterest[]> {
  return api<MetaInterest[]>(`/v1/meta/interests?q=${encodeURIComponent(query)}`);
}

export type PerformanceInsights = {
  reach: number;
  impressions: number;
  clicks: number;
  spend: number;
  currency: string;
  timeframe: string;
  status: string;
  message?: string;
};

export async function getInsights(timeframe: string = '7d'): Promise<PerformanceInsights> {
  return api<PerformanceInsights>(`/v1/meta/insights?timeframe=${encodeURIComponent(timeframe)}`);
}


export type MetaLocation = { key: string; name: string; type: string; country_code: string };

export const searchLocations = (q: string, country: string) =>
  api<MetaLocation[]>(`/v1/meta/locations?q=${encodeURIComponent(q)}&country=${encodeURIComponent(country)}`);

// --- Instagram DM agent + organic posts --------------------------------------------------------

export type DmConfig = {
  enabled: boolean;
  business_name: string;
  tone: string;
  knowledge: string;
  handoff_message: string;
};
export type DmMessage = { role: 'customer' | 'agent' | 'admin'; text: string; at: string };
export type DmThread = {
  id: string;
  customer_id: string;
  customer_name?: string;
  status: 'BOT' | 'NEEDS_HUMAN' | 'HUMAN';
  last_inbound_at: string;
  minutes_since_inbound?: number;
  reply_window_warning?: boolean;
  needs_attention?: boolean;
  attention_reason?: string | null;
  updated_at: string;
  messages: DmMessage[];
};
export type DmSummary = { enabled: boolean; needs_human: number; needs_attention?: number; last_inbound_at: string | null };
export const saveDmConfig = (config: DmConfig) => put<DmConfig>('/v1/dm/config', config);
export const previewDm = (message: string) =>
  post<{ reply: string; needs_human: boolean }>('/v1/dm/preview', { message });
export const replyDm = (id: string, message: string) =>
  post<DmThread>(`/v1/dm/threads/${encodeURIComponent(id)}/reply`, { message });
export const resumeDm = (id: string) => post<DmThread>(`/v1/dm/threads/${encodeURIComponent(id)}/resume`);

export type OrganicPost = {
  id: string;
  image_id: string;
  caption: string;
  selected_hashtags?: string[] | null;
  status: 'PUBLISHED' | 'FAILED';
  media_id: string | null;
  error: string | null;
  ig_user_id?: string;
  created_at: string;
};
export const generateOrganicImage = (prompt: string) =>
  post<MediaItem>('/v1/organic/images/generate', { prompt });
export function uploadOrganicImage(file: File) {
  const form = new FormData();
  form.append('file', file);
  return api<MediaItem>('/v1/organic/images', { method: 'POST', body: form });
}
export type OrganicAccounts = {
  default: string | null;
  accounts: { instagram_user_id: string; username: string; page_id: string; page_name: string }[];
  unavailable: { page_id: string; page_name: string; reason: string }[];
};
export const publishOrganicPost = (
  image_id: string,
  caption: string,
  instagram_user_id?: string,
  selected_hashtags?: string[]
) =>
  post<OrganicPost>('/v1/organic/posts', {
    image_id,
    caption,
    ...(instagram_user_id ? { instagram_user_id } : {}),
    ...(selected_hashtags && selected_hashtags.length > 0 ? { selected_hashtags } : {}),
  });
export const deleteOrganicPost = (id: string) =>
  api<{ status: string; id: string }>(`/v1/organic/posts/${encodeURIComponent(id)}`, { method: 'DELETE' });

// --- Hashtags API -------------------------------------------------------------

export type RecommendedHashtagItem = {
  tag: string;
  reason?: string;
};

export type HashtagsRecommendResponse = {
  advertisement_title?: string;
  business_category?: string;
  recommended_hashtags?: RecommendedHashtagItem[];
  alternative_hashtags?: string[];
  ai_recommended: string[];
  max_limit: number;
};

export type HashtagsData = {
  categories: Record<string, string[]>;
  recommended?: string[];
  ai_recommended?: string[];
  recommended_hashtags?: RecommendedHashtagItem[];
  alternative_hashtags?: string[];
  custom: string[];
  max_limit: number;
};

export const getHashtags = (query?: string, context?: string) => {
  const params = new URLSearchParams();
  if (query) params.set('query', query);
  if (context) params.set('context', context);
  const qs = params.toString();
  return api<HashtagsData>(`/v1/hashtags${qs ? `?${qs}` : ''}`);
};

export type RecommendHashtagsPayload = {
  text?: string;
  title?: string;
  caption?: string;
  headline?: string;
  primary_text?: string;
  description?: string;
  business_category?: string;
  product_service?: string;
  image_prompt?: string;
  objective?: string;
  audience?: unknown;
  platform?: string;
};

export const recommendHashtags = (payload: RecommendHashtagsPayload) =>
  post<HashtagsRecommendResponse>('/v1/hashtags/recommend', payload);

export const addCustomHashtag = (hashtag: string) =>
  post<{ hashtag: string; custom: string[]; message?: string }>('/v1/hashtags/custom', { hashtag });

export const deleteCustomHashtag = (tag: string) =>
  api<{ deleted: string; custom: string[] }>(`/v1/hashtags/custom/${encodeURIComponent(tag.replace(/^#/, ''))}`, {
    method: 'DELETE',
  });

export const validateHashtags = (hashtags: string[]) =>
  post<{ valid: string[]; errors: string[]; is_valid: boolean }>('/v1/hashtags/validate', { hashtags });

