/**
 * The PAR-Q+ questions as members read them, and the risk wording they agree to.
 *
 * PLACEHOLDER — not reviewed. The questions are a Thai rendering of a standard
 * pre-exercise screening instrument, and the acknowledgement below is a plain-language
 * draft. Both must be checked by โรงพยาบาลโพธาราม's PDPA officer / DPO and its legal
 * adviser before launch: this is a health questionnaire run by a hospital's club, and
 * the acknowledgement is the club telling a member what it is and is not taking
 * responsibility for.
 *
 * The keys are the contract with the backend, which stores them and refuses a partial
 * set. Wording may be revised freely; changing a KEY is a data change and needs the
 * instrument version bumped alongside it (PARQ_VERSION in domain/screening.py), so that
 * old answers keep meaning what they meant.
 */

export type ScreeningQuestion = {
  key: string;
  text: string;
};

export type ScreeningSection = {
  title: string;
  hint: string;
  questions: ScreeningQuestion[];
};

export const SCREENING_SECTIONS: ScreeningSection[] = [
  {
    title: "หัวใจและหลอดเลือด",
    hint: "ข้อที่สำคัญที่สุด หากตอบ “ใช่” ข้อใดข้อหนึ่ง ควรพบแพทย์ก่อนเริ่มซ้อม",
    questions: [
      {
        key: "heart_condition",
        text: "แพทย์เคยบอกว่าคุณมีโรคหัวใจ หรือให้ออกกำลังกายเฉพาะที่แพทย์แนะนำเท่านั้นหรือไม่",
      },
      {
        key: "chest_pain_activity",
        text: "คุณเคยเจ็บแน่นหน้าอกขณะออกกำลังกายหรือไม่",
      },
      {
        key: "chest_pain_at_rest",
        text: "ในเดือนที่ผ่านมา คุณเคยเจ็บแน่นหน้าอกขณะพัก (ไม่ได้ออกกำลังกาย) หรือไม่",
      },
      {
        key: "dizziness_or_fainting",
        text: "คุณเคยเวียนศีรษะจนเสียการทรงตัว หรือเป็นลมหมดสติหรือไม่",
      },
    ],
  },
  {
    title: "โรคประจำตัวและกระดูก-ข้อ",
    hint: "โรคที่ต้องดูแลเป็นพิเศษระหว่างออกกำลังกาย",
    questions: [
      {
        key: "high_blood_pressure",
        text: "แพทย์เคยวินิจฉัยว่าคุณมีความดันโลหิตสูงหรือไม่",
      },
      { key: "diabetes", text: "คุณเป็นเบาหวานหรือไม่" },
      {
        key: "asthma_or_lung_disease",
        text: "คุณเป็นหืด หรือมีโรคปอด/ระบบทางเดินหายใจเรื้อรังหรือไม่",
      },
      {
        key: "bone_or_joint_problem",
        text: "คุณมีปัญหากระดูกหรือข้อ ที่อาจแย่ลงเมื่อวิ่งหรือไม่",
      },
    ],
  },
  {
    title: "ประวัติครอบครัวและยาที่ใช้",
    hint: "ข้อมูลประกอบที่ช่วยประเมินความเสี่ยง",
    questions: [
      {
        key: "family_heart_disease",
        text: "มีคนในครอบครัวสายตรงเสียชีวิตกะทันหันจากโรคหัวใจก่อนอายุ 55 ปี (ชาย) หรือ 65 ปี (หญิง) หรือไม่",
      },
      {
        key: "prescribed_medication",
        text: "ขณะนี้คุณใช้ยาที่แพทย์สั่งเป็นประจำอยู่หรือไม่",
      },
      {
        key: "other_reason_not_to_exercise",
        text: "มีเหตุผลอื่นใดที่คุณคิดว่าไม่ควรออกกำลังกายหนักหรือไม่",
      },
    ],
  },
];

export const SCREENING_ALL_KEYS = SCREENING_SECTIONS.flatMap((section) =>
  section.questions.map((question) => question.key),
);

export const RISK_ACKNOWLEDGEMENT =
  "ข้าพเจ้ายืนยันว่าข้อมูลข้างต้นเป็นความจริง เข้าใจว่าการวิ่งและการออกกำลังกายมีความเสี่ยงต่อสุขภาพ " +
  "และจะดูแลตนเองตามความเหมาะสม หากตอบ “ใช่” ข้อใดข้อหนึ่ง ข้าพเจ้าจะปรึกษาแพทย์ก่อนเริ่มซ้อมอย่างหนัก " +
  "แบบคัดกรองนี้เป็นการคัดกรองเบื้องต้นเท่านั้น ไม่ใช่การวินิจฉัยทางการแพทย์";

export const RISK_WARNING =
  "คุณตอบ “ใช่” อย่างน้อยหนึ่งข้อ — แนะนำให้พบแพทย์เพื่อตรวจประเมิน หรือขอใบรับรองแพทย์ ก่อนเริ่มซ้อมวิ่ง " +
  "คุณยังใช้งานแอปและส่งผลวิ่งได้ตามปกติ ระบบไม่ได้ปิดกั้นการเข้าร่วม";

export const NO_RISK_NOTE =
  "ไม่พบข้อบ่งชี้ที่ต้องพบแพทย์ก่อนเริ่มซ้อม — หากมีอาการผิดปกติระหว่างซ้อม ให้หยุดและปรึกษาแพทย์";
