export const meta = {
  name: 'tester',
  description: 'Tester — 3 agent "รีวิวอย่างเดียว" (① ช่องโหว่ฟังก์ชัน · ② ความถูกต้องโค้ด · ③ ภาพรวม perf/UX/โครงสร้าง) ออดิตโปรเจคปัจจุบันแบบขนาน แล้วคืน findings · ❌ agent ไม่แก้/ไม่ spawn ต่อ — Coddy อ่าน findings แล้ววิเคราะห์+แก้เองทั้งหมด',
  phases: [
    { title: 'ออดิต', detail: '3 agent รีวิวอย่างเดียว (lens ละตัว) ขนานกัน → คืน findings P0–P3' },
  ],
}

// ───────────────────────────────────────────────────────────────────────
// เรียกผ่าน: Nick พิมพ์ "Tester" → Coddy ทำตาม command_pattern ข้อ 5:
//   1) เรียก Workflow tool: { scriptPath: "<ไฟล์นี้>", args: { workdir } }
//      workdir = โฟลเดอร์โปรเจคปัจจุบัน (ออดิต in-place แบบ "อ่านอย่างเดียว" — ไม่ต้องทำ worktree เพราะ agent ไม่แก้อะไร)
//   2) ผลกลับมา = findings (P0–P3) จาก 3 lens รวมแล้วเรียงตามความรุนแรง
//   3) Coddy (ตัวหลัก): อ่าน findings → verify กับโค้ดจริง → **แก้เองด้วยมือ 0 agent**
//      → analyze+test → build → อัพ Play internal (mobile) + Drive → อัปเดต memory → รายงาน findings/fixes/สรุปโทเค้น
//
// ⛔ ทำไมต้องเป็น script (เหตุ 2026-06-13): Tester แบบ freeform เคยให้ agent 3 ตัวแตกลูกตัวละ ~30 = ~70 agent.
//    script นี้บังคับด้วยโครงสร้าง: เรียก agent() แค่ "3 ครั้ง" ครั้งเดียว (parallel) ไม่มี loop fan-out ตาม finding,
//    และทุก agent ถูกสั่งเด็ดขาดว่า "รีวิวอย่างเดียว · ห้ามเรียก Agent/Task tool · ห้ามแก้ไฟล์".
//    (ถ้าวันใดยังเห็นเกิน 3 → เพิ่ม agentType:'Explore'/'Plan' ซึ่งไม่มี Agent tool = spawn ต่อไม่ได้แบบ hard-lock)
// ───────────────────────────────────────────────────────────────────────

// ⚠️ args มาถึงสคริปต์เป็น JSON "string" ในฮาร์เนสนี้ (พิสูจน์ 2026-06-13) → ต้อง parse + กัน throw · ❌ ห้ามลบ guard
let _A = args
if (typeof _A === 'string') { try { _A = JSON.parse(_A) } catch { _A = {} } }
_A = _A || {}
const workdir = _A.workdir
if (!workdir)
  return { error:'tester: ไม่มี workdir ใน args — ส่ง args เป็น object {workdir} (Workflow แปลงเป็น string สคริปต์ parse เอง)', findings:[], lenses:[] }

const FINDINGS = { type:'object', required:['lens','summary','findings'], properties:{
  lens:    { type:'string' },
  summary: { type:'string' },
  findings:{ type:'array', items:{ type:'object',
    required:['severity','title','file','problem','suggestedFix'], properties:{
      severity:    { type:'string', enum:['P0','P1','P2','P3'] },
      title:       { type:'string' },
      file:        { type:'string' },   // file:line เป็นหลักฐาน
      problem:     { type:'string' },
      suggestedFix:{ type:'string' },
      evidence:    { type:'string' },   // code path / บรรทัดที่ตรวจแล้วยืนยัน
    } } } } }

const LENSES = [
  { key:'functional-gaps',
    title:'① ช่องโหว่ฟังก์ชัน (functional gaps)',
    brief:'ฟีเจอร์ที่ขาด/ทำครึ่งๆ · flow ที่ตัน · ปุ่ม/หน้าที่ไม่ได้ wire · error/empty/edge state ที่ไม่จัดการ · โค้ดที่มีแต่ไม่มี UI (orphaned) · onboarding/permission ที่ทำแอป soft-brick ได้' },
  { key:'code-correctness',
    title:'② ความถูกต้องของโค้ด (code correctness)',
    brief:'บั๊ก logic · race condition · null/empty/ค่าใหญ่/ลำดับ · ทางที่ทำข้อมูลหาย · regression ตรงรอยต่อของการแก้ล่าสุด · serialization ไม่ตรง · การ drop เงียบๆ' },
  { key:'holistic',
    title:'③ ภาพรวม — perf / UX / โครงสร้าง (holistic)',
    brief:'งานที่เปลืองโดยไม่จำเป็น · ผิดโครงสร้าง (dependency ทางเดียว, แยก UI/logic) · pattern ไม่สม่ำเสมอ · security/privacy · perf บน path หลัก · UX สะดุด' },
]

const reviewPrompt = (lens) => [
  `คุณคือ 1 ใน "ทีม Tester" ของ Nick — มี **เป๊ะ 3 ตัว** ทำขนานกัน · คุณรับผิดชอบ lens: **${lens.title}**`,
  lens.brief,
  ``,
  `ออดิตโปรเจคปัจจุบันที่: ${workdir}`,
  `ใช้ **Read / Grep / Glob เท่านั้น** อ่านโค้ดจริง · เดิน code path จริง end-to-end (ไม่ใช่เดาจากชื่อไฟล์) · cite file:line เป็นหลักฐานเสมอ · แยก "claim (โค้ดบอกว่า)" กับ "ตรวจแล้วยืนยัน/ค้าน"`,
  ``,
  `⛔ กฎเหล็ก (Nick #16 — กฎที่โดนละเมิดบ่อยสุด · เหตุ 70-agent 2026-06-13):`,
  `  • ❌ ห้ามเรียก Agent/Task tool · ❌ ห้าม spawn subagent ใดๆ — คุณรีวิว "คนเดียว"`,
  `  • ❌ ห้ามแก้/เขียน/build/run อะไรทั้งสิ้น — คุณ "อ่านแล้วรายงาน" อย่างเดียว`,
  `  • ถ้ารู้สึกว่าต้องมีตัวช่วยเพิ่ม → อย่า spawn เด็ดขาด · เขียนเป็น finding ให้ Coddy แทน`,
  ``,
  `คืนผลเป็น findings ทุกจุดที่เจอ "จริง": severity P0–P3 · title สั้น · file (file:line) · problem · suggestedFix · evidence · เรียง blocker → nit · ❌ ห้าม pad nit · ❌ ห้าม rubber-stamp · ไม่แน่ใจ = ใส่ severity ต่ำไว้ก่อน + บอกว่ายังไม่ยืนยัน`,
  `Coddy (ตัวหลัก) จะอ่าน findings ของคุณแล้ว verify + แก้เอง — หน้าที่คุณคือ "รีวิว" เท่านั้น`,
].join('\n')

phase('ออดิต')

// ⛔ เป๊ะ 3 ตัว — parallel ครั้งเดียว ไม่มี fan-out ตาม finding
const reports = (await parallel(LENSES.map(lens => () =>
  agent(reviewPrompt(lens), { label:`รีวิว:${lens.key}`, phase:'ออดิต', schema: FINDINGS })
))).filter(Boolean)

const order = { P0:0, P1:1, P2:2, P3:3 }
const findings = reports
  .flatMap(r => (r.findings || []).map(f => ({ ...f, lens: r.lens })))
  .sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9))
const tally = sev => findings.filter(f => f.severity === sev).length

log(`Tester ออดิตเสร็จ: ${reports.length}/3 lens · ${findings.length} findings (P0:${tally('P0')} P1:${tally('P1')} P2:${tally('P2')} P3:${tally('P3')})`)

return {
  agentsUsed: LENSES.length,   // = 3 เสมอ (script บังคับ ไม่มีทางเกิน)
  lenses: reports.map(r => ({ lens: r.lens, summary: r.summary, count: (r.findings || []).length })),
  findings,
  next: 'Coddy: อ่าน findings → verify กับโค้ดจริง → แก้เอง (0 agent) → analyze+test → build → อัพ Play internal + Drive → อัปเดต memory → รายงาน findings/fixes/สรุปโทเค้น',
}
