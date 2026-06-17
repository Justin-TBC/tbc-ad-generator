#!/usr/bin/env python3
"""
Ad Generator - lokaler Static+Proxy-Server.

Servt die HTML-App auf http://localhost:8000 und proxied /api/* Calls zu
https://mcp.higgsfield.ai, damit Browser-CORS nicht in Quer schiesst.

Verwendung:
    python3 proxy.py [port]
"""
from __future__ import annotations

import http.server
import os
import socketserver
import sys
import urllib.request
import urllib.error
from urllib.parse import urlparse

UPSTREAM_BASE = "https://mcp.higgsfield.ai"
DEFAULT_PORT = int(os.environ.get("PORT", 8000))
PROXY_PREFIX = "/api"

# Header die unveraendert an Higgsfield weitergegeben werden
PASS_THROUGH_REQUEST_HEADERS = {
    "content-type",
    "authorization",
    "accept",
    "accept-language",
    "user-agent",
    "mcp-session-id",
    "mcp-protocol-version",
}

# Falls der Client keinen User-Agent schickt, nutzen wir einen browser-aehnlichen
FALLBACK_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# Header die in der Antwort an den Browser durchgegeben werden
PASS_THROUGH_RESPONSE_HEADERS = {
    "content-type",
    "www-authenticate",
    "mcp-session-id",
    "mcp-protocol-version",
}


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Kompakteres Logging
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    # --- CORS ---
    def _add_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, PUT, DELETE, OPTIONS, PATCH",
        )
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, Accept, Mcp-Session-Id, Mcp-Protocol-Version",
        )
        self.send_header(
            "Access-Control-Expose-Headers",
            "Content-Type, WWW-Authenticate, Mcp-Session-Id, Mcp-Protocol-Version",
        )
        self.send_header("Access-Control-Max-Age", "600")

    def do_OPTIONS(self):
        self.send_response(204)
        self._add_cors()
        self.end_headers()

    # --- Dispatch ---
    def do_GET(self):
        if self.path.startswith(PROXY_PREFIX + "/") or self.path == PROXY_PREFIX:
            self._proxy()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith(PROXY_PREFIX + "/") or self.path == PROXY_PREFIX:
            self._proxy()
        else:
            self.send_error(404)

    def do_PUT(self):
        if self.path.startswith(PROXY_PREFIX + "/") or self.path == PROXY_PREFIX:
            self._proxy()
        else:
            self.send_error(404)

    def do_DELETE(self):
        if self.path.startswith(PROXY_PREFIX + "/") or self.path == PROXY_PREFIX:
            self._proxy()
        else:
            self.send_error(404)

    def do_PATCH(self):
        if self.path.startswith(PROXY_PREFIX + "/") or self.path == PROXY_PREFIX:
            self._proxy()
        else:
            self.send_error(404)

    # --- Proxy core ---
    def _proxy(self):
        upstream_path = self.path[len(PROXY_PREFIX):] or "/"
        url = UPSTREAM_BASE + upstream_path
        method = self.command

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else None

        req = urllib.request.Request(url, data=body, method=method)
        has_user_agent = False
        for name, value in self.headers.items():
            if name.lower() in PASS_THROUGH_REQUEST_HEADERS:
                req.add_header(name, value)
                if name.lower() == "user-agent":
                    has_user_agent = True
        if not has_user_agent:
            req.add_header("User-Agent", FALLBACK_USER_AGENT)
        # Origin/Referer wie ein echter Browser-Call von higgsfield.ai
        req.add_header("Origin", "https://higgsfield.ai")
        req.add_header("Referer", "https://higgsfield.ai/")

        sys.stderr.write(f"[proxy] {method} {url}\n")

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                self._relay(resp.status, resp.getheaders(), resp.read())
        except urllib.error.HTTPError as e:
            body = e.read()
            self._relay(e.code, e.headers.items(), body)
        except urllib.error.URLError as e:
            self.send_response(502)
            self._add_cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                f'{{"error":"proxy_upstream_error","detail":"{str(e).replace(chr(34), "")}"}}'.encode()
            )

    def _relay(self, status: int, headers, body: bytes):
        self.send_response(status)
        self._add_cors()
        for name, value in headers:
            if name.lower() in PASS_THROUGH_RESPONSE_HEADERS:
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)


class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Jeder Request laeuft in einem eigenen Thread.

    Wichtig: Der alte single-threaded TCPServer fror komplett ein, sobald ein
    einzelner Upstream-Call haengen blieb (langer Poll, offene Streaming-Antwort).
    Dann blockierten auch Login-POSTs (/oauth2/token, /oauth2/register) und die
    Anmeldung schlug fehl, obwohl Higgsfield laengst geantwortet haette.
    """
    daemon_threads = True
    allow_reuse_address = True


def main():
    port = int(os.environ.get("PORT", int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT))
    with ThreadingHTTPServer(("0.0.0.0", port), Handler) as httpd:
        print(f"==> Ad Generator on http://localhost:{port}/ad-generator.html")
        print(f"==> Proxy {PROXY_PREFIX}/* -> {UPSTREAM_BASE}/*")
        print("==> Ctrl+C zum Beenden")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nBye.")


if __name__ == "__main__":
    main()
