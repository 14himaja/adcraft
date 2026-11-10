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
