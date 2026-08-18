/**
 * The units and job titles at โรงพยาบาลโพธาราม, as the hospital writes them.
 *
 * These are a *convenience for typing*, not a constraint. The backend stores both fields
 * as free text and always has: the org chart is the hospital's to change, and a member
 * whose unit is not on this list picks "อื่นๆ (ระบุเอง)" and types their own — which is
 * saved exactly as typed and is **not** added to the list. The list only grows when
 * somebody edits this file.
 *
 * Kept here rather than fetched, because a dropdown that needs a round-trip is a
 * dropdown that is empty on a bad hospital wifi connection.
 *
 * Order: as supplied by the club. Not sorted — the lists are searchable, and the reader
 * scans for their own entry rather than reading top to bottom.
 */

export const DEPARTMENTS = [
  "สำนักงานแพทย์",
  "งานยุทธศาสตร์",
  "งานเภสัชกรรม",
  "งานพยาธิวิทยาคลินิก",
  "งานห้องผ่าตัด",
  "งานอาชีวเวชกรรม",
  "งานบริหารงานทั่วไป",
  "งานพัสดุด้านสนับสนุนบริการ",
  "งานการเงินและบัญชี",
  "งานสุขศึกษา",
  "งานศัลยกรรม",
  "งานสงฆ์อาพาธ",
  "งานเวชกรรมฟื้นฟู",
  "งานแพทย์แผนไทย",
  "งานแพทย์ผสมผสาน",
  "งานผู้ป่วยหนัก",
  "งานทันตกรรม",
  "งานผู้ป่วยนอก",
  "งานเทคโนโลยีสารสนเทศ",
  "งานวิสัญญี",
  "งานบริหารสินทรัพย์",
  "งานพักศพ",
  "งานจ่ายกลาง",
  "งานโภชนาการ",
  "งานจิตเวช",
  "งานศัลยกรรมกระดูกและข้อ",
  "พิเศษ 2",
  "พิเศษ 3",
  "ศูนย์รักษ์เคหะ",
  "ศูนย์แพทย์",
] as const;

export const POSITIONS = [
  "นายแพทย์",
  "นักวิชาการสาธารณสุข",
  "เภสัชกร",
  "นักเทคนิคการแพทย์",
  "พยาบาลวิชาชีพ",
  "นักวิเคราะห์นโยบายและแผน",
  "นักประชาสัมพันธ์",
  "นิติกร",
  "นักจัดการงานทั่วไป",
  "นักวิชาการพัสดุ",
  "เจ้าพนักงานพัสดุ",
  "เจ้าพนักงานการเงิน",
  "พนักงานบริการ",
  "เจ้าพนักงานการเงินและบัญชี",
  "นักวิชาการเงินและบัญชี",
  "พนักงานการเงิน",
  "เจ้าพนักงานธุรการ",
  "นักกายภาพบำบัด",
  "ผู้ช่วยนักกายภาพบำบัด",
  "แพทย์แผนไทย",
  "พนักงานช่วยการพยาบาล",
  "แพทย์แผนไทยปฏิบัติการ",
  "พนักงานเก็บเอกสาร",
  "ทันตแพทย์",
  "เจ้าพนักงานทันตสาธารณสุข",
  "พนักงานช่วยเหลือคนไข้",
  "เจ้าพนักงานเภสัชกรรม",
  "พนักงานประจำห้องยา",
  "นักวิชาการคอมพิวเตอร์",
  "พนักงานเก็บเงิน",
  "พนักงานผ่าและรักษาศพ",
  "พนักงานประกอบอาหาร",
  "ผู้ช่วยพยาบาล",
  "พนักงานประจำตึก",
] as const;
