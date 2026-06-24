"""Local dashboard server. Serves dashboard.html and triggers Garmin sync."""

import http.server
import json
import os
import subprocess
import sys
from pathlib import Path

PORT = int(os.getenv("PORT", 8080))
BASE = Path(__file__).parent


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE), **kwargs)

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    def do_GET(self):
        if self.path == "/activities.json":
            self._serve_json()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/refresh":
            self._run_refresh()
        else:
            self.send_error(404)

    def _serve_json(self):
        p = BASE / "activities.json"
        if not p.exists():
            self.send_error(404, "activities.json not found — run a refresh first")
            return
        data = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _run_refresh(self):
        python = BASE / ".venv" / "bin" / "python"
        script = BASE / "fetch_activities.py"
        print("\n  → Running fetch_activities.py ...")
        try:
            result = subprocess.run(
                [str(python), str(script), "500"],
                capture_output=True, text=True, timeout=60, cwd=str(BASE)
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            print(f"  → stdout: {stdout}")
            if stderr:
                print(f"  → stderr: {stderr}")

            if result.returncode != 0:
                body = json.dumps({"ok": False, "error": stderr or stdout}).encode()
                self.send_response(500)
            else:
                p = BASE / "activities.json"
                activities = json.loads(p.read_text()) if p.exists() else {}
                body = json.dumps({
                    "ok": True,
                    "message": stdout.split("\n")[-1],
                    "data": activities,
                }).encode()
                self.send_response(200)

        except subprocess.TimeoutExpired:
            body = json.dumps({"ok": False, "error": "Timed out after 60s"}).encode()
            self.send_response(500)

        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print(f"Dashboard → http://localhost:{PORT}")
    print("Press Ctrl-C to stop.\n")
    try:
        with http.server.HTTPServer(("localhost", PORT), Handler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)
