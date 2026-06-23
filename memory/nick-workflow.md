# nick-master-workflow.md
**Central rule-state brief — read THIS ONE small file to know what's current (sync point for all instances)**

> 📍 Master copy: `C:\Users\NickSuksanTr\Documents\Claude\Projects\Nick\nick-master-workflow.md`
> 📍 Every project keeps a synced copy: `[project]\memory\nick-workflow.md` (English)
> ⚙️ **Update rule:** anyone who changes MASTER / SHARED / command_pattern / any workflow rule MUST update this brief in the same sitting — this file is the single sync point.
> ⚡ **Trigger "sync กฎ"** (Nick, in any project): read this file ONLY → update that project's `memory\nick-workflow.md` + MEMORY.md quick-ref where changed. ❌ No full MASTER re-read.

---

## Current rule state

| File | State |
|---|---|
| command_pattern.md | **v3.10** · 2026-06-22 · English · **22 rules** |
| MASTER.md | 2026-06-11 · English · Section 0 Fast Path |
| SHARED.md | 2026-06-11 · English (tool data as of 2026-06-09) |
| Note Master.txt | Nick's handwritten (Thai) — versioning line (3-digit `v0.0.0`) again matches #14.7 since 2026-06-12 |

## Workflow essence

- **Fast Path:** new/cleared chat → read `[project]\memory\MEMORY.md` + latest 1 file in `chat_log\` → work. Full MASTER chain ONLY on "อ่าน MASTER" / first onboarding.
- **Language:** chat with Nick = Thai · all written records = English (#17) · **Nick's quotes too — paraphrase to English, no verbatim Thai** (triggers are the only exception).
- **chat_log:** append 1 essence entry (asked/done/decisions/pending) after every task (#18).
- **Records:** 20 entries/file · keep 2 files/category · older → `_trash\` · never read `_trash\` (#6–#8).
- **Versioning:** **3 digits `vX.Y.Z`** for ALL projects, each digit 0–9, carry at 9 (`v0.0.9`→`v0.1.0`) · never `v1.022` · 2-digit `vX.Y` (06-11) REVOKED (#14.7).
- **Tester / Lucifer:** run ONLY when Nick types the trigger himself · **default ≤3 agents/round, max 5, >5 STOP+ask** · **"unlimited tokens" ≠ unlimited agents** (Tester = `tester.js` only — 3 review-only agents, Coddy fixes itself 0 agents · Lucifer = `lucifer.js` only, ≤5/round) · never self-start · **FAIL = STOP, not retry: fail/error/empty → report + wait for Nick, never blind-retry or self-re-launch (1 trigger = 1 launch), diagnose 0-agent first** · frugal default (#5/#12/#16).
- **New project:** grill (#13) → feature-based structure, two stacks only: Flutter / Python+CustomTkinter (#14) → README + CODEMAP (#15).
- **Gemini:** AI Studio key only · `gemini-3.1-flash-lite` · RPM15/RPD500 · **never borrow another project's key** — key-path listings (e.g. `~/.happy/auth.json`) are location pointers only; each project's key lives in its own `.env` (#2).
- **Git push (#20, 2026-06-16):** task done → **commit + push automatically**, no asking · no remote yet = create a **private** repo once (`gh repo create <proj> --private --source=. --remote=origin --push`) after a secret-scan of tracked files · **never force-push / never push over a diverged remote**, on fail report + keep the commit · shippable apps also build+upload per their own conventions (analyze 0 + tests green) · memory/docs-only = commit+push, no build.
- **Git pull (#21, 2026-06-22):** session start in a git repo w/ remote → **`git fetch` FIRST; behind → `git pull --ff-only` BEFORE working**; **diverged → STOP, never force-push.** Cloud (GitHub agent/web) + local share the repo as the bus — whoever finishes pushes code+records, whoever starts pulls first → no one builds on stale state / clobbers the other. Global SessionStart hook `~/.claude/git-sync-check.ps1` auto-fetches + warns if behind. Pairs with #20 (#21 = pull at start · #20 = push at end).
- **Rules-in-repo (#22, 2026-06-22):** a cloud/web instance sees ONLY the repo (not `~/.claude/`, skills, master files). So **every repo has a tracked root `CLAUDE.md` bootstrap** → any instance auto-reads it (session start: read `memory/MEMORY.md` + chat_log + `memory/nick-workflow.md`; follow) + key rules inline. **New repo (#20/#14.8) MUST be created WITH it:** copy `templates/CLAUDE.template.md` → root + current `nick-workflow.md` → `memory/` in the first commit. A cloud instance spinning up a new project replicates these from its OWN repo. ⚠️ local-only tooling (`tester.js`/`lucifer.js`/`/chat`/`/coddymesh`) is NOT in repos → cloud can't run them unless committed.

## Latest changes (newest first — keep max 10, move older lines to the bottom note)

★ **2026-06-22 (newest)** — **#22 added: rules-in-repo / bootstrap `CLAUDE.md`.** A cloud/web instance sees ONLY the repo (not `~/.claude/`, skills, master files) — so every repo now carries a tracked root `CLAUDE.md` that auto-loads the workflow (read memory/MEMORY + chat_log + nick-workflow → follow) + key rules inline. New repos are created WITH it (copy `templates/CLAUDE.template.md` + `nick-workflow.md` in the first commit, #20/#14.8); a cloud instance spinning up a new project replicates these from its own repo. Local-only tooling (tester.js / lucifer.js / /chat / /coddymesh) is NOT in repos → a cloud instance can't run them unless the script is committed. Created CLAUDE.md across the active repos; template lives in `Test-Memory-Structure-Workflow/templates/`. (command_pattern → v3.10)

**2026-06-22** — **#21 added: pull-before-work (git sync).** Session start in a git repo with a remote → `git fetch`; if BEHIND → `git pull --ff-only` BEFORE working; DIVERGED → STOP (never force-push). Reason: the GitHub cloud agent pushes commits newer than local, so local must sync first or it works on stale state / clobbers the cloud. Commit+push code **and** records on both sides so a pull restores full context (what + why). Global SessionStart hook `~/.claude/git-sync-check.ps1` auto-`git fetch`es + injects a "GIT SYNC: behind/diverged" warning. Pairs with #20 (#21 pull at start · #20 push at end). Mirrored: CLAUDE.md READ-FIRST #1 + MASTER Section 0 + command_pattern #21. (command_pattern → v3.9)

**2026-06-16** — **#20 added: auto-commit + auto-push on task done.** `git push` is now **automatic after every commit** (was: auto-commit project-only, push manual). No remote yet → create a **private** GitHub repo ONCE (`gh repo create <proj> --private --source=. --remote=origin --push`) after a secret-scan of tracked files; on failure report + keep the commit, **never force-push / never push over a diverged remote**. Shippable apps still build+upload per their own conventions (analyze 0 + tests green); memory/docs-only = commit+push only. Supersedes the 2026-06-14 project-only auto-commit note — now universal for every project + instance. (command_pattern → v3.8)

1. **2026-06-13** — #16 gains **STOP-on-fail**: a workflow/agent returning fail/error/empty/unexpected = **STOP + report + wait for Nick** — never blind-retry / tweak-args-and-refire / self-re-launch (**1 Nick-trigger = 1 launch**), diagnose **0-agent** first. Cause: the args-as-string bug → Coddy blind-retried Lucifer **6× (×10 = 60 agents)**; fixed by `lucifer.js`/`tester.js` JSON.parse args (fail-fast 0-agent). (command_pattern → v3.7)
2. **2026-06-13** — #16 cap TIGHTENED + #5 Tester SCRIPTED. A single "Tester" run hit **~70 agents**. Now **default ≤3/round · max 5 · >5 STOP+ask**; "unlimited tokens" ≠ unlimited agents. Tester → deterministic `tester.js` (3 review-only → Coddy fixes itself, 0 agents); Lucifer = `lucifer.js` only. Never self-start. (command_pattern → v3.6)
3. **2026-06-12** — #2: NEVER borrow another project's API key (`~/.happy/auth.json` etc.) — path listings are location pointers, not usage permission. (command_pattern → v3.4)
4. **2026-06-12** — #14.7 versioning reverted to **3 digits `vX.Y.Z`** for all projects (the 2026-06-11 2-digit rule caused confusion, revoked). Carry at 9 stays. (command_pattern → v3.3)
5. **2026-06-11** — #17 tightened: Nick's direct quotes also paraphrased to English — NO verbatim Thai in any record (command_pattern → v3.2).
6. **2026-06-11** — Rule-sync brief system: this file + per-project `memory\nick-workflow.md` + trigger "sync กฎ" (#19, command_pattern → v3.1).
7. **2026-06-11** — English restructure: MASTER/SHARED/command_pattern in English · Fast Path · records English (#17) · chat_log (#18) · read cap latest 1 file/20 entries (#8) · keep 2 files/category (#7) · never read `_trash` (#6).
8. **2026-06-11** — Tester/Lucifer trigger-only by Nick, never self-start · frugal default (#5/#12/#16).
9. **2026-06-11** — Versioning `vX.Y` digits 0–9, carry at 9 (#14.7). *(Revoked 2026-06-12 — see item 4.)*
10. **2026-06-10** — #16 agent cap first added (24-agent incident @NotiWallet) — superseded by items 1–2.

> Older: **2026-06-09** — #14 feature-based structure · #15 README/CODEMAP · Streamlit/web retired.

---
— Created 2026-06-11 by Coddy (Nick's order, designed in Test-Memory-Structure-Workflow) —
