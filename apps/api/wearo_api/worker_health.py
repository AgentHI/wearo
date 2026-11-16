from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def start_worker_health_server(service: str, port: int) -> ThreadingHTTPServer:
    """Expose a small process-local liveness endpoint for a long-running worker."""

    payload = json.dumps({"status": "ok", "service": service}).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/health":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(
        target=server.serve_forever,
        name=f"{service}-health",
        daemon=True,
    ).start()
    return server
