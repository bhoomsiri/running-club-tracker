import { ComingSoon, PageHeader } from "@/components/page-header";

export default function SubmitPage() {
  return (
    <>
      <PageHeader title="ส่งผลวิ่ง" subtitle="อัปโหลดหลักฐาน ตรวจตัวเลข แล้วยืนยัน" />
      <ComingSoon>
        หน้านี้จะเป็นขั้นตอน อัปโหลดรูป → ให้ AI อ่านค่าเป็น <em>ร่าง</em> → คุณตรวจและแก้ →
        กดยืนยัน (<code className="font-mono">/runs/evidence</code> →{" "}
        <code className="font-mono">/runs/extract</code> →{" "}
        <code className="font-mono">POST /runs</code>)
        <br />
        ค่าที่ AI อ่านได้จะไม่ถูกบันทึกเองโดยอัตโนมัติ — ต้องให้คนยืนยันเสมอ
      </ComingSoon>
    </>
  );
}
