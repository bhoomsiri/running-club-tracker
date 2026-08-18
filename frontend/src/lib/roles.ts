import type { Role } from "@/lib/types";

/**
 * Who sees which screens.
 *
 * Navigation only. Every one of these questions is answered again by the backend, which
 * reads the role from the database on every request and refuses whatever this file says
 * — so a wrong answer here shows somebody a link that 403s, not data they may not have.
 *
 * The two capabilities mirror the backend's split exactly:
 *   staff     — the club's helpers: the member list, one member's page, deciding runs,
 *               and the audited sensitive reads.
 *   superuser — what the club *offers* (campaigns, rewards, notices, the redemption
 *               queue) and who else may look.
 */

export function isStaff(role: Role): boolean {
  return role === "admin" || role === "superuser";
}

export function isSuperuser(role: Role): boolean {
  return role === "superuser";
}

export const ROLE_LABELS: Record<Role, string> = {
  member: "สมาชิก",
  admin: "ผู้ดูแล",
  superuser: "ผู้ดูแลระบบ",
};
