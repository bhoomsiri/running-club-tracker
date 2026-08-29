"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback } from "react";

import { apiDownload, apiFetch } from "@/lib/api";

/**
 * The API client for client components.
 *
 * `getToken()` is called per request rather than once and cached: Clerk session tokens
 * are short-lived, and a token captured when the page mounted would start failing while
 * the member is still on the screen.
 */
export function useApi() {
  const { getToken } = useAuth();

  return useCallback(
    async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
      return apiFetch<T>(path, await getToken(), init);
    },
    [getToken],
  );
}

/** The same, for an endpoint that answers with a file instead of JSON. */
export function useApiDownload() {
  const { getToken } = useAuth();

  return useCallback(
    async function download(path: string) {
      return apiDownload(path, await getToken());
    },
    [getToken],
  );
}
