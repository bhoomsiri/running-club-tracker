import Link from "next/link";
import { auth } from "@clerk/nextjs/server";

import { AnnouncementBody } from "@/components/announcement-body";
import { Card } from "@/components/ui";
import { apiPublic } from "@/lib/api";
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

const CAMPAIGNS = [
  {
    icon: "🏃",
    title: "สะสมระยะ 100 กิโลเมตร",
    blurb:
      "วิ่งสะสมไปเรื่อย ๆ ตลอดปี ทุกกิโลเมตรที่ส่งเข้ามานับหมด ครบ 100 กม. รับเสื้อ finisher",
  },
  {
    icon: "🎁",
    title: "วันละ 10 กิโลเมตร สะสมแลกของรางวัล",
    blurb:
      "วันไหนวิ่งครบ 10 กม. ได้แต้ม สะสมแต้มไว้แลกของรางวัลจากชมรมได้ตลอดปี",
  },
];

export default async function LandingPage() {
  const { userId } = await auth();
  const news = await latestNews();

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-10">
      <header className="text-center">
        <p className="text-sm font-medium tracking-wide text-brand">PTRH RunClub</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          ชมรมวิ่ง โรงพยาบาลโพธาราม
        </h1>
        <p className="mx-auto mt-3 max-w-lg text-muted">
          วิ่งด้วยกันทั้งโรงพยาบาล — บันทึกทุกครั้งที่วิ่ง เห็นระยะสะสมของตัวเอง
          และสะสมแต้มแลกของรางวัลไปพร้อมกัน
        </p>

        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-center">
          {userId ? (
            <Link
              href="/dashboard"
              className="rounded-lg bg-brand px-6 py-3.5 font-medium text-white active:opacity-80"
            >
              เข้าหน้าของฉัน
            </Link>
          ) : (
            <>
              <Link
                href="/sign-up"
                className="rounded-lg bg-brand px-6 py-3.5 font-medium text-white active:opacity-80"
              >
                สมัครเข้าร่วมชมรม
              </Link>
              <Link
                href="/sign-in"
                className="rounded-lg border border-border px-6 py-3.5 font-medium active:opacity-80"
              >
                เข้าสู่ระบบ
              </Link>
            </>
          )}
        </div>
      </header>

      <section className="mt-12">
        <h2 className="mb-3 text-sm font-semibold text-muted">กิจกรรมปีนี้</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {CAMPAIGNS.map((campaign) => (
            <Card key={campaign.title} className="h-full">
              <p className="text-2xl" aria-hidden>
                {campaign.icon}
              </p>
              <h3 className="mt-2 font-medium">{campaign.title}</h3>
              <p className="mt-1 text-sm text-muted">{campaign.blurb}</p>
            </Card>
          ))}
        </div>
      </section>

      <section className="mt-10">
        <h2 className="mb-3 text-sm font-semibold text-muted">ข่าวประชาสัมพันธ์</h2>
        {news.length === 0 ? (
          <Card>
            <p className="text-sm text-muted">
              ยังไม่มีประกาศในตอนนี้ — ติดตามข่าวกิจกรรมได้ที่หน้านี้
            </p>
          </Card>
        ) : (
          <ul className="space-y-3">
            {news.map((notice) => (
              <li key={notice.id}>
                <Card>
                  <p className="text-xs text-muted tabular-nums">
                    {formatDate(notice.created_at)}
                  </p>
                  <h3 className="mt-1 font-medium">{notice.title}</h3>
                  <AnnouncementBody body={notice.body} className="mt-2 text-sm" />
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-12 rounded-xl border border-brand/30 bg-brand/5 p-5 text-center">
        <p className="font-medium">เริ่มวันนี้ได้เลย</p>
        <p className="mt-1 text-sm text-muted">
          ไม่ต้องวิ่งเร็ว ไม่ต้องวิ่งไกล — เดินเร็วหรือวิ่งเบา ๆ วันละนิด
          ก็สะสมระยะได้เหมือนกัน
        </p>
        {userId ? null : (
          <Link
            href="/sign-up"
            className="mt-4 inline-block rounded-lg bg-brand px-6 py-3 font-medium text-white active:opacity-80"
          >
            สมัครเข้าร่วมชมรม
          </Link>
        )}
      </section>

      <footer className="mt-12 text-center text-xs text-muted">
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
