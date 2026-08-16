/**
 * The one place the backend is called.
 *
 * Every request carries a Clerk session token, because the backend derives `member_id`
 * from it — the client never sends an id of its own, which is what stops one member
 * from reading another's data. A call without a token is not a degraded call, it is a
 * 401, so `apiFetch` refuses to send one.
 *
 * The token comes from Clerk in two different ways depending on where the code runs, so
 * this module holds the part that is the same either way. Use `useApi()` from
 * `api-client.ts` in a client component, `apiServer()` from `api-server.ts` on the
 * server.
 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
  }
}

/** Thai copy for the failures a member can actually do something about. */
export function messageFor(error: unknown): string {
  if (!(error instanceof ApiError)) return "เชื่อมต่อไม่ได้ ลองใหม่อีกครั้ง";
  switch (error.status) {
    case 401:
      return "เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่";
    case 403:
      return "ไม่มีสิทธิ์เข้าถึงส่วนนี้";
    case 404:
      return "ไม่พบข้อมูลที่ต้องการ";
    case 429:
      return "ส่งคำขอถี่เกินไป รอสักครู่แล้วลองใหม่";
    default:
      return error.status >= 500 ? "ระบบขัดข้อง ลองใหม่อีกครั้ง" : error.detail;
  }
}

function baseUrl(): string {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) {
    // Loud, because the alternative is every call quietly hitting the wrong origin.
    throw new Error("NEXT_PUBLIC_API_URL is not set");
  }
  return url.replace(/\/$/, "");
}

/**
 * The one endpoint that answers without a session: the club's published news.
 *
 * Separate from `apiFetch` on purpose rather than making the token optional there —
 * "no token" must be a deliberate choice made once, at the call site of a public
 * endpoint, not something a bug can turn every other request into.
 */
export async function apiPublic<T>(path: string, init: RequestInit = {}): Promise<T> {
  return send<T>(path, new Headers(init.headers), init);
}

export async function apiFetch<T>(
  path: string,
  token: string | null,
  init: RequestInit = {},
): Promise<T> {
  if (!token) throw new ApiError(401, "ไม่พบเซสชัน");

  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  return send<T>(path, headers, init);
}

async function send<T>(
  path: string,
  headers: Headers,
  init: RequestInit,
): Promise<T> {
  // FormData sets its own multipart boundary; setting Content-Type here would break it.
  if (init.body !== undefined && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${baseUrl()}${path}`, { ...init, headers });

  if (!response.ok) {
    // The backend answers every error as {"detail": "..."}; anything else means the
    // request never reached it (a proxy, a gateway) and the body is not ours to show.
    const detail = await response
      .json()
      .then((body: unknown) =>
        typeof body === "object" && body !== null && "detail" in body
          ? String((body as { detail: unknown }).detail)
          : response.statusText,
      )
      .catch(() => response.statusText);
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
