# Cloudflare หน้า API + Production Lockdown — runbook

โดเมน: **brightbhoom.com** (อยู่บน Cloudflare, Full, active แล้ว)
เป้าหมาย: `api.brightbhoom.com` → Cloud Run โดยมี Cloudflare บัง (WAF + rate-limit + origin lock)
แล้วปิดท้ายด้วยการเปิด production mode บน Cloud Run

🧑 = คุณทำใน dashboard   🤖 = ก๊อปให้ CC รัน (gcloud)
เรียงตามลำดับ **ห้ามสลับ** — โดยเฉพาะ C10 (env) ต้องเป็นตัวท้าย

resource: SERVICE=`running-club-api` · REGION=`asia-southeast1`
run.app URL = `https://running-club-api-473776200408.asia-southeast1.run.app`
origin-guard header name (จากโค้ด) = `CF-Origin-Secret`

---

## C1 🤖 — สร้าง Cloud Run domain mapping (บอก CC: "รัน C1")
```bash
gcloud beta run domain-mappings create \
  --service running-club-api \
  --domain api.brightbhoom.com \
  --region asia-southeast1 \
  --platform managed
```
→ output จะบอก **DNS record ที่ต้องเพิ่ม** (ปกติเป็น `CNAME api → ghs.googlehosted.com`
   หรือชุด A/AAAA) **ก๊อป record นั้นมา** ใช้ต่อ C2

ดู status/cert ได้ตลอดด้วย:
```bash
gcloud beta run domain-mappings describe --domain api.brightbhoom.com \
  --region asia-southeast1 --format="yaml(status)"
```

## C2 🧑 — เพิ่ม DNS record ที่ Cloudflare **แบบเมฆเทา (DNS only) ก่อน**
Cloudflare → brightbhoom.com → **DNS → Records → Add record**
- ใส่ record ตามที่ C1 บอก (เช่น Type `CNAME`, Name `api`, Target `ghs.googlehosted.com`)
- **Proxy status: DNS only (เมฆเทา)** ← สำคัญ! ให้ Cloud Run ออก cert ให้ก่อน
- Save

## C3 🤖/🧑 — รอ cert ขึ้น Active
รัน describe (C1) ซ้ำจนกว่า `status` จะโชว์ว่า certificate provisioned / `CertificateProvisioned=True`
(ปกติ 15 นาที – ไม่กี่ ชม.) — ยังไม่ Active **อย่าเพิ่งเปิดเมฆส้ม**

## C4 🧑 — เปิด Proxy (เมฆส้ม) + ตั้ง SSL เป็น Full (strict)
- DNS → record `api` → เปลี่ยนเป็น **Proxied (เมฆส้ม)**
- SSL/TLS → Overview → เลือก **Full (strict)**
- ✅ เทส: เปิด `https://api.brightbhoom.com/livez` → ควรได้ `{"status":"ok"}` (200)

---

## C5 🧑 — Origin lock: Transform Rule เติม header ลับ
Cloudflare → **Rules → Transform Rules → Modify Request Header → Create rule**
- ชื่อ: `add origin secret`
- If: `Hostname equals api.brightbhoom.com`
- Then → **Set static** → Header name: `CF-Origin-Secret` · Value: `<CF_ORIGIN_SECRET>`
  (ค่าลับ — ผมจะให้ตอนถึงสเต็ปนี้ในแชต เก็บเป็นความลับ)
- Deploy
> นี่คือ header ที่ origin guard ในแอปจะเทียบ ทุก request ที่ผ่าน Cloudflare จะได้ header นี้
> ส่วนคนที่ยิงตรง run.app จะไม่มี → โดน 403

## C6 🧑 — WAF (free plan)
Security → WAF
- **Managed rules:** เปิด "Cloudflare Free Managed Ruleset" เท่าที่ free plan ให้
- **Custom rules (มีได้ ~5):** เพิ่มกฎ block ง่ายๆ ได้ตามต้องการ (option)
> free plan ได้ WAF จำกัด — ตัวหลักที่กัน abuse จริงคือ rate limiter ในแอปเราอยู่แล้ว
> Cloudflare เป็นชั้นเสริม

## C7 🧑 — Rate limiting rule (free = 1 rule)
Security → Rate limiting rules → Create
- ใส่ที่ **endpoint แพงสุด**: `/runs/extract` (ยิง Gemini เสียเงินทุกครั้ง)
  - If URI Path contains `/runs/extract` → เกิน N req/10s ต่อ IP → Block
- ที่เหลือปล่อยให้ app limiter (`RATE_LIMIT`, `EXTRACT_RATE_LIMIT`) คุม

## C8 🧑 — ยกเว้น webhook ไม่ให้โดน WAF/limit บล็อก
`/webhooks/clerk` ต้องเข้าได้เสมอ (Clerk retry + signature เป็นตัว auth เองอยู่แล้ว)
- ถ้ากฎ WAF/rate-limit ข้อไหนอาจโดน `/webhooks/clerk` → เพิ่มเงื่อนไข **ยกเว้น path นี้**
  (เช่น `and not (URI Path contains "/webhooks/clerk")`)

## C9 🧑 — ย้าย Clerk webhook มาโดเมนจริง
Clerk → Configure → Webhooks → endpoint เดิม → แก้ URL เป็น:
```
https://api.brightbhoom.com/webhooks/clerk
```
(ผ่าน Cloudflare แล้ว จะได้ header `CF-Origin-Secret` → ผ่าน origin guard)

---

## C10 🖱️ — เปิด production env บน Cloud Run (ทำเป็น "ตัวท้าย")
Cloud Run Console → running-club-api → Edit & deploy new revision → Variables & Secrets
ใส่ **ตามลำดับนี้**:
1. `FRONTEND_URL` = โดเมน frontend จริง (ถ้ายังไม่ deploy Vercel ใส่ค่าที่วางแผนไว้ก่อน เช่น `https://brightbhoom.com` แล้วมาแก้ทีหลังได้)
2. `CF_ORIGIN_SECRET` = ค่าเดียวกับ C5 เป๊ะ
3. `APP_ENV` = `production`  ← ใส่ตัวนี้ **หลังสุด**
   (พอเป็น production, startup validation จะเช็คครบทุกตัว ขาดตัวไหน revision fail + บอกชื่อใน log)
- `TRUST_PROXY` ยังไม่ต้องใส่ (ปล่อย false) — เปิดใน C12
- Deploy

## C11 ✅ — เทส origin lock
```bash
BASE_DIRECT=https://running-club-api-473776200408.asia-southeast1.run.app
BASE_CF=https://api.brightbhoom.com

# ยิงตรง run.app path ที่ไม่ได้ยกเว้น → ควรโดน 403 (origin guard)
curl -s -o /dev/null -w "direct openapi -> %{http_code}\n" $BASE_DIRECT/openapi.json   # คาด 403
# ผ่าน Cloudflare → ควรผ่าน
curl -s -o /dev/null -w "cf openapi     -> %{http_code}\n" $BASE_CF/openapi.json        # คาด 200
curl -s -o /dev/null -w "cf me/summary  -> %{http_code}\n" $BASE_CF/me/summary          # คาด 401 (auth)
# livez ยัง exempt เข้าตรงได้ (ไว้ให้ probe/monitor)
curl -s -o /dev/null -w "direct livez   -> %{http_code}\n" $BASE_DIRECT/livez           # คาด 200
```

## C12 🖱️ — เปิด TRUST_PROXY (ด่านสุดท้าย)
เมื่อ C11 ผ่านครบ (direct โดน 403, ผ่าน CF ได้) = ยืนยันแล้วว่า Cloudflare เป็นทางเข้าเดียว
→ Cloud Run env เพิ่ม `TRUST_PROXY=true` → Deploy
(ตอนนี้ rate limiter ถึงจะเชื่อ `CF-Connecting-IP` ได้อย่างปลอดภัย — ก่อนหน้านี้เชื่อไม่ได้
เพราะคนยิงตรงจะปลอม IP หนี limit ได้)

---

## หลังจบ Cloudflare
- seed prod DB (2 กิจกรรม + ของรางวัล): `python -m app.seed` กับ prod DATABASE_URL
- frontend (Next.js) → Vercel → อัปเดต `FRONTEND_URL` + Clerk allowed origins ให้ตรงโดเมนจริง
- อัป Clerk เป็น production instance (`clerk.brightbhoom.com`)
- smoke test end-to-end

## เผื่อ domain mapping cert ไม่ยอมขึ้น (แผนสำรอง)
ถ้า C3 รอ cert นานผิดปกติ (>ครึ่งวัน) หรือ error — สลับไปวิธี **Cloudflare Worker proxy**:
Worker บน route `api.brightbhoom.com/*` → fetch run.app origin + เติม header `CF-Origin-Secret`
เอง (ไม่ต้องใช้ domain mapping/cert เลย) — บอกผม เดี๋ยวเขียน Worker ให้
