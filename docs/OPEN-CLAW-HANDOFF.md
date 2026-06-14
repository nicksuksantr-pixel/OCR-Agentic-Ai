# Handoff to Open-Claw (the Heart) — contract changes to adopt

> Source of truth: OCR-Agentic-Ai (the eyes). Open-Claw must adopt the change
> below or its POST calls will start failing. Created 2026-06-14 (eyes v0.2.4/0.2.5).
> Per project rule #1 we never edit Open-Claw — Nick carries this note over.
>
> ✅ **ADOPTED 2026-06-15** — Nick relayed this to Open-Claw; they now send
> `X-OCR-Token` on POST and the integration is confirmed working. Kept for history.

## 🔴 BREAKING (eyes v0.2.4) — the local API now requires a token on POST

The localhost API (`http://127.0.0.1:8765`) was unauthenticated. As of **v0.2.4**,
**POST routes require a shared token** or they return **HTTP 401**:

- `POST /scan` → needs header **`X-OCR-Token: <token>`**
- `POST /boost/run` → needs header **`X-OCR-Token: <token>`**

**GET routes are UNCHANGED** (no token needed): `/health`, `/introduce`, `/jobs`,
`/jobs/{id}`, `/jobs/{id}/result`.

### Where Open-Claw gets the token (it already reads the handshake)
The token is published in the self-introduction Open-Claw already consumes:

- `GET http://127.0.0.1:8765/introduce` → `interfaces.api.auth`:
  ```json
  "interfaces": {
    "api": {
      "auth": {
        "scheme": "shared-token",
        "header": "X-OCR-Token",
        "token": "<hex token here>",
        "required_on": "POST routes (/scan, /boost/run) — 401 without it"
      }
    }
  }
  ```
- Or read the same from the file `%LOCALAPPDATA%\OCR-Agentic-Ai\introduction.json`.

The token is **stable per Shared Store** (stored in `meta.api_token`); it only
changes if that meta row is cleared. Reading it once per session is enough.

### What Open-Claw must change
1. On startup (or before the first POST), read `interfaces.api.auth.token` from
   `/introduce` (or `introduction.json`).
2. Attach `X-OCR-Token: <token>` to **every** `POST /scan` and `POST /boost/run`.
3. Leave GET calls as they are.

### Example
```
GET  /introduce                     # → grab interfaces.api.auth.token = "ab12…"
POST /scan        X-OCR-Token: ab12…   body {"path": "C:\\...\\drawing.pdf"}
POST /boost/run   X-OCR-Token: ab12…
```
Missing/wrong header → `401 {"error": "missing or invalid X-OCR-Token header …"}`.

## 🟡 Minor behaviour note (eyes v0.2.5) — boost queue when no key
If the eyes have AI Boost enabled but **no Gemini key configured**, low-confidence
sections are **no longer queued** for AI (previously they piled up as undrainable
rows). The **local Raw Extract is still complete** — sections just won't gain an
`[AI Boost]` reading until a key is added and the file is re-scanned. So: don't
assume every `low_conf`/`unreadable` section will eventually receive an AI reading
when the eyes have no key.

## 🟢 No schema changes
DB schema, `result.json` fields, and endpoint payloads are unchanged. The new
`interfaces.api.auth` block in the introduction is additive (safe to ignore by
older readers, except that POSTs will 401 until the token is sent).

---
Checklist for Nick → Open-Claw:
- [ ] Open-Claw reads `interfaces.api.auth.token` from the handshake
- [ ] Open-Claw sends `X-OCR-Token` on POST /scan and POST /boost/run
- [ ] (optional) Open-Claw tolerates "no AI reading" for low_conf sections when the eyes have no key
