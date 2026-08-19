# GCP + WIF setup — เวอร์ชันป้อน Claude Code ทีละ step

🧑 = คุณทำเอง (interactive / dashboard — CC ทำแทนไม่ได้)   🤖 = ก๊อปให้ CC รัน
ชื่อ resource ตรงกับ `deploy.yml` แล้ว. ทุก step ของ CC จะ `source` ไฟล์ตัวแปร เพราะ
shell ของ CC ไม่จำ env var ข้าม step.

---

### 🧑 Step 0a — auth (คุณทำเอง ครั้งเดียว)
ต้องลง gcloud CLI ก่อน แล้วรันในเทอร์มินัลของคุณเอง (เปิด browser ให้ login):
```bash
gcloud auth login
```
> `gcloud auth login` เป็น interactive — **อย่าให้ CC รัน** พอ login แล้ว CC จะใช้ config
> เดียวกันรัน gcloud ต่อได้เอง

### 🤖 Step 0b — สร้างไฟล์ตัวแปร (บอก CC: "รัน step 0b")
**แก้ `PROJECT_ID` ให้ไม่ซ้ำใครก่อน** (GCP project id ต้อง unique ทั้งโลก เช่นเติมเลขท้าย):
```bash
cat > ~/rc-deploy.env <<'EOF'
export PROJECT_ID="running-club-505603"     # <-- แก้ให้ไม่ซ้ำ
export REGION="asia-southeast1"
export REPOSITORY="running-club"
export SERVICE="running-club-api"
export GH_REPO="bhoomsiri/running-club-tracker"
export SA_NAME="gh-deployer"
export SA_EMAIL="gh-deployer@running-club-505603.iam.gserviceaccount.com"  # <-- แก้ให้ตรง PROJECT_ID
EOF
cat ~/rc-deploy.env
```

### 🤖 Step 1 — สร้าง project (บอก CC: "รัน step 1")
```bash
source ~/rc-deploy.env
gcloud projects create "$PROJECT_ID"
gcloud config set project "$PROJECT_ID"
gcloud billing accounts list
```
→ CC จะโชว์ billing account มา **คุณดู ACCOUNT_ID** (XXXXXX-XXXXXX-XXXXXX) แล้วบอก CC ต่อ:

### 🤖 Step 1b — ผูก billing + เก็บ project number (แทน `<ACCOUNT_ID>` ด้วยของจริง)
```bash
source ~/rc-deploy.env
gcloud billing projects link "$PROJECT_ID" --billing-account="<ACCOUNT_ID>"
echo "export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')" >> ~/rc-deploy.env
tail -1 ~/rc-deploy.env
```

### 🤖 Step 2 — เปิด API
```bash
source ~/rc-deploy.env
gcloud services enable run.googleapis.com artifactregistry.googleapis.com iamcredentials.googleapis.com sts.googleapis.com
```

### 🤖 Step 3 — Artifact Registry
```bash
source ~/rc-deploy.env
gcloud artifacts repositories create "$REPOSITORY" --repository-format=docker --location="$REGION" --description="Running club images"
```

### 🤖 Step 4 — Service account + สิทธิ์
```bash
source ~/rc-deploy.env
gcloud iam service-accounts create "$SA_NAME" --display-name="GitHub Actions deployer"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA_EMAIL" --role="roles/run.admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA_EMAIL" --role="roles/artifactregistry.writer"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA_EMAIL" --role="roles/iam.serviceAccountUser"
```

### 🤖 Step 5 — Workload Identity Federation
```bash
source ~/rc-deploy.env
gcloud iam workload-identity-pools create github-pool --location=global --display-name="GitHub Actions"
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global --workload-identity-pool=github-pool \
  --display-name="GitHub OIDC" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository == '${GH_REPO}'"
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${GH_REPO}"
echo "=== ค่าสำหรับ GitHub secret GCP_WORKLOAD_IDENTITY_PROVIDER: ==="
gcloud iam workload-identity-pools providers describe github-provider \
  --location=global --workload-identity-pool=github-pool --format="value(name)"
echo "=== ค่าสำหรับ GitHub secret GCP_DEPLOY_SERVICE_ACCOUNT: ==="
echo "$SA_EMAIL"
```

### 🤖 Step 6 — ใส่ GitHub secrets/variables ด้วย gh CLI
ต้องมี `gh` CLI + `gh auth login` (ถ้ายังไม่มี ให้ CC ลง/คุณ login ก่อน หรือทำผ่านเว็บ GitHub แทน)
แทน `<PROVIDER>` ด้วย output จาก step 5:
```bash
source ~/rc-deploy.env
gh variable set GCP_PROJECT_ID --repo "$GH_REPO" --body "$PROJECT_ID"
gh secret set GCP_DEPLOY_SERVICE_ACCOUNT --repo "$GH_REPO" --body "$SA_EMAIL"
gh secret set GCP_WORKLOAD_IDENTITY_PROVIDER --repo "$GH_REPO" --body "<PROVIDER>"
```
> ทางเลือก 🧑: ทำผ่านเว็บ GitHub → Settings → Secrets and variables → Actions

### 🧑 Step 7 — Neon (dashboard — คุณทำเอง)
- สร้าง project region **Singapore** → ก๊อป **pooled** connection string
- **แก้ scheme เป็น `postgresql+psycopg://`** (โค้ดใช้ psycopg3) เก็บ `?sslmode=require` ไว้
- เอาไปใส่ GitHub secret `DATABASE_URL` (🤖 ให้ CC: `gh secret set DATABASE_URL --repo "$GH_REPO" --body "<neon-url>"`)
  และเก็บไว้ใช้เป็น env บน Cloud Run (Step 8)

### 🧑 Step 8 — Deploy แรก + env (ทำหลัง Neon เสร็จ)
1. merge branch `deploy-infra` → `main` (หรือ GitHub → Actions → Deploy → Run workflow)
   → deploy แรก boot แบบ local (validation ข้าม) → **service ถูกสร้าง**
2. ตั้ง env จริงบน service — **ผ่าน Cloud Run Console** (Edit & deploy new revision → Variables)
   ใส่: `APP_ENV=production`, `DATABASE_URL`, `CLERK_*`, `SUPERUSER_CLERK_USER_ID`, `FRONTEND_URL`,
   `S3_*`, `GEMINI_API_KEY`, `CF_ORIGIN_SECRET`, `TRUST_PROXY=false`
   → `APP_ENV=production` เปิด validation; ขาดตัวไหน revision fail + บอกชื่อที่ขาด
   → `TRUST_PROXY=false` จนกว่า Cloudflare origin lock เสร็จ

### 🤖 verify (หลัง Step 8)
```bash
source ~/rc-deploy.env
URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
echo "$URL"
curl -s -o /dev/null -w "%{http_code}\n" "$URL/healthz"        # คาด 200
curl -s -o /dev/null -w "%{http_code}\n" "$URL/me/summary"     # คาด 403 (origin guard)
```

---

**สรุปสิ่งที่คุณทำเอง 🧑:** Step 0a (auth login), Step 7 (Neon), Step 8 (merge + ตั้ง env console)
**ที่เหลือ 🤖 ให้ CC รันได้** โดยคั่นด้วยการที่คุณส่ง ACCOUNT_ID (1b) และ PROVIDER (6) ให้มัน
**ถัดไป:** Cloudflare (DNS → WAF → CF-Origin-Secret → rate-limit → webhook exception) → เปิด TRUST_PROXY → seed
