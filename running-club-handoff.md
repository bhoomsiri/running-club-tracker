# Running Club App — สรุปการออกแบบ (Handoff)

เอกสารนี้สรุปทุกอย่างที่ตัดสินใจไว้ สำหรับเอาไปคุยต่อใน Cowork / Claude Code
โดยไม่ต้องเล่าใหม่ตั้งแต่ต้น

---

## 1. โปรเจกต์คืออะไร

เว็บสำหรับสมาชิกชมรมวิ่ง (~100 คน) ส่งผลวิ่งเก็บระยะสะสม มีระบบกิจกรรมที่เปลี่ยน
รูปแบบได้ทุกปี

- **ปีนี้มี 2 กิจกรรม:** สะสมระยะ 100 กม. + วิ่งแลกของรางวัล
- **เก็บข้อมูลสุขภาพ** before/after กิจกรรม (ข้อมูลอ่อนไหวภายใต้ PDPA)
- **เป้าหมาย:** เว็บเร็ว เสถียร โค้ดไม่เยอะ ดูแลคนเดียวได้

ลำดับความสำคัญ: **ถูกต้อง → ปลอดภัย → เร็ว/เสถียร → โค้ดน้อย**

---

## 2. Stack

| ชั้น | เลือก |
|---|---|
| Frontend | Next.js (App Router) + TypeScript + Tailwind |
| Auth | Clerk (`@clerk/nextjs` + `clerk-backend-api`) |
| Backend | FastAPI (Python 3.12) |
| ORM / migrate | SQLAlchemy 2.x + Alembic |
| DB | PostgreSQL |
| Object storage | S3-compatible: Cloudflare R2 (prod) / MinIO (local) via boto3 |
| AI vision | Gemini (`google-genai`) — อ่านสกรีนช็อต → pre-fill |
| Test / lint | pytest, ruff, mypy |
| CI/CD | GitHub Actions |

---

## 3. สถาปัตยกรรม — Hexagonal (Ports & Adapters) + SOLID

Dependency ชี้เข้าใน: `api → adapters → application → domain`

| Layer | มีอะไร | import ได้ |
|---|---|---|
| `domain` | entity + business rule | stdlib เท่านั้น |
| `application` | ports (Protocol) + use cases | `domain` + stdlib |
| `adapters` | DB / Clerk / storage / AI จริง | อะไรก็ได้ (framework อยู่ที่นี่) |
| `api` | FastAPI routers, DTO, wiring | `application`, `adapters`, framework |

**กฎเหล็ก:** `domain/` และ `application/` ห้าม import fastapi/sqlalchemy/boto3/google
เช็คด้วย `grep -rn "import fastapi\|import sqlalchemy" app/domain app/application` → ต้องว่าง

SOLID mapping:
- **S** — 1 use case = 1 action = 1 ไฟล์
- **O** — เพิ่มฟีเจอร์ = เพิ่มไฟล์ ไม่แก้ของเดิม
- **L** — fake repo (test) กับ SQLAlchemy repo (prod) สลับได้เพราะทำตาม port เดียวกัน
- **I** — port เล็ก แยก (RunRepository / Clock / ImageStorage)
- **D** — use case พึ่ง Protocol ไม่พึ่ง concrete

---

## 4. เรื่อง "แยกตามปี" — ปีคือ data ไม่ใช่ code

**อย่า** fork โฟลเดอร์เป็น `2569/`, `2570/` (ซ้ำโค้ด ละเมิด OCP)

ใช้โมเดล 2 ชั้น **Season → Campaign** + **Strategy pattern**:

- `Season` = จัดกลุ่มตามปี
- `Campaign` = กิจกรรมจริง มี `type` (ชี้ไป policy) + `config` (พารามิเตอร์ เช่น goal_km)
- `CampaignPolicy` = interface กำหนด "1 run นับเป็นอะไร" + "รวมแล้ว progress เป็นยังไง"

**ปีหน้าเกิดอะไร:**

| สถานการณ์ | ต้องทำ |
|---|---|
| กิจกรรมปีใหม่ รูปแบบเดิม | insert row → **โค้ด 0 บรรทัด** |
| รูปแบบใหม่หมด | เพิ่ม enum + policy 1 ไฟล์ + registry 1 บรรทัด |
| ของเดิม | ไม่แตะ |

**progress คำนวณจาก run ตอนอ่าน** (run = source of truth เดียว ไม่มีตาราง progress ให้ตกหล่น)
ห้าม `if/elif` เช็ค `campaign.type` นอก registry

---

## 5. ส่งผลวิ่ง — 2 ทางบรรจบจุดเดียว

ทั้งคู่จบที่ `RunEntry` + ภาพหลักฐาน ต่างแค่วิธี fill:

- **ใช้แอป track** → อัปสกรีนช็อต → Gemini อ่าน → **pre-fill ฟอร์ม** → คนตรวจ/แก้ → ยืนยัน
- **ไม่ใช้แอป** → ถ่ายรูปตอนวิ่ง → กรอกเอง → ยืนยัน

**กฎเหล็ก: AI แค่ pre-fill คนกดยืนยันคือ source of truth** ห้าม auto-commit ค่าที่ AI อ่าน
อ่านไม่ชัด → คืน `null` + warning ไม่ปั้นเลข

**3 endpoint แยกหน้าที่:**
```
POST /runs/evidence   รูป → {image_key}  (เก็บรูป + hash, ทั้ง 2 ทางใช้)
POST /runs/extract    {image_key} → draft (Gemini อ่าน, ทาง AI เท่านั้น)
POST /runs            {data, image_key, source} → สร้าง RunEntry
```

---

## 6. กันโกง / Sanity / Audit

- **hash 2 ระดับ:** คนเดิมส่งรูปเดิม = block, คนละคนใช้รูปเดียวกัน = flag ให้ admin ดู
- **sanity rules** (อิงคนวิ่งจริง): reject เฉพาะที่เป็นไปไม่ได้ (ระยะ≤0, อนาคต) ที่เหลือ
  flag `needs_review` ไม่ปฏิเสธ — เกณฑ์เช่น pace < 2:30/กม., > 50 กม./ครั้ง, > 6 ชม./ครั้ง
  ค่าเก็บใน config ปรับได้ไม่แก้โค้ด
- **audit:** เก็บทั้ง JSON ดิบที่ AI อ่าน (`run_extraction`) คู่กับค่าที่คนยืนยัน

---

## 7. Database — PostgreSQL ตัวเดียว (~11 ตาราง)

`member`, `consent`, `season`, `campaign`, `run_entry`, `run_extraction`,
`points_ledger`, `reward_item`, `redemption`, `health_record`, `audit_log`

**หลักที่ใช้:**
- **แต้มเป็น ledger** (`balance = SUM(delta)`) ไม่ใช่ column — แลกของทำใน transaction เดียว
  กัน double-spend
- **`numeric` ไม่ใช่ float** สำหรับค่าที่กระทบรางวัล (ระยะ/แต้ม/ราคา)
- **`jsonb`** สำหรับ config กิจกรรม + JSON ที่ AI อ่าน
- **BMI ไม่เก็บ** derive ตอนอ่าน
- **รูปไม่เก็บใน Postgres** — เก็บใน object storage, DB เก็บแค่ `evidence_key` + `sha256`
- health data **แยกตาราง** จำกัดสิทธิ + audit ทุกการเข้าถึง

---

## 8. PDPA — ข้อมูลสุขภาพ = ข้อมูลอ่อนไหว (ม.26)

1. **consent ก่อนเก็บ** — เขียน health_record ไม่ได้ถ้าไม่มี consent active (gate ใน use case + UI)
2. **data minimization** — เก็บเฉพาะ field ที่เปรียบเทียบ before/after จริง
3. **แยก + จำกัดสิทธิ** — เจ้าตัว + admin เท่านั้น, admin เปิดดู = เขียน audit_log
4. **สิทธิเจ้าของข้อมูล** — export / แก้ / ถอน consent / ขอลบ (soft delete → hard delete หลัง grace)
5. **retention** — กำหนดระยะเก็บ + cron purge
6. **เข้ารหัส** — at-rest (Neon/R2) + HTTPS

---

## 9. Security — 8 ข้อที่ต้องฝังในโค้ด

| # | ข้อ | สถานะ |
|---|---|---|
| 1 | verify Clerk **webhook signature** (svix) | ต้องเพิ่ม |
| 2 | **admin role** ดู health + audit ทุกการเข้าถึง | ต้องเพิ่ม |
| 3 | กรอง upload: magic bytes + size limit + private bucket + presigned expiry | ต้องเพิ่ม |
| 4 | **strip EXIF** จากรูป (กัน GPS รั่ว) | ต้องเพิ่ม |
| 5 | **CORS ล็อก** โดเมน frontend | ต้องเพิ่ม |
| 6 | **rate limiting** เน้น `/runs/extract` | ต้องเพิ่ม |
| 7 | **pip-audit + Dependabot** ใน CI | ต้องเพิ่ม |
| 8 | **ห้าม log** ข้อมูลอ่อนไหว (token/health/email) | ต้องเพิ่ม |

**มีแล้วจากดีไซน์:** member_id จาก token (กัน IDOR), ledger transaction (กัน double-spend),
hash dedup, sanity rules, consent-gate, validate ที่ entity, prompt-injection ปลอดภัยเพราะ
AI แค่ pre-fill

**ให้น้ำหนักสูงสุด:** #1, #2, #8 — แตะข้อมูลสุขภาพตรง ๆ พลาดแล้วผิด PDPA

---

## 10. Infra & Deploy — Managed ทั้งหมด

เลือก **managed** (ไม่ใช่ VM) เพราะดูแลคนเดียว + มีข้อมูลสุขภาพ PDPA — งาน patch/
เข้ารหัส/backup ยกให้ผู้ให้บริการ ลดความเสี่ยงข้อมูลรั่ว

| ชั้น | บริการ | ภูมิภาค |
|---|---|---|
| Frontend | **Vercel** | Global CDN |
| Backend | **Cloud Run** (`min-instances=1` กัน cold start) | asia-southeast1 (SG) |
| Database | **Neon** (Postgres serverless) | Singapore |
| Object storage | **Cloudflare R2** (ไม่มีค่า egress) | Auto |
| Auth | **Clerk** | Global |
| AI | **Gemini API** | Google |

- **CI/CD = GitHub Actions:** test gate (ruff/mypy/pytest) → deploy → migration (step แยก)
- **frontend ไม่ต้องเขียน Actions** — Vercel auto-deploy จาก GitHub
- **local dev:** docker-compose (postgres + minio จำลอง R2) — โค้ดชุดเดียว ต่างแค่ env
- **ค่าใช้จ่าย:** ~หลักร้อยบาท/เดือน ตอนเริ่ม (100 คน)

> managed = เขียนโค้ด เขาดูแลเครื่อง | VM = ทำเองหมด

---

## 11. ไฟล์ที่ทำไว้แล้ว (สำหรับ Claude Code)

วางที่ root ของ repo `running-club/`:

```
running-club/
├── CLAUDE.md                          # master context, always-on
└── .claude/skills/
    ├── club-backend/SKILL.md          # FastAPI hexagonal + testing
    ├── club-frontend/SKILL.md         # Next.js + Clerk + submit flow
    └── security-pdpa/SKILL.md         # security 8 ข้อ + PDPA
```

- ตั้งชื่อ `club-*` เพื่อกันชนกับ frontend/backend skill เดิมของ Safem0de-GPT
- instruction เป็นอังกฤษ (trigger แม่น) / UI copy เป็นไทย
- grill-me (Matt Pocock, `npx skills@latest add mattpocock/skills`) ติดตั้งไว้เค้นแผนก่อนเขียน

---

## 12. ลำดับ build ที่วางไว้

1. **schema + Alembic migration** (`0001_init.py`) — วางฐาน
2. **redeem_reward + ledger** — transaction-safe กัน double-spend (จุดหินสุด)
3. **consent-gate + admin role + audit** — จุด PDPA
4. **evidence + Gemini extract flow** — upload filtering + auto-fill
5. **frontend pages** — dashboard / submit / campaigns / rewards / leaderboard / health

---

## 13. Edge case ที่ยังไม่ได้เคาะ (เอาไป grill ต่อ)

- สมาชิกลาออก/ถูกลบกลางกิจกรรม → ระยะ/แต้มที่สะสมไว้เป็นยังไง
- กิจกรรม 2 อันทับช่วงเวลากัน → 1 run นับให้ทั้งคู่ไหม
- ถอน consent หลังเก็บ health data ไปแล้ว → ลบย้อนหลังหรือ freeze
- presigned URL หมดอายุตอนไหน / ใครขอ URL รูปคนอื่นได้บ้าง
- reward stock หมดตอนหลายคนแลกพร้อมกัน (นอกจาก double-spend)
- สมาชิกแก้/ลบ run ที่ส่งไปแล้ว ได้ไหม กระทบ ledger ยังไง

---

## สถานะปัจจุบัน

- ✅ ออกแบบครบทุกชั้น (architecture, DB, strategy, evidence+AI, infra, deploy, PDPA, security)
- ✅ CLAUDE.md + 3 skills พร้อมใช้ วางลง repo แล้ว
- ✅ VS Code + Claude Code + grill-me พร้อม
- ⬜ ยังไม่มีโค้ดจริงสักไฟล์ (เริ่มที่ schema + migration)
