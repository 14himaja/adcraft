import useSWR from 'swr';
import { api, fetcher } from './api';
import {
  AdvertisingPlatformReadiness,
  MultiPublishPayload,
  MultiPublishPreviewItem,
  MultiPublishResultItem,
  PublishHistoryItem,
  SocialAccountsResponse,
  SocialIntegrationsResponse,
  SocialPlatformConnection,
  SocialPlatformId,
} from './types';

export function useSocialConnections() {
  const { data, error, isLoading, mutate } = useSWR<SocialIntegrationsResponse>(
    '/v1/integrations',
    fetcher
  );
  return {
    data,
    platforms: data?.platforms ?? [],
    connectedCount: data?.connected_count ?? 0,
    isLoading,
    error,
    mutate,
  };
}

export function usePlatformAccounts(platform: SocialPlatformId | null, enabled: boolean) {
  const { data, error, isLoading, mutate } = useSWR<SocialAccountsResponse>(
    platform && enabled ? `/v1/integrations/${platform}/accounts` : null,
    fetcher
  );
  return {
    accounts: data?.accounts ?? [],
    selectedTargetId: data?.selected_target_id ?? null,
    isLoading,
    error,
    mutate,
  };
}

export function usePublishHistory() {
  const { data, error, isLoading, mutate } = useSWR<PublishHistoryItem[]>(
    '/v1/integrations/publish/history',
    fetcher
  );
  return {
    history: data ?? [],
    isLoading,
    error,
    mutate,
  };
}

export function useAdvertisingPlatforms() {
  const { data, error, isLoading, mutate } = useSWR<{
    organization_id: string;
    note: string;
    platforms: AdvertisingPlatformReadiness[];
  }>('/v1/integrations/advertising/platforms', fetcher);
  return {
    adPlatforms: data?.platforms ?? [],
    note: data?.note ?? '',
    isLoading,
    error,
    mutate,
  };
}

export function getPlatformConnectUrl(platform: SocialPlatformId, returnTo = '/?section=connections') {
  return `/api/v1/integrations/${platform}/connect?return_to=${encodeURIComponent(returnTo)}`;
}

export function selectPlatformAccount(platform: SocialPlatformId, target_id: string) {
  return api<SocialPlatformConnection>(`/v1/integrations/${platform}/account`, {
    method: 'PUT',
    body: JSON.stringify({ target_id }),
  });
}

export function refreshPlatformConnection(platform: SocialPlatformId) {
  return api<SocialPlatformConnection>(`/v1/integrations/${platform}/refresh`, {
    method: 'POST',
  });
}

export function disconnectSocialPlatform(platform: SocialPlatformId) {
  return api<SocialPlatformConnection>(`/v1/integrations/${platform}/disconnect`, {
    method: 'POST',
  });
}

export function previewMultiPublish(payload: MultiPublishPayload) {
  return api<{ previews: Record<string, MultiPublishPreviewItem> }>('/v1/integrations/publish/preview', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function publishMultiPlatform(payload: MultiPublishPayload) {
  return api<{ results: Record<string, MultiPublishResultItem> }>('/v1/integrations/publish', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

