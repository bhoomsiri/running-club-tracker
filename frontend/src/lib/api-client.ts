"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback } from "react";

import { apiFetch } from "@/lib/api";

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
