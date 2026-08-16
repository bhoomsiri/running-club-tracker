"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui";
import { barWidth, formatDecimal, unitLabel } from "@/lib/format";
import type { ClubOverview, MemberOverview } from "@/lib/types";

/**
 * Sorting and filtering happen here, on data already fetched: a hundred rows is nothing
 * to a browser, and doing it on the server would mean a round trip per column click.
 *
 * Sorting on numbers means comparing them, and the club's numbers arrive as strings to
 * keep them exact. `compareDecimal` compares them digit by digit instead of parsing, so
 * ordering a table can never be the thing that rounds someone's distance.
 */

type SortKey = "distance" | "points" | "name" | "pending";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "distance", label: "ระยะสะสม" },
  { key: "points", label: "แต้ม" },
  { key: "pending", label: "รอตรวจ" },
  { key: "name", label: "ชื่อ" },
];

export function OverviewTable({ overview }: { overview: ClubOverview }) {
  const [sort, setSort] = useState<SortKey>("distance");
  const [query, setQuery] = useState("");
  const [pendingOnly, setPendingOnly] = useState(false);

  // The campaign whose points the table sorts and shows; the first that tracks any.
  const pointsCampaignId = useMemo(() => {
    const withPoints = overview.members
      .flatMap((member) => member.campaigns)
      .find((campaign) => campaign.points_balance !== null);
    return withPoints?.campaign_id ?? null;
  }, [overview.members]);

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = overview.members.filter((member) => {
      if (pendingOnly && member.pending_review_count === 0) return false;
      if (needle === "") return true;
      // Department too, so "กลุ่มงานการพยาบาล" pulls up that unit's members — the club
      // is organised by unit, and that is how the superuser thinks about it.
      return `${member.name} ${member.department ?? ""}`.toLowerCase().includes(needle);
    });

    return [...filtered].sort((a, b) => {
      switch (sort) {
        case "name":
          return a.name.localeCompare(b.name, "th");
        case "pending":
          return b.pending_review_count - a.pending_review_count;
        case "points":
          return compareDecimal(
            pointsOf(b, pointsCampaignId),
            pointsOf(a, pointsCampaignId),
          );
        default:
          return compareDecimal(b.total_distance_km, a.total_distance_km);
      }
    });
  }, [overview.members, query, pendingOnly, sort, pointsCampaignId]);

  const totalPending = overview.members.reduce(
    (sum, member) => sum + member.pending_review_count,
    0,
  );

  return (
    <div>
      <div className="mb-4 space-y-3">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="ค้นหาชื่อหรือหน่วยงาน"
          aria-label="ค้นหาชื่อหรือหน่วยงาน"
          className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-base outline-none focus:border-brand"
        />

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted">เรียงตาม</span>
          {SORTS.map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => setSort(option.key)}
              aria-pressed={sort === option.key}
              className={`rounded-full px-3 py-1.5 text-sm ${
                sort === option.key
                  ? "bg-brand font-medium text-white"
                  : "border border-border text-muted"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={pendingOnly}
            onChange={(event) => setPendingOnly(event.target.checked)}
          />
          เฉพาะคนที่มีรันรอตรวจ
          {totalPending > 0 ? (
            <span className="text-muted">({totalPending} รายการ)</span>
          ) : null}
        </label>
      </div>

      <p className="mb-3 text-sm text-muted">แสดง {rows.length} คน</p>

      {rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
          ไม่พบสมาชิกตามเงื่อนไขที่เลือก
        </p>
      ) : (
        <ol className="space-y-2">
          {rows.map((member, index) => (
            <li key={member.member_id}>
              <MemberRow member={member} rank={sort === "name" ? null : index + 1} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function MemberRow({
  member,
  rank,
}: {
  member: MemberOverview;
  rank: number | null;
}) {
  return (
    <Link
      href={`/admin/members/${member.member_id}`}
      className="block rounded-xl border border-border bg-surface p-3 hover:border-brand"
    >
      <div className="flex items-start gap-3">
        {rank !== null ? (
          <span className="w-6 shrink-0 pt-0.5 text-sm text-muted tabular-nums">
            {rank}
          </span>
        ) : null}

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{member.name}</span>
            {member.role !== "member" ? (
              <Badge tone="brand">{member.role === "admin" ? "ผู้ดูแล" : "ผู้ดูแลระบบ"}</Badge>
            ) : null}
            {member.pending_review_count > 0 ? (
              <Badge>รอตรวจ {member.pending_review_count}</Badge>
            ) : null}
          </div>

          {member.department ? (
            <p className="mt-0.5 truncate text-sm text-muted">{member.department}</p>
          ) : (
            <p className="mt-0.5 text-sm text-amber-700 dark:text-amber-300">
              ยังไม่ได้กรอกหน่วยงาน
            </p>
          )}

          <p className="mt-1 text-sm text-muted tabular-nums">
            {formatDecimal(member.total_distance_km)} กม. · ส่งแล้ว {member.run_count} ครั้ง
          </p>

          <div className="mt-2 space-y-2">
            {member.campaigns.map((campaign) => (
              <div key={campaign.campaign_id}>
                <div className="flex items-baseline justify-between gap-2 text-xs">
                  <span className="truncate text-muted">{campaign.name}</span>
                  <span className="shrink-0 tabular-nums">
                    {formatDecimal(campaign.value)}
                    {campaign.target !== null
                      ? ` / ${formatDecimal(campaign.target)}`
                      : ""}{" "}
                    {unitLabel(campaign.unit)}
                    {campaign.points_balance !== null
                      ? ` · ${formatDecimal(campaign.points_balance)} แต้ม`
                      : ""}
                  </span>
                </div>
                {campaign.percent !== null ? (
                  <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-border">
                    <div
                      className="h-full rounded-full bg-brand"
                      style={{ width: `${barWidth(campaign.percent)}%` }}
                    />
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </div>
    </Link>
  );
}

function pointsOf(member: MemberOverview, campaignId: string | null): string {
  if (campaignId === null) return "0";
  const campaign = member.campaigns.find((row) => row.campaign_id === campaignId);
  return campaign?.points_balance ?? "0";
}

/**
 * Orders two decimal strings without converting either to a number.
 *
 * Sorting is presentation, so a float here would not corrupt anything stored — but the
 * whole app keeps these values exact, and a comparison that quietly disagrees with the
 * numbers on screen at the seventeenth digit is a confusing thing to leave lying around.
 */
export function compareDecimal(a: string, b: string): number {
  const [aNeg, aWhole, aFrac] = split(a);
  const [bNeg, bWhole, bFrac] = split(b);

  if (aNeg !== bNeg) return aNeg ? -1 : 1;
  const sign = aNeg ? -1 : 1;

  if (aWhole.length !== bWhole.length) {
    return sign * (aWhole.length - bWhole.length);
  }
  if (aWhole !== bWhole) return sign * (aWhole < bWhole ? -1 : 1);

  const width = Math.max(aFrac.length, bFrac.length);
  const aPadded = aFrac.padEnd(width, "0");
  const bPadded = bFrac.padEnd(width, "0");
  if (aPadded === bPadded) return 0;
  return sign * (aPadded < bPadded ? -1 : 1);
}

function split(value: string): [boolean, string, string] {
  const trimmed = value.trim();
  const negative = trimmed.startsWith("-");
  const [whole = "0", fraction = ""] = trimmed.replace(/^[-+]/, "").split(".");
  // Leading zeros stripped so digit-count comparison means magnitude.
  return [negative, whole.replace(/^0+(?=\d)/, ""), fraction];
}
