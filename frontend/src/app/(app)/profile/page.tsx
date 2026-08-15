import { ComingSoon, PageHeader } from "@/components/page-header";

export default function ProfilePage() {
  return (
    <>
      <PageHeader title="โปรไฟล์" subtitle="ข้อมูลของคุณและความยินยอม" />
      <ComingSoon>
        หน้านี้จะแสดงประวัติการวิ่งของคุณ และส่วนข้อมูลสุขภาพซึ่งจะใช้งานได้
        <strong> ต่อเมื่อให้ความยินยอมก่อนเท่านั้น</strong> (PDPA) พร้อมสิทธิ์ในการดู แก้ไข
        ถอนความยินยอม และขอลบข้อมูล
      </ComingSoon>
    </>
  );
}
