# Spec: Personal Health Record Dashboard — PTRH RunClub

เอกสารสำหรับ CC ใช้ implement · เขียนโดย architect · อ้างอิงโครงปัจจุบันบน `main`

> **rev 2 (หลัง CC review):** แก้ §3 (consent — สมมติฐานเดิมกลับด้าน), §6 (scope = run ทั้งหมด
> + valid_runs_of + avg_pace + partial count), §7 (reuse `lib/bmi.ts`, ไม่ยก advisory มาหน้าแรก),
> §5 (clamp calories/steps). migration ถัดไป = `0009`

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

**กติกาที่ถูกต้อง — gate ที่ backend:**

- ส่วน `health` ที่ dashboard ใช้ ต้องถูก **กรองด้วย consent v2 ที่ยัง active เท่านั้น**
  สมาชิกที่ **ถอน / ไม่เคยยินยอม** → **ไม่ส่งค่า health ออกจาก server** (หยุดประมวลผลที่ต้นทาง
  ตาม [[consent-and-audit-policy]] "ถอนแล้วหยุดประมวลผลโดยไม่ลบ") — ดีกว่าซ่อนที่ frontend
- นี่คือการ **ปิดช่องที่มีอยู่เดิม** (summary คืน health ไม่ดู consent) ให้ถือเป็นส่วนหนึ่งของฟีเจอร์นี้
  ⚠️ ต้องเช็กว่าหน้า `/health` เดิมอ่าน health จาก path ไหน — ถ้าใช้ `GetMySummary` ร่วมกัน
  ต้องไม่ทำหน้า `/health` พัง (มันมี consent-gate ของตัวเองอยู่แล้ว) แนะนำแยก field/flag ให้ชัด
- ไม่มี health_record / ไม่ยินยอม / ถอนแล้ว → การ์ดน้ำหนัก/BMI ขึ้น **empty state** เป็นกลาง
  ("ยังไม่มีข้อมูลสุขภาพ" / ลิงก์ไปยินยอมที่ `/health`) ห้ามโชว์ค่าว่าง/ศูนย์เป็นตัวเลข
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
5. **consent เมื่อถอน** — gate ที่ backend, ถอน/ไม่มี = ไม่ส่ง health ออก (ดู §3) ← จุดสำคัญสุด
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
- /me/summary health: consent-gated (withdrawn/none → not emitted)   ← closes existing gap
- dashboard redesign: real-data cards + empty states, period labels, benchmark retained
- weight/BMI reuse existing consent-v2 health_record; band via lib/bmi.ts,
  no "see a doctor" advisory on home (stays on /health)
```

