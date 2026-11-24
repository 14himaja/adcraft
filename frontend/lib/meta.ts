import useSWR from 'swr';
import { fetcher } from './api';
import { MetaAssets, MetaConnection } from './types';

export function useMetaConnection() {
  const { data, error, isLoading, mutate } = useSWR<MetaConnection>(
    '/v1/meta/connection',
    fetcher
  );

  return {
    connection: data,
    isLoading,
    isError: !!error,
    error,
    mutate,
  };
}

export function useMetaAssets(isConnected: boolean) {
  const { data, error, isLoading, mutate } = useSWR<MetaAssets>(
    isConnected ? '/v1/meta/assets' : null,
    fetcher
  );

  return {
    assets: data,
    isLoading,
    isError: !!error,
    error,
    mutate,
  };
}
