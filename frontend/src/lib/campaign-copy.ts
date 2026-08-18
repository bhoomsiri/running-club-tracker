/**
 * What each activity is, in a sentence.
 *
 * The backend knows a campaign's name, window, target and rules — everything except how
 * to explain it to somebody who has never joined a running club. That sentence is
 * copy, it changes when the club changes how it talks about itself, and it has to exist
 * before anyone signs in (the landing page has no token and so cannot ask the API for
 * anything member-shaped). So it lives here, keyed by the campaign's `code`.
 *
 * The names below are duplicated from the database on purpose, for the landing page
 * alone: it is public, and a front door that shows nothing until an API answers is a
 * front door that is sometimes shut. Every signed-in screen uses the name the API
 * returns and takes only the icon and the blurb from here — so if a campaign is renamed,
 * members see the new name immediately and only the landing page waits for this file.
 *
 * A campaign with no entry here still renders: it keeps its name and its numbers and
 * simply has no sentence under it. That is the right failure — next year's activity
 * appears the day it is created, rather than not at all.
 */

export type CampaignCopy = {
  /** The campaign's `code` in the database — the join key, not a display value. */
  code: string;
  icon: string;
  /** For the public landing page only. Signed-in screens use the API's name. */
  title: string;
  blurb: string;
};

export const CAMPAIGN_COPY: CampaignCopy[] = [
  {
    code: "hundred-km-2026",
    icon: "🏃",
    title: "สะสมระยะ 100 กิโลเมตร",
    blurb:
      "วิ่งสะสมไปเรื่อย ๆ ตลอดปี ทุกกิโลเมตรที่ส่งเข้ามานับหมด ครบ 100 กม. รับเสื้อ finisher",
  },
  {
    code: "daily-10km-2026",
    icon: "🎁",
    title: "วันละ 10 กิโลเมตร สะสมแลกของรางวัล",
    blurb: "วันไหนวิ่งครบ 10 กม. ได้แต้ม สะสมแต้มไว้แลกของรางวัลจากชมรมได้ตลอดปี",
  },
];

export function copyFor(code: string): CampaignCopy | undefined {
  return CAMPAIGN_COPY.find((entry) => entry.code === code);
}
