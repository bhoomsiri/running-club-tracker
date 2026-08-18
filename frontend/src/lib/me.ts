import "server-only";

import { cache } from "react";

import { apiServer } from "@/lib/api-server";
import type { MemberSummary } from "@/lib/types";

/**
 * The signed-in member's own summary, fetched at most once per request.
 *
 * The shell needs the role to decide whether to show the admin link, and several pages
 * need the same response for their own content. `cache()` deduplicates them within a
 * single render, so the header costs nothing extra on the screens that were already
 * asking — and one call on the screens that were not.
 *
 * Everything through this helper, then, rather than `apiServer("/me/summary")` inline:
 * a second direct call is a second round trip that looks identical in the code.
 */
export const getMySummary = cache(() => apiServer<MemberSummary>("/me/summary"));
