/**
 * PLACEHOLDER WORDING — not legally reviewed.
 *
 * This is the text a member agrees to before the club may hold their health data, which
 * under Thailand's PDPA is sensitive personal data (มาตรา 26). It must be checked by the
 * hospital's PDPA officer / DPO against actual practice before launch: what is
 * collected, why, who can see it, how long it is kept, and how to withdraw. Wording that
 * does not match what the system actually does is worse than none, because it is a
 * promise on record.
 *
 * Two claims below are deliberately weaker than they could be, because the code behind
 * them does not exist yet:
 *   - deletion at the end of the retention period is described as something an
 *     administrator does, not something that happens automatically. There is no purge
 *     job; health_record.retention_until is written and nothing reads it yet.
 *   - erasure on request points at a person, because there is no self-service use case.
 * Both are deferred (see Phase 8 of the deploy checklist). When either is built, this
 * text can promise more — and the promise will then be true.
 *
 * When the wording changes in substance, bump CONSENT_VERSION on the backend. Every
 * member who agreed to the old text is then treated as not having consented and is
 * asked again — which is the point, and why this file does not hold a version of its
 * own to drift out of step.
 */

export const CONSENT_PURPOSE = "เก็บข้อมูลสุขภาพเพื่อวัดผลก่อน/หลังกิจกรรมของชมรม";

export const CONSENT_POINTS = [
  "เก็บอะไร: น้ำหนัก ส่วนสูง ชีพจรขณะพัก และความดันโลหิต เฉพาะที่คุณกรอกเอง — ไม่บังคับกรอกครบทุกช่อง",
  "เก็บไปทำไม: เปรียบเทียบผลก่อนและหลังกิจกรรม เพื่อให้คุณเห็นความเปลี่ยนแปลงของตัวเอง",
  "ใครเห็นได้: ตัวคุณเอง และผู้ดูแลชมรมที่ได้รับสิทธิ์ ซึ่งทุกครั้งที่เปิดดูจะถูกบันทึกไว้ตรวจสอบได้",
  "เก็บนานแค่ไหน: ชมรมเก็บข้อมูลไว้ตามระยะเวลาที่กำหนด (ประมาณ 2 ปีหลังจบกิจกรรม) และผู้ดูแลจะลบเมื่อครบกำหนด",
  "สิทธิ์ของคุณ: ขอดู แก้ไข และถอนความยินยอมได้เองทุกเมื่อ — หากต้องการลบข้อมูลก่อนกำหนดหรือใช้สิทธิ์อื่นตาม PDPA โปรดติดต่อผู้ดูแลชมรม",
] as const;

export const CONSENT_WITHDRAW_NOTE =
  "การถอนความยินยอมจะทำให้ระบบหยุดใช้ข้อมูลสุขภาพของคุณทันที และคุณจะกรอกข้อมูลใหม่ไม่ได้จนกว่าจะให้ความยินยอมอีกครั้ง";
