export const meta = {
  name: 'supertester',
  description: 'SuperTester — รีวิวเชิงลึก "เป๊ะ 3 รอบ" รอบละ 3 agent (รีวิวอย่างเดียว) ทำทีละรอบ (review→Coddy แก้→review→แก้→review→แก้). สคริปต์นี้ = เครื่องยนต์ "1 รอบ" (3 agent) · auto-scope จากงานล่าสุด + log 20 entry ล่าสุด · ❌ agent ไม่แก้/ไม่ build/ไม่ spawn — Coddy แก้เอง 0 agent คั่นทุกรอบ',
  phases: [
    { title: 'รีวิว', detail: '3 agent รีวิวอย่างเดียว (lens ตามรอบ) ขนานกัน → คืน findings P0–P3' },
  ],
}

// ───────────────────────────────────────────────────────────────────────
// เรียกผ่าน: Nick พิมพ์ "supertester" → Coddy ทำตาม command_pattern ข้อ 23:
//   0) Coddy หาขอบเขตเอง: อ่าน "สิ่งที่เพิ่งทำล่าสุด" + log\ 20 entry ล่าสุด → สรุปเป็น scope
//   1) วน "เป๊ะ 3 รอบ" — แต่ละรอบ:
//        a) เรียก Workflow: { scriptPath:"<ไฟล์นี้>", args:{ workdir, round, scope } }  → 3 agent รีวิว → findings
//        b) Coddy (ตัวหลัก): verify + **แก้เองด้วยมือ 0 agent**
//      รอบ1 broad → รอบ2 verify+ลึก → รอบ3 final/release-ready  (review→fix ×3)
//   2) จบ 3 รอบ → analyze+test → build → อัพ Play internal (mobile) + Drive → อัปเดต memory + bug/ + SHARED_LESSONS → รายงาน findings/fixes/สรุปโทเค้น
//
// ⛔ AGENT CAP (Nick #16): 3 ตัว/รอบ · ทำ "ทีละรอบ" (Coddy เรียกสคริปต์นี้ทีละครั้ง) → ไม่เกิน 3 ตัวพร้อมกันเลย
//    รวมทั้งรัน = 9 ตัว แต่ sequential. ❌ ห้ามเรียกสคริปต์นี้ 3 ครั้งพร้อมกัน · ❌ agent ห้ามแตกลูก (review-only)
//    (เหตุที่ต้องเป็นสคริปต์ = บังคับ 3/รอบ เหมือน tester.js กัน fan-out 70-agent 2026-06-13)
// ───────────────────────────────────────────────────────────────────────

// ⚠️ args มาถึงสคริปต์เป็น JSON "string" ในฮาร์เนสนี้ (พิสูจน์ 2026-06-13) → ต้อง parse + กัน throw · ❌ ห้ามลบ guard
let _A = args
if (typeof _A === 'string') { try { _A = JSON.parse(_A) } catch { _A = {} } }
_A = _A || {}
const workdir = _A.workdir
if (!workdir)
  return { error:'supertester: ไม่มี workdir ใน args — ส่ง args เป็น object {workdir, round, scope}', findings:[], lenses:[] }
const round = Number(_A.round) || 1               // 1 | 2 | 3
const scope = (_A.scope || '').toString().trim()  // สรุป "งานล่าสุด" ที่ Coddy ส่งมา (ว่างได้ — agent อ่าน log เอง)

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

// lens ลึกขึ้นต่อรอบ — รอบหลังต่อยอดจากของที่เพิ่งแก้
const ROUNDS = {
  1: { name:'broad scan (สแกนกว้างจากงานล่าสุด)', lenses:[
    { key:'functional-gaps', title:'① ช่องโหว่ฟังก์ชัน', brief:'ฟีเจอร์ขาด/ทำครึ่ง · flow ตัน · ปุ่ม/หน้าไม่ wire · error/empty/edge state ไม่จัดการ · โค้ดมีแต่ไม่มี UI · onboarding/permission ที่ทำแอป soft-brick' },
    { key:'code-correctness', title:'② ความถูกต้องโค้ด', brief:'บั๊ก logic · race · null/empty/ค่าใหญ่/ลำดับ · ทางทำข้อมูลหาย · regression ตรงรอยต่อการแก้ล่าสุด · serialization ไม่ตรง · drop เงียบๆ' },
    { key:'holistic', title:'③ ภาพรวม perf/UX/โครงสร้าง', brief:'งานเปลืองเกินจำเป็น · ผิดโครงสร้าง · pattern ไม่สม่ำเสมอ · security/privacy · perf บน path หลัก · UX สะดุด' },
  ]},
  2: { name:'verify + deeper (ตรวจของที่แก้ + ขุดลึก)', lenses:[
    { key:'fix-verify-regression', title:'① ตรวจฟิกซ์รอบก่อน + regression', brief:'ของที่เพิ่งแก้รอบที่แล้ว แก้จริง/ครบทุกจุดไหม (grep หา occurrence ที่ตกหล่น) · การแก้สร้างบั๊กใหม่ตรงรอยต่อไหม · อ่าน log/bug ล่าสุดเทียบกับโค้ดจริง' },
    { key:'deep-correctness-data', title:'② correctness ลึก + ความปลอดภัยข้อมูล', brief:'edge/null/concurrency/ลำดับ · atomic write / clear-then-parse / WAL / serialization ฟิลด์ใหม่ · ทางที่ข้อมูลหายตอน crash/ไฟดับ · silent drop · ดูเทียบ SHARED_LESSONS' },
    { key:'security-privacy', title:'③ security / privacy', brief:'secret ใน tracked file · key/permission/allowBackup · auth บน endpoint · path traversal/zip-slip · ข้อมูลลับใน backup/log' },
  ]},
  3: { name:'final / release-ready (ปิดจ็อบ)', lenses:[
    { key:'acceptance-vs-intent', title:'① ทำได้ตรงเจตนาจริงไหม (end-to-end)', brief:'เดิน flow จริงทั้งเส้นเทียบกับ "สิ่งที่ Nick สั่งล่าสุด" (จาก log/scope) · ผลลัพธ์ตรงเจตนาไหม · acceptance จริง ไม่ใช่แค่ unit test เขียว' },
    { key:'cross-file-consistency', title:'② regression sweep + ความสม่ำเสมอข้ามไฟล์', brief:'กวาดทั้งบริเวณที่แตะ · version/const หลายที่ตรงกันไหม · สำเนา logic ที่ลืมอัพเดท · dead code/TODO ที่ค้าง' },
    { key:'release-readiness', title:'③ พร้อมปล่อย', brief:'กับดัก build/release (versionCode, R8, manifest, obfuscate) · UX polish รอบสุดท้าย · copy/marketing ตรงความจริง · ของที่ต้องทำก่อนปล่อยจริง' },
  ]},
}
const R = ROUNDS[round] || ROUNDS[1]

const reviewPrompt = (lens) => [
  `คุณคือ 1 ใน "ทีม SuperTester" ของ Nick — **เป๊ะ 3 ตัว** ทำขนานกัน · นี่คือ **รอบที่ ${round}/3 (${R.name})** · คุณรับผิดชอบ lens: **${lens.title}**`,
  lens.brief,
  ``,
  `ออดิตโปรเจคปัจจุบันที่: ${workdir}`,
  scope ? `ขอบเขตที่ Coddy สรุปจากงานล่าสุด: ${scope}` : ``,
  `**ก่อนรีวิว**: อ่าน \`log/\` ไฟล์ล่าสุด (20 entry ล่าสุด) + \`bug/\` ล่าสุด + ดูการเปลี่ยนแปลงล่าสุด (git ถ้ามี) เพื่อเข้าใจ "สิ่งที่เพิ่งทำ" แล้วโฟกัสรีวิวบริเวณนั้นเป็นหลัก (แต่จับบั๊กร้ายแรงนอกบริเวณได้ด้วย)`,
  round >= 2 ? `รอบนี้ต่อยอด: สมมติรอบก่อนแก้ไปบางส่วนแล้ว — ตรวจว่าแก้ครบ/ไม่ regress และขุดที่ลึกกว่าเดิม` : ``,
  `ใช้ **Read / Grep / Glob (+ Bash อ่านอย่างเดียว เช่น git diff/log) เท่านั้น** · เดิน code path จริง end-to-end (ไม่เดาจากชื่อไฟล์) · cite file:line เสมอ · แยก "claim" กับ "ยืนยัน/ค้านแล้ว"`,
  ``,
  `⛔ กฎเหล็ก (Nick #16 — เหตุ 70-agent 2026-06-13):`,
  `  • ❌ ห้ามเรียก Agent/Task tool · ❌ ห้าม spawn subagent — คุณรีวิว "คนเดียว"`,
  `  • ❌ ห้ามแก้/เขียน/build/run อะไรที่เปลี่ยนสถานะ — "อ่านแล้วรายงาน" อย่างเดียว`,
  `  • ต้องการตัวช่วย → เขียนเป็น finding ให้ Coddy แทน · ❌ ห้าม spawn`,
  ``,
  `คืน findings ทุกจุดที่เจอ "จริง": severity P0–P3 · title สั้น · file (file:line) · problem · suggestedFix · evidence · เรียง blocker→nit · ❌ ห้าม pad nit · ❌ ห้าม rubber-stamp · ไม่แน่ใจ = severity ต่ำ + บอกว่ายังไม่ยืนยัน`,
].filter(Boolean).join('\n')

phase('รีวิว')

// ⛔ เป๊ะ 3 ตัว — parallel ครั้งเดียว ไม่มี fan-out ตาม finding
const reports = (await parallel(R.lenses.map(lens => () =>
  agent(reviewPrompt(lens), { label:`R${round}:${lens.key}`, phase:'รีวิว', schema: FINDINGS })
))).filter(Boolean)

const order = { P0:0, P1:1, P2:2, P3:3 }
const findings = reports
  .flatMap(r => (r.findings || []).map(f => ({ ...f, lens: r.lens })))
  .sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9))
const tally = sev => findings.filter(f => f.severity === sev).length

log(`SuperTester รอบ ${round}/3 (${R.name}) เสร็จ: ${reports.length}/3 lens · ${findings.length} findings (P0:${tally('P0')} P1:${tally('P1')} P2:${tally('P2')} P3:${tally('P3')})`)

return {
  round,
  roundName: R.name,
  agentsUsed: R.lenses.length,   // = 3 เสมอ (script บังคับ ไม่มีทางเกิน)
  lenses: reports.map(r => ({ lens: r.lens, summary: r.summary, count: (r.findings || []).length })),
  findings,
  next: round < 3
    ? `Coddy: verify + แก้เอง (0 agent) → แล้วเรียกสคริปต์นี้ "รอบ ${round + 1}" ต่อ`
    : `Coddy: verify + แก้เอง (0 agent) → จบ 3 รอบ → analyze+test → build → อัพ Play/Drive → อัปเดต memory/bug/SHARED_LESSONS → รายงาน findings/fixes/สรุปโทเค้น`,
}
