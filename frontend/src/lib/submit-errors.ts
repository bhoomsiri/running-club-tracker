import { ApiError, messageFor } from "@/lib/api";

/**
 * Thai copy for the failures this screen can actually produce, each one phrased as what
 * the member should do next. Anything unmapped falls through to the generic wording.
 */
export function uploadErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 415) {
    return "ไฟล์นี้ใช้ไม่ได้ — รองรับเฉพาะรูป jpg, png, webp ขนาดไม่เกิน 10 MB";
  }
  return messageFor(error);
}

export function submitErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return messageFor(error);
  switch (error.status) {
    case 409:
      // Raised at confirm time, not on upload: the backend matches the image against
      // this member's previous runs.
      return "รูปนี้เคยส่งไปแล้ว กรุณาใช้รูปของการวิ่งครั้งใหม่";
    case 422:
      return "ข้อมูลไม่ผ่านการตรวจสอบ — วันที่ต้องไม่ใช่วันในอนาคต และต้องอยู่ในช่วงกิจกรรมที่เปิดอยู่";
    default:
      return messageFor(error);
  }
}

/** Extraction is a convenience, never a gate — a failure here still lets the member type
 * the numbers in. */
export function extractionNotice(error: unknown): string {
  if (error instanceof ApiError && error.status === 502) {
    return "ระบบอ่านค่าจากรูปไม่สำเร็จ กรุณากรอกตัวเลขเอง";
  }
  if (error instanceof ApiError && error.status === 429) {
    return "อ่านค่าจากรูปถี่เกินไป กรุณากรอกตัวเลขเอง หรือรอสักครู่";
  }
  return "อ่านค่าจากรูปไม่ได้ กรุณากรอกตัวเลขเอง";
}
