import { ComingSoon, PageHeader } from "@/components/page-header";

export default function RewardsPage() {
  return (
    <>
      <PageHeader title="รางวัล" subtitle="แต้มคงเหลือและของรางวัลที่แลกได้" />
      <ComingSoon>
        หน้านี้จะแสดงแต้มคงเหลือและรายการของรางวัล พร้อมปุ่มแลก
        (<code className="font-mono">GET /rewards</code> →{" "}
        <code className="font-mono">POST /rewards/{"{id}"}/redeem</code>)
      </ComingSoon>
    </>
  );
}
