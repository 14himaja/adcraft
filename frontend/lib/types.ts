export type MetaConnection = {
  status: "NOT_CONNECTED" | "ACTIVE" | "EXPIRED";
  mode?: "real" | "fake";
  expires_at?: string;
  expiring_soon?: boolean;
  ad_account_id?: string | null;
  ad_account_name?: string | null;
  currency?: string | null;
  page_id?: string | null;
  page_name?: string | null;
  instagram_user_id?: string | null;
  instagram_username?: string | null;
};

export type MetaAssets = {
  ad_accounts: { id: string; name: string; currency: string | null; min_daily_budget_minor?: number }[];
  pages: { id: string; name: string; instagram: { id: string; username: string } | null }[];
  instagram_accounts?: { id: string; username: string; page_id: string; page_name: string }[];
  selected?: {
    ad_account_id?: string | null;
    ad_account_name?: string | null;
    page_id?: string | null;
    page_name?: string | null;
    instagram_user_id?: string | null;
    instagram_username?: string | null;
    currency?: string | null;
  };
};

export type SocialPlatformId =
  | "facebook"
  | "instagram"
  | "linkedin";

export type SocialConnectionStatus =
  | "NOT_CONNECTED"
  | "ACTIVE"
  | "EXPIRED"
  | "REVOKED"
  | "ERROR";

export type PlatformCapabilities = {
  supports_oauth: boolean;
  supports_refresh: boolean;
  supports_account_selection: boolean;
  supports_text_post: boolean;
  supports_image_post: boolean;
  supports_link_post: boolean;
  supports_title: boolean;
  requires_image: boolean;
  requires_target_selection: boolean;
  max_text_length: number;
  target_label: string;
};

export type SocialPlatformConnection = {
  platform: SocialPlatformId;
  name: string;
  description: string;
  configured: boolean;
  required_env_vars: string[];
  required_scopes: string[];
  capabilities: PlatformCapabilities;
  advertising: {
    supported: boolean;
    status: string;
    note: string;
  };
  status: SocialConnectionStatus;
  connected: boolean;
  mode?: "real" | "fake";
  expires_at?: string | null;
  expiring_soon?: boolean;
  has_refresh_token?: boolean;
  platform_account_id?: string | null;
  account_display_name?: string | null;
  account_username?: string | null;
  account_type?: string | null;
  selected_target_id?: string | null;
  selected_target_name?: string | null;
  selected_target_type?: string | null;
  granted_scopes?: string[];
  metadata?: Record<string, unknown>;
  last_error?: string | null;
  connected_at?: string | null;
  updated_at?: string | null;
};

export type SocialIntegrationsResponse = {
  organization_id: string;
  connected_count: number;
  total_platforms: number;
  platforms: SocialPlatformConnection[];
};

export type SocialDiscoveredAccount = {
  account_id: string;
  display_name: string;
  account_type: string;
  username?: string | null;
  target_id: string;
  target_name: string;
  target_type: string;
  avatar_url?: string | null;
  can_publish: boolean;
  permission_note?: string | null;
  extra?: Record<string, unknown>;
};

export type SocialAccountsResponse = {
  platform: SocialPlatformId;
  selected_target_id?: string | null;
  accounts: SocialDiscoveredAccount[];
};

export type MultiPublishPayload = {
  platforms: SocialPlatformId[];
  text: string;
  title?: string;
  link_url?: string;
  image_id?: string;
  hashtags?: string[];
  targets?: Record<string, string>;
};

export type MultiPublishPreviewItem = {
  platform: SocialPlatformId;
  name: string;
  connection_status: string;
  target_id?: string | null;
  target_name?: string | null;
  formatted_text: string;
  character_count: number;
  max_text_length: number;
  valid: boolean;
  errors: string[];
};

export type MultiPublishResultItem = {
  platform: SocialPlatformId;
  status: "PUBLISHED" | "FAILED";
  platform_post_id?: string | null;
  post_url?: string | null;
  target_id?: string | null;
  target_name?: string | null;
  error?: string | null;
  error_code?: string | null;
};

export type PublishHistoryItem = {
  id: string;
  platform: SocialPlatformId;
  title?: string | null;
  text: string;
  link_url?: string | null;
  image_id?: string | null;
  hashtags: string[];
  target_id?: string | null;
  target_name?: string | null;
  status: "PUBLISHED" | "FAILED";
  platform_post_id?: string | null;
  post_url?: string | null;
  error?: string | null;
  created_at: string;
};

export type AdvertisingPlatformReadiness = {
  id: string;
  social_platform: SocialPlatformId;
  name: string;
  status: string;
  organic_connected: boolean;
  api_approved: boolean;
  billing_supported_india: string;
  min_daily_budget: string;
  available_features: string[];
  gated_features: string[];
  requirements_note: string;
};
