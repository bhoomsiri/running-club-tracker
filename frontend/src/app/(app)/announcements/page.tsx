import { AnnouncementBody } from "@/components/announcement-body";
import { PageHeader } from "@/components/page-header";
import { Card, EmptyState } from "@/components/ui";
import { apiPublic } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Announcement } from "@/lib/types";

/**
 * Every published notice, for members who are already signed in.
 *
 * It calls the same public endpoint the landing page does — there is nothing
 * member-specific about club news, and giving a signed-in member a second, private copy
 * of the same list would be two things to keep in step for no gain.
 */
export default async function AnnouncementsPage() {
  const news = await apiPublic<Announcement[]>("/announcements?limit=50");

  return (
    <>
      <PageHeader title="ข่าวประชาสัมพันธ์" subtitle="ประกาศและกิจกรรมจากชมรม" />

      {news.length === 0 ? (
        <EmptyState>ยังไม่มีประกาศในตอนนี้</EmptyState>
      ) : (
        <ul className="space-y-3">
          {news.map((notice) => (
            <li key={notice.id}>
              <Card>
                <p className="text-sm text-muted tabular-nums">
                  {formatDate(notice.created_at)}
                </p>
                <h2 className="mt-1 text-lg font-semibold">{notice.title}</h2>
                <AnnouncementBody body={notice.body} className="mt-2 text-base" />
              </Card>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
