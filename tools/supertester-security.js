export const meta = {
  name: 'supertester-security',
  description: 'SuperTester Security — รีวิว "มุมผู้โจมตี" เชิงลึก เป๊ะ 3 รอบ รอบละ 3 agent (attacker angle ละตัว: 🌐 Remote/Network · 🔧 Tampering/Supply-chain · 🔑 Auth/Privilege/Secrets) ทำทีละรอบ (recon → exploit-chain → remediation-verify). 🔐 SAFE MODE (approve-before-fix): review→Coddy เสนอแผนแก้(พร้อม side-effect/blast-radius)→รอ Nick อนุมัติ→แก้เฉพาะที่อนุมัติบน security branch แยก(+backup)→รอบถัดไป · ❌ ไม่ auto-build/deploy. Defensive audit ระบบของ Nick เอง — agent อ่านโค้ด+รายงานช่องโหว่+วิธี harden อย่างเดียว · ❌ ไม่เขียน exploit/ไม่ยิง/ไม่แก้/ไม่ build/ไม่ spawn. สคริปต์นี้ = เครื่องยนต์ "1 รอบ" (3 agent) · แยกจาก supertester.js เดิม 100% (security-only, อัพเดต supertester ไม่กระทบกัน)',
  phases: [
    { title: 'ตรวจช่องโหว่', detail: '3 agent (attacker angle ละตัว) รีวิวอย่างเดียว → คืน findings P0–P3 + attack chain + blast radius' },
  ],
}

// ───────────────────────────────────────────────────────────────────────
// เรียกผ่าน: Nick พิมพ์ "supertester security" → Coddy ทำแบบเดียวกับ supertester (#23) แต่ lens = "มุมผู้โจมตี":
//   0) Coddy หาขอบเขตเอง: อ่าน "สิ่งที่เพิ่งทำล่าสุด" + log\ 20 entry ล่าสุด → สรุปเป็น scope
//   1) วน "เป๊ะ 3 รอบ" — แต่ละรอบ:
//        a) เรียก Workflow: { scriptPath:"<ไฟล์นี้>", args:{ workdir, round, scope } } → 3 agent (angle ละตัว) รีวิว → findings
//        b) Coddy (ตัวหลัก): verify กับโค้ดจริง → **เสนอแผนแก้ (พร้อม side-effect/blast-radius ต่ออัน) → หยุดรอ Nick อนุมัติ**
//           → แก้เฉพาะที่อนุมัติ บน "security branch" แยก (backup ก่อน) → 0 agent → รอบถัดไป
//      รอบ1 Recon (แผนที่พื้นผิวโจมตี) → รอบ2 Exploit-chain+verify (ต่อ chain จริง เดิน code path) → รอบ3 Remediation-verify+residual (ปิดจ็อบ)
//   2) จบ 3 รอบ → analyze+test → security-regression → **STOP: สรุป hardening report + residual/blast-radius/verdict trusted-LAN**
//      → memory + bug/ + SHARED_LESSONS (หมวด security) → **Nick ตัดสินใจ build/deploy เอง (❌ ไม่ auto-build/upload ลงเรือ)**
//
// 🔐 SAFE MODE (approve-before-fix) — Nick เลือก 2026-07-12: security fix มี blast radius สูง (ใส่ auth → client หลุด,
//    pin signature → updater ตาย, เข้ม validation → ข้อมูลถูกต้องโดน reject) → บนระบบเรือจริง "ห้าม" auto-fix เหมือน Tester.
//    Coddy ต้อง เสนอ→รออนุมัติ→แก้บน branch เท่านั้น. agent = read-only อยู่แล้ว (ออดิตไม่มีทางพังระบบ); ด่านอนุมัตินี้กันช่วง "แก้".
//
// 🛡️ กรอบงาน = DEFENSIVE / AUTHORIZED: ระบบของ Nick เอง, audit เพื่อป้องกัน. agent หา "ช่องโหว่จริง" จากการอ่านโค้ด
//    แล้วรายงาน + เสนอวิธี harden. ❌ ไม่เขียน exploit/PoC พร้อมยิง · ❌ ไม่เขียนมัลแวร์/เครื่องมือหลบการตรวจจับ · ❌ ไม่ยิง/สแกน/รัน/ต่อระบบจริง
//
// ⛔ AGENT CAP (Nick #16): 3 ตัว/รอบ · ทำ "ทีละรอบ" (Coddy เรียกสคริปต์นี้ทีละครั้ง) → ไม่เกิน 3 ตัวพร้อมกันเลย
//    รวมทั้งรัน = 9 ตัว แต่ sequential. ❌ ห้ามเรียกสคริปต์นี้ 3 รอบพร้อมกัน · ❌ agent ห้ามแตกลูก (review-only)
//    (เหตุที่ต้องเป็นสคริปต์ = บังคับ 3/รอบ เหมือน supertester.js/tester.js กัน fan-out 70-agent 2026-06-13)
//    🛑 FAIL=STOP: รอบไหน error/empty/0-agent → รายงาน + หยุด รอ Nick (1 trigger = 1 รัน 3 รอบ) · ❌ ห้าม blind-retry
// ───────────────────────────────────────────────────────────────────────

// ⚠️ args มาถึงสคริปต์เป็น JSON "string" ในฮาร์เนสนี้ (พิสูจน์ 2026-06-13) → ต้อง parse + กัน throw · ❌ ห้ามลบ guard
let _A = args
if (typeof _A === 'string') { try { _A = JSON.parse(_A) } catch { _A = {} } }
_A = _A || {}
const workdir = _A.workdir
if (!workdir)
  return { error:'supertester-security: ไม่มี workdir ใน args — ส่ง args เป็น object {workdir, round, scope}', findings:[], angles:[] }
const round = Number(_A.round) || 1               // 1 | 2 | 3
const scope = (_A.scope || '').toString().trim()  // สรุป "งานล่าสุด" ที่ Coddy ส่งมา (ว่างได้ — agent อ่าน log เอง)

// schema security-only (ต่างจาก supertester: เพิ่ม attackVector / exploitChain / blastRadius / likelihood / assumptionChallenged)
const FINDINGS = { type:'object', required:['angle','summary','findings'], properties:{
  angle:   { type:'string' },
  summary: { type:'string' },
  findings:{ type:'array', items:{ type:'object',
    required:['severity','title','file','problem','attackVector','suggestedFix'], properties:{
      severity:     { type:'string', enum:['P0','P1','P2','P3'] }, // P0 = unauth remote/LAN/RF → code-exec/full-node/mesh/update-channel takeover
      title:        { type:'string' },
      file:         { type:'string' },   // file:line = หลักฐาน
      problem:      { type:'string' },
      attackVector: { type:'string' },   // ใครโจมตีได้ + precondition (remote / LAN / RF-mesh / local / physical · ต้องมี cred ไหม)
      exploitChain: { type:'string' },   // ขั้นตอนเชิงอธิบาย "พอให้เข้าใจ+แก้" — ❌ ไม่ใช่ PoC พร้อมยิง
      blastRadius:  { type:'string' },   // โดนแล้วลามแค่ไหน (1 node → ทั้ง mesh? ทั้งเรือ? แค่ session?)
      likelihood:   { type:'string' },   // โอกาสจริงตาม trust model ที่เป็นอยู่
      assumptionChallenged: { type:'string' }, // สมมติฐานที่ท้า เช่น "trusted-ship-LAN" ยัง valid ไหม
      suggestedFix: { type:'string' },   // วิธี harden (auth/allowlist/signing/param-bind/least-priv/CSP ฯลฯ)
      evidence:     { type:'string' },   // code path ที่ตรวจแล้วยืนยัน
    } } } } }

// 3 มุมผู้โจมตี "คงที่ทุกรอบ" (agent ละมุม ตามที่ Nick วางไว้) — ความลึกเปลี่ยนตามรอบ (ROUND_FOCUS ด้านล่าง)
const ANGLES = [
  { key:'network', title:'🌐 Remote / Network',
    base:'ทุกช่องทางที่เข้าถึงจาก "นอกกระบวนการ": MQTT/broker (anonymous? bind 0.0.0.0:1883?), webserver/REST/socket บน LAN (มี auth ไหม เช่น :47820), broadcast/discovery, mesh RF (Zigbee/ESP-NOW — spoof/replay ได้ไหม), mesh_key/PSK. คำถามหลัก: peer ที่ไม่มี credential ปลอม readings/alarms/board-state หรือยิงคำสั่งควบคุมได้ไหม' },
  { key:'tampering', title:'🔧 Tampering / Supply-chain',
    base:'ความสมบูรณ์ของโค้ด/ไบนารี + ช่องที่ของ "ไม่พึงประสงค์" เข้าระบบได้: auto-updater (ดาวน์โหลด+รัน .exe /SILENT จาก public repo — hijack / MITM / downgrade / ไม่เช็ค signature?), installer/UAC, native bridge (pywebview JS→Python: XSS → เรียก full API?), DLL search-order planting, plugin/ไฟล์ภายนอกที่โหลดเข้ามารันได้' },
  { key:'auth-secrets', title:'🔑 Auth / Privilege / Secrets',
    base:'ตัวตน/สิทธิ์/ความลับ + สมมติฐานความเชื่อใจ: roles + @_gate (bypass / privilege escalation?), secret at-rest (auth.json, default/hardcoded password), input sink (SQLi, topic injection, path traversal, zip-slip). **ท้าสมมติฐาน "trusted-ship-LAN"** ว่าจริงไหม — โดน 1 จุด (มือถือแขก, sensor ปลอม, USB) แล้ว blast radius แค่ไหน' },
]

// ความลึกต่อรอบ (recon → exploit → remediation-verify) — key ตรงกับ ANGLES
const ROUND_FOCUS = {
  1: { name:'Recon — แผนที่พื้นผิวโจมตี (เขียน trust model ออกมา)', by:{
    'network':      'ลิสต์ listener/port/topic/broadcast/RF-channel ทั้งหมด + trust boundary — อะไร "เปิดโดยไม่ต้อง auth" · จุดไหนรับ input จากภายนอกโดยตรง',
    'tampering':    'ลิสต์ช่อง download/exec/native-bridge/DLL-path/สิทธิ์ install ทั้งหมด — ทุกจุดที่โค้ดหรือไบนารี "ถูกแทน/แทรก" ได้',
    'auth-secrets': 'ลิสต์ role/gate/secret-at-rest/input-sink ทั้งหมด + เขียน "trust model ปัจจุบัน" ออกมาเป็นข้อๆ (ใครเชื่อใครโดยอัตโนมัติ)',
  }},
  2: { name:'Exploit-chain + verify — ต่อ chain จริง เดิน code path ยืนยัน', by:{
    'network':      'ต่อ chain: rogue publisher ปลอม reading/alarm/board · spoof/replay mesh · no-auth fetch/command — เดิน code path ยืนยัน "ยิงได้จริง" + ระบุ precondition ชัด',
    'tampering':    'ต่อ chain: updater hijack/MITM/downgrade · รัน .exe ที่ไม่ verify · XSS→bridge→API · DLL planting — ยืนยันจาก code path ว่าถึง sink จริง',
    'auth-secrets': 'ต่อ chain: privilege escalation · default/leaked cred · injection (SQL/topic/path/zip) — **ท้า trusted-LAN**: ถ้า LAN "ไม่" trusted ช่องไหนพังทันที + blast radius แต่ละช่อง',
  }},
  3: { name:'Remediation-verify + residual risk — ปิดจ็อบ (สมมติ Coddy แก้ R1–R2 ไปแล้ว)', by:{
    'network':      'ยืนยัน auth/allowlist/signing ที่เพิ่ม "ปิดช่องจริง" ไม่มี bypass/variant ตกหล่น (grep occurrence อื่นของ pattern เดิม) → residual + blast radius คงเหลือ',
    'tampering':    'ยืนยัน signature-pin/CSP/UAC/DLL-hardening "ปิดช่องจริง" ไม่มีทางอ้อม → residual',
    'auth-secrets': 'ยืนยัน least-priv/param-bind/secret-handling → **verdict สุดท้าย: "trusted-ship-LAN" valid ไหมหลัง harden + blast radius คงเหลือ + hardening checklist ก่อนปล่อยจริง**',
  }},
}
const RF = ROUND_FOCUS[round] || ROUND_FOCUS[1]

const reviewPrompt = (angle) => [
  `คุณคือ 1 ใน "ทีม SuperTester Security" ของ Nick — **เป๊ะ 3 ตัว** ทำขนานกัน (angle ละตัว) · นี่คือ **รอบที่ ${round}/3 (${RF.name})** · คุณรับผิดชอบมุม: **${angle.title}**`,
  angle.base,
  `โฟกัสรอบนี้: ${RF.by[angle.key]}`,
  ``,
  `ออดิตโปรเจคปัจจุบันที่: ${workdir}`,
  scope ? `ขอบเขตที่ Coddy สรุปจากงานล่าสุด: ${scope}` : ``,
  `**ก่อนรีวิว**: อ่าน \`log/\` ล่าสุด (20 entry) + \`bug/\` ล่าสุด + ดูการเปลี่ยนแปลงล่าสุด (git ถ้ามี) เพื่อเข้าใจ "สิ่งที่เพิ่งทำ" แล้วโฟกัสบริเวณนั้นก่อน (แต่จับช่องโหว่ร้ายแรงนอกบริเวณได้ด้วย)`,
  round >= 2 ? `รอบนี้ต่อยอด: สมมติรอบก่อน Coddy harden ไปบางส่วนแล้ว — ตรวจว่าปิดครบ/ไม่มี variant หลุด และต่อ chain ที่ลึกกว่าเดิม` : ``,
  ``,
  `🛡️ กรอบงาน (DEFENSIVE / AUTHORIZED): นี่คือระบบของ Nick เอง — audit เพื่อ "ป้องกัน". หน้าที่คุณ = หา "ช่องโหว่จริง" จากการอ่านโค้ด แล้วรายงาน + เสนอวิธี harden`,
  `  • ✅ อธิบาย exploit chain "พอให้เข้าใจและแก้ได้" (precondition + code path)`,
  `  • ❌ ไม่เขียน exploit/PoC ที่พร้อมนำไปใช้โจมตีจริง · ❌ ไม่เขียนสคริปต์โจมตี/มัลแวร์/เครื่องมือหลบเลี่ยงการตรวจจับ`,
  `  • ❌ ไม่ยิง/สแกน/รัน/เชื่อมต่อระบบจริงใดๆ — static code audit อย่างเดียว`,
  ``,
  `คิดแบบผู้โจมตี แต่รายงานแบบฝ่ายป้องกัน · ใช้ **Read / Grep / Glob (+ Bash อ่านอย่างเดียว เช่น git diff/log) เท่านั้น** · เดิน code path จริง end-to-end (ไม่เดาจากชื่อไฟล์) · cite file:line เสมอ · แยก "claim" กับ "ยืนยัน/ค้านแล้ว"`,
  ``,
  `⛔ กฎเหล็ก (Nick #16 — เหตุ 70-agent 2026-06-13):`,
  `  • ❌ ห้ามเรียก Agent/Task tool · ❌ ห้าม spawn subagent — คุณรีวิว "คนเดียว"`,
  `  • ❌ ห้ามแก้/เขียน/build/run อะไรที่เปลี่ยนสถานะ — "อ่านแล้วรายงาน" อย่างเดียว`,
  `  • ต้องการตัวช่วย → เขียนเป็น finding ให้ Coddy แทน · ❌ ห้าม spawn`,
  ``,
  `severity: **P0** = unauth จาก remote/LAN/RF → code-exec / ยึด node / ยึด mesh / ยึดช่อง update · **P1** = แบบเดียวกันแต่ต้องมี precondition, หรือ spoof alarm/ปลอมข้อมูลร้ายแรง · **P2** = ต้อง local/มี cred/จำกัดผล · **P3** = defense-in-depth / hardening nit`,
  `คืน findings ทุกจุดที่เจอ "จริง": severity · title สั้น · file (file:line) · problem · attackVector · exploitChain · blastRadius · likelihood · assumptionChallenged(ถ้ามี) · suggestedFix · evidence · เรียง P0→P3 · ❌ ห้าม pad · ❌ ห้าม rubber-stamp · ไม่แน่ใจ = severity ต่ำ + บอกว่ายังไม่ยืนยัน`,
].filter(Boolean).join('\n')

phase('ตรวจช่องโหว่')

// ⛔ เป๊ะ 3 ตัว — parallel ครั้งเดียว ไม่มี fan-out ตาม finding
const reports = (await parallel(ANGLES.map(angle => () =>
  agent(reviewPrompt(angle), { label:`SEC-R${round}:${angle.key}`, phase:'ตรวจช่องโหว่', schema: FINDINGS })
))).filter(Boolean)

const order = { P0:0, P1:1, P2:2, P3:3 }
const findings = reports
  .flatMap(r => (r.findings || []).map(f => ({ ...f, angle: r.angle })))
  .sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9))
const tally = sev => findings.filter(f => f.severity === sev).length

log(`SuperTester Security รอบ ${round}/3 (${RF.name}) เสร็จ: ${reports.length}/3 angle · ${findings.length} findings (P0:${tally('P0')} P1:${tally('P1')} P2:${tally('P2')} P3:${tally('P3')})`)

return {
  round,
  roundName: RF.name,
  agentsUsed: ANGLES.length,   // = 3 เสมอ (script บังคับ ไม่มีทางเกิน)
  angles: reports.map(r => ({ angle: r.angle, summary: r.summary, count: (r.findings || []).length })),
  findings,
  next: round < 3
    ? `Coddy: verify → เสนอแผนแก้ (side-effect/blast-radius ต่ออัน) → **หยุดรอ Nick อนุมัติ** → แก้เฉพาะที่อนุมัติ บน security branch (+backup, 0 agent) → แล้วเรียกสคริปต์นี้ "รอบ ${round + 1}" ต่อ`
    : `Coddy: verify → เสนอแผนแก้ → **หยุดรอ Nick อนุมัติ** → แก้บน security branch (+backup) → จบ 3 รอบ → analyze+test → security-regression → **STOP: สรุป threat-model/findings/fixes/residual/blast-radius/verdict trusted-LAN + memory/bug/SHARED_LESSONS(หมวด security) → Nick ตัดสินใจ build/deploy เอง (❌ ไม่ auto-build/upload)**`,
}
