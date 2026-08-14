---
name: club-frontend
description: How to build the Next.js (App Router) frontend of THIS running-club app — pages, components, Clerk authentication wiring, the token-attached API client, and the run-submission flow (upload evidence → AI extract → human confirm). (This is the running-club frontend — not the Safem0de-GPT chat UI; this app uses Clerk auth and a run-submission flow, not a streaming chat interface or Keycloak.) Use this skill whenever working under frontend/ — adding a page or component, protecting a route, calling the FastAPI backend, building the submit/dashboard/rewards/leaderboard screens, or handling the health-data consent UI. Consult it even for small changes, because the auth token flow, the server/client component split, and the "AI pre-fills, user confirms" rule are easy to get wrong. Read CLAUDE.md first for the golden rules.
---

# Frontend — Next.js App Router + Clerk

The frontend is a thin, fast client over the FastAPI backend. Clerk handles sign-in;
every backend call carries a Clerk token; the UI never trusts AI-read values without
the user confirming them. Keep components small and push logic to the backend.

## Auth wiring (do this once, rely on it everywhere)

**Provider** wraps the app in `app/layout.tsx`:

```tsx
import { ClerkProvider } from "@clerk/nextjs";
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <ClerkProvider><html lang="th"><body>{children}</body></html></ClerkProvider>;
}
```

**Middleware** protects routes in `src/middleware.ts`:

```ts
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
const isProtected = createRouteMatcher(["/dashboard(.*)", "/submit(.*)",
                                        "/campaigns(.*)", "/rewards(.*)", "/leaderboard(.*)"]);
export default clerkMiddleware(async (auth, req) => {
  if (isProtected(req)) await auth.protect();
});
export const config = { matcher: ["/((?!_next|.*\\..*).*)", "/(api|trpc)(.*)"] };
```

## The API client — always attaches the token

Every call to the backend must send the Clerk session token as a Bearer header. Wrap it
once and use it everywhere; never call the backend without it.

```ts
// src/lib/api.ts
"use client";
import { useAuth } from "@clerk/nextjs";

export function useApi() {
  const { getToken } = useAuth();
  return async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = await getToken();
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}${path}`, {
      ...init,
      headers: { ...init.headers, Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  };
}
```

The backend derives `member_id` from this token, so the client never sends its own id.

## The run-submission flow (the important screen)

Two entry paths, one shared form. This mirrors the backend's three endpoints. **The AI
result pre-fills the form; the user reviews and confirms. Never auto-submit an AI-read
value.**

```tsx
// inside the submit page (client component)
const api = useApi();

// path A — member used a tracking app (Strava/Nike/Garmin…)
async function onScreenshot(file: File) {
  const form = new FormData(); form.append("file", file);
  const { image_key } = await api<{ image_key: string }>("/runs/evidence",
    { method: "POST", body: form });

  const { draft, confidence, warnings } = await api<ExtractResult>("/runs/extract",
    { method: "POST", body: JSON.stringify({ image_key }),
      headers: { "Content-Type": "application/json" } });

  setForm(draft);                       // ★ fill, don't send
  setEvidenceKey(image_key);
  if (confidence < 0.7) setReview(warnings);   // low confidence → ask user to check
}

// path B — member has no app: photo + manual entry. Skip /runs/extract.

// both paths end here, only after the user reviews and clicks confirm
async function onConfirm() {
  await api("/runs", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...form, image_key: evidenceKey,
                           source: usedApp ? "app_screenshot" : "manual_photo" }) });
}
```

Show a clear "please double-check the numbers the app read" banner whenever confidence
is low or warnings exist. The user's confirmed values are what get saved.

## Pages (App Router)

Keep pages server components by default; make a component `"use client"` only when it
needs hooks/interactivity (forms, the API client, Clerk client hooks).

| Route            | Purpose                                                        |
|------------------|---------------------------------------------------------------|
| `/`              | landing / sign-in entry                                       |
| `/dashboard`     | this member's progress on active campaigns (100 km ring, etc.)|
| `/submit`        | the submission flow above                                     |
| `/campaigns`     | list of campaigns; `/campaigns/[id]` shows detail + progress   |
| `/rewards`       | reward catalogue, current points balance, redeem action        |
| `/leaderboard`   | ranked cumulative distance                                     |
| `/health`        | before/after health form — **requires consent first** (below)  |

## Types mirror the backend DTOs

Keep `src/lib/types.ts` in sync with `api/schemas.py`. Don't reshape data on the client
to paper over a backend mismatch — fix the DTO instead so both sides agree.

```ts
export type ExtractResult = {
  draft: { distance_km: number | null; duration_seconds: number | null; run_date: string | null };
  confidence: number;
  warnings: string[];
};
```

## Health data UI — consent is a hard gate

The `/health` form is sensitive personal data under PDPA. The UI must:
- Show the consent purpose and version, and require an explicit opt-in **before** the
  form is usable. Don't pre-tick it.
- Only ever display the signed-in member's own health data. Admin views are a separate,
  role-gated screen — never mix them into the member UI.
- Offer the member their PDPA rights plainly: view/export their data, edit it, withdraw
  consent, request deletion.

The backend enforces the gate too (defence in depth) — but the UI must not even let a
member submit health data without a recorded consent.

## Rules of thumb

- Secrets never go in `NEXT_PUBLIC_*`. Only the API base URL and Clerk's *publishable*
  key are public; everything else stays server-side.
- Don't fetch protected data in a server component without Clerk's server auth helpers;
  for most member data, fetch from the client with `useApi()` so the token flows naturally.
- Render Thai copy for anything the member sees; keep code identifiers in English.
- Keep components presentational and small; if a component grows business logic, that
  logic probably belongs in the backend.
- Show loading and error states for every backend call — a flaky network shouldn't leave
  the member staring at a frozen screen (this is part of "fast and stable").
