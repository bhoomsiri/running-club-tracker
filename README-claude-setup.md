# วิธีใช้ชุดไฟล์นี้กับ Claude Code

ชุดนี้คือ "สมอง" ให้ Claude Code สร้างโปรเจกต์ตาม architecture ที่วางไว้ ไม่ใช่โค้ดของ
แอปเอง — เอาไว้วางก่อนเริ่มสั่งให้ Claude Code เขียนโค้ดจริง

## โครงไฟล์ที่ได้

```
running-club/
├── CLAUDE.md                              ← วางที่ root ของ repo
└── .claude/
    └── skills/
        ├── club-backend/SKILL.md
        ├── club-frontend/SKILL.md
        └── security-pdpa/SKILL.md
```

## วิธีวาง

1. แตก zip นี้ที่ root ของ repo (หรือสร้าง repo ใหม่แล้ววางลงไป)
2. `CLAUDE.md` ต้องอยู่ที่ root — Claude Code โหลดไฟล์นี้เข้า context อัตโนมัติทุกครั้ง
3. โฟลเดอร์ `.claude/skills/` — Claude Code จะหยิบ skill ที่ตรงกับงานมาใช้เอง
   (club-backend เมื่อแตะ backend/, club-frontend เมื่อแตะ frontend/, security-pdpa เมื่อใกล้
   ข้อมูลอ่อนไหว)
4. commit เข้า git ได้เลย ไฟล์พวกนี้ควรอยู่ใน repo ให้ทีม (และ Claude Code) ใช้ร่วมกัน

## บทบาทของแต่ละไฟล์

| ไฟล์ | โหลดเมื่อไหร่ | ทำหน้าที่ |
|---|---|---|
| `CLAUDE.md` | ทุกครั้ง (always-on) | ภาพรวม + กฎเหล็ก + โครงสร้าง + คำสั่ง |
| `club-backend/SKILL.md` | เมื่องานอยู่ที่ backend | วิธีสร้างฟีเจอร์แบบ hexagonal + test |
| `club-frontend/SKILL.md` | เมื่องานอยู่ที่ frontend | Next.js + Clerk + submit flow |
| `security-pdpa/SKILL.md` | เมื่อใกล้ข้อมูลอ่อนไหว | security 8 ข้อ + PDPA |

## ประโยคเปิดที่แนะนำเมื่อเริ่มกับ Claude Code

วางไฟล์แล้วเปิดด้วยประโยคทำนองนี้ เพื่อให้เริ่มถูกลำดับ (ฐานก่อน แล้วต่อยอด):

> "อ่าน CLAUDE.md และ skills ใน .claude/skills/ ให้ครบก่อน แล้วเริ่มที่ schema +
> Alembic migration (`0001_init.py`) ตามตารางใน CLAUDE.md ทำทีละ step ให้ผมรีวิว
> ก่อนไป step ถัดไป"

ลำดับที่วางไว้ใน CLAUDE.md:
1. schema + migration
2. redeem_reward + ledger (transaction-safe)
3. consent-gate + admin role + audit (PDPA)
4. evidence + Gemini extract flow
5. frontend pages

## หมายเหตุ

- ถ้าอยากปรับกฎข้อไหน แก้ที่ `CLAUDE.md` หรือ skill ที่เกี่ยวข้อง แล้ว Claude Code จะ
  ทำตามเวอร์ชันใหม่ทันที
- เนื้อหา instruction เขียนเป็นภาษาอังกฤษเพื่อให้ Claude Code trigger และทำตามแม่นสุด
  ส่วน UI copy ที่สมาชิกเห็นให้เป็นภาษาไทย (ระบุไว้ใน frontend skill แล้ว)
- ไฟล์พวกนี้ไม่ผูกกับ deploy target — จะรัน managed (Cloud Run/Vercel/Neon/R2) ตามที่
  เคาะไว้ หรือย้ายทีหลังก็ได้ โดยไม่ต้องแก้ skill
