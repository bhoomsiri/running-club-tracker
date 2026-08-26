/**
 * REVIEWED WORDING — approved as it stands. Do not edit casually.
 *
 * This is the text a member agrees to before the club may hold their health data, which
 * under Thailand's PDPA is sensitive personal data (มาตรา 26). โรงพยาบาลโพธาราม's PDPA
 * officer / DPO checked it against actual practice and approved it unchanged: what is
 * collected, why, who can see it, how long it is kept, and how to withdraw. The club
 * launched on it and members have consented under it (CONSENT_VERSION v2).
 *
 * That makes every sentence here a promise on record, and the bar for touching one
 * higher than it was while this was a draft — see the versioning note at the end.
 *
 * One bullet is a NOTICE rather than a consent item, and the DPO was told which:
 * the leaderboard line. Showing a member's name and distance to the rest of the club
 * comes from taking part in the club's activity, not from this health-data consent — and
 * the code matches that reading, because withdrawing consent stops the health data being
 * processed and does NOT remove anyone from the leaderboard. It is said here because
 * this is the moment a member is actually reading, not because agreeing to health data
 * is what permits it. If the club would rather it be a real choice, that is an opt-out
 * flag on the member and a use case to honour it — not a change to this sentence.
 *
 * Two claims below are deliberately weaker than they could be, because the code behind
 * them does not exist yet:
 *   - deletion at the end of the retention period is described as something an
 *     administrator does, not something that happens automatically. There is no purge
 *     job; health_record.retention_until is written and nothing reads it yet.
 *   - erasure on request points at a person, because there is no self-service use case.
 * Both are still deferred, and the wording was approved on that basis. When either is
 * built, this text can promise more — and the promise will then be true.
 *
 * When the wording changes in substance, bump CONSENT_VERSION on the backend. Every
 * member who agreed to the old text is then treated as not having consented and is
 * asked again — which is the point, and why this file does not hold a version of its
 * own to drift out of step. Members have already consented under v2 in production, so
 * that re-consent is now real people being asked again, not a hypothetical.
 */

export const CONSENT_PURPOSE = "เก็บข้อมูลสุขภาพเพื่อวัดผลก่อน/หลังกิจกรรมของชมรม";

export const CONSENT_POINTS = [
  "เก็บอะไร: น้ำหนัก ส่วนสูง ชีพจรขณะพัก และความดันโลหิต เฉพาะที่คุณกรอกเอง — ไม่บังคับกรอกครบทุกช่อง",
  "เก็บไปทำไม: เปรียบเทียบผลก่อนและหลังกิจกรรม เพื่อให้คุณเห็นความเปลี่ยนแปลงของตัวเอง",
  "ใครเห็นได้: ข้อมูลสุขภาพ — ตัวคุณเอง และผู้ดูแลชมรมที่ได้รับสิทธิ์ ซึ่งทุกครั้งที่เปิดดูจะถูกบันทึกไว้ตรวจสอบได้",
  "การเข้าร่วมจะแสดงชื่อ-นามสกุลและระยะสะสมของคุณในตารางอันดับ (leaderboard) ที่สมาชิกในชมรมเห็นได้",
  "เก็บนานแค่ไหน: ชมรมเก็บข้อมูลไว้ตามระยะเวลาที่กำหนด (ประมาณ 2 ปีหลังจบกิจกรรม) และผู้ดูแลจะลบเมื่อครบกำหนด",
  "สิทธิ์ของคุณ: ขอดู แก้ไข และถอนความยินยอมได้เองทุกเมื่อ — หากต้องการลบข้อมูลก่อนกำหนดหรือใช้สิทธิ์อื่นตาม PDPA โปรดติดต่อผู้ดูแลชมรม",
] as const;

export const CONSENT_WITHDRAW_NOTE =
  "การถอนความยินยอมจะทำให้ระบบหยุดใช้ข้อมูลสุขภาพของคุณทันที และคุณจะกรอกข้อมูลใหม่ไม่ได้จนกว่าจะให้ความยินยอมอีกครั้ง";
