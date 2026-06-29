"""Local dashboard server. Serves dashboard.html and triggers Garmin / PO10 syncs."""

import http.server
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = int(os.getenv("PORT", 8080))
BASE = Path(__file__).parent
DATA = Path(os.getenv("DASH_DATA", BASE))  # persistent data dir (overridden to /data in container)
_venv_python = BASE / ".venv" / "bin" / "python"
PYTHON = _venv_python if _venv_python.exists() else Path(sys.executable)

GUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _json_response(handler, data: dict, status: int = 200):
    body = json.dumps(data).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _run(script: str, *args, timeout: int = 300) -> dict:
    result = subprocess.run(
        [str(PYTHON), str(BASE / script), *args],
        capture_output=True, text=True, timeout=timeout, cwd=str(BASE),
    )
    return {"ok": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE), **kwargs)

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    # ── GET ──────────────────────────────────────────────────────────────────
    def do_GET(self):
        p = urlparse(self.path)

        if p.path == "/activities.json":
            self._serve_file("activities.json")

        elif p.path == "/po10/athletes":
            self._serve_file("po10_athletes.json", empty={"athletes": []})

        elif p.path.startswith("/po10/athlete/"):
            guid = p.path.split("/")[-1]
            if not GUID_RE.match(guid):
                self.send_error(400, "Invalid GUID")
                return
            self._serve_file(f"po10_{guid}.json")

        else:
            super().do_GET()

    # ── POST ─────────────────────────────────────────────────────────────────
    def do_POST(self):
        p = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if p.path == "/refresh":
            self._refresh_garmin(body.get("limit", 10))

        elif p.path == "/po10/add":
            self._po10_add(body.get("url", ""))

        elif p.path == "/po10/refresh":
            self._po10_refresh(body.get("guid", ""))

        elif p.path == "/po10/remove":
            self._po10_remove(body.get("guid", ""))

        else:
            self.send_error(404)

    # ── Handlers ─────────────────────────────────────────────────────────────
    def _serve_file(self, filename: str, empty=None):
        f = DATA / filename
        if not f.exists():
            if empty is not None:
                _json_response(self, empty)
            else:
                self.send_error(404, f"{filename} not found")
            return
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _refresh_garmin(self, limit=10):
        arg = "all" if limit == "all" else str(int(limit))
        label = "all activities" if arg == "all" else f"last {arg} activities"
        print(f"\n  → Syncing Garmin ({label}) …")
        r = _run("fetch_activities.py", arg, timeout=300)
        print(f"  → {r['stdout'][-80:]}")
        if r["ok"]:
            p = DATA / "activities.json"
            data = json.loads(p.read_text()) if p.exists() else {}
            _json_response(self, {"ok": True, "message": r["stdout"].split("\n")[-1], "data": data})
        else:
            _json_response(self, {"ok": False, "error": r["stderr"] or r["stdout"]}, 500)

    def _po10_add(self, url_or_guid: str):
        m = GUID_RE.search(url_or_guid)
        if not m:
            _json_response(self, {"ok": False, "error": "No valid PO10 GUID found in input"}, 400)
            return
        guid = m.group(0)
        print(f"\n  → Fetching PO10 athlete {guid} …")
        r = _run("fetch_po10.py", guid, timeout=30)
        print(f"  → {r['stdout']}")
        if r["ok"]:
            f = DATA / f"po10_{guid}.json"
            athlete = json.loads(f.read_text()) if f.exists() else {}
            index = self._read_index()
            _json_response(self, {"ok": True, "athlete": athlete, "athletes": index["athletes"]})
        else:
            _json_response(self, {"ok": False, "error": r["stderr"] or r["stdout"]}, 500)

    def _po10_refresh(self, guid: str):
        if not GUID_RE.match(guid):
            _json_response(self, {"ok": False, "error": "Invalid GUID"}, 400)
            return
        print(f"\n  → Refreshing PO10 {guid} …")
        r = _run("fetch_po10.py", guid, timeout=30)
        if r["ok"]:
            f = DATA / f"po10_{guid}.json"
            athlete = json.loads(f.read_text()) if f.exists() else {}
            _json_response(self, {"ok": True, "athlete": athlete})
        else:
            _json_response(self, {"ok": False, "error": r["stderr"] or r["stdout"]}, 500)

    def _po10_remove(self, guid: str):
        index_path = DATA / "po10_athletes.json"
        index = self._read_index()
        index["athletes"] = [a for a in index["athletes"] if a["guid"] != guid]
        index_path.write_text(json.dumps(index, indent=2))
        f = DATA / f"po10_{guid}.json"
        if f.exists():
            f.unlink()
        _json_response(self, {"ok": True, "athletes": index["athletes"]})

    def _read_index(self) -> dict:
        p = DATA / "po10_athletes.json"
        return json.loads(p.read_text()) if p.exists() else {"athletes": []}


if __name__ == "__main__":
    print(f"Dashboard → http://localhost:{PORT}")
    print("Press Ctrl-C to stop.\n")
    try:
        with http.server.HTTPServer(("", PORT), Handler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)
