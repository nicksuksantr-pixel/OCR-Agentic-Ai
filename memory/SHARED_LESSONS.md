# SHARED_LESSONS.md — Cross-project bugs & lessons (shared by Cos + Coddy)

**The central registry of IMPORTANT, GENERAL bugs + their fixes across ALL projects.**
Reading MASTER surfaces this → any instance knows "who hit what important bug, and how it was
fixed" before starting work, so the same mistake isn't repeated in another project.

> Detail lives in each project's own `bug/` + `memory/MEMORY.md`. This file is the cross-project
> INDEX of the ones that bite OTHER projects too (curated; project-specific bugs stay in-project).
> A copy is mirrored into every project at `memory/SHARED_LESSONS.md` (via `sync-rules-to-projects.ps1`)
> so local AND cloud instances can read it. Format: **slug** (projects) — symptom → cause → fix.

## 📏 Rule — how this stays alive (pairs with bug-logging #10)
- After fixing a bug ask **"would this bite another project?"** → if yes, add/extend one row here, then re-run the sync script + commit.
- **Refresh:** periodically harvest each project's `bug/` + `MEMORY.md` (grep `Lesson`/`⚠`/`root cause`/`บทเรียน`) and promote the general ones.
- Read on **MASTER onboarding**; kept current via **"sync กฎ"** / cloud re-sync.

---

## ⚙️ Build / Release / Auto-update
- **gradle-loopback-windows-jdk21** (ScanDocs, Happy-Origin, MyDocs) — `flutter build` dies ~7s in: "Unable to establish loopback connection" (JDK21+Gradle9 on Windows). Cause: AF_UNIX pipe tmpdir bug + Gradle applies `-D` jvmargs AFTER daemon start, so `gradle.properties` is too late. Fix: set ENV `JAVA_TOOL_OPTIONS=-Djdk.net.unixdomain.tmpdir=C:/tmp -Djava.io.tmpdir=C:/tmp -Djava.net.preferIPv4Stack=true` + create `C:\tmp` (JVM honours it at startup).
- **build≠user-update** (HAPPY, PLC, OCR, Happy-Photo) — bumping/merging to main does NOT reach users; the updater pulls GitHub **Releases assets**. Release = build + push + `gh release create vX.Y.Z <asset> --latest` (+ SHA in body). `gh --target` needs a branch or FULL sha (short = 422).
- **updater-integrity-sha-gate** (HAPPY, PLC) — running a downloaded installer without a content-hash check = MITM/tamper risk. Parse expected SHA-256 from the release body, verify after download before launch; mismatch = wipe+retry; missing = skip (back-compat).
- **record-applied-only-after-success** (OCR) — writing "update applied" BEFORE the install runs poisons the updater forever on any failure. Gate solely on `is_newer(latest, RUNNING build)`; delete the poison flag on start.
- **version-compare-fixed-tuple** (OCR, HAPPY) — variable-length/zero-padded (`0.1.5.0`>`0.1.5`) or pre-release-equals-final compares break the updater. Fixed 3-tuple compare + pre-release < final.
- **check-update-every-start** (OCR) — a once-per-day throttle misses same-day releases. Check on every start (tiny anon call) + a manual "Check now".
- **play-versioncode-must-increase** (MyDocs, AI-Inventory) — Play rejects a duplicate versionCode; versionName may drop but versionCode must monotonically increase. Watch the **Gradle config-cache serving a stale versionCode** (just rebuild).
- **r8-for-native/sideload-apps** (Happy-Origin, AI-Inventory) — R8/minify fails on native/reflective deps (MediaPipe/protobuf); the failure is a **HARD CRASH**, not a silently-dead feature. For sideloaded apps disable R8 or add keep+dontwarn.
- **release-obfuscate-with-symbols** (AI-Inventory) — always `--obfuscate --split-debug-info=...\v<ver>` + ship symbols; a stale build note dropped them.
- **green-analyze/test≠release-build** (Happy-Origin) — analyze + unit tests run host-side and never exercise the Android release Gradle/R8 path. A real `build apk --release` is part of "done" for any native-plugin change.
- **pyinstaller-add-data-preserves-subfolders** (HAPPY) — `--add-data "src;."` flattens to bundle root → 404 on web assets. Use `dest = Path(asset).parent`.
- **pyinstaller-no-secret-in-spec** (HAPPY) — a PAT/.env bundled in the `.exe` is readable by anyone. Token-less updater (public repo) or a scoped/rotated PAT; never bundle secrets.
- **artifact-name-collision** (MyDocs, NotiWallet) — Flutter hardcodes `app-release.aab`; set `base.archivesName` + a `doLast` rename to `<App>-v<ver>.aab` and SHIP the renamed file (the build-log echo can be stale).
- **gh-release-notes-file** (OCR, MyDocs) — PowerShell here-strings mangle long inline `--notes`; Play caps notes at 500 chars/lang (fails at commit). Use `--notes-file`; keep ≤500/lang.

## 💾 Data / Persistence / Backup-Restore
- **atomic-write-everywhere** (ScanDocs, PLC, ENA) — in-place write of jobs.json/project/autosave → a kill or **power-loss** (Nick's ship dips) truncates and silently wipes. Write temp + flush + `os.fsync` + `os.replace` (atomic on NTFS).
- **parse-then-swap-never-clear-then-parse** (NotiWallet, ScanDocs) — restore that clears then parses a malformed/foreign backup wipes everything. Always parse-then-swap; extract to a staging dir then move; mirror the "claimed-but-none-parsed → abort" guard on EVERY box; only wipe when the zip has files; zip-slip guard.
- **wal-checkpoint-before-copy** (AI-Inventory, ENA) — copying a SQLite `.db` without flushing WAL gives stale data; leftover `-wal/-shm` on restore corrupts. `checkpoint()` before copy; delete siblings on restore. Wrap connections in `contextlib.closing` (a `with connect()` commits but never CLOSES).
- **new-field→update-(de)serialization** (NotiWallet, Happy-Origin) — adding a persisted field without updating to/from-map (or `fromMap` not reading a column) silently drops it on backup/reload. Update both maps in the SAME change + a round-trip test.
- **rebase-paths-inside-json-indexes** (ScanDocs) — restore that only re-bases prefs leaves absolute paths embedded INSIDE jobs.json → blank grid on a new device. Field-aware rebase of path fields ONLY (never password/credential fields), and only when the zip hasFiles.
- **open-box-retry-before-wipe** (NotiWallet) — auto-wipe on a single Hive `openBox` failure = data-loss time bomb. Retry 4x + restore from `.corrupt-*.bak`; check `apksigner` before blaming signing.
- **stream-large-zip-not-into-ram** (ScanDocs) — decoding a whole backup zip in RAM OOMs. Stream it.
- **soft-delete-upsert-reset-flag** (AI-Inventory) — upsert must set `deletedAt=null` on conflict, else it revives invisible trashed rows.
- **reset-static-caches-on-restore** (NotiWallet) — static caches mirroring the DB keep stale state after a restore. Reset them.
- **derive-identity-from-db-id-not-glob** (OCR) — numbering folders from a directory glob reuses a deleted id → "deleted jobs come back" + collisions. Derive identity from the monotonic DB id; make archive idempotent.
- **one-canonical-data-dir** (OCR) — splitting DATA_DIR on `sys.frozen` (dev vs installed) = two stores; many "wrong/old data" symptoms = ONE shared-state divergence first. One canonical `%LOCALAPPDATA%` store + migrate-legacy.
- **upsert-blank-cell-value-absent** (AI-Inventory) — `Value(blankCell)` = `Value(null)` overwrites existing columns on re-import. Emit `Value.absent()` for blanks.
- **audit-delta-from-live-not-snapshot** (AI-Inventory) — compute a stock delta from LIVE qty inside one txn, not a screen-open snapshot.
- **header-aware-table-mapping** (MyDocs) — mapping table cells by fixed positional index breaks when the real template's column count differs. Read the header row (handle gridSpan).
- **lexicographic-date-sort** (Happy-Photo) — sorting `DD-MM-YY` strings orders by day-of-month. Sort by a parsed `(yy,mm,dd)` key.
- **non-atomic-multi-connection-write** (OCR) — a merge across 3 DB connections loses data on a crash between steps. One transaction + a reconcile-on-start that re-folds any lost answer (idempotent).
- **empty-results-index-guard** (OCR, PLC) — indexing `results[0]`/`[-1]` or `max([])` crashes on empty input. Guard the empty case / pass `default=`.

## 🔐 Security / Secrets / Privacy
- **secret-never-in-tracked-file** (AI-Inventory, HAPPY) — a keystore password in MEMORY.md / a PAT shipped by auto-push. Reference secrets by LOCATION only; secret-scan staged CONTENT (`git grep --cached`) before the FIRST push.
- **unauthenticated-localhost-api** (OCR) — an on-by-default localhost POST API lets any local process spend quota. Require a token header (constant-time compare) on POST; GET-open is OK (CORS blocks browser reads).
- **android-allowbackup-false-for-secrets** (NotiWallet) — `allowBackup` defaults TRUE → financial DB/keys/PIN cloud-backed-up. Set `allowBackup=false` for any app holding secrets/financial data.
- **backup-doesnt-carry-credentials** (ScanDocs) — a backup zip carried users' plaintext PDF passwords; a blind path-replace also rewrote password fields. Warn+confirm before exporting; field-aware rebase never touches credential fields.
- **entitlement-not-backed-up** (ScanDocs) — never back up/restore `pro_active`; entitlement comes only from Play Billing.
- **strong-backup-kdf** (NotiWallet) — weak backup key-derivation. PBKDF2-HMAC-SHA256 (120k) + per-file salt.

## 🤖 AI / Gemini API
- **gemini-empty-candidates-rangeerror** (AI-Inventory) — `data['candidates']?[0]` throws RangeError on a SAFETY-blocked empty list (null-aware index only guards a null receiver). Empty-list-safe helper + throw a typed BlockedException (fail fast, no retry).
- **json-raw-decode-not-greedy-regex** (Happy-Photo) — greedy `{.*}`+DOTALL fails when the model emits prose/two objects. Use `JSONDecoder().raw_decode` scanning each `{`/`[`.
- **react-to-429-shared-cooldown** (NotiWallet, AI-Inventory) — a client limiter is per-device and can't cap a per-KEY quota across installs; proactive-only still 429s. REACT to the server 429 with a persisted SHARED cooldown; multi-device on one key needs separate keys; a 429 retry handler must CONSUME the budget or it loops forever.
- **grounding-separate-quota** (AI-Inventory) — Google-Search grounding has its own ~0 free-tier quota. On grounded-429 fall back to a plain call (static disable flag).
- **never-block-on-quota-in-timeout** (NotiWallet) — a quota-wait inside a timeout-wrapped path turns "quota exhausted" into "permanent failure". Bail fast with a retryable error.
- **tests-must-not-send-live-requests** (OCR, AI-Inventory) — smoke tests hitting the live sender burn real quota + drain the real queue; "green" hides it. Force the API key to None (returns before the drain) — NOT clear-rows (a queue-repopulating change defeats that guard); scope tests to rows they created + set a test DATA_DIR.
- **concurrent-drain-atomic-claim** (OCR, NotiWallet) — two drain paths grab the same item → double-spend quota. Module lock + atomic claim (`UPDATE…WHERE status='pending'`) + persist the dedup marker BEFORE the durable work; store content hashes, not file copies.
- **amount-in-text≠transaction** (NotiWallet) — a promo "win ฿999" got recorded as income. Promo gate (promo-signal AND no tx-signal) + an AI step-0 not_transaction check.
- **script-agnostic-on-device-gate** (NotiWallet) — ML Kit OCR is Latin-only, silently fails on Thai → everything floods the paid cloud. Use a script-agnostic signal (QR/2D barcode); fail CLOSED (skip) when OCR is unavailable.
- **thai-substring-intent-hijack** (NotiWallet, AI-Inventory) — Thai keyword matching by raw substring (Dart `\b` doesn't know Thai) mis-routes ('งบ' inside 'ยังไงบ้าง'). Thai-aware lookaheads + combine verb+noun signals.
- **resolve-provider-per-use** (AI-Inventory) — an agent capturing `ref.read(provider)` once keeps the stale keyless instance after a key change. Resolve per-use via a builder.
- **auth-gate-refresh-on-bg-validation** (HAPPY, AI-Inventory) — a key that passes format but is API-rejected (validated in background) must refresh the Run/insight gate.
- **verify-domain-data-vs-datasheet** (PLC) — a generated report embedded a fake part ('FX3N' = a clone) across versions. Verify model/domain names against a real datasheet, not AI/generated text; treat in-code warning comments as real signals.
- **tesseract-tha-on-english-hallucinates** (OCR) — `tha+eng` on no-Thai pages hallucinates Thai glyphs. Latin-dominance character-mass gate → rerun `eng` only; use `TESSDATA_PREFIX` env not a quoted `--tessdata-dir`.

## 🧠 Local / on-device LLM
- **thinking-model-shares-num_predict** (Open-Claw) — a thinking LLM returns ZERO answer (`done_reason: length`): think-trace + answer share one maxTokens budget. Raise the budget AND use an explicit `-instruct` tag (verify by manifest digest; bare/`-thinking` can't be disabled with `/no_think`).
- **local-llm-ram-paging-hang** (Open-Claw) — working set > free RAM → Windows pages to SSD → looks like a timeout (a bigger timeout never fixes a paging cause). Drop `num_ctx`; set `OLLAMA_KEEP_ALIVE` to free idle RAM. iGPU offload on shared DDR4 = ~0 gain.
- **on-device-llm-gated-download-dealbreaker** (Happy-Origin, Open-Claw) — a gated model + multi-GB download is the dealbreaker, not the code. For mobile, Ollama-direct beats a heavy agent prompt (CPU prefill overruns idle timeouts).

## 📱 Flutter / UI
- **imagefile-caches-by-path** (ScanDocs) — `Image.file`/`FileImage`/`imageCache` key by PATH not bytes; overwriting a fixed path shows the stale image. Unique filename + `ValueKey`, or evict the cache.
- **image-cachewidth-and-isolate** (ScanDocs) — full-res `Image.file` in a small cell OOMs / decoding on the main isolate freezes. Pass `cacheWidth`; move heavy image work to `Isolate.run` (pure-Dart only) in bounded batches.
- **riverpod3-keepalive** (ScanDocs) — Riverpod 3 auto-disposes by default → in-memory store dropped when the last watcher leaves. `ref.keepAlive()` in store providers.
- **runtime-theme-needs-watch-non-const** (ScanDocs) — a global-static token read won't notify + const widgets can't use runtime getters. `ref.watch` the theme on each page; drop `const` at broken sites.
- **predictive-back-bypasses-popscope** (NotiWallet) — Android target36 predictive-back bypasses PopScope. `enableOnBackInvokedCallback=false` + a BackPressHandler.
- **tree-shake-icons-runtime-codepoint** (MyDocs) — a runtime-built IconData is stripped by icon tree-shaking. Build with `--no-tree-shake-icons`.
- **dispose-controllers-and-ui-images** (AI-Inventory, ScanDocs) — TextEditingControllers in stateless dialogs + `dart:ui` Images + native `cv.Mat` leak. Dispose via `showDialog().then` / across the lifecycle; `try/finally` frees every Mat on the error path (guard `work==src` double-free).
- **stale-state-on-show/listen** (HAPPY, AI-Inventory) — `initState`-computed state in an always-mounted IndexedStack / segmented buttons / dropdowns goes stale after a Settings change. Re-sync from state on `on_show` / `ref.listen` in build (and `configure(values=)` when resetting a menu var).
- **pdf-page-physical-size** (ScanDocs) — raw image PIXELS used as PDF POINTS make an 80-inch page. Cap to a physical size (A4 842pt); embed the full-res image inside.
- **opaque-bg-per-transitioned-page** (ScanDocs) — translucent glass pages don't cover the old page on an instant push. Back each transitioned page with an opaque gradient (NOT BackdropFilter, which is expensive).
- **opencv_core-not-dartcv4** (ScanDocs) — `dartcv4` is the pure-Dart binding only (no Android `.so`) and dartcv4 2.2.1 uses native-assets hooks-1.0 that Flutter 3.44 (hooks-2.0) never invokes → green build, dlopen crash on first scan. Use `opencv_core` (bundles natives via gradle/jniLibs).

## 🪟 Windows / Platform / tooling
- **release-manifest-internet-permission** (Happy-Origin) — flutter create adds INTERNET only to debug/profile manifests → release APK has no network. Add it to the MAIN AndroidManifest.
- **request-post-notifications-at-onboarding** (NotiWallet) — Android13+ notifications silently dead if POST_NOTIFICATIONS is behind a feature toggle. Request at first run.
- **powershell-bom-pipe** (Coddy) — piping a string into node/python adds a UTF-8 BOM → `JSON.parse` fails silently. Strip the BOM.
- **powershell-mangles-json-cli-arg** (Open-Claw) — PowerShell mangles a JSON arg to a native CLI. Write the JSON to the config file directly.
- **windows-python-print-cp1252** (Coddy) — `print()` of Thai to the console throws even after the file write succeeded. Keep tool stdout ASCII.
- **dpi-aware-screen-capture** (PLC) — capture of a frozen app crops on high-DPI. `SetProcessDpiAwarenessContext(-4)` before capture.
- **schtasks-change-needs-password** (ScanDocs) — `schtasks /Change` prompts for the account password. Overwrite the task's target `.bat` in place + `schtasks /Run` (stored creds).
- **git-longpaths-deep-pubcache** (ScanDocs) — a deep MSIX-virtualized pub-cache path exceeds the Windows limit. `git config --global core.longpaths true`.
- **grep-nul-false-negative** (Coddy) — ripgrep silently skips binary/NUL files; cross-check a "not found" with Read.
- **in-agent-flutter-build-cannot-work** (ScanDocs) — the in-agent shell can't run the full Gradle/Flutter build (sandbox/loopback). Build via a Windows Scheduled Task; only analyze/test/deploy run in-agent.

## ⚙️ Workflow / process / agents
- **agent-hard-cap** (NotiWallet) — fan-out "1 agent per finding" burned 24→60 agents. ≤3/round · max 5 · >5 STOP+ask. FAIL = stop+report, never blind-retry; a single transient (e.g. SSL timeout) on a real upload may get ONE retry AFTER diagnosing — only loop-retrying fleets is banned.
- **workflow-args-string-not-object** (tester/lucifer) — the Workflow harness passes `args` as a JSON STRING; `args.x` is undefined unless `JSON.parse`'d first.
- **edit-source-with-edit-tool-not-heredoc** (MyDocs) — a bash heredoc turns `\n` into a real newline → SyntaxError. Edit source only with Edit/Write; if a script must, `ast.parse` right after writing.
- **verify-before-delete-or-claiming-fixed** (NotiWallet, ScanDocs, OCR) — don't trust a subagent's "unused/remove" claim, nor a "fixed" status; grep-verify against live code; verify the fix is actually MERGED to main (a Lucifer-worktree fix never merged); confirm the LIVE running version before treating a report as unfixed.
- **test-with-real-corpus** (MyDocs, NotiWallet, OCR) — bugs slip past tests built on idealized synthetic inputs; a permanent-drop gate tested only on clean formats can silently kill the whole pipeline ("all banks silent" ≠ the listener died). Build the corpus from REAL files/formats.
- **green-test≠real-acceptance** (ScanDocs) — for an OpenCV/CV fix a green flutter test means nothing (the cv2≠app trap); acceptance = Python+cv2 on the REAL photo / on-device logcat / Nick's REAL exported file. Don't chase a fully-AUTOMATIC CV result — default to user-confirmed manual corners + a real-photo regression net.
- **silent-op-reads-as-broken** (NotiWallet) — a silent background op (auto-update on quit, no status) reads as broken. Give a visible "ready + Install now" affordance; never silent-install-on-quit as the only path for a tray app.
- **gate-destructive-actions-not-just-creation** (ScanDocs) — a Pro gate on create but not delete lets a lapsed user destroy what they can't recreate. Gate every destructive action.
- **race-generation-counter** (ENA) — an orphaned worker's late callback paints stale data / clears the new flag. A generation counter drops stale-gen callbacks; one consumer per cycle.
- **off-thread-ui-work** (OCR, ENA) — DB/decode/render on the Tk/UI thread hangs. Run off-thread via a controller with debounced refresh; logging belongs in the fetch worker, not card render.
- **exception-before-reschedule-kills-ticker** (HAPPY) — an exception escaping before the reschedule line stops the periodic drain forever. Wrap the handler in `try/except` so the ticker always reschedules.
- **dead-feature-from-namedtuple-arity** (HAPPY) — growing a NamedTuple but unpacking the old arity crashes the page. Attribute access + a field-count regression test.
- **central-resolver-leaves-local-copies** (NotiWallet) — centralizing one lookup leaves drifting local copies. After delegating, grep for local copies (e.g. `Icons.*`) and fix every surface in one change.
- **replace-all-misses-quote-variant** (PLC) — a literal appears single- AND double-quoted; `replace_all` matches one style. Shared helper + grep both quote styles.
- **hang-is-not-a-throw** (ScanDocs) — `catch` handles a throw but not a HANG; spinners spin forever. Add a timeout to every heavy await + wrap busy flags in `try/finally`; surface a clear error.
- **silent-catcherror-hides-failure** (ScanDocs, ScanDocs) — a `catchError`/composite helper that swallows the error makes a failure look like slowness / a silently-missing stamp. Log errors; make composite helpers THROW; resume unfinished work at startup.

## ☁️ MCP / Google Drive / OAuth
- **drive-upload-no-base64-transcribe** (ScanDocs) — Drive `create_file` MCP has no path-upload; hand-copying base64 corrupts + blows the Read cap. Pass `textContent` for text/HTML, or `SendUserFile` the PNG.
- **service-account-no-drive-quota** (Happy-Origin) — a personal-Gmail service account can read but uploads fail 403 (no storage quota). Use installed-OAuth + refresh token, or SendUserFile + GitHub Releases.
- **oauth-test-user-and-android-client** (Happy-Origin) — Sign-In 403 access_denied = account not a Test User; error code 10 = missing Android OAuth client (package + debug SHA-1). Add both.
- **markSynced-compare-and-set** (Happy-Origin) — `markSynced` overwriting without checking the record changed mid-push drops a concurrent update. Compare-and-set on `expectUpdatedAt`.
- **no-key-borrowing** (OCR) — never copy another project's API key; a path listing is a location map, not a usage grant. Each project uses its OWN key.

---
*Harvested 2026-06-23 from 200 bug/lesson findings across 11 projects (3 read-only agents), curated
to the cross-project ones + de-duplicated. Refresh via the harvest note above.*
