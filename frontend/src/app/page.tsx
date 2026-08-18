import { auth } from "@clerk/nextjs/server";

import { AnnouncementBody } from "@/components/announcement-body";
import { ButtonLink, Card, SectionHeading } from "@/components/ui";
import { apiPublic } from "@/lib/api";
import { CAMPAIGN_COPY } from "@/lib/campaign-copy";
import { formatDate } from "@/lib/format";
import type { Announcement } from "@/lib/types";

/**
 * The club's front door — the only page anyone can open without signing in.
 *
 * It exists for one person: a member of hospital staff who has heard about the running
 * club and wants to know what it is before handing over an email address. So it says
 * what the club is doing this year, shows what has been happening lately, and gets out
 * of the way with two buttons.
 *
 * The news feed is fetched without a token (`apiPublic`) and is allowed to fail: if the
 * API is unreachable the page still renders everything else, because a landing page that
 * 500s because a notice board is down is worse than one with no notices on it.
 *
 * The page itself renders per request — `auth()` reads the session to decide which
 * buttons to show — so the caching is put on the one fetch that can take it. Five
 * minutes of staleness on a notice board is nobody's problem; a cold API call in front
 * of every first-time visitor is.
 */

export default async function LandingPage() {
  const { userId } = await auth();
  const news = await latestNews();

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-10">
      <header className="text-center">
        <p className="text-base font-semibold tracking-wide text-brand">PTRH RunClub</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
          ชมรมวิ่ง โรงพยาบาลโพธาราม
        </h1>
        <p className="mx-auto mt-4 max-w-lg text-lg text-muted">
          วิ่งด้วยกันทั้งโรงพยาบาล — บันทึกทุกครั้งที่วิ่ง เห็นระยะสะสมของตัวเอง
          และสะสมแต้มแลกของรางวัลไปพร้อมกัน
        </p>

        {/* One primary action. Signing in is the quieter twin of signing up, so it is
            the outline button — a member who already has an account is looking for it,
            and a member who does not should not have to choose between two greens. */}
        <div className="mx-auto mt-7 flex max-w-sm flex-col gap-3">
          {userId ? (
            <ButtonLink href="/dashboard">เข้าหน้าของฉัน</ButtonLink>
          ) : (
            <>
              <ButtonLink href="/sign-up">สมัครเข้าร่วมชมรม</ButtonLink>
              <ButtonLink href="/sign-in" tone="secondary">
                เข้าสู่ระบบ
              </ButtonLink>
            </>
          )}
        </div>
      </header>

      <section>
        <SectionHeading>กิจกรรมปีนี้</SectionHeading>
        <div className="grid gap-4 sm:grid-cols-2">
          {CAMPAIGN_COPY.map((campaign) => (
            <Card key={campaign.code} className="h-full">
              <p className="text-3xl" aria-hidden>
                {campaign.icon}
              </p>
              <h3 className="mt-2 text-lg font-semibold">{campaign.title}</h3>
              <p className="mt-2 text-base text-muted">{campaign.blurb}</p>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <SectionHeading>ข่าวประชาสัมพันธ์</SectionHeading>
        {news.length === 0 ? (
          <Card>
            <p className="text-base text-muted">
              ยังไม่มีประกาศในตอนนี้ — ติดตามข่าวกิจกรรมได้ที่หน้านี้
            </p>
          </Card>
        ) : (
          <ul className="space-y-3">
            {news.map((notice) => (
              <li key={notice.id}>
                <Card>
                  <p className="text-sm text-muted tabular-nums">
                    {formatDate(notice.created_at)}
                  </p>
                  <h3 className="mt-1 text-lg font-semibold">{notice.title}</h3>
                  <AnnouncementBody body={notice.body} className="mt-2 text-base" />
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-12 rounded-card border border-brand/40 bg-brand-tint p-6 text-center">
        <p className="text-xl font-bold">เริ่มวันนี้ได้เลย</p>
        <p className="mt-2 text-base text-muted">
          ไม่ต้องวิ่งเร็ว ไม่ต้องวิ่งไกล — เดินเร็วหรือวิ่งเบา ๆ วันละนิด
          ก็สะสมระยะได้เหมือนกัน
        </p>
        {userId ? null : (
          <div className="mx-auto mt-5 max-w-sm">
            <ButtonLink href="/sign-up">สมัครเข้าร่วมชมรม</ButtonLink>
          </div>
        )}
      </section>

      <footer className="mt-12 text-center text-sm text-muted">
        ชมรมวิ่ง โรงพยาบาลโพธาราม · PTRH RunClub
      </footer>
    </main>
  );
}

async function latestNews(): Promise<Announcement[]> {
  try {
    return await apiPublic<Announcement[]>("/announcements?limit=5", {
      next: { revalidate: 300 },
    });
  } catch {
    // Deliberately silent: the club's front door should still open when the API is
    // having a bad morning, and a visitor can do nothing with the error either way.
    return [];
  }
}
