"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ProfileForm } from "@/components/forms/profile-form";
import { Card } from "@/components/ui";
import type { MemberProfile } from "@/lib/types";

/**
 * Collapsed by default: after onboarding this is a screen people come to read, not to
 * fill in, and six form fields at the top would bury everything else.
 */
export function EditProfile({ profile }: { profile: MemberProfile }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(false);

  if (!open) {
    return (
      <Card>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-lg font-semibold">ข้อมูลติดต่อและผู้ติดต่อฉุกเฉิน</p>
            {profile.department ? (
              <p className="mt-1 truncate text-base">
                {profile.position ? `${profile.position} · ` : ""}
                {profile.department}
              </p>
            ) : null}
            {profile.shirt_size ? (
              <p className="mt-1 text-base">เสื้อไซส์ {profile.shirt_size}</p>
            ) : null}
            <p className="mt-1 text-base text-muted">
              {profile.phone ? `โทร ${profile.phone}` : "ยังไม่ได้กรอกเบอร์โทร"}
              {profile.emergency_contact_name
                ? ` · ฉุกเฉิน: ${profile.emergency_contact_name}`
                : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              setOpen(true);
              setSaved(false);
            }}
            className="btn btn-secondary shrink-0"
          >
            แก้ไข
          </button>
        </div>
        {saved ? (
          <p className="mt-3 text-base font-medium text-emerald-800 dark:text-emerald-300">
            บันทึกเรียบร้อยแล้ว
          </p>
        ) : null}
      </Card>
    );
  }

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-lg font-semibold">แก้ไขข้อมูล</p>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="tap text-base text-muted underline"
        >
          ยกเลิก
        </button>
      </div>
      <ProfileForm
        initial={profile}
        submitLabel="บันทึก"
        onSaved={() => {
          setOpen(false);
          setSaved(true);
          router.refresh();
        }}
      />
    </Card>
  );
}
