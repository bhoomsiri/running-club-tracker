import Link from "next/link";

import { AnnouncementBody } from "@/components/announcement-body";
import { formatDate } from "@/lib/format";
import type { Announcement } from "@/lib/types";

/**
 * A club notice, at the foot of the dashboard.
 *
 * Two layouts, picked by whether there is a picture: a wide image panel beside the text,
 * or a brand-coloured rule down the left where the image would have been. The second is
 * not a degraded version of the first — a notice with no picture should look finished,
 * not like one whose image failed to load.
 *
 * **Today it is always the second.** `Announcement` carries no image field: pictures on
 * notices are a deferred feature (spec §12), and inventing a URL to fill the panel would
 * be exactly the fabrication golden rule #4 forbids. The `imageUrl` prop is how that
 * feature will arrive — when the API sends one, this renders it and nothing else here
 * changes.
 */
export function NewsBanner({
  announcement,
  imageUrl = null,
}: {
  announcement: Announcement;
  imageUrl?: string | null;
}) {
  return (
    <article
      className={`flex overflow-hidden rounded-card border border-border bg-surface max-sm:flex-col ${
        imageUrl ? "" : "border-l-4 border-l-brand"
      }`}
    >
      {imageUrl ? (
        // An arbitrary notice image, not a build-time asset: routing it through
        // next/image would need every future host allow-listed in the config.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={imageUrl}
          alt=""
          aria-hidden
          loading="lazy"
          decoding="async"
          className="w-full shrink-0 object-cover sm:max-w-[300px] sm:basis-[34%]"
        />
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col justify-center gap-2 p-5">
        <p className="flex items-center gap-2">
          <span className="rounded-control bg-brand-tint px-2 py-1 text-xs font-bold text-brand">
            {formatDate(announcement.created_at)}
          </span>
        </p>
        <h3 className="text-lg font-bold">{announcement.title}</h3>
        <AnnouncementBody body={announcement.body} className="line-clamp-3 text-sm" />
        <Link
          href="/announcements"
          className="mt-1 self-start text-sm font-bold text-brand"
        >
          อ่านต่อ ›
        </Link>
      </div>
    </article>
  );
}
