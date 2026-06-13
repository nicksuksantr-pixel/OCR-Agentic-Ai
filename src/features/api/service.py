"""Local API — the second hand-off interface for Open-Claw (the Heart).

A thin localhost-only REST shell over the same engine the GUI uses. Bound to
127.0.0.1 (never reachable from the network). All payloads English, JSON.

Endpoints (the contract — changes are breaking, note them in V-Log):
  GET  /health                → {"status":"ok","version":...,"pending_boost":N}
  GET  /introduce             → full self-description (identity, paths, schema,
                                interfaces, conventions) — the Heart's handshake
  GET  /jobs?limit=50         → newest jobs (id, created_at, source, status, conf)
  GET  /jobs/{id}             → one job + its sections (DB rows)
  GET  /jobs/{id}/result      → the job folder's result.json (full Raw Extract)
  POST /scan                  → body {"path": "<image or PDF path>"} — scans
                                synchronously, returns the job summary; a PDF
                                makes one job per page (additive "jobs" list).
                                Add "async": true to return 202 at once and poll
                                /jobs + /jobs/{id}/result (v0.2.2, additive)
  POST /boost/run             → drain the Boost Queue now; returns the run summary
"""
import json
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.core.config.settings import Settings
from src.core.services import introduce, store
from src.features.boost import service as boost_service
from src.features.scan import service as scan_service


class ApiServer:
    """Owns the HTTP server thread; one instance per app."""

    def __init__(self, settings: Settings, version: str, on_event=lambda msg: None):
        self.settings = settings
        self.version = version
        self.on_event = on_event
        self._httpd: ThreadingHTTPServer | None = None
        self._scan_lock = threading.Lock()  # one scan at a time keeps Tesseract honest

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self) -> str | None:
        """Bind and serve in a daemon thread. Returns an error message or None."""
        if self.running:
            return None
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep the console quiet
                pass

            def _send(self, code: int, payload: dict | list) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                try:
                    api._route_get(self)
                except Exception as exc:
                    self._send(500, {"error": repr(exc)})

            def do_POST(self):
                try:
                    api._route_post(self)
                except Exception as exc:
                    self._send(500, {"error": repr(exc)})

        try:
            self._httpd = ThreadingHTTPServer(("127.0.0.1", self.settings.api_port), Handler)
        except OSError as exc:
            return f"API port {self.settings.api_port} unavailable: {exc}"
        threading.Thread(target=self._httpd.serve_forever, daemon=True,
                         name="local-api").start()
        self.on_event(f"API listening on http://127.0.0.1:{self.settings.api_port}")
        return None

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None

    # --- routing -----------------------------------------------------------

    def _route_get(self, h) -> None:
        path, _, query = h.path.partition("?")
        parts = [p for p in path.split("/") if p]
        if parts == ["health"]:
            h._send(200, {"status": "ok", "version": self.version,
                          "pending_boost": store.pending_boost_count()})
        elif parts == ["introduce"]:
            h._send(200, introduce.build_introduction(self.settings, self.version))
        elif parts == ["jobs"]:
            limit = _query_int(query, "limit", 50)
            h._send(200, store.list_jobs(limit=limit))
        elif len(parts) == 2 and parts[0] == "jobs" and parts[1].isdigit():
            job = store.get_job(int(parts[1]))
            h._send(200, job) if job else h._send(404, {"error": "job not found"})
        elif len(parts) == 3 and parts[0] == "jobs" and parts[1].isdigit() and parts[2] == "result":
            job = store.get_job(int(parts[1]))
            if not job:
                h._send(404, {"error": "job not found"})
                return
            result_path = Path(job["job_dir"]) / "result.json"
            if not result_path.exists():
                # No result.json (older error job) → return the DB record so the
                # Heart still gets a machine-readable status instead of a 404.
                h._send(200, {"job_id": job["id"], "source_path": job["source_path"],
                              "status": job["status"], "error": job.get("error"),
                              "full_text": job.get("full_text") or "",
                              "note": "result.json absent — job did not finish"})
                return
            h._send(200, json.loads(result_path.read_text(encoding="utf-8")))
        else:
            h._send(404, {"error": "unknown endpoint"})

    def _route_post(self, h) -> None:
        parts = [p for p in h.path.split("/") if p]
        length = int(h.headers.get("Content-Length") or 0)
        body = json.loads(h.rfile.read(length) or b"{}") if length else {}

        if parts == ["scan"]:
            source = str(body.get("path", "")).strip()
            if not source or not Path(source).is_file():
                h._send(400, {"error": "body must be {\"path\": \"<existing image or PDF file>\"}"})
                return
            if body.get("async"):
                # Long PDFs can take minutes — async returns at once and the Heart
                # polls /jobs then /jobs/{id}/result instead of holding the HTTP
                # connection open the whole scan (additive flag, v0.2.2).
                def _bg(src=source):
                    try:
                        with self._scan_lock:
                            scan_service.run_source(src, self.settings)
                    except Exception as exc:  # background — report, never crash the server
                        self.on_event(f"async scan failed for {src}: {exc!r}")
                threading.Thread(target=_bg, daemon=True, name="api-scan").start()
                h._send(202, {"status": "accepted", "async": True, "source": source,
                              "note": "scanning in the background — poll GET /jobs, "
                                      "then GET /jobs/{id}/result"})
                return
            with self._scan_lock:
                results = scan_service.run_source(source, self.settings)
            # Original single-job fields stay (contract); "jobs" is additive for PDFs.
            first = results[0]
            h._send(200, {"job_id": first.job_id,
                          "mean_conf": round(sum(r.mean_conf for r in results) / len(results), 1),
                          "full_text": "\n\n".join(r.full_text for r in results),
                          "queued_sections": sum(1 for r in results for s in r.sections
                                                 if s.status in ("low_conf", "unreadable")),
                          "jobs": [{"job_id": r.job_id, "page": r.page,
                                    "mean_conf": r.mean_conf} for r in results]})
        elif parts == ["boost", "run"]:
            summary = boost_service.send_pending(self.settings)
            h._send(200, asdict(summary))
        else:
            h._send(404, {"error": "unknown endpoint"})


def _query_int(query: str, key: str, default: int) -> int:
    for pair in query.split("&"):
        k, _, v = pair.partition("=")
        if k == key and v.isdigit():
            return int(v)
    return default
