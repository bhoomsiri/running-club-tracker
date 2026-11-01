import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    // The optimizer is switched off for the whole app, which closes the
    // `/_next/image` route entirely.
    //
    // It costs us nothing, because nothing was using it. There is exactly one
    // `next/image` in the codebase — the evidence preview in submit-run-form.tsx —
    // and it already passes `unoptimized` on a local blob URL, which the optimizer
    // cannot fetch anyway. Everything else is a deliberate plain `<img>`: evidence
    // photos on presigned R2 URLs that expire, Clerk avatars at 40–72px, and
    // announcement images on hosts we do not control. So this flag changes no
    // rendering; it only removes a door.
    //
    // Why remove it: two of the three CRITICAL Next.js advisories we closed in
    // Nov 2026 were in `/_next/image` specifically, and that route is unusual in
    // that it takes a URL from the query string and fetches it server-side. A
    // feature we do not use should not be left listening — if the next advisory
    // lands there too, we are simply not affected. Defense in depth, not a
    // substitute for keeping Next up to date.
    unoptimized: true,
  },
};

export default nextConfig;
