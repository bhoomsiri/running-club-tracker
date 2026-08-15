# Running Club — Deploy & Launch Checklist

เป้าหมาย: เปิดใช้จริง (กิจกรรม 2026-08-15 → 09-30). ทำเรียงตามลำดับ dependency ด้านล่าง.
เครื่องหมาย 🖥️ = โค้ด (Claude Code) · 🖱️ = ตั้งค่าใน dashboard · ✅ = verify

> **Prerequisite:** Cloudflare WAF/proxy หน้า API ต้องมี **โดเมนบน Cloudflare** (เช่น `api.<yourdomain>`).
> ถ้ายังไม่มีโดเมน: จดโดเมน (ไม่กี่ร้อยบาท/ปี) แล้วชี้ NS มา Cloudflare — หรือข้าม Cloudflare-หน้า-API
> ไปก่อน (พึ่ง app limiter + Cloud Run) แล้วค่อยเพิ่มทีหลัง.

---

## Phase 0 — Code prep (Claude Code) 🖥️ — **เสร็จแล้ว**
- [x] Dockerfile ของ backend สำหรับ Cloud Run (non-root uid 10001, `uvicorn app.main:app`, PORT จาก env)
- [x] `deploy.yml` GitHub Action: push → test gate (ruff/mypy/pytest) → build+push image → deploy Cloud Run → **`alembic upgrade head` เป็น job แยกหลัง deploy** (ไม่รันตอน startup)
- [x] rate limiter อ่าน IP จริงจาก `CF-Connecting-IP` เมื่อ `TRUST_PROXY=true`
- [x] middleware ปฏิเสธ request ที่ไม่มี header `CF-Origin-Secret` (ค่า = `CF_ORIGIN_SECRET`) — ยกเว้น `/healthz`
- [x] `.env.example` ครบตาม master list
- [x] startup validation: `APP_ENV=production` แล้ว env ขาด → container ไม่ boot (exit 3)
      → Cloud Run คา revision เดิมไว้, deploy fail สะอาด แทนที่จะขึ้นแล้ว 500 ทั้งเว็บ

## Phase 0.5 — GitHub repo settings สำหรับ deploy.yml 🖱️
- [ ] Artifact Registry: สร้าง repository `running-club` (format Docker) ที่ **asia-southeast1**
- [ ] Workload Identity Federation: pool + provider ผูกกับ repo นี้, และ service account สำหรับ deploy
      (roles: `run.admin`, `artifactregistry.writer`, `iam.serviceAccountUser`)
- [ ] Repository **variable**: `GCP_PROJECT_ID`
- [ ] Repository **secrets**: `GCP_WORKLOAD_IDENTITY_PROVIDER` · `GCP_DEPLOY_SERVICE_ACCOUNT` · `DATABASE_URL` (Neon)
- [ ] ✅ push main แล้ว workflow ผ่านครบ 3 job (test → deploy → migrate)

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
- [ ] deploy image, region **asia-southeast1**, **min-instances=1** (กัน cold start)
- [ ] ใส่ env ครบ (master list)
- [ ] custom domain `api.<yourdomain>` (จะให้ Cloudflare proxy)
- [ ] ✅ `GET /healthz` ผ่าน

## Phase 5 — Cloudflare หน้า API 🖱️
- [ ] DNS `api.<yourdomain>` → Cloud Run, **proxied (เมฆส้ม)**
- [ ] WAF: เปิด managed ruleset
- [ ] Rate limiting rules: เข้มที่ `/runs/extract` และ `/webhooks/clerk`, ทั่วไปที่เหลือ
- [ ] **Origin lock:** Transform Rule (Modify Request Header → Set static) ชื่อ header **`CF-Origin-Secret`**
      ค่าเดียวกับ env `CF_ORIGIN_SECRET` บน Cloud Run — แล้วค่อยตั้ง `TRUST_PROXY=true`
      (สลับลำดับไม่ได้: เปิด trust_proxy ก่อน origin lock = ใครก็ปลอม IP หนี rate limit ได้)
- [ ] **WAF exception ให้ `/webhooks/clerk`** (skip managed ruleset + Bot Fight Mode สำหรับ path นี้
      หรือ allowlist IP ของ Clerk) — webhook เป็น server-to-server ไม่มี browser fingerprint
      จึงมีสิทธิ์โดน bot rule เด้ง. Transform Rule ยังต้องเติม `CF-Origin-Secret` ให้ path นี้ด้วย
      (origin guard ไม่ยกเว้น webhook — ยกเว้นแค่ `/healthz`)
      ⚠️ ถ้าพลาดข้อนี้จะ **เงียบ**: Clerk ยิงไม่ถึง → สมาชิกใหม่ไม่มี row → รู้ตอนมีคนบ่นว่าเข้าไม่ได้
- [ ] ✅ ยิงตรง `*.run.app` (ไม่มี header) → โดนบล็อก; ผ่าน `api.<yourdomain>` → ผ่าน
- [ ] ✅ ดู Clerk dashboard → Webhooks → Message attempts ต้องเป็น 2xx (ไม่ใช่ 403)

## Phase 6 — Seed prod 🖱️
- [ ] รัน `python -m app.seed` กับ prod DB (ครั้งเดียว) → 2 กิจกรรม + ของรางวัล
- [ ] ✅ campaigns/rewards ครบ (idempotent รันซ้ำได้)

## Phase 7 — Frontend บน Vercel 🖱️
- [ ] import repo, framework Next.js
- [ ] env: `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` · `CLERK_SECRET_KEY` · `NEXT_PUBLIC_API_URL=https://api.<yourdomain>`
- [ ] deploy (ต่อไป auto-deploy จาก GitHub)
- [ ] custom domain frontend → อัปเดต backend `FRONTEND_URL` (CORS) + Clerk allowed origins ให้ตรง

## Phase 8 — ยืนยัน placeholder (นโยบาย/PDPA) 🖱️
- [ ] `CONSENT_VERSION` = v1 — โอเคไหม
- [ ] `HEALTH_RETENTION_DAYS` = 730 — ยืนยันกับนโยบาย
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
- [ ] ยิง API ไม่มี token → 401; ยิง `*.run.app` ตรง → บล็อก

---

## Env var master list

**Backend (Cloud Run):**
`APP_ENV=production` (ต้องตั้ง! ไม่งั้น startup validation ไม่ทำงาน) · `DATABASE_URL` · `CLERK_ISSUER` · `CLERK_JWKS_URL` · `CLERK_WEBHOOK_SECRET` · `SUPERUSER_CLERK_USER_ID` ·
`FRONTEND_URL` · `S3_BUCKET` · `S3_ENDPOINT_URL` · `S3_ACCESS_KEY` · `S3_SECRET_KEY` · `S3_REGION` ·
`GEMINI_API_KEY` · `CF_ORIGIN_SECRET` · `TRUST_PROXY=true` · (`CONSENT_VERSION`, `HEALTH_RETENTION_DAYS`,
`AUDIT_RETENTION_DAYS`, `RATE_LIMIT`, `EXTRACT_RATE_LIMIT` — มี default อยู่แล้ว)

> `PORT` ไม่ต้องตั้ง — Cloud Run ใส่ให้เอง. ตั้ง env พวกนี้ที่ service โดยตรง (หรือ Secret Manager)
> เพราะ `deploy.yml` ตั้งใจไม่ส่ง `--set-env-vars` — secret จะได้ไม่โผล่ใน workflow log.

**Frontend (Vercel):**
`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` · `CLERK_SECRET_KEY` · `NEXT_PUBLIC_API_URL`

---

## ลำดับ dependency (ทำผิดลำดับจะติด)
Clerk → Neon → R2 → deploy backend → Cloudflare หน้า API → seed → deploy frontend → smoke test
