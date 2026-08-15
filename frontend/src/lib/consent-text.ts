/**
 * PLACEHOLDER WORDING — not legally reviewed.
 *
 * This is the text a member agrees to before the club may hold their health data, which
 * under Thailand's PDPA is sensitive personal data (มาตรา 26). The club must have a real
 * person check this against its actual practice before launch: what is collected, why,
 * who can see it, how long it is kept, and how to withdraw. Wording that does not match
 * what the system actually does is worse than none, because it is a promise on record.
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
  "เก็บนานแค่ไหน: ตามระยะเวลาที่ชมรมกำหนดหลังกิจกรรมจบ แล้วระบบจะลบให้อัตโนมัติ",
  "สิทธิ์ของคุณ: ขอดู แก้ไข ถอนความยินยอม หรือขอลบข้อมูลได้ทุกเมื่อ",
] as const;

export const CONSENT_WITHDRAW_NOTE =
  "การถอนความยินยอมจะทำให้ระบบหยุดใช้ข้อมูลสุขภาพของคุณทันที และคุณจะกรอกข้อมูลใหม่ไม่ได้จนกว่าจะให้ความยินยอมอีกครั้ง";
