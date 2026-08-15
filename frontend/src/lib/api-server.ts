import "server-only";

import { auth } from "@clerk/nextjs/server";

import { apiFetch } from "@/lib/api";

/**
 * The API client for server components and route handlers.
 *
 * `server-only` is imported for its side effect: it makes the build fail if this module
 * is ever pulled into a client bundle, where `auth()` would not work and the import
 * would be a confusing runtime error instead of a compile-time one.
 *
 * Most member data is better fetched from the client with `useApi()` — the token flows
 * naturally there and the page can show its own loading state. Reach for this when the
 * server needs the data to render, e.g. to decide a redirect.
 */
export async function apiServer<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { getToken } = await auth();
  return apiFetch<T>(path, await getToken(), init);
}
