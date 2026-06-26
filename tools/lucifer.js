export const meta = {
  name: 'lucifer',
  description: 'Lucifer — ทีม 3 ตัวรีเลย์ (① วางแผน → ② โค้ด → ③ Scrutinize รีวิวให้คะแนน 1–5) + ด่านคะแนน วนสูงสุด 2 รอบ',
  phases: [
    { title: 'วิเคราะห์', detail: '① สถาปนิก อ่านโค้ดปัจจุบัน → ออกแผน' },
    { title: 'เขียนโค้ด', detail: '② เขียนโค้ดตามแผน (ใน worktree ที่ Coddy เตรียม)' },
    { title: 'รีวิว',     detail: '③ Lucifer panel 3 ตัว (วิธี Scrutinize) ให้คะแนน 1–5 เอาต่ำสุด' },
  ],
}

// ───────────────────────────────────────────────────────────────────────
// เรียกผ่าน: Nick พิมพ์ "Lucifer: <งาน>" → Coddy ทำตาม command_pattern ข้อ 12:
//   1) Coddy สร้าง git worktree แยกจาก main → ส่ง path เข้าทาง args.workdir (ของจริงไม่ถูกแตะ)
//   2) เรียก Workflow tool: { scriptPath: "<ไฟล์นี้>", args: { task, workdir } }
//   3) ผลกลับมา:
//        passed=true  → Coddy: emulator test → build → อัพ (Play/Drive) → merge worktree
//        passed=false → Coddy: ❌ ไม่ build/ไม่อัพ → ทิ้ง worktree → คุยกับนิก
// ❌ ห้ามจำลอง 3 agent เอง / ห้ามให้คะแนนตัวเอง / ห้าม build ก่อนผ่าน — ตัว script บังคับให้เป๊ะ
// ───────────────────────────────────────────────────────────────────────

// ⚠️ args มาถึงสคริปต์เป็น JSON "string" ในฮาร์เนสนี้ (พิสูจน์ 2026-06-13: ส่ง object → typeof args==='string')
// → ต้อง parse ก่อนเสมอ + กัน throw (JSON.parse("undefined")/quote แตก = SyntaxError) · ❌ ห้ามลบ guard นี้
let _A = args
if (typeof _A === 'string') { try { _A = JSON.parse(_A) } catch { _A = {} } }
_A = _A || {}
const task = _A.task, workdir = _A.workdir
if (!task || !workdir)
  return { passed:false, error:'lucifer: ไม่มี task/workdir ใน args — ส่ง args เป็น object {task,workdir} (Workflow แปลงเป็น string สคริปต์ parse เอง)', rawType: typeof args }

const PLAN = { type:'object', required:['summary','changes','acceptance'], properties:{
  summary:{type:'string'}, acceptance:{type:'array', items:{type:'string'}},
  changes:{type:'array', items:{type:'object', required:['file','what','why'],
    properties:{file:{type:'string'}, what:{type:'string'}, why:{type:'string'}}}} }}
const CODE = { type:'object', required:['filesChanged','summary'], properties:{
  filesChanged:{type:'array', items:{type:'string'}}, summary:{type:'string'}, deviations:{type:'string'} }}
const REVIEW = { type:'object', required:['score','verdict','issues'], properties:{
  score:{type:'integer', minimum:1, maximum:5}, verdict:{type:'string'},
  issues:{type:'array', items:{type:'object', required:['severity','file','problem','fix'],
    properties:{severity:{type:'string'}, file:{type:'string'}, problem:{type:'string'}, fix:{type:'string'}}}} }}

const LENS = [
  'ตรงโจทย์ที่นิกสั่งจริงไหม + ความถูกต้องของ logic',
  'คุณภาพ / ความสวยงาม / UX + ความสะอาดของโค้ด',
  'ความเสี่ยง: regression, edge case, ของเดิมพังไหม',
]

const planPrompt = (round, fb) => [
  `คุณคือ ① สถาปนิก/นักวิเคราะห์ ของทีม Lucifer`,
  `โจทย์จากนิก: "${task}"`,
  `อ่าน "โค้ดปัจจุบันล่าสุด" ใน ${workdir} เท่านั้น — ❌ ห้ามอ่านโค้ดเก่า/เวอร์ชันก่อน/โปรเจคอื่น (เปลืองโทเค้น)`,
  round > 1 ? `รอบ ${round} — รอบก่อนยังไม่ผ่าน แก้ตามรีวิวนี้:\n${fb}` : ``,
  `ออก "แผน" ที่ชัดที่สุดเพื่อแก้โจทย์ให้ดีที่สุดตามที่นิกต้องการ: แก้ไฟล์ไหน/ทำอะไร/ทำไม + acceptance ("ดี" คือแบบไหน)`,
  `❌ อย่าเพิ่งเขียนโค้ด — แค่วางแผน`,
].filter(Boolean).join('\n')

const codePrompt = (plan) => [
  `คุณคือ ② ช่างเขียนโค้ด ของทีม Lucifer · ทำตามแผนของ ① เป๊ะ:`,
  JSON.stringify(plan, null, 2),
  `โจทย์: "${task}"`,
  `เขียน/แก้โค้ดจริง "เฉพาะใน ${workdir}" (worktree แยก — ของจริงปลอดภัย) · ครบ ใช้ได้จริง · เบี่ยงจากแผนให้บอกใน deviations`,
].join('\n')

// ③ ใช้วิธี "Scrutinize" (skill: ~/.claude/skills/scrutinize/SKILL.md) — รีวิวแบบคนนอก end-to-end
const reviewPrompt = (plan, code, lens) => [
  `คุณคือ ③ "Lucifer" — นักรีวิวตัวแทนนิก เข้มงวดสุด · ใช้วิธี **Scrutinize** (รีวิวแบบคนนอก end-to-end)`,
  `จุดยืน: ลืมว่าใครเขียน/ทำไม อ่าน cold · ❌ ห้าม rubber-stamp ("LGTM" ใช้ไม่ได้) · ❌ ห้ามประจบ · cite file:line เสมอ · แยก "claim (โค้ดบอกว่า)" กับ "ตรวจแล้วยืนยัน/ค้าน"`,
  `โจทย์ที่นิกสั่ง: "${task}"`,
  `แผนของ ①: ${JSON.stringify(plan)}`,
  `สิ่งที่ ② ทำ: ${JSON.stringify(code)}`,
  `ดูโค้ด/diff จริงใน ${workdir} (git -C ${workdir} diff)`,
  `ทำ 4 step ตามลำดับ (ห้ามข้าม):`,
  `  1) INTENT — พูดเป้าหมายเป็นประโยคเดียว · **บังคับถาม: มีวิธีง่าย/เล็ก/สวยกว่าที่ได้ผลเท่ากันไหม** (ทำเฉยๆ? ใช้ของที่มีอยู่แล้ว? แก้คนละ layer? เล็กกว่าแก้ 90% เสี่ยง 10%) — ถ้ามี เสนอก่อนเลย`,
  `  2) TRACE — เดิน code path จริง end-to-end (entry→call→branch→state→exit) รวมโค้ดที่ไม่ได้แก้รอบๆ diff ด้วย (bug ซ่อนที่รอยต่อ) ไม่ใช่ดูแค่ diff`,
  `  3) VERIFY — claim แต่ละอันจริงไหม (เดิน path ให้เห็น) · input/state อะไรพัง (edge/concurrent/error/null/empty/ใหญ่/ลำดับ) · อะไรเปลี่ยนเงียบๆ (perf/error-semantics/contract/format) · test ครอบ path จริง หรือ happy-path/mock บัง`,
  `  4) เน้นมุมพิเศษของคุณ: ${lens}`,
  `สรุป → verdict (ship / fix-then-ship / rework / reject) + score 1–5 ให้ตรงกับ verdict:`,
  `  5=ship (ตรงเป๊ะ trace ผ่านหมด) · 4=fix-then-ship เหลือจุดเล็ก · 3=มีจุดต้องแก้ชัด · 2=rework หลายจุด/structural · 1=reject ผิดทาง`,
  `ใส่ verdict ลง field "verdict" · issues ทุกจุด (severity/file/problem/fix · เรียง blocker→nit · อย่า pad nit ถ้ามีปัญหา structural) · ไม่แน่ใจ=ให้ต่ำไว้ก่อน`,
].join('\n')

const MAX_ROUNDS = 2
let review, plan, code, feedback = ''

for (let round = 1; round <= MAX_ROUNDS; round++) {
  // ① วางแผน — relay: await บังคับให้ "จบก่อน" ② เริ่ม
  plan = await agent(planPrompt(round, feedback), { label:`①วางแผน·รอบ${round}`, phase:'วิเคราะห์', schema: PLAN })

  // ② เขียนโค้ด — เริ่ม "หลัง" ① เท่านั้น (ขนานไม่ได้)
  code = await agent(codePrompt(plan), { label:`②เขียนโค้ด·รอบ${round}`, phase:'เขียนโค้ด', schema: CODE })

  // ③ Lucifer panel 3 ตัว — agent คนละตัวกับ ② → "ให้คะแนนตัวเองไม่ได้"
  const panel = await parallel(LENS.map((lens, i) => () =>
    agent(reviewPrompt(plan, code, lens), { label:`③Lucifer#${i+1}·รอบ${round}`, phase:'รีวิว', schema: REVIEW })))
  const scored = panel.filter(Boolean)
  review = scored.length ? scored.reduce((m, r) => (r.score < m.score ? r : m), scored[0]) : { score:1, verdict:'reviewer ล่มทั้ง panel', issues:[] }
  log(`รอบ ${round}: คะแนนต่ำสุด ${review.score}/5 (panel: ${scored.map(r => r.score).join('/') || '—'})`)

  const passBar = round === 1 ? 5 : 4   // รอบ1 ต้อง 5 · รอบ2 รับ 4–5
  if (review.score >= passBar)
    return { passed:true, round, score:review.score, plan, code, review, workdir, next:'Coddy: emulator test → build → อัพ → merge worktree' }
  feedback = (review.issues || []).map(x => `- [${x.severity}] ${x.file}: ${x.problem} → ${x.fix}`).join('\n')
}

// รอบ 2 ยังได้ 1–3 → ไม่ผ่าน (❌ ไม่มีรอบ 3)
return { passed:false, round:MAX_ROUNDS, score:review.score, plan, code, review, workdir, next:'Coddy: ❌ ไม่ build/ไม่อัพ → ทิ้ง worktree → วิเคราะห์ + คุยกับนิก' }
