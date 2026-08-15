import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

/**
 * The auth boundary. Named `proxy.ts` because Next 16 renamed the convention away from
 * `middleware.ts`; the default export is still what Next picks up, so Clerk's helper
 * drops straight in.
 *
 * Everything is protected; sign-in and sign-up are the two ways in.
 *
 * Written as a deny-by-default list on purpose: a new page added later is private the
 * moment it exists, without anyone remembering to add it here. Getting that the other
 * way round would leak a member's data the first time someone forgot.
 */
const isPublicRoute = createRouteMatcher(["/sign-in(.*)", "/sign-up(.*)"]);

export default clerkMiddleware(async (auth, request) => {
  if (!isPublicRoute(request)) {
    await auth.protect();
  }
});

export const config = {
  // Skips Next's internals and anything that looks like a static file, and always runs
  // on API/tRPC routes.
  matcher: ["/((?!_next|.*\\..*).*)", "/(api|trpc)(.*)"],
};
