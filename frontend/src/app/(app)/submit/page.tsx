import { PageHeader } from "@/components/page-header";

import { SubmitRunForm } from "./submit-run-form";

/**
 * The form is a client component: it holds a file, three requests and the values the
 * member is editing. The page around it stays on the server, so only the interactive
 * part ships as JavaScript.
 */
export default function SubmitPage() {
  return (
    <>
      <PageHeader title="ส่งผลวิ่ง" subtitle="อัปโหลดหลักฐาน ตรวจตัวเลข แล้วยืนยัน" />
      <SubmitRunForm />
    </>
  );
}
