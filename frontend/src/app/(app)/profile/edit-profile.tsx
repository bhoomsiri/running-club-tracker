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
            <p className="font-medium">ข้อมูลติดต่อและผู้ติดต่อฉุกเฉิน</p>
            <p className="mt-0.5 text-sm text-muted">
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
            className="shrink-0 rounded-lg border border-border px-3 py-2 text-sm"
          >
            แก้ไข
          </button>
        </div>
        {saved ? (
          <p className="mt-3 text-sm text-emerald-600 dark:text-emerald-400">
            บันทึกเรียบร้อยแล้ว
          </p>
        ) : null}
      </Card>
    );
  }

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between">
        <p className="font-medium">แก้ไขข้อมูล</p>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-sm text-muted underline"
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
