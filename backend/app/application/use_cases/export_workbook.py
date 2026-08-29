"""The whole club's records as one spreadsheet, for the superuser.

This is the largest single disclosure the app can make, so most of what follows is
about making that deliberate rather than convenient.

**Superuser only.** Not admin. An admin may read one named member's health data and be
accountable for that one act; taking every record at once is a different thing, and it
is the person who answers for the club's data who does it. Checked here as well as at
the router, because the router gate is convenience and this one is the control.

**The sensitive sheets go through the same door as everything else.** Screening, health
records, consent and the sensitive profile fields (sex, birth date, emergency contact)
are not dumped from a wider query — each member's is read one at a time, consent is
required exactly as `ViewMemberHealth` requires it, and each read writes its own audit
row naming that member. The invariant in `models.py` is that those fields cannot be
reached without an audit row, and an export is not an exception to it. A member whose
consent is not active is skipped: withdrawn consent closes this door too.

**Nothing measured reaches the audit log.** The export row carries sheet names and row
counts and nothing else, and `AuditEntry.create` rejects the rest by key and by type
rather than trusting this file to remember (golden rule #8).

**One transaction.** The rendered bytes and every audit row commit together. If the
audit write fails there is no file; if rendering fails there is no audit row claiming
one was made.

The health sheets are behind `health_export_enabled`, off by default, so this can ship
and be used for the operational half while the wording that governs the sensitive half
is still with the DPO.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.application.ports.export_unit_of_work import ExportUnitOfWork
from app.application.ports.workbook_renderer import Cell, Sheet, WorkbookRenderer
from app.domain.audit import AuditAction, AuditEntry
from app.domain.campaign import Campaign
from app.domain.consent import ConsentPurpose
from app.domain.entities import Member, RunEntry
from app.domain.errors import MemberNotFound, NotAuthorized
from app.domain.health import HealthRecord
from app.domain.redemption import PointsEntry, Redemption, Reward
from app.domain.screening import Screening

REVIEW_STATUS_TH = {"ok": "ผ่าน", "flagged": "รอตรวจ", "rejected": "ไม่ผ่าน"}
SOURCE_TH = {"app_screenshot": "แคปจากแอป", "manual_photo": "ถ่ายเอง"}
REDEMPTION_STATUS_TH = {"pending": "รอรับของ", "fulfilled": "รับแล้ว", "cancelled": "ยกเลิก"}
SEX_TH = {"male": "ชาย", "female": "หญิง"}


@dataclass(frozen=True)
class ExportedWorkbook:
    filename: str
    content: bytes
    # What the audit row recorded, so the caller can report it without re-deriving it.
    sheet_rows: dict[str, int]


class ExportWorkbook:
    def __init__(
        self,
        uow: ExportUnitOfWork,
        renderer: WorkbookRenderer,
        consent_version: str,
        health_export_enabled: bool,
    ) -> None:
        self._uow = uow
        self._renderer = renderer
        self._consent_version = consent_version
        self._health_export_enabled = health_export_enabled

    def execute(self, actor_id: UUID) -> ExportedWorkbook:
        with self._uow as uow:
            actor = uow.members.get(actor_id)
            if actor is None:
                raise MemberNotFound(str(actor_id))
            if not actor.role.may_edit_records:
                raise NotAuthorized("only the superuser may export the club's records")

            now = uow.clock.now()
            members = uow.members.list_all()
            campaigns = uow.campaigns.list_all()
            rewards = [r for c in campaigns for r in uow.rewards.list_for_campaign(c.id)]
            names = {m.id: m.preferred_name for m in members}
            campaign_names = {c.id: c.name for c in campaigns}
            reward_names = {r.id: r.name for r in rewards}

            sheets = [
                _members_sheet(members),
                _runs_sheet(uow.runs.list_all(), names),
                _redemptions_sheet(uow.redemptions.list_all(), names, reward_names),
                _ledger_sheet(uow.ledger.list_all(), names, campaign_names),
                _rewards_sheet(rewards, campaign_names),
                _campaigns_sheet(campaigns),
            ]

            if self._health_export_enabled:
                sheets.extend(self._sensitive_sheets(uow, actor, members, campaign_names, now))

            content = self._renderer.render(sheets)
            sheet_rows = {sheet.key: sheet.row_count for sheet in sheets}

            uow.audit.record(
                AuditEntry.create(
                    actor_member_id=actor.id,
                    action=AuditAction.EXPORT_WORKBOOK,
                    # No subject: this is about all of them. The per-member rows written
                    # above name the individuals whose sensitive data was read.
                    subject_member_id=None,
                    # Sheet names and counts only. Never a value out of any of them.
                    detail={**sheet_rows, "health_included": self._health_export_enabled},
                    now=now,
                )
            )
            # Commit BEFORE returning: past this line the export is on the record.
            uow.commit()

        return ExportedWorkbook(
            filename=f"ptrh-runclub-{now:%Y%m%d-%H%M}.xlsx",
            content=content,
            sheet_rows=sheet_rows,
        )

    def _sensitive_sheets(
        self,
        uow: ExportUnitOfWork,
        actor: Member,
        members: list[Member],
        campaign_names: dict[UUID, str],
        now: datetime,
    ) -> list[Sheet]:
        """Read one member at a time, each read audited, each gated on live consent.

        Deliberately not a bulk query. The cost of a hundred small reads is nothing at
        this club's size, and what it buys is that the audit log names every member whose
        sensitive data left the app — which is the only form in which this disclosure is
        accountable to the person it is about.
        """
        contact_rows: list[list[Cell]] = []
        screening_rows: list[list[Cell]] = []
        health_rows: list[list[Cell]] = []
        consent_rows: list[list[Cell]] = []

        for member in members:
            consent = uow.consents.get_current(member.id, ConsentPurpose.HEALTH_DATA)
            # Consent is the club's basis for processing this at all. Its absence is not
            # an error here — the export simply does not carry that member.
            if consent is None or not consent.is_active(self._consent_version):
                continue

            consent_rows.append(
                [
                    member.preferred_name,
                    consent.version,
                    consent.granted_at,
                    consent.withdrawn_at,
                    consent.is_active(self._consent_version),
                ]
            )

            contact_rows.append(_contact_row(member))
            uow.audit.record(
                AuditEntry.create(
                    actor_member_id=actor.id,
                    action=AuditAction.VIEW_CONTACT,
                    subject_member_id=member.id,
                    detail={"via": "export"},
                    now=now,
                )
            )

            screening = uow.screenings.get_for_member(member.id)
            if screening is not None:
                screening_rows.append(_screening_row(member, screening))
                uow.audit.record(
                    AuditEntry.create(
                        actor_member_id=actor.id,
                        action=AuditAction.VIEW_SCREENING,
                        subject_member_id=member.id,
                        detail={"via": "export"},
                        now=now,
                    )
                )

            records = uow.health.list_by_member(member.id)
            if records:
                health_rows.extend(_health_row(member, r, campaign_names) for r in records)
                uow.audit.record(
                    AuditEntry.create(
                        actor_member_id=actor.id,
                        action=AuditAction.VIEW_HEALTH,
                        subject_member_id=member.id,
                        # Context only — never the measurements themselves.
                        detail={"via": "export", "record_count": len(records)},
                        now=now,
                    )
                )

        return [
            Sheet(
                key="contact",
                title="ข้อมูลส่วนตัว (อ่อนไหว)",
                headers=[
                    "ชื่อ", "วันเกิด", "เพศ", "เบอร์โทร",
                    "ผู้ติดต่อฉุกเฉิน", "เบอร์ผู้ติดต่อฉุกเฉิน",
                ],
                rows=contact_rows,
            ),
            Sheet(
                key="screening",
                title="แบบคัดกรอง (อ่อนไหว)",
                headers=[
                    "ชื่อ", "เวอร์ชันแบบคัดกรอง", "วันที่คัดกรอง",
                    "ตอบว่าใช่ (ข้อ)", "รับทราบความเสี่ยง",
                ],
                rows=screening_rows,
            ),
            Sheet(
                key="health",
                title="ข้อมูลสุขภาพ (อ่อนไหว)",
                headers=[
                    "ชื่อ", "กิจกรรม", "ช่วง", "วันที่วัด",
                    "น้ำหนัก (กก.)", "ส่วนสูง (ซม.)", "ชีพจรขณะพัก",
                    "ความดันตัวบน", "ความดันตัวล่าง", "เก็บถึงวันที่",
                ],
                rows=health_rows,
            ),
            Sheet(
                key="consent",
                title="ความยินยอม",
                headers=["ชื่อ", "เวอร์ชัน", "ให้ความยินยอมเมื่อ", "ถอนเมื่อ", "ยังมีผล"],
                rows=consent_rows,
            ),
        ]


def _members_sheet(members: Iterable[Member]) -> Sheet:
    """Ordinary personal data only.

    Sex, birth date and the emergency contact are absent on purpose — they are the
    มาตรา 26 half of the profile and they live on the audited sheet, so that opening
    this tab is not the same act as opening that one.
    """
    rows: list[list[Cell]] = [
        [
            member.preferred_name,
            member.display_name,
            member.role.value,
            member.profile.department,
            member.profile.position,
            member.profile.shirt_size.value if member.profile.shirt_size else None,
            member.profile.phone,
            member.created_at,
        ]
        for member in members
    ]
    return Sheet(
        key="members",
        title="สมาชิก",
        headers=[
            "ชื่อ", "ชื่อในระบบ", "สิทธิ์", "หน่วยงาน", "ตำแหน่ง",
            "ไซส์เสื้อ", "เบอร์โทร", "สมัครเมื่อ",
        ],
        rows=rows,
    )


def _runs_sheet(runs: Iterable[RunEntry], names: dict[UUID, str]) -> Sheet:
    rows: list[list[Cell]] = [
        [
            names.get(run.member_id, "—"),
            run.run_date,
            run.distance_km,
            run.duration_seconds,
            run.pace_min_per_km,
            SOURCE_TH.get(run.source.value, run.source.value),
            REVIEW_STATUS_TH.get(run.review_status.value, run.review_status.value),
            run.created_at,
        ]
        for run in runs
    ]
    return Sheet(
        key="runs",
        title="ผลวิ่ง",
        headers=[
            "ชื่อ", "วันที่วิ่ง", "ระยะทาง (กม.)", "เวลา (วินาที)",
            "เพซ (นาที/กม.)", "ที่มา", "สถานะ", "ส่งเมื่อ",
        ],
        rows=rows,
    )


def _redemptions_sheet(
    redemptions: Iterable[Redemption], names: dict[UUID, str], rewards: dict[UUID, str]
) -> Sheet:
    rows: list[list[Cell]] = [
        [
            names.get(redemption.member_id, "—"),
            rewards.get(redemption.reward_id, "—"),
            redemption.points_spent,
            REDEMPTION_STATUS_TH.get(redemption.status.value, redemption.status.value),
            redemption.created_at,
        ]
        for redemption in redemptions
    ]
    return Sheet(
        key="redemptions",
        title="การแลกรางวัล",
        headers=["ชื่อ", "ของรางวัล", "แต้มที่ใช้", "สถานะ", "แลกเมื่อ"],
        rows=rows,
    )


def _ledger_sheet(
    entries: Iterable[PointsEntry], names: dict[UUID, str], campaigns: dict[UUID, str]
) -> Sheet:
    """The rows, not a balance. A balance is SUM(delta) over exactly these — golden rule
    #5 — and someone checking the total needs what it was summed from."""
    rows: list[list[Cell]] = [
        [
            names.get(entry.member_id, "—"),
            campaigns.get(entry.campaign_id, "—"),
            entry.delta,
            entry.reason.value,
            entry.created_at,
        ]
        for entry in entries
    ]
    return Sheet(
        key="ledger",
        title="แต้ม",
        headers=["ชื่อ", "กิจกรรม", "แต้ม (+/-)", "เหตุผล", "เมื่อ"],
        rows=rows,
    )


def _rewards_sheet(rewards: Iterable[Reward], campaigns: dict[UUID, str]) -> Sheet:
    rows: list[list[Cell]] = [
        [
            reward.name,
            campaigns.get(reward.campaign_id, "—"),
            reward.points_cost,
            reward.stock,
            reward.is_active,
        ]
        for reward in rewards
    ]
    return Sheet(
        key="rewards",
        title="ของรางวัล",
        headers=["ของรางวัล", "กิจกรรม", "แต้มที่ต้องใช้", "คงเหลือ", "เปิดใช้"],
        rows=rows,
    )


def _campaigns_sheet(campaigns: Iterable[Campaign]) -> Sheet:
    rows: list[list[Cell]] = [
        [
            campaign.name,
            campaign.code,
            campaign.type.value,
            campaign.starts_on,
            campaign.ends_on,
            campaign.is_active,
        ]
        for campaign in campaigns
    ]
    return Sheet(
        key="campaigns",
        title="กิจกรรม",
        headers=["ชื่อกิจกรรม", "รหัส", "ประเภท", "เริ่ม", "สิ้นสุด", "เปิดใช้"],
        rows=rows,
    )


def _contact_row(member: Member) -> list[Cell]:
    profile = member.profile
    return [
        member.preferred_name,
        profile.birth_date,
        SEX_TH.get(profile.sex.value, profile.sex.value) if profile.sex else None,
        profile.phone,
        profile.emergency_contact_name,
        profile.emergency_contact_phone,
    ]


def _screening_row(member: Member, screening: Screening) -> list[Cell]:
    """The count of 'yes' answers, not the answers themselves.

    Which specific condition somebody declared is health data about a named person, and
    a spreadsheet row is not where it belongs. The count is what tells an organiser
    whether a screening needs a second look; the detail stays behind the app, where
    reading it is its own audited act.
    """
    return [
        member.preferred_name,
        screening.version,
        screening.screened_on,
        sum(1 for answered in screening.answers.values() if answered),
        screening.risk_acknowledged,
    ]


def _health_row(
    member: Member, record: HealthRecord, campaigns: dict[UUID, str]
) -> list[Cell]:
    return [
        member.preferred_name,
        campaigns.get(record.campaign_id, "—"),
        record.phase.value,
        record.measured_on,
        record.weight_kg,
        record.height_cm,
        record.resting_hr,
        record.systolic,
        record.diastolic,
        record.retention_until,
    ]
