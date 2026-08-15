import { ComingSoon, PageHeader } from "@/components/page-header";

export default function DashboardPage() {
  return (
    <>
      <PageHeader title="แดชบอร์ด" subtitle="ความคืบหน้ากิจกรรมของคุณ" />
      <ComingSoon>
        หน้านี้จะแสดงระยะสะสม ความคืบหน้ากิจกรรม 100 กม. และแต้มจากกิจกรรมวันละ 10 กม.
        (ดึงจาก <code className="font-mono">GET /me/summary</code>)
      </ComingSoon>
    </>
  );
}
