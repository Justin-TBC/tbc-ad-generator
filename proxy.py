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

UPSTREAM_BASE  = "https://mcp.higgsfield.ai"
DEFAULT_PORT   = int(os.environ.get("PORT", 8000))
PROXY_PREFIX   = "/api"
NOTION_PREFIX   = "/notion"
NOTION_BASE     = "https://api.notion.com/v1"
NOTION_TOKEN    = os.environ.get("NOTION_TOKEN", "")
SHOPIFY_PREFIX  = "/shopify"
SHOPIFY_DOMAIN  = os.environ.get("SHOPIFY_DOMAIN", "")
SHOPIFY_TOKEN   = os.environ.get("SHOPIFY_TOKEN", "").strip()
META_PREFIX     = "/meta"
META_BASE       = "https://graph.facebook.com/v21.0"
META_TOKEN      = os.environ.get("META_ACCESS_TOKEN", "")

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
    def _is_api(self):
        return self.path.startswith(PROXY_PREFIX + "/") or self.path == PROXY_PREFIX

    def _is_notion(self):
        return self.path.startswith(NOTION_PREFIX + "/") or self.path == NOTION_PREFIX

    def _is_shopify(self):
        return self.path.startswith(SHOPIFY_PREFIX + "/") or self.path == SHOPIFY_PREFIX

    def _is_meta(self):
        return self.path.startswith(META_PREFIX + "/") or self.path == META_PREFIX

    def do_GET(self):
        if self._is_api():      self._proxy()
        elif self._is_notion(): self._notion_proxy()
        elif self._is_shopify():self._shopify_proxy()
        elif self._is_meta():   self._meta_proxy()
        else:                   super().do_GET()

    def do_POST(self):
        if self._is_api():      self._proxy()
        elif self._is_notion(): self._notion_proxy()
        elif self._is_shopify():self._shopify_proxy()
        elif self._is_meta():   self._meta_proxy()
        else:                   self.send_error(404)

    def do_PUT(self):
        if self._is_api():      self._proxy()
        elif self._is_notion(): self._notion_proxy()
        elif self._is_shopify():self._shopify_proxy()
        elif self._is_meta():   self._meta_proxy()
        else:                   self.send_error(404)

    def do_DELETE(self):
        if self._is_api():      self._proxy()
        elif self._is_notion(): self._notion_proxy()
        elif self._is_shopify():self._shopify_proxy()
        elif self._is_meta():   self._meta_proxy()
        else:                   self.send_error(404)

    def do_PATCH(self):
        if self._is_api():      self._proxy()
        elif self._is_notion(): self._notion_proxy()
        elif self._is_shopify():self._shopify_proxy()
        elif self._is_meta():   self._meta_proxy()
        else:                   self.send_error(404)

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

    # --- Shopify proxy ---
    def _shopify_proxy(self):
        if not SHOPIFY_DOMAIN:
            self.send_response(503)
            self._add_cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"SHOPIFY_DOMAIN not set"}')
            return
        shopify_path = self.path[len(SHOPIFY_PREFIX):] or "/"
        url = f"https://{SHOPIFY_DOMAIN}/admin/api/2024-01{shopify_path}"
        method = self.command

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else None

        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("X-Shopify-Access-Token", SHOPIFY_TOKEN)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        sys.stderr.write(f"[shopify] {method} {url}\n")
        sys.stderr.write(f"[shopify-debug] domain present: {bool(SHOPIFY_DOMAIN)}, token present: {bool(SHOPIFY_TOKEN)}, token length: {len(SHOPIFY_TOKEN)}, token prefix: {SHOPIFY_TOKEN[:6]!r}\n")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status = resp.status
                raw = resp.read()
                sys.stderr.write(f"[shopify-status] {method} {shopify_path} → {status}\n")
                if status in (401, 407):
                    error_body = b'{"pablo_error":"shopify_auth_failed","status":' + str(status).encode() + b'}'
                    self._relay(200, [], error_body)
                else:
                    self._relay(status, resp.getheaders(), raw)
        except urllib.error.HTTPError as e:
            status = e.code
            raw = e.read()
            sys.stderr.write(f"[shopify-status] {method} {shopify_path} → {status} (HTTPError) body={raw[:200]}\n")
            if status in (401, 407):
                error_body = b'{"pablo_error":"shopify_auth_failed","status":' + str(status).encode() + b'}'
                self._relay(200, [], error_body)
            else:
                self._relay(status, e.headers.items(), raw)
        except urllib.error.URLError as e:
            self.send_response(200)
            self._add_cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                f'{{"pablo_error":"shopify_network_error","detail":"{str(e).replace(chr(34), "")}"}}'.encode()
            )

    # --- Meta Ad Library proxy ---
    def _meta_proxy(self):
        if not META_TOKEN:
            self.send_response(503)
            self._add_cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"META_ACCESS_TOKEN not set"}')
            return
        meta_path = self.path[len(META_PREFIX):] or "/"
        # Append access_token as query param (Graph API standard)
        sep = "&" if "?" in meta_path else "?"
        url = f"{META_BASE}{meta_path}{sep}access_token={META_TOKEN}"
        method = self.command

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else None

        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Content-Type", "application/json")

        sys.stderr.write(f"[meta] {method} {META_BASE}{meta_path}\n")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
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
                f'{{"error":"meta_upstream_error","detail":"{str(e).replace(chr(34), "")}"}}'.encode()
            )

    # --- Notion proxy ---
    def _notion_proxy(self):
        notion_path = self.path[len(NOTION_PREFIX):] or "/"
        url = NOTION_BASE + notion_path
        method = self.command

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else None

        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Authorization", f"Bearer {NOTION_TOKEN}")
        req.add_header("Notion-Version", "2022-06-28")
        req.add_header("Content-Type", "application/json")

        sys.stderr.write(f"[notion] {method} {url}\n")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
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
                f'{{"error":"notion_upstream_error","detail":"{str(e).replace(chr(34), "")}"}}'.encode()
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
