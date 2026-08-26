# ย้าย 6 runtime secrets → Secret Manager

ตอนนี้ค่าความลับ 6 ตัวเก็บเป็น **plaintext env var บน Cloud Run service** ใครก็ตามที่มีสิทธิ์
`run.viewer` ขึ้นไปอ่านได้หมดด้วย `gcloud run services describe` คำสั่งเดียว และมันติดอยู่ใน
revision เก่าทุกอันย้อนหลัง

หลังย้ายแล้ว service จะถือแค่ **ชื่ออ้างอิง** (`database-url:latest`) ส่วนค่าจริงอยู่ใน Secret
Manager ที่มี IAM แยก มี audit log ของตัวเอง และหมุนค่าได้โดยไม่ต้องแก้โค้ดหรือ deploy ใหม่

## ค่าที่ discover มาแล้ว (ตรวจแล้ว ไม่ต้องเดา)

| อะไร | ค่า |
|---|---|
| project id | `running-club-505603` |
| project number | `473776200408` |
| region | `asia-southeast1` |
| service | `running-club-api` |
| **runtime service account** | `473776200408-compute@developer.gserviceaccount.com` |
| deploy service account (GitHub) | `gh-deployer@running-club-505603.iam.gserviceaccount.com` |
| Secret Manager API | ❌ **ยังไม่เปิด** — Phase A ต้องเปิดก่อน |
| secret ที่มีอยู่ | ยังไม่มีเลย |

ทั้ง 6 ตัวอยู่บน service เป็น plaintext จริงทุกตัว — ไม่มีตัวไหนหายไปแล้ว

## Phase A — สร้าง secret + ให้สิทธิ์ (คุณรันเอง)

Claude **ไม่รันให้และไม่อ่านค่า** ค่าความลับเป็นของคุณ ไม่ควรผ่านมือ agent

```bash
export PROJECT=running-club-505603
export RUNTIME_SA=473776200408-compute@developer.gserviceaccount.com

# 0) เปิด API ก่อน — ตอนนี้ยังปิดอยู่ ข้ามไม่ได้
gcloud services enable secretmanager.googleapis.com --project "$PROJECT"
```

### 1) สร้าง secret ทั้ง 6 พร้อมใส่ค่า

ค่าปัจจุบันดึงจาก service ได้ด้วย `gcloud run services describe running-club-api
--region asia-southeast1 --format=json` แล้วอ่านที่ `spec.template.spec.containers[0].env`

> ⚠️ **อย่าใส่ค่าเป็น argument ในบรรทัดคำสั่ง** (`--data-string=...`) เพราะมันจะติดอยู่ใน
> shell history ใช้ `--data-file=-` แล้วป้อนทาง stdin แทน — และ `printf` ไม่ใช่ `echo`
> เพราะ `echo` ต่อท้าย newline เข้าไปในค่า secret

```bash
for NAME in database-url cf-origin-secret clerk-webhook-secret \
            s3-access-key s3-secret-key gemini-api-key; do
  gcloud secrets create "$NAME" --project "$PROJECT" --replication-policy=automatic
done

# แล้วใส่ค่าทีละตัว (พิมพ์ค่าแล้วกด Ctrl-D — ไม่โผล่ใน history)
gcloud secrets versions add database-url         --project "$PROJECT" --data-file=-
gcloud secrets versions add cf-origin-secret     --project "$PROJECT" --data-file=-
gcloud secrets versions add clerk-webhook-secret --project "$PROJECT" --data-file=-
gcloud secrets versions add s3-access-key        --project "$PROJECT" --data-file=-
gcloud secrets versions add s3-secret-key        --project "$PROJECT" --data-file=-
gcloud secrets versions add gemini-api-key       --project "$PROJECT" --data-file=-
```

ถ้าค่าไหนอยู่ในไฟล์อยู่แล้ว ใช้ `--data-file=path` ตรง ๆ ได้ แต่ระวังไฟล์นั้นมี newline ปิดท้าย
(`printf '%s' "$v" | gcloud secrets versions add NAME --data-file=-` ปลอดภัยกว่า)

### 2) ให้สิทธิ์ runtime service account อ่าน — ทีละ secret ไม่ใช่ทั้ง project

```bash
for NAME in database-url cf-origin-secret clerk-webhook-secret \
            s3-access-key s3-secret-key gemini-api-key; do
  gcloud secrets add-iam-policy-binding "$NAME" \
    --project "$PROJECT" \
    --member "serviceAccount:$RUNTIME_SA" \
    --role roles/secretmanager.secretAccessor
done
```

### 3) ตรวจก่อนไปต่อ

```bash
gcloud secrets list --project "$PROJECT" --format='table(name)'          # ต้องได้ 6 แถว
gcloud secrets versions list database-url --project "$PROJECT"           # ต้องมี version 1 enabled
```

## Phase B — deploy (merge branch นี้)

`deploy.yml` ต่อ 2 flag เข้า `gcloud run deploy` เดิม → **revision เดียว atomic**
mount secret ทั้ง 6 และถอด plaintext ทั้ง 6 พร้อมกัน ไม่มี revision ไหนถือทั้งสองแบบ

หลัง deploy ตรวจว่า env กลายเป็น secret ref ครบ:

```bash
gcloud run services describe running-club-api --region asia-southeast1 \
  --format='value(spec.template.spec.containers[0].env)' | tr ';' '\n' | grep -E 'DATABASE_URL|SECRET|KEY'
```

ต้องเห็น `valueFrom` / `secretKeyRef` ไม่ใช่ `value=`

แล้ว smoke test: `/livez` ตอบ 200 · login ได้ (Clerk webhook secret) · ส่งผลวิ่ง + อัปรูป
(S3 keys) · autofill ทำงาน (Gemini key) · ยิง `*.run.app` ตรงต้องได้ 403 (CF_ORIGIN_SECRET)

**ถ้าพัง rollback ได้ทันที** — revision เก่ายังถือ plaintext อยู่:
`gcloud run services update-traffic running-club-api --region asia-southeast1 --to-revisions <revision เก่า>=100`

## Phase C — เก็บกวาดหลังนิ่งแล้ว (อย่ารีบ)

- ลบ revision เก่าที่ยังฝัง plaintext ไว้ — ตราบใดที่ยังอยู่ ค่าความลับก็ยังอ่านได้จาก revision นั้น
  แต่ **อย่าลบจนกว่าจะมั่นใจว่าไม่ต้อง rollback แล้ว**
- **หมุนค่าทั้ง 6 ตัว** — ค่าเดิมเคยอยู่ในรูปแบบที่อ่านง่ายมานาน ย้ายที่เก็บไม่ได้ทำให้ค่าเก่า
  ปลอดภัยขึ้น หมุนแล้วค่อยเรียกว่าจบ
- ลด `roles/editor` ของ runtime SA (ดูหัวข้อถัดไป)

## เรื่องที่เจอระหว่าง discover — ควรรู้ แต่ไม่ได้อยู่ในงานนี้

**1. runtime service account ถือ `roles/editor` ทั้ง project**

`473776200408-compute@developer.gserviceaccount.com` มี `roles/editor` ซึ่งกว้างมาก — แก้ไข
ทรัพยากรได้เกือบทุกอย่างในโปรเจกต์ ทั้งที่แอปต้องการแค่ อ่าน secret 6 ตัว + เขียน log
ควรทำ service account เฉพาะของ Cloud Run แล้วให้เท่าที่จำเป็น เป็นงานแยกที่ควรทำหลังงานนี้นิ่ง
(สคริปต์ Phase A ให้สิทธิ์แบบราย secret ไว้แล้ว ไม่ได้ให้ทั้ง project เพื่อไม่ให้แย่ลงกว่าเดิม)

**2. deploy SA ไม่มี role ฝั่ง Secret Manager เลย**

`gh-deployer` มีแค่ `run.admin`, `artifactregistry.writer`, `iam.serviceAccountUser` —
สิทธิ์ที่ *จำเป็น* จริง ๆ คือของ runtime SA ตามข้อ 2 ข้างบน ส่วน deployer แค่ส่งชื่ออ้างอิงไป
ให้ Cloud Run แต่ถ้า deploy ครั้งแรกฟ้องเรื่องสิทธิ์ตรวจสอบ secret ให้เพิ่ม:

```bash
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member serviceAccount:gh-deployer@running-club-505603.iam.gserviceaccount.com \
  --role roles/secretmanager.viewer
```

**3. `DATABASE_URL` ยังมี 2 ที่เก็บ โดยตั้งใจ**

job `migrate` รัน alembic บน GitHub runner ไม่ใช่บน Cloud Run จึงไม่มี runtime service
account ไว้อ่าน Secret Manager — ยังใช้ `secrets.DATABASE_URL` ของ GitHub ต่อไปตามเดิม
**ผลที่ตามมา: เปลี่ยนรหัสผ่าน Neon เมื่อไหร่ ต้องอัปเดตทั้งสองที่** เขียนกำกับไว้ใน
`deploy.yml` แล้วกันคนมาแก้ให้ "เหมือนกัน" ทีหลัง
