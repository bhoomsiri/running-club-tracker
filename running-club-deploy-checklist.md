# Running Club — Deploy & Launch Checklist

เป้าหมาย: เปิดใช้จริง (กิจกรรม 2026-08-15 → 09-30). ทำเรียงตามลำดับ dependency ด้านล่าง.
เครื่องหมาย 🖥️ = โค้ด (Claude Code) · 🖱️ = ตั้งค่าใน dashboard · ✅ = verify

> **โดเมน:** `brightbhoom.com` อยู่บน Cloudflare แล้ว → API จะอยู่ที่ `api.brightbhoom.com`
>
> **ทำไมไม่ใช้ Cloud Run domain mapping:** ลองแล้วติด 2 ชั้น — (1) ต้อง verify ownership กับ Google
> ผ่าน Search Console ก่อน (2) Google ต้องออก managed cert เอง ซึ่ง validate ผ่าน DNS สาธารณะ
> จึงต้องปิด proxy (เมฆเทา) รอจน cert ออก = มีช่วงที่ API เปิดโล่งบนโดเมนจริงโดยไม่มี WAF
> จึงใช้ **Origin Rule + Host Header Rewrite** แทน: เปิดเมฆส้มได้ตั้งแต่วินาทีแรก ไม่ต้อง verify
> ไม่ต้องรอ cert (edge cert ของ Cloudflare มีอยู่แล้ว)

---

## Phase 0 — Code prep (Claude Code) 🖥️ — **เสร็จแล้ว**
- [x] Dockerfile ของ backend สำหรับ Cloud Run (non-root uid 10001, `uvicorn app.main:app`, PORT จาก env)
- [x] `deploy.yml` GitHub Action: push → test gate (ruff/mypy/pytest) → build+push image → deploy Cloud Run → **`alembic upgrade head` เป็น job แยกหลัง deploy** (ไม่รันตอน startup)
- [x] rate limiter อ่าน IP จริงจาก `CF-Connecting-IP` เมื่อ `TRUST_PROXY=true`
- [x] middleware ปฏิเสธ request ที่ไม่มี header `CF-Origin-Secret` (ค่า = `CF_ORIGIN_SECRET`)
      — ยกเว้น `/healthz` (probe ภายใน) และ `/livez` (uptime monitor ภายนอก)
- [x] `.env.example` ครบตาม master list
- [x] startup validation: `APP_ENV=production` แล้ว env ขาด → container ไม่ boot (exit 3)
      → Cloud Run คา revision เดิมไว้, deploy fail สะอาด แทนที่จะขึ้นแล้ว 500 ทั้งเว็บ

## Phase 0.5 — GCP + GitHub repo settings สำหรับ deploy.yml 🖱️ — **เสร็จแล้ว**
project `running-club-505603` (number `473776200408`) · billing `013659-38A823-A2B33C`
- [x] Artifact Registry: repository `running-club` (Docker) ที่ **asia-southeast1**
- [x] Workload Identity Federation: pool `github-pool` + provider `github-provider`,
      service account `gh-deployer` (`run.admin`, `artifactregistry.writer`, `iam.serviceAccountUser`)
      ล็อกไว้ 2 ชั้นที่ repo เดียว: provider `attributeCondition` และ SA `principalSet`
      = `bhoomsiri/running-club-tracker` — ถ้าหลวมกว่านี้ repo ไหนบน GitHub ก็ deploy ทับได้
- [x] Repository **variable**: `GCP_PROJECT_ID`
- [x] Repository **secrets**: `GCP_WORKLOAD_IDENTITY_PROVIDER` · `GCP_DEPLOY_SERVICE_ACCOUNT` · `DATABASE_URL`
- [x] ✅ push main → workflow ผ่าน, service ขึ้นจริง (revision 00007 รับ traffic 100%)

## Phase 1 — Clerk 🖱️
- [ ] สร้าง Clerk application (production instance)
- [ ] Publishable key → frontend `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- [ ] Secret key → `CLERK_SECRET_KEY`
- [ ] JWKS URL → backend `CLERK_JWKS_URL` · Issuer → `CLERK_ISSUER`
- [ ] Webhook endpoint → `https://api.<yourdomain>/webhooks/clerk`, events `user.created` + `user.updated`; signing secret → `CLERK_WEBHOOK_SECRET`
- [ ] clerk_user_id ของ **คุณ** → `SUPERUSER_CLERK_USER_ID` (login 1 ครั้งหรือดูใน dashboard → Users)
- [ ] Allowed origins / authorized parties = โดเมน frontend

## Phase 2 — Neon (Postgres, Singapore) 🖱️
- [ ] สร้าง project region **Singapore**
- [ ] pooled connection string → `DATABASE_URL`
- [ ] (migration รันใน deploy step)

## Phase 3 — Cloudflare R2 (private bucket) 🖱️
- [ ] สร้าง bucket แบบ **private** (ห้าม public access)
- [ ] R2 API token → access key / secret / endpoint URL
- [ ] `S3_BUCKET` · `S3_ENDPOINT_URL` · `S3_ACCESS_KEY` · `S3_SECRET_KEY` · `S3_REGION=auto`

## Phase 4 — Backend บน Cloud Run (asia-southeast1) 🖱️
- [x] deploy image, region **asia-southeast1**, **min-instances=1** (กัน cold start)
- [ ] ใส่ env ครบ (master list) — ยังขาด `APP_ENV` · `FRONTEND_URL` · `CF_ORIGIN_SECRET`
      ใส่ 2 ตัวหลังก่อน แล้วค่อยใส่ `APP_ENV=production` เป็นตัวสุดท้าย
      (ใส่ `APP_ENV` ก่อน = revision ใหม่ fail ทันทีตาม startup validation — ถูกต้องแต่เสียรอบ deploy)
- [ ] ✅ `GET /livez` ผ่าน (ดูกล่องด้านล่างว่าทำไมไม่ใช่ `/healthz`)
- ~~custom domain บน Cloud Run~~ → ไม่ใช้แล้ว ดู Phase 5 (Origin Rule แทน)

> **`/healthz` ใช้ verify จากภายนอกไม่ได้ — ใช้ `/livez`**
> Google frontend สงวน path `/healthz` ไว้บนโดเมน `*.run.app`: request ไม่เคยถึง container
> เลย (ได้หน้า HTML 404 ของ Google, ไม่มี `server` header, ไม่มีบรรทัดใน Cloud Run logs)
> `/healthz` ยังอยู่และยังใช้ได้สำหรับ probe ภายในของ Cloud Run ซึ่งยิงเข้า container ตรง —
> ส่วน `/livez` คือ route เดียวกันภายใต้ชื่อที่ edge ยอมส่งต่อ ใช้กับ uptime monitor
> ทั้งคู่อยู่ใน `EXEMPT_PATHS` ของ origin guard จึงตอบ 200 ต่อไปแม้เปิด `CF_ORIGIN_SECRET` แล้ว

## Phase 5 — Cloudflare หน้า API 🖱️
- [ ] **DNS:** `CNAME api → running-club-api-473776200408.asia-southeast1.run.app` **proxied (เมฆส้ม)**
- [ ] **Origin Rule — Host Header Rewrite** (ขาดไม่ได้)
      Rules → Origin Rules → If `Hostname equals api.brightbhoom.com`
      Then Host Header → Rewrite to → `running-club-api-473776200408.asia-southeast1.run.app`
      ⚠️ Cloud Run route ตาม Host: ถ้าส่ง `api.brightbhoom.com` ไปดิบ ๆ จะได้ **404 ทุก request**
- [ ] **SSL/TLS mode = Full (strict)** — origin เป็น `*.run.app` ที่ Google ออก cert ถูกต้องอยู่แล้ว
      (ค่านี้ระดับ zone มีผลทั้งโดเมน — subdomain อื่นที่ origin ไม่มี cert ที่ถูกต้องจะพังตาม)
- [ ] WAF: เปิด managed ruleset
- [ ] Rate limiting rules: เข้มที่ `/runs/extract` และ `/webhooks/clerk`, ทั่วไปที่เหลือ
- [ ] **Origin lock:** Transform Rule (Modify Request Header → Set static) ชื่อ header **`CF-Origin-Secret`**
      ค่าเดียวกับ env `CF_ORIGIN_SECRET` บน Cloud Run — แล้วค่อยตั้ง `TRUST_PROXY=true`
      (สลับลำดับไม่ได้: เปิด trust_proxy ก่อน origin lock = ใครก็ปลอม IP หนี rate limit ได้)
- [ ] **WAF exception ให้ `/webhooks/clerk`** (skip managed ruleset + Bot Fight Mode สำหรับ path นี้
      หรือ allowlist IP ของ Clerk) — webhook เป็น server-to-server ไม่มี browser fingerprint
      จึงมีสิทธิ์โดน bot rule เด้ง. Transform Rule ยังต้องเติม `CF-Origin-Secret` ให้ path นี้ด้วย
      (origin guard ไม่ยกเว้น webhook — ยกเว้นแค่ `/healthz` กับ `/livez`)
      ⚠️ ถ้าพลาดข้อนี้จะ **เงียบ**: Clerk ยิงไม่ถึง → สมาชิกใหม่ไม่มี row → รู้ตอนมีคนบ่นว่าเข้าไม่ได้
- [ ] ✅ ยิงตรง `*.run.app` (ไม่มี header) → โดนบล็อก; ผ่าน `api.brightbhoom.com` → ผ่าน
      แต่ `*.run.app/livez` ต้องยัง 200 อยู่ (ยกเว้นไว้ให้ monitor)
- [ ] ✅ ดู Clerk dashboard → Webhooks → Message attempts ต้องเป็น 2xx (ไม่ใช่ 403)

## Phase 6 — Seed prod 🖱️
- [ ] รัน `python -m app.seed` กับ prod DB (ครั้งเดียว) → 2 กิจกรรม + ของรางวัล
- [ ] ✅ campaigns/rewards ครบ (idempotent รันซ้ำได้)

## Phase 7 — Frontend บน Vercel 🖱️
- [ ] import repo, framework Next.js
- [ ] env: `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` · `CLERK_SECRET_KEY` · `NEXT_PUBLIC_API_URL=https://api.brightbhoom.com`
- [ ] deploy (ต่อไป auto-deploy จาก GitHub)
- [ ] custom domain frontend → อัปเดต backend `FRONTEND_URL` (CORS) + Clerk allowed origins ให้ตรง

## Phase 8 — ยืนยัน placeholder (นโยบาย/PDPA) 🖱️
> **สถานะ: ปิดไป 1 จาก 4 — launch ไปแล้ว** ข้อมูลสุขภาพเป็น sensitive personal data
> ตาม PDPA มาตรา 26 ทั้ง 4 อย่างนี้ต้องให้ DPO ของโรงพยาบาลโพธารามตรวจ:
>
> - ✅ **`frontend/src/lib/consent-text.ts`** — DPO อนุมัติถ้อยคำแล้วโดยไม่แก้ = `CONSENT_VERSION` v2
>   เป็นฉบับสมบูรณ์ **ไม่มี v3** และมีสมาชิกให้ความยินยอมภายใต้ v2 ใน prod แล้ว
> - 🔴 **`frontend/src/lib/screening-text.ts`** (คำถาม PAR-Q+ 11 ข้อ + ข้อความยินยอมรับความเสี่ยง)
>   — **ยังไม่ผ่าน** ต้องผ่านนิติกร/ฝ่ายกฎหมายด้วย ไม่ใช่แค่ DPO (เหตุผลย่อหน้าถัดไป)
> - 🔴 ค่า `HEALTH_RETENTION_DAYS` · `AUDIT_RETENTION_DAYS` — **ยังไม่ยืนยัน**
>
> ข้อสุดท้ายต้องผ่าน **นิติกร/ฝ่ายกฎหมายของโรงพยาบาล** ด้วย ไม่ใช่แค่ DPO — เพราะข้อความ
> "ยินยอมรับความเสี่ยง" คือการที่ชมรมบอกสมาชิกว่ารับผิดชอบแค่ไหน และคำถามคัดกรองเป็นแบบสอบถาม
> สุขภาพที่ชมรมของโรงพยาบาลเป็นคนถาม
>
> ถ้าแก้ **ข้อความ** คำถามได้เลย แต่ถ้าแก้ **key** ของคำถาม (เช่น `heart_condition`) ต้องขยับ
> `PARQ_VERSION` ใน `backend/app/domain/screening.py` ด้วย ไม่งั้นคำตอบเก่าจะเปลี่ยนความหมายเงียบ ๆ
>
> ถ้อยคำปัจจุบันเขียนให้ **ตรงกับสิ่งที่ระบบทำได้จริงตอนนี้**: บอกว่าผู้ดูแลจะลบเมื่อครบกำหนด
> (ไม่อ้างว่าอัตโนมัติ เพราะ purge job ยังไม่มี) และให้ติดต่อผู้ดูแลถ้าจะขอลบก่อนกำหนด
> (ยังไม่มี use case erasure) — ถ้าสร้าง 2 อย่างนั้นเมื่อไหร่ ค่อยแก้ข้อความให้สัญญามากขึ้นได้
>
> 🆕 **บรรทัด leaderboard** ใน `consent-text.ts` — "การเข้าร่วมจะแสดงชื่อ-นามสกุลและระยะสะสม
> ของคุณในตารางอันดับที่สมาชิกในชมรมเห็นได้" ต้องให้ DPO ตรวจเป็นพิเศษ เพราะมันเป็น
> **การแจ้งให้ทราบ ไม่ใช่ข้อความขอความยินยอม**: ฐานทางกฎหมายมาจากการเข้าร่วมกิจกรรมของชมรม
> ไม่ใช่จาก consent เรื่องข้อมูลสุขภาพ — และโค้ดก็ทำตามนั้นจริง คือ **ถอนความยินยอมแล้วชื่อยัง
> อยู่ในตารางอันดับ** (ถอนแล้วหยุดประมวลผลเฉพาะข้อมูลสุขภาพ) ถ้า DPO เห็นว่าควรให้เลือกได้
> ต้องทำ opt-out flag ที่ member + use case มารองรับ ไม่ใช่แก้ถ้อยคำ
- [x] `CONSENT_VERSION` = **v2** — ✅ **ปิดแล้ว ไม่ต้องขยับเป็น v3** DPO อนุมัติถ้อยคำ v2
      ตามเดิมโดยไม่แก้ (ยืนยันจาก product owner) และ **launch ไปแล้วบน v2 มีสมาชิกให้ความยินยอม
      จริงใน prod แล้ว** → v2 คือฉบับสมบูรณ์ ไม่ใช่ placeholder อีกต่อไป
      · ขยับจาก v1 ตอนเพิ่มบรรทัด leaderboard เพราะมีบัญชียินยอมข้อความเดิมไปแล้วใน prod
      (คนที่ยินยอม v1 ไม่เคยเห็นประโยคนั้น จะนับว่ายินยอมไม่ได้)
      · ไม่ได้ตั้งเป็น env ที่ Cloud Run — ค่า default ใน `config.py` คือค่าที่ใช้จริง
      · **กฎที่ยังอยู่:** แก้ถ้อยคำใน `consent-text.ts` แบบมีนัยเมื่อไหร่ → ขยับเวอร์ชันเมื่อนั้น
      แต่ตอนนี้การขยับหมายถึง **ไล่ถามสมาชิกจริงที่ยินยอมไปแล้วใหม่ทุกคน** ไม่ใช่เรื่องสมมติแล้ว
- [x] บรรทัด leaderboard — ✅ DPO ตรวจและอนุมัติแล้ว พร้อมกับถ้อยคำ v2 ทั้งฉบับ (ดูกรอบด้านบน)
      · ที่ยัง**ไม่**ได้ทำคือ opt-out flag — DPO ไม่ได้ขอ เพราะรับได้กับการเป็น "แจ้งให้ทราบ"
- [ ] **data inventory: `member.birth_date`** — เดิมเก็บแค่ปีเกิด ตอนนี้เก็บวันเกิดเต็ม
      (migration `0008`) เพราะกฎอายุขั้นต่ำเป็นเรื่องของ "คนคนหนึ่งในวันหนึ่ง" ไม่ใช่การลบปี
      · วันเกิดเต็มระบุตัวตนได้มากกว่าปีเกิดเล็กน้อย — ปกติสำหรับโรงพยาบาล แต่ต้องบันทึกไว้ใน
      บัญชีรายการข้อมูล (data inventory) และให้ DPO รับทราบ · ยังเป็น **ข้อมูลส่วนบุคคลทั่วไป**
      ไม่ใช่ข้อมูลอ่อนไหวตามมาตรา 26 แต่โค้ดคืนค่าเฉพาะทาง `/admin/members/{id}/contact`
      ที่บันทึก audit ทุกครั้ง
- [ ] `HEALTH_RETENTION_DAYS` = 730 — ยืนยันกับนโยบาย · ⚠️ **launch แล้ว** ค่านี้ถูก freeze ลง
      `health_record.retention_until` ตอนเขียนแต่ละแถว การแก้ทีหลังจึงมีผลกับแถวใหม่เท่านั้น
      แถวที่มีอยู่ต้อง backfill แยก
- [ ] `AUDIT_RETENTION_DAYS` = 1825 — ยืนยัน
- [ ] `FRONTEND_URL` = โดเมนจริง (CORS ไม่ใช่ `*`)

## Phase 9 — Smoke test end-to-end (ก่อนประกาศ) ✅
- [ ] สมัครสมาชิกใหม่ → webhook สร้าง member row
- [ ] login เป็นคุณ (superuser) → role ถูก
- [ ] ส่งผลวิ่ง + รูป → upload → extract เติมฟอร์ม → ยืนยัน → ขึ้นใน `/me/runs`
- [ ] dashboard โชว์ระยะ + (ถ้า ≥10 กม./วัน ส่งทัน) แต้มกิจกรรม 2
- [ ] แลกของที่แต้มพอ → balance ลด, redemption pending
- [ ] (superuser) fulfill/cancel ผ่าน API
- [ ] ให้ consent → ฟอร์มสุขภาพปลดล็อก → บันทึก before/after → BMI ขึ้น
- [ ] ยิง API ไม่มี token → 401; ยิง `*.run.app` ตรง → 403 (แต่ `/livez` ยัง 200)

---

## Env var master list

**Backend (Cloud Run):**
`APP_ENV=production` (ต้องตั้ง! ไม่งั้น startup validation ไม่ทำงาน) · `DATABASE_URL` · `CLERK_ISSUER` · `CLERK_JWKS_URL` · `CLERK_WEBHOOK_SECRET` · `SUPERUSER_CLERK_USER_ID` ·
`FRONTEND_URL` · `S3_BUCKET` · `S3_ENDPOINT_URL` · `S3_ACCESS_KEY` · `S3_SECRET_KEY` · `S3_REGION` ·
`GEMINI_API_KEY` · `CF_ORIGIN_SECRET` · `TRUST_PROXY=true` · (`CONSENT_VERSION`, `HEALTH_RETENTION_DAYS`,
`AUDIT_RETENTION_DAYS`, `RATE_LIMIT`, `EXTRACT_RATE_LIMIT`, `HEALTH_EXPORT_ENABLED` — มี default อยู่แล้ว)

> `PORT` ไม่ต้องตั้ง — Cloud Run ใส่ให้เอง. ตั้ง env พวกนี้ที่ service โดยตรง
> เพราะ `deploy.yml` ตั้งใจไม่ส่ง `--set-env-vars` — secret จะได้ไม่โผล่ใน workflow log.

### 🔐 6 ตัวนี้ไม่ได้อยู่บน service แล้ว — อยู่ใน Secret Manager

`DATABASE_URL` · `CF_ORIGIN_SECRET` · `CLERK_WEBHOOK_SECRET` · `S3_ACCESS_KEY` · `S3_SECRET_KEY` ·
`GEMINI_API_KEY` — `deploy.yml` ส่งเป็น **ชื่ออ้างอิง** (`--set-secrets DATABASE_URL=database-url:latest`)
ที่เหลือยังเป็น env ธรรมดาบน service เพราะไม่ใช่ความลับ

- [x] ✅ **หมุนครบทั้ง 6 ตัวแล้ว — 29 ส.ค. 2026 · ค่าเก่า revoke ที่ต้นทางหมดแล้ว**
      `database-url` (Neon reset password) · `clerk-webhook-secret` (svix roll) ·
      `s3-access-key` + `s3-secret-key` (R2 token ใหม่ + ลบ token เก่า) ·
      `gemini-api-key` (key ใหม่ + ลบ key เก่า) ·
      `cf-origin-secret` (zero-downtime ผ่าน comma list ใน `CloudflareOriginGuard`)

> ⚠️ **`DATABASE_URL` มี 2 ที่เก็บ โดยตั้งใจ** — Secret Manager (Cloud Run) และ GitHub Secrets
> (job `migrate`: alembic รันบน runner ไม่มี runtime SA ไว้อ่าน Secret Manager)
> **เปลี่ยนรหัส Neon เมื่อไหร่ ต้องอัปเดตทั้งสองที่** ลืมอันหลัง = deploy รอบถัดไปพังที่ job
> `migrate` ทั้งที่แอปยังทำงานปกติ · รอบ 29 ส.ค. ทำครบทั้งคู่แล้ว

> **ขั้นตอนหมุน + งานเก็บกวาดที่เหลือ** อยู่ใน [docs/secret-manager-migration.md](docs/secret-manager-migration.md)

**Frontend (Vercel):**
`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` · `CLERK_SECRET_KEY` · `NEXT_PUBLIC_API_URL`

---

## ลำดับ dependency (ทำผิดลำดับจะติด)
Clerk → Neon → R2 → deploy backend → Cloudflare หน้า API → seed → deploy frontend → smoke test
