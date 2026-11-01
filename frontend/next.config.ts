import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    // Turns off Next's image optimization app-wide. Read all three parts of this
    // note before relying on it for anything: the first version said this "closes
    // the `/_next/image` route entirely", which production proved false within
    // minutes of deploying it.
    //
    // WHAT IT DOES. Next no longer emits `/_next/image?url=…` URLs into the pages
    // it renders, so our own app sends no traffic through the optimizer and incurs
    // no image-optimization cost. It costs us nothing in return, because nothing
    // was using it: there is exactly one `next/image` in the codebase — the
    // evidence preview in submit-run-form.tsx — and it already passed
    // `unoptimized` on a local blob URL the optimizer cannot fetch anyway.
    // Everything else is a deliberate plain `<img>`: evidence photos on presigned
    // R2 URLs that expire, Clerk avatars at 40–72px, and announcement images on
    // hosts we do not control. So no rendering changes.
    //
    // WHAT IT DOES NOT DO. It does not close the route. `/_next/image` is still
    // reachable on production and still answers. Next's own server would 404 it —
    // see the `unoptimized` branch in next-server.js that calls `render404()` —
    // but on Vercel that line is never reached, because Vercel intercepts
    // `/_next/image` at the edge with its own optimizer before the request gets
    // to the Next server. The evidence is what production returns for a bad
    // request: `INVALID_IMAGE_OPTIMIZE_REQUEST`, which is a Vercel error code,
    // not any string Next produces. So this flag would close the route if we ever
    // self-hosted, and does not close it where we actually run.
    //
    // WHAT WOULD ACTUALLY CLOSE IT. Only a platform-level rule — a `vercel.json`
    // route or a Vercel Firewall rule. Neither has been tried, so neither is
    // known to work; do not read this paragraph as a verified recipe.
    //
    // And keep the proportions straight: the thing that actually closed the two
    // CRITICAL `/_next/image` advisories in Nov 2026 was upgrading Next, both
    // times. Not this line. This line is a small amount of defense in depth whose
    // reach turned out to be smaller than intended, and it is never a reason to
    // delay a patch.
    unoptimized: true,
  },
};

export default nextConfig;
