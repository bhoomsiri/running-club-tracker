# Spec: Personal Health Record Dashboard — PTRH RunClub

เอกสารสำหรับ CC ใช้ implement · เขียนโดย architect · อ้างอิงโครงปัจจุบันบน `main`

> **rev 2 (หลัง CC review):** แก้ §3 (consent), §6 (scope=run ทั้งหมด + valid_runs_of + avg_pace
> + partial count), §7 (reuse `lib/bmi.ts`, ไม่ยก advisory มาหน้าแรก), §5 (clamp). migration = `0009`
>
> **rev 3 (เจ้าของเคาะ consent = ตัวเลือก A):** §3 กลับอีกครั้ง — **ไม่ gate** `/me/summary`
> (เจ้าตัวดูตัวเองเห็นเสมอ ทั้ง dashboard + /health) · consent gate ไปอยู่ฝั่งชมรม (admin ดูคนอื่น) แทน
>
> **rev 4:** เพิ่ม §11 — รูปโปรไฟล์จาก Clerk (`image_url`) สำหรับ dashboard/leaderboard
>
> **rev 5:** เพิ่ม §12 — ขอบเขต UI redesign (dashboard เท่านั้น) + reference mockup
>
> **rev 6:** เพิ่ม §13 — backfill re-scan รูปเก่าด้วย Gemini เติม calories/steps ให้ run เดิม
>
> **rev 7:** เพิ่ม §14 — backfill avatar จาก Clerk Backend API ให้สมาชิกที่สมัครก่อน `0010`
>
> **rev 8:** เพิ่ม §15 — ผลการรันจริง §13/§14 บน production + ข้อสรุปว่า**ห้าม**ทำ plausibility
> guard กับ calories/steps

---

## 1. เป้าหมาย

ปรับหน้า **personal dashboard** (`frontend/src/app/(app)/dashboard/page.tsx`) ให้แสดงผลแบบ
"Personal Health Record" (การ์ดเมตริกหลายใบ สไตล์ health-tracker) โดย **แสดงเฉพาะข้อมูลที่สมาชิก
ส่งเข้ามาจริง** — ไม่มีการสร้างตัวเลขปลอมมาเติมช่องว่าง (golden rule #4)

ขยายฟอร์มส่งผลวิ่งให้เก็บ **แคลอรี่ที่เผา** และ **จำนวนก้าว** เพิ่ม (optional) เพื่อป้อนการ์ดใหม่

**benchmark แคมเปญ (ระยะสะสม → 100 กม. + แต้ม) ยังอยู่** เป็นการ์ดเด่นบนหน้า

---

## 2. ขอบเขต (ยึดตามที่เจ้าของเลือก)

**ทำ:**

- Activity เพิ่มในฟอร์มวิ่ง: `calories_burned`, `steps` (optional ทั้งคู่)
- การ์ด dashboard จากข้อมูลจริง: benchmark แคมเปญ, ระยะสะสม, pace เฉลี่ย, เวลาวิ่งรวม,
  แคลอรี่ (รวม/ล่าสุด), ก้าว (รวม/ล่าสุด), จำนวนครั้งวิ่ง
- น้ำหนัก + BMI: **ดึงจาก `health_record` เดิม** (screening before/after) มาแสดง —
  **ไม่เก็บใหม่** BMI คำนวณ ณ ตอนอ่าน ไม่เก็บลง DB (ตามโดเมนเดิม `domain/health.py`)

**ไม่ทำ (ตัดออกชัดเจน):**

- ❌ % ไขมัน (body fat) — ไม่เก็บ ไม่แสดง
- ❌ หัวใจ / ความดัน เป็นการ์ดใหม่ (มีใน `health_record` แต่เจ้าของไม่ขอแสดงรอบนี้)
- ❌ การนอน / การดื่มน้ำ (lifestyle diary)
- ❌ ฟอร์ม "บันทึกสุขภาพแยก" ใหม่ — ใช้ตัว screening health-form เดิม ไม่สร้างเพิ่ม

---

## 3. PDPA — ทำไม consent v2 เดิมพอ (เขียนไว้ให้ DPO อ้างอิง)

หัวใจของเหตุผล: **ฟีเจอร์นี้ไม่ได้เก็บข้อมูลสุขภาพ (sensitive/มาตรา 26) ใหม่เลย**

1. **น้ำหนัก/BMI** = ข้อมูลที่เก็บใต้ consent v2 อยู่แล้ว (screening before/after) และแอป
   **แสดงให้เจ้าตัวดูอยู่แล้ว** ผ่าน `HealthComparisonResponse` (bmi_before/after/delta)
   หน้า dashboard เป็นเพียงการ **จัดแสดงข้อมูลเดิมให้อ่านง่ายขึ้น** ไม่ใช่วัตถุประสงค์ใหม่
   → อยู่ในขอบเขต consent v2
2. **แคลอรี่/ก้าว** = ข้อมูลกิจกรรม (activity/fitness) ไม่เข้านิยามข้อมูลสุขภาพอ่อนไหว
   มาตรา 26 → consent v2 ครอบคลุมการเก็บผลกิจกรรมอยู่แล้ว
3. **ไม่มีการเก็บ body fat / vitals ใหม่** = ไม่มีหมวดข้อมูลอ่อนไหวใหม่เข้ามา

**⚠️ แก้จาก rev 1 — consent gate อยู่คนละที่กับที่เข้าใจ (CC review):**

ข้อเท็จจริงบนโค้ดจริง: `/me/summary` (`GetMySummary`) **ไม่มี consent gate** โดยตั้งใจ —
docstring เขียนว่า "owner reading their own record — not admin access, not audited"
consent gate ตัวจริงอยู่ที่ **UI `health/consent-gate.tsx` บนหน้า `/health` เท่านั้น**
ไม่ได้อยู่ที่ API → ตอนนี้ `/me/summary` คืน health มาแบบไม่ผ่าน gate

ดังนั้นการย้ายน้ำหนัก/BMI มา dashboard = **พามันออกจากที่เดียวที่มี gate** ไปหน้าที่ไม่มี gate
ไม่ใช่ "อย่าข้าม gate เดิม" (rev 1 เข้าใจกลับด้าน)

**กติกาที่ถูกต้อง (rev 3 — เจ้าของเคาะ = A "เจ้าตัวเห็นเสมอ"):**

หลักการ: consent v2 คุม "สิทธิที่**ชมรม**จะเอาข้อมูลไปใช้" ไม่ใช่ "สิทธิที่**เจ้าตัว**จะดูข้อมูลตัวเอง"
การถอนยินยอมจึงหยุด**การประมวลผลฝั่งชมรม** แต่ไม่ลบสิทธิเข้าถึงข้อมูลตัวเอง (PDPA ม.30)

- **`/me/summary` (เจ้าตัวดูตัวเอง) — ไม่ต้อง gate** เจ้าตัวเห็นน้ำหนัก/BMI ตัวเองเสมอ ทั้ง
  dashboard และ /health คงพฤติกรรม `GetMySummary` เดิม (docstring "owner reading own record")
  ⚠️ **revert** consent-gate ที่เผลอ add ใน branch (a) + คืนเทส
  `test_the_owner_still_sees_their_data_after_withdrawing` ให้ assert เดิม
- **empty state ขึ้นเฉพาะ "ยังไม่เคยวัด"** (ไม่มี health_record) — **ไม่ใช่** "ถอนแล้ว"
  ห้ามโชว์ค่าว่าง/ศูนย์เป็นตัวเลข
- **ที่ต้อง gate จริงคือฝั่งชมรม** (flip side ที่ทำให้ "ถอน" มีความหมาย):
  - **admin ดูสุขภาพคนอื่น** (`ViewMemberHealth`, `may_view_others_health`) **ต้องเคารพการถอน** —
    ⚠️ เช็กว่าตอนนี้ gate ด้วย consent รึยัง ถ้าไม่ = ช่องจริงที่ต้องปิด (branch นี้หรือ follow-up)
  - **export** — เช็ก consent ต่อ member อยู่แล้ว (งานก่อน) ยืนยันว่ายังจริง
- golden rule #8: endpoint/logger **ห้าม log ค่าน้ำหนัก/BMI** เด็ดขาด

> หมายเหตุ DPO: ฟีเจอร์นี้ **ไม่** ผูกกับ `HEALTH_EXPORT_ENABLED` (นั่นคือการ export ข้อมูล
> ของทุกคนโดย admin — คนละเรื่อง) การแสดงข้อมูลตัวเองให้เจ้าตัวไม่ต้องรอ flag นั้น

---

## 4. โมเดลข้อมูล + migration

เพิ่มคอลัมน์ใน `run_entry` เท่านั้น — ไม่มีตารางใหม่:

```
calories_burned  int  NULL   CHECK (calories_burned  > 0 AND calories_burned  < 10000)
steps            int  NULL   CHECK (steps            > 0 AND steps            < 200000)
```

เหตุผลชนิดข้อมูล: แคลอรี่/ก้าวเป็น **จำนวนนับ (count)** ไม่ใช่ระยะ/แต้มที่เป็นเงิน →
ใช้ `int` ได้ ไม่ต้อง `Decimal` (golden rule #6 บังคับ Decimal เฉพาะ points/distance)

- migration alembic ใหม่: `ADD COLUMN ... NULL` + CHECK — ปลอดภัย ไม่ต้อง backfill
  (แถวเก่าเป็น NULL = "ไม่ได้บันทึก" ซึ่งถูกต้องตามความจริง)
- อัปเดต mapper (`adapters/persistence/mappers.py`) + `models.py` + domain `RunEntry`
  ให้ถือ 2 ฟิลด์นี้เป็น `int | None`

---

## 5. ฟอร์มส่งผลวิ่ง (`submit-run-form.tsx` + extraction)

**flow เดิม:** อัปโหลด screenshot → Gemini สกัด ระยะ+เวลา → ผู้ใช้ยืนยัน → submit

**เพิ่ม:**

1. **Gemini extraction** (`adapters/extraction/gemini_extractor.py`): สกัด `calories_burned`
   และ `steps` เพิ่ม **ถ้ามีในภาพ** — ไม่มีก็คืน `None` (rule #4: ไม่เดา ไม่กรอกมั่ว)
   - **clamp ค่าเกินจริงเหมือน distance/duration** (ดู `_to_draft` เดิม): output ของโมเดล =
     untrusted input ค่าเกินขอบเขต CHECK (calories ≤0 หรือ ≥10000, steps ≤0 หรือ ≥200000) → `None`
   - การเพิ่มฟิลด์ใน prompt **เปลี่ยนพฤติกรรมโมเดลกับฟิลด์เดิมด้วย** → ต้อง **รันเทสสกัด
     distance/duration ซ้ำ** ไม่ใช่แค่เทสฟิลด์ใหม่ (CC ตั้งข้อสังเกต — ถูก)
2. **ฟอร์ม**: ช่อง "แคลอรี่ (kcal)" และ "ก้าว" เป็น **optional** พรีฟิลจากค่าที่สกัดได้
   ผู้ใช้แก้/เว้นว่างได้ ป้ายกำกับชัดว่าไม่บังคับ
3. **API request** (`SubmitRunRequest` / `RunDraftResponse` ใน `schemas.py`):
   เพิ่ม `calories_burned: int | None`, `steps: int | None` พร้อม validation
   (`Field(default=None, gt=0, lt=10000)` / `lt=200000`)
4. **use case** `submit_run.py`: ส่งค่า 2 ตัวลง `RunEntry` — **ไม่กระทบ pace validation เดิม**
   (calories/steps ไม่เกี่ยวกับ 5–11 min/km ที่ flag อยู่)

---

## 6. API สำหรับ dashboard

`/me/summary` (→ `MemberSummaryResponse`) ปัจจุบันมี `total_distance_km` + `health:
list[HealthComparisonResponse]` อยู่แล้ว → ต่อยอดจากตัวนี้ อย่าสร้าง endpoint ซ้ำซ้อน

เพิ่ม **aggregate ฝั่ง activity** เข้า `MemberSummaryResponse`

**scope (แก้จาก rev 1 — CC review):** คิดจาก **run ทั้งหมดของสมาชิก** ผ่าน `valid_runs_of()`
(ตัด rejected) — **ชุดเดียวกับ `total_distance_km` ที่มีอยู่** ห้าม window ตามแคมเปญ ไม่งั้นจะมี
เลขสองนิยาม (all-runs vs campaign) นั่งบนจอเดียวกัน · benchmark เท่านั้นที่คิดตาม window แคมเปญ

```
run_count            int
total_calories       int          # sum เฉพาะ run ที่มีค่า
calories_from_runs   int          # จำนวน run ที่มี calories (คู่กับ total → "จาก N ใน run_count")
total_steps          int
steps_from_runs      int
avg_pace_min_per_km  Decimal | None   # = เวลารวม ÷ ระยะรวม (ของ valid runs) ไม่ใช่ mean ของเพซรายครั้ง
active_seconds       int          # sum duration ของ valid runs
latest_run           { date, distance_km, pace, calories_burned?, steps? } | None
```

กติกา aggregate:

- **avg_pace = Σduration ÷ Σdistance** (ตรงกับความหมาย "เพซเฉลี่ย" ของนักวิ่ง + สอดคล้อง aggregate)
  ไม่ใช่ค่าเฉลี่ยของ pace รายครั้ง (ได้เลขคนละตัว)
- **total_calories/steps ตอนมีข้อมูลบางส่วน** — ส่ง `*_from_runs` (count) มาด้วยเสมอ ให้ frontend
  เขียน "รวมจาก 3 ใน 12 ครั้งที่บันทึก" ห้ามโชว์ยอดรวมลอยๆ ราวกับครบทุก run (rule #4)
- ไม่มี run เลย → นับได้เป็น 0 ตามจริง, `avg_pace=None`, `latest_run=None`
  → frontend โชว์ empty state ไม่ใช่เลขปลอม

---

## 7. หน้า Dashboard — mapping การ์ด → แหล่งข้อมูลจริง

จับคู่จาก reference (Seehats) → ข้อมูลจริงที่เรามี · การ์ดไหนไม่มีข้อมูล = empty state

| การ์ด | แหล่งข้อมูลจริง | ไม่มีข้อมูล → |
|---|---|---|
| **Benchmark แคมเปญ** (เด่นสุด) | total_distance_km / 100km + แต้ม | โชว์ 0/100 ตามจริง |
| ระยะสะสม | total_distance_km | 0 กม. |
| Pace เฉลี่ย | avg_pace_min_per_km | "ยังไม่มีผลวิ่ง" |
| เวลาวิ่งรวม | active_seconds | 0 |
| แคลอรี่ (รวม + ล่าสุด) | total_calories / latest_run.calories | "ยังไม่ได้บันทึก" |
| ก้าว (รวม + ล่าสุด) | total_steps / latest_run.steps | "ยังไม่ได้บันทึก" |
| จำนวนครั้งวิ่ง | run_count | 0 |
| **น้ำหนัก + BMI** (+ band กลางๆ) | health comparison (before/after/delta) — **consent-gated** | ไม่มี/ถอน consent → "ยังไม่มีข้อมูลสุขภาพ" |

> **ป้ายช่วงบนการ์ด (§6):** การ์ด activity ทั้งหมด = "ทั้งหมด" · benchmark = "แคมเปญ 15 ส.ค.–30 ก.ย."
> ต้องเขียนกำกับให้ผู้ใช้รู้ว่าเลขไหนคือช่วงไหน ป้องกันเข้าใจผิดว่าเป็นนิยามเดียวกัน

**เรื่อง badge BMI (แก้ rev 1 — มีของอยู่แล้ว + ประเด็นจริยธรรม):**

- **reuse `frontend/src/lib/bmi.ts`** — มี `BMI_BANDS` เกณฑ์เอเชีย (`<18.5 / 18.5–22.9 /
  23–24.9 / ≥25`) + `bandFor()` + `shouldSeeADoctor()` อยู่แล้ว **ห้ามเขียนเกณฑ์ใหม่**
- การ์ด dashboard โชว์แค่ **ตัวเลข + band กลางๆ** (จาก `bandFor()`) — **ไม่ยกประโยค advisory
  "แนะนำให้พบแพทย์" (`shouldSeeADoctor()`) มาหน้าแรก** ประโยคนั้นคงไว้ที่ `bmi-scale.tsx`
  บนหน้า `/health` ที่ผู้ใช้ตั้งใจเข้าไปดูเท่านั้น (หน้าแรกที่เปิดเจอทุกครั้ง = informational
  ไม่ใช่ diagnostic — สำคัญเป็นพิเศษเพราะเป็นชมรมของโรงพยาบาล)
- การ์ดมีลิงก์ "ดูรายละเอียดสุขภาพ" → `/health` สำหรับภาพเต็ม + advisory
- การ์ดนี้ขึ้นเฉพาะเมื่อ consent v2 ยัง active (ดู §3) — ถอน/ไม่มี = empty state

**น้ำหนัก/BMI ไม่ใช่ time-series:** มีแค่ before/after (2 จุด) + delta เท่านั้น —
ออกแบบการ์ดให้โชว์ "ค่าล่าสุด + การเปลี่ยนแปลงจากตอนเริ่ม" ไม่ใช่กราฟหลายจุด
(ถ้ายังมีแค่ before → โชว์ค่าเริ่มต้นเฉยๆ ไม่มี delta)

---

## 8. Golden rules / gates ที่ CC ต้องผ่าน

- **#4 ไม่เดา**: ทุกการ์ดที่ไม่มีข้อมูล = empty state ห้ามเลข 0 ปลอมหรือ placeholder
- **#6 Decimal**: distance/points คง Decimal; calories/steps เป็น int count (โอเค)
- **#8 ไม่ log ค่าสุขภาพ**: endpoint/summary ห้าม log weight/BMI
- **BMI คำนวณ ณ อ่าน** ไม่เก็บ (คงพฤติกรรม `domain/health.py`)
- **consent gate เดิม**: การอ่านน้ำหนัก/BMI ใช้ use-case เดิมที่ผ่าน consent — ไม่เปิดช่องใหม่
- gates ปกติ: ruff, mypy, pytest เขียว + เพิ่ม test: extraction คืน None เมื่อไม่มีในภาพ,
  submit รับ/เก็บ calories+steps, summary aggregate ถูกเมื่อบาง run เป็น None,
  dashboard empty state เมื่อไม่มี health/ไม่มี run

---

## 9. การตัดสิน (ปิดหลัง CC review — rev 2)

1. **HR card** — ❌ ไม่ทำ (เจ้าของไม่เลือก vitals)
2. **Gemini optional calories/steps** — ทำ + clamp + รันเทสสกัด distance/duration ซ้ำ (ดู §5)
3. **window** — activity = run ทั้งหมด (valid_runs_of), benchmark = campaign, ติดป้ายช่วง (ดู §6/§7)
4. **rejected runs** — aggregate ใช้ `valid_runs_of()` ชุดเดียวกับ summary
5. **consent เมื่อถอน (rev 3 = A)** — `/me/summary` ไม่ gate เจ้าตัวเห็นเสมอ · gate ฝั่งชมรม
   (admin ดูคนอื่น) แทน · revert gate ที่ add ใน branch (a) (ดู §3) ← จุดสำคัญสุด
6. **BMI advisory** — reuse `lib/bmi.ts`, ไม่ยก "พบแพทย์" มาหน้าแรก (ดู §7)
7. **avg_pace** — เวลารวม ÷ ระยะรวม · **partial total** — ส่ง count คู่ ("จาก N ใน M ครั้ง")
8. **ลำดับงาน** — 2 branch: (a) backend (migration+extraction+API+aggregate+**consent gate**)
   merge ก่อน → (b) frontend (ฟอร์ม 2 ช่อง + redesign dashboard)

---

## 10. สรุปสั้นสำหรับ commit แรก

```
feat: personal health record dashboard
- run_entry += calories_burned, steps (nullable int + CHECK)   [migration 0009]
- gemini extraction: optional calories/steps (clamped; re-test distance/duration)
- submit form + schemas: optional 2 fields
- /me/summary: activity aggregates over valid_runs_of (all runs) + *_from_runs count
  + latest_run; avg_pace = Σtime ÷ Σdist
- /me/summary health: NOT gated — owner always sees own (rev 3 = decision A);
  consent gate belongs on club-side admin view instead (verify ViewMemberHealth respects withdrawal)
- dashboard redesign: real-data cards + empty states, period labels, benchmark retained
- weight/BMI reuse existing consent-v2 health_record; band via lib/bmi.ts,
  no "see a doctor" advisory on home (stays on /health)
```

---

## 11. รูปโปรไฟล์จาก Clerk (avatar) — rev 4

ใช้รูปที่มากับบัญชี Clerk ตอนสมัคร ไม่ต้องสร้างฟีเจอร์อัปโหลดรูปใหม่

- Clerk ให้ `image_url` (+ `has_image`) กับทุก user — สมัคร **Google/LINE** มักได้รูปจริงจาก
  provider ติดมา, สมัครอีเมลล้วนอาจเป็นรูป default (`has_image=false`)
- **แหล่ง = Clerk webhook** (`user.created` / `user.updated`) → sync `image_url` + `has_image`
  ลง member record · เข้ากฎ "identity มาจาก webhook ที่ verify แล้ว" · migration เพิ่ม
  `image_url text NULL` (+ `has_image bool` ถ้าต้องแยกรูปจริง/default) · sync `user.updated`
  เมื่อสมาชิกเปลี่ยนรูป
- **avatar ตัวเอง** (topbar/โปรไฟล์): ใช้ Clerk client SDK ตรงๆ ได้ หรือใช้ field ที่ sync — เลือก source เดียว
- **leaderboard/คนอื่น:** ต้องใช้ `member.image_url` ที่ sync ไว้ (client ดึงรูปคนอื่นจาก Clerk ไม่ได้)
  → เพิ่ม `image_url` (+ ชื่อ) ใน leaderboard entry — **ขยาย payload ที่เดิมตั้งใจ minimal**
- **frontend:** `<img>` จาก `img.clerk.com` → เพิ่ม host ใน `next.config` images / CSP ·
  **fallback = avatar อักษรย่อ** เมื่อ `has_image=false` หรือ url ว่าง
- **PDPA:** leaderboard เดิมเปิดแค่ ชื่อ+ระยะ (ตั้งใจ) — ใส่รูป = โชว์หน้าสมาชิกทุกคนทั้งชมรม
  ชื่อก็ระบุตัวตนอยู่แล้ว + ชมรมวิ่งใส่รูปเป็นปกติ แต่เป็น exposure ที่เพิ่มขึ้น →
  แนะนำ **opt-out ซ่อนรูปตัวเองในโปรไฟล์** เป็น fast-follow (ไม่บล็อกรอบแรก)
- **ขอบเขต:** ต้องมี backend เล็กน้อย (webhook sync + migration + leaderboard schema) — ทำใน branch (b)
  หรือแตก branch ย่อยก็ได้

---

## 12. ขอบเขต UI redesign (rev 5)

- **redesign สไตล์ Seehats + teal = หน้า `dashboard` เท่านั้น** — cards/charts (bar 7 วัน + sparkline เพซ)/
  อันดับสะสมระยะ + avatar/สุขภาพ + banner ข่าว (มีรูป/ไม่มีรูป) + ปุ่ม CTA ส่งผลวิ่ง
- **shell ที่ใช้ร่วมทั้งแอป** ((app)/layout): sidebar **พับ/ขยายได้** (เดสก์ท็อป←→ไอคอน, มือถือ drawer),
  ปุ่ม **ส่งผลวิ่ง = primary**, **แยกลิงก์แอดมิน** ไป `/admin` (มี layout เมนูของตัวเอง) — โผล่ทุกหน้า
- **หน้าอื่นคงเดิม:** ส่งผลวิ่ง / ผลวิ่ง / ข่าวประชาสัมพันธ์ / รางวัล / โปรไฟล์ / แอดมิน — เนื้อหา+หน้าตาเดิม
  ไม่ redesign รอบนี้ (ค่อยทยอยปรับตามสไตล์ทีหลังถ้าต้องการ)
- **reference:** `phr-dashboard-mockup.html` (visual target ของ branch b) — ข้อมูลใน mockup เป็น mock
  แต่ทุก field ผูกกับ `/me/summary` / leaderboard จริง

---

## 13. Backfill: re-scan รูปเก่าด้วย Gemini (เติม calories/steps ให้ run เดิม) — rev 6

**Forward (มีใน §5 แล้ว):** หน้าส่งผลวิ่งเพิ่มช่อง calories/steps · Gemini สกัดเพิ่ม → **auto-fill ถ้าเจอ
ในรูป** ผู้ใช้แก้/เว้นว่างได้ (backend พร้อมแล้วบน prod)

**Backfill (ของใหม่):** run เดิมที่ `calories_burned`/`steps` = NULL และ **มีรูป evidence** →
สคริปต์ re-scan รูปด้วย Gemini (ตัวสกัด + clamp ตัวเดียวกับ forward) เจอก็ `UPDATE` เติมค่า
→ dashboard โชว์ผ่าน aggregate เดิม (`total_*` + `*_from_runs`)

**Guardrails (แพตเทิร์นเดียวกับ `flag_implausible_pace.py`):**

- `--expect-host` prod guard · **dry-run default** · batch · idempotent
- **เฉพาะ NULL → ค่า เท่านั้น** — ห้ามทับค่าที่ผู้ใช้กรอก/ยืนยันเอง
- **แตะแค่ `calories_burned` / `steps`** — ❌ ห้าม re-extract distance/duration (ผู้ใช้ยืนยันตอนส่งแล้ว
  เขียนทับ = เปลี่ยนผล/แต้ม/pace) · ❌ ไม่แตะ `review_status` / points / pace
- เจอไม่ครบ / อ่านไม่ได้ = ปล่อย NULL (rule #4 ไม่เดา) · clamp ช่วง CHECK (untrusted output)
- **rule #8:** ไม่ log รูปหรือค่าที่สกัดได้
- รายงานท้ายรัน: สแกนกี่รูป · เติม calories กี่แถว · steps กี่แถว · อ่านไม่เจอกี่แถว

**PDPA:** re-process รูป evidence เดิมเพื่อดึง activity เพิ่ม (แคลอรี่/ก้าว = ไม่ sensitive) เพื่อ dashboard
ของเจ้าตัว = วัตถุประสงค์เดียวกับตอนเก็บรูป (ติดตามการวิ่ง) → อยู่ในขอบ consent v2 · ไม่ใช่ข้อมูลสุขภาพ

**ขอบเขต:** backend script + Gemini batch (ราว ~145 รูปเดิม) — แตก branch ย่อย เช่น
`chore-backfill-activity` ทำหลัง (b) ได้ (ไม่บล็อก UI) · รันจริงครั้งเดียว (run ใหม่ได้ค่าตอนส่งอยู่แล้ว)

---

## 14. Backfill: avatar จาก Clerk ให้สมาชิกเดิม — rev 7

**ปัญหา:** `member.image_url` / `has_image` มาพร้อม migration `0010` และเขียนโดย **webhook
ที่ verify แล้วเท่านั้น** (`user.created` / `user.updated`) สมาชิกที่สมัครก่อนหน้านั้นจึงเป็น
`NULL` / `false` และจะไม่มีอะไรไปเปลี่ยนจนกว่าเขาจะบังเอิญไปแก้โปรไฟล์ที่ Clerk

**สคริปต์:** `backend/scripts/backfill_avatars.py` — ถาม Clerk ทีละคน
`GET https://api.clerk.com/v1/users/{clerk_user_id}` แล้วเติม 2 คอลัมน์นั้น ครั้งเดียวจบ
**หลังจากนี้ ongoing updates มาจาก webhook เหมือนเดิม** สคริปต์นี้ไม่ใช่ sync path ที่สอง

**กฎเดียวกับ webhook เป๊ะ (ห้ามเขียนใหม่):**

- `has_image = data.get("has_image") is True` — **strict** ไม่ใช่ truthy · อ่านไม่ออก = false
  ("ไม่รู้" ต้องไม่กลายเป็น "ใช่ นั่นรูปเขา")
- **เก็บ `image_url` เฉพาะเมื่อ `has_image=true`** — Clerk ให้ URL กับทุกบัญชี และชี้ไปที่รูป
  default ของคนที่ไม่เคยตั้ง เก็บไว้ = เอาสไตล์คนอื่นไปแปะคนที่ไม่ได้เลือกอะไร (เหตุผลเดียวกับที่
  `0010` แยกเป็น 2 คอลัมน์ และที่ `_avatar()` ใน `get_leaderboard.py` คืน None)

**Guardrails (แพตเทิร์นเดียวกับ `flag_implausible_pace.py`):**

- `--expect-host` prod guard · **dry-run default** · verification gate ต่อแถว → COMMIT/ROLLBACK
- **แตะแค่ `image_url` / `has_image`** — ❌ ไม่แตะ `display_name` (เจ้าตัวเป็นเจ้าของ webhook เขียนได้
  แค่ตอน INSERT) ❌ ไม่แตะ role/profile/อะไรอื่นบนแถว
- **ถามทุกคน อัปเดตเฉพาะแถวที่ค่าต่าง** → idempotent จริง (รันซ้ำเขียน 0 แถว) และแก้เคสคนที่เปลี่ยนรูป
  ไปก่อน webhook จะมีด้วย · ~40 คน ยังไงก็ ~40 request
- Clerk 404 (ลบบัญชีไปแล้ว) = นับ "not found" ปล่อยแถวไว้เฉยๆ · 429/5xx retry 2 ครั้ง · error อื่น
  นับแล้วไปต่อ (คนเดียวล่มต้องไม่ทำให้อีก 39 คนอด)
- rate-limit friendly: หน่วง 0.15s/request
- **ไม่ log URL และไม่ log key** — รายงานเป็นจำนวน ไม่ใช่ว่าใครหน้าตายังไง · error จาก Clerk print
  แค่ status code (body อาจ echo request ซึ่งมี key ติดไปด้วย)

**⚠️ secret ที่ต้องใช้ ยังไม่มีในระบบ:** ที่ migrate เข้า Secret Manager คือ
`clerk-webhook-secret` = **svix signing secret** ใช้ verify webhook — **เรียก Backend API ไม่ได้**
สคริปต์ต้องใช้ **Clerk Secret Key (`sk_live_...`)** คนละตัว

สคริปต์อ่านจาก env `CLERK_SECRET_KEY` ตอนรัน **ไม่ใส่ใน `Settings` และไม่ต้องเข้า Secret Manager** —
service ตอนรันใช้ JWKS verify token + svix verify webhook ไม่ได้ต้องการ Backend API key เลย
และ key ที่อ่าน user ได้ทั้ง instance ไม่ควรนั่งอยู่ใน config ของ service ที่ไม่ได้ใช้มัน
(one-off script รันจากเครื่อง maintainer แบบเดียวกับ `clear_test_data.py`)

**รายงานท้ายรัน:** ถามกี่คน · ตอบกลับกี่คน · มีรูปจริงกี่คน · default กี่คน · ไม่พบที่ Clerk กี่คน ·
อ่านไม่ได้กี่คน · จะเปลี่ยนกี่แถว

**PDPA:** ดึงรูปที่สมาชิกตั้งไว้เองที่ Clerk มาแสดงในแอปชมรม = วัตถุประสงค์เดียวกับฟีเจอร์ avatar
(§11) ที่ launch ไปแล้ว ไม่ใช่หมวดข้อมูลใหม่ ไม่ใช่ข้อมูลอ่อนไหว · ยังค้าง fast-follow เดิมจาก §11:
**opt-out ซ่อนรูปตัวเองบน leaderboard**

**ขอบเขต:** `chore-backfill-avatars` — script อย่างเดียว ไม่มี migration ไม่แตะโค้ดแอป
## 15. ผลการรันจริง + ข้อสรุปที่ได้ — rev 8

### §14 avatar (รันแล้ว 29 ส.ค. 2569)

```
asked 40 · answered 39 · has a picture 35 · default only 4 · not found at Clerk 1
updated 35 rows · verification passed
invariant (has_image=false AND image_url IS NOT NULL) = 0
```

**ค้าง:** 1 member row ที่ Clerk ไม่รู้จักแล้ว → คนนั้นล็อกอินไม่ได้ ควรตามว่าเป็นใครและตั้งใจไหม
(ถ้าเป็นคนที่ลบบัญชีเอง = PDPA erasure ที่ทำไม่ครบ)

**บั๊กที่เจอตอนรันจริง (แก้แล้ว ควรจำไว้ใช้กับสคริปต์ตัวอื่น):**

- `.env` **ไม่เข้า `os.environ`** — pydantic-settings อ่านเข้า `Settings` เท่านั้น สคริปต์ที่อ่าน
  `os.environ` ตรงๆ ต้องเรียก `load_dotenv()` เอง
- **`api.clerk.com` อยู่หลัง Cloudflare และบล็อก `User-Agent: Python-urllib/*` ทิ้ง** → 403 (error 1010)
  ทุก request ก่อนถึง Clerk ต้องตั้ง UA ชื่อจริงเสมอ
- **อย่าปิดบัง error body** — เดิมพิมพ์แค่ status code เพราะกลัว body echo key (ซึ่ง**เป็นไปไม่ได้** —
  response ไม่มี request header) ผลคือ 403 ×40 ที่ดูเหมือน key พัง ทั้งที่คำตอบอยู่ใน body

### §13 activity (รันแล้ว 30 ส.ค. 2569)

```
candidates 115 (147 runs − 32 rejected) · scanned 115 · calories 86 · steps 37
nothing in the image 27 · could not be read 0 · 6 batches, all committed
rejected rows touched 0 · values outside CHECK 0 · run_entry total unchanged
```

**บั๊ก:** SQLAlchemy 2.0 **autobegin** — statement แรกเปิด transaction เอง สคริปต์ที่อ่าน baseline
ก่อนเข้าลูป batch ต้อง `connection.rollback()` ปิดก่อน ไม่งั้น `connection.begin()` ของ batch แรกชน

### ⚠️ ข้อสรุปสำคัญ: **ห้ามทำ plausibility guard สำหรับ calories/steps**

หลังรันเสร็จพบค่าที่ดู "เป็นไปไม่ได้ทางสรีระ" 7 ใบ:

| | ค่า | ที่ควรเป็น |
|---|---|---|
| ก้าว 1 ใบ | 4.20 กม. / 2,978 ก้าว = stride **141 ซม.** | 70–80 ซม. ที่เพซ 7:22 |
| kcal 3 ใบ (คนเดียวกัน) | **20–29** kcal/km | ~55–80 |
| kcal 3 ใบ (คนเดียวกัน) | **117–130** kcal/km | ~55–80 |

**เปิดรูปเทียบทุกใบแล้ว — Gemini อ่านถูกหมด** ตัวเลขพวกนั้นคือสิ่งที่แอปของสมาชิกแสดงจริง
(ตัวนับก้าวจับไม่ครบ / แอปคนละยี่ห้อรายงาน active vs total calories)

จึง **ห้ามเพิ่ม guard แบบ `domain/pace.py` กับ 2 ฟิลด์นี้** เหตุผล:

> **pace flag ได้เพราะมีตัวตรวจสอบไขว้** — ระยะกับเวลาสมาชิกยืนยันมาทั้งคู่ อัตราส่วนเพี้ยน =
> ตัวใดตัวหนึ่งผิดแน่นอน
> **calories/steps เป็นค่าเดี่ยวที่อุปกรณ์รายงานมา ไม่มีอะไรให้ไขว้** — การ flag มันคือการที่แอปเรา
> ไปเถียงกับนาฬิกาของสมาชิก ซึ่งผิดกว่าปล่อยผ่าน

CHECK เดิม (0–10000, 0–200000) กว้างพอดีแล้ว: กันค่าเพี้ยนสุดขั้วโดยไม่ตัดสินสรีระของใคร

### ⚠️ ยังค้าง: golden rule #3

backfill **auto-commit ค่าที่ AI อ่าน** ซึ่งขัดกฎข้อ 3 ("Never auto-commit AI-read values") ตรงๆ
เจ้าของอนุมัติเป็นราย ๆ ไป และรอบนี้ผ่านการ spot-check ด้วยตาแล้ว **แต่ยังไม่มีทางแก้ค่าย้อนหลัง** —
ไม่มี use case ไหนอัปเดต `calories_burned`/`steps` หลังส่ง สมาชิกและแอดมินแก้เองไม่ได้ ต้องแก้ผ่าน SQL
ถ้าจะ backfill ด้วย AI อีกในอนาคต ควรมีทางแก้ก่อน
