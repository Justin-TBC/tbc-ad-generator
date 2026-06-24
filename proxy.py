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
import json
import os
import re
import socketserver
import sys
import threading
import uuid
import urllib.request
import urllib.error
from urllib.parse import urlparse, parse_qs

_ASSETS_LOCK = threading.Lock()

UPSTREAM_BASE  = "https://mcp.higgsfield.ai"
DEFAULT_PORT   = int(os.environ.get("PORT", 8000))
PROXY_PREFIX   = "/api"
NOTION_PREFIX   = "/notion"
NOTION_BASE     = "https://api.notion.com/v1"
NOTION_TOKEN    = os.environ.get("NOTION_TOKEN", "")
SHOPIFY_PREFIX      = "/shopify"
SHOPIFY_AUTH_PREFIX = "/shopify-auth"
SHOPIFY_DOMAIN      = os.environ.get("SHOPIFY_DOMAIN", "")
SHOPIFY_TOKEN       = os.environ.get("SHOPIFY_TOKEN", "").strip()
SHOPIFY_CLIENT_ID   = os.environ.get("SHOPIFY_CLIENT_ID", "").strip()
SHOPIFY_CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "").strip()
# shpat_ = Admin API token; anything else = Storefront token
SHOPIFY_IS_STOREFRONT = bool(SHOPIFY_TOKEN) and not SHOPIFY_TOKEN.startswith("shpat_")
META_PREFIX     = "/meta"
ASSETS_PREFIX   = "/assets"
ASSETS_DIR      = os.environ.get("ASSETS_DIR", "/data/assets")
META_BASE       = "https://graph.facebook.com/v19.0"
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

    def _is_shopify_auth(self):
        return self.path.startswith(SHOPIFY_AUTH_PREFIX + "/") or self.path == SHOPIFY_AUTH_PREFIX

    def _is_meta(self):
        return self.path.startswith(META_PREFIX + "/") or self.path == META_PREFIX

    def _is_assets(self):
        return self.path.startswith(ASSETS_PREFIX + "/") or self.path == ASSETS_PREFIX

    def do_GET(self):
        if self._is_api():           self._proxy()
        elif self._is_notion():      self._notion_proxy()
        elif self._is_shopify_auth():self._shopify_auth()
        elif self._is_shopify():     self._shopify_proxy()
        elif self._is_meta():        self._meta_proxy()
        elif self._is_assets():      self._assets_handler()
        else:                        super().do_GET()

    def do_POST(self):
        if self._is_api():           self._proxy()
        elif self._is_notion():      self._notion_proxy()
        elif self._is_shopify():     self._shopify_proxy()
        elif self._is_meta():        self._meta_proxy()
        elif self._is_assets():      self._assets_handler()
        else:                        self.send_error(404)

    def do_PUT(self):
        if self._is_api():      self._proxy()
        elif self._is_notion(): self._notion_proxy()
        elif self._is_shopify():self._shopify_proxy()
        elif self._is_meta():   self._meta_proxy()
        else:                   self.send_error(404)

    def do_DELETE(self):
        if self._is_api():           self._proxy()
        elif self._is_notion():      self._notion_proxy()
        elif self._is_shopify():     self._shopify_proxy()
        elif self._is_meta():        self._meta_proxy()
        elif self._is_assets():      self._assets_handler()
        else:                        self.send_error(404)

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

    # --- Shopify OAuth helper (one-time token setup) ---
    def _shopify_auth(self):
        import json as _json
        from urllib.parse import urlparse, parse_qs, urlencode, quote

        sub = self.path[len(SHOPIFY_AUTH_PREFIX):]  # e.g. "/start" or "/callback"
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        def html_page(title, body):
            page = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>{title}</title>
<style>body{{font-family:system-ui,sans-serif;background:#0a0a0b;color:#e4e4e7;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
.box{{background:#141416;border:1px solid #2a2a2e;border-radius:12px;padding:2rem;max-width:560px;width:100%}}
h2{{margin:0 0 1rem;color:#fff}}p{{color:#a1a1aa;font-size:.9rem;line-height:1.6}}
code{{background:#1c1c1f;border:1px solid #2a2a2e;padding:.25rem .5rem;border-radius:4px;font-size:.85rem;word-break:break-all}}
.btn{{display:inline-block;margin-top:1rem;padding:.6rem 1.2rem;background:#f97316;color:#1a0f04;border-radius:8px;text-decoration:none;font-weight:600;cursor:pointer;border:none;font-size:.9rem}}
.ok{{color:#10b981}}.err{{color:#f43f5e}}
</style></head><body><div class="box">{body}</div></body></html>"""
            data = page.encode()
            self.send_response(200)
            self._add_cors()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        # ── /shopify-auth/start ──────────────────────────────────
        if sub.startswith("/start"):
            if not SHOPIFY_CLIENT_ID or not SHOPIFY_DOMAIN:
                html_page("Setup needed", "<h2>Setup needed</h2><p>Set <code>SHOPIFY_CLIENT_ID</code> and <code>SHOPIFY_DOMAIN</code> in Railway environment variables first.</p>")
                return
            redirect_uri = f"{self._origin()}/shopify-auth/callback"
            scope = "read_products,read_collections,read_inventory"
            auth_url = (f"https://{SHOPIFY_DOMAIN}/admin/oauth/authorize"
                        f"?client_id={SHOPIFY_CLIENT_ID}"
                        f"&scope={scope}"
                        f"&redirect_uri={quote(redirect_uri, safe='')}"
                        f"&grant_options[]=offline")
            sys.stderr.write(f"[shopify-auth] redirect_uri={redirect_uri}\n")
            sys.stderr.write(f"[shopify-auth] auth_url={auth_url}\n")
            html_page("Connect Shopify", f"""
<h2>Connect Shopify</h2>
<p>Your redirect URI — copy this <strong>exactly</strong> into Partners dashboard → your app → App setup → <strong>Allowed redirection URL(s)</strong>:</p>
<code>{redirect_uri}</code>
<p style="margin-top:1.5rem">Once that's saved in Partners dashboard, click below to authorize:</p>
<a href="{auth_url}" class="btn">Authorize in Shopify →</a>""")
            return

        # ── /shopify-auth/callback ───────────────────────────────
        if sub.startswith("/callback"):
            code = qs.get("code", [None])[0]
            shop = qs.get("shop", [SHOPIFY_DOMAIN])[0]
            error = qs.get("error", [None])[0]

            if error:
                html_page("Auth failed", f"<h2 class='err'>Auth failed</h2><p>{error}</p>")
                return
            if not code:
                html_page("No code", "<h2 class='err'>No code returned</h2><p>Try starting the flow again.</p>")
                return
            if not SHOPIFY_CLIENT_SECRET:
                html_page("Missing secret", "<h2 class='err'>SHOPIFY_CLIENT_SECRET not set</h2><p>Add it to Railway environment variables.</p>")
                return

            # Exchange code for access token
            try:
                payload = _json.dumps({
                    "client_id": SHOPIFY_CLIENT_ID,
                    "client_secret": SHOPIFY_CLIENT_SECRET,
                    "code": code,
                }).encode()
                req = urllib.request.Request(
                    f"https://{shop}/admin/oauth/access_token",
                    data=payload, method="POST",
                )
                req.add_header("Content-Type", "application/json")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    token_data = _json.loads(resp.read())
                access_token = token_data.get("access_token", "")
                scope = token_data.get("scope", "")
                if not access_token:
                    raise ValueError("No access_token in response: " + str(token_data))
                sys.stderr.write(f"[shopify-auth] token obtained, scope={scope}\n")
                html_page("Connected!", f"""
<h2 class='ok'>✓ Shopify connected!</h2>
<p>Your Admin API access token:</p>
<code>{access_token}</code>
<p style='margin-top:1rem'>Copy this token and set it as <code>SHOPIFY_TOKEN</code> in your Railway environment variables, then redeploy.</p>
<p style='color:#71717a;font-size:.8rem'>Scopes granted: {scope}</p>""")
            except Exception as e:
                sys.stderr.write(f"[shopify-auth] token exchange failed: {e}\n")
                html_page("Token exchange failed", f"<h2 class='err'>Token exchange failed</h2><p>{str(e)}</p>")
            return

        html_page("Not found", "<h2>Not found</h2>")

    def _origin(self):
        host = self.headers.get("Host", "localhost")
        proto = "https" if "railway" in host or "." in host.split(":")[0] else "http"
        return f"{proto}://{host}"

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
        if SHOPIFY_IS_STOREFRONT:
            # Storefront API: public REST endpoints, no /admin prefix
            url = f"https://{SHOPIFY_DOMAIN}/api/2024-01{shopify_path}"
        else:
            url = f"https://{SHOPIFY_DOMAIN}/admin/api/2024-01{shopify_path}"
        method = self.command

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else None

        req = urllib.request.Request(url, data=body, method=method)
        if SHOPIFY_IS_STOREFRONT:
            req.add_header("X-Shopify-Storefront-Access-Token", SHOPIFY_TOKEN)
        else:
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
                # Always return JSON — never relay HTML error pages
                ct = dict(e.headers.items()).get('content-type', '')
                if 'html' in ct.lower():
                    error_body = f'{{"pablo_error":"shopify_error","status":{status}}}'.encode()
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

    # --- Asset storage (Railway Volume at ASSETS_DIR) ---
    def _assets_handler(self):
        os.makedirs(ASSETS_DIR, exist_ok=True)
        meta_path = os.path.join(ASSETS_DIR, "_meta.json")

        def load_meta():
            if os.path.exists(meta_path):
                try:
                    with open(meta_path) as f: return json.load(f)
                except Exception: pass
            return []

        def save_meta(m):
            with open(meta_path, "w") as f: json.dump(m, f)

        def json_resp(data, status=200):
            body = json.dumps(data).encode()
            self.send_response(status)
            self._add_cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        sub = parsed.path[len(ASSETS_PREFIX):]  # e.g. "/list", "/upload", "/serve/abc.png", "/delete/abc.png"

        # GET /assets/list
        if sub in ("/list", "/list/") and self.command == "GET":
            json_resp(load_meta())
            return

        # POST /assets/upload?name=...&category=...&mime=...
        if sub in ("/upload", "/upload/") and self.command == "POST":
            name     = qs.get("name",     ["unnamed"])[0]
            category = qs.get("category", ["other"])[0]
            mime     = qs.get("mime",     ["application/octet-stream"])[0]
            ext      = os.path.splitext(name)[1].lower() or ".bin"
            asset_id = uuid.uuid4().hex[:16] + ext
            length   = int(self.headers.get("Content-Length", "0") or "0")
            data     = self.rfile.read(length) if length else b""
            with open(os.path.join(ASSETS_DIR, asset_id), "wb") as f:
                f.write(data)
            with _ASSETS_LOCK:
                m = load_meta()
                m.append({"id": asset_id, "name": name, "category": category, "mime": mime})
                save_meta(m)
            sys.stderr.write(f"[assets] saved {asset_id} ({len(data)} bytes, cat={category})\n")
            json_resp({"ok": True, "id": asset_id})
            return

        # GET /assets/serve/{id}
        if sub.startswith("/serve/") and self.command == "GET":
            asset_id = sub[7:]
            if "/" in asset_id or ".." in asset_id:
                self.send_error(400); return
            path = os.path.join(ASSETS_DIR, asset_id)
            if not os.path.exists(path):
                self.send_error(404); return
            m    = load_meta()
            meta = next((a for a in m if a["id"] == asset_id), {})
            mime = meta.get("mime", "application/octet-stream")
            with open(path, "rb") as f: body = f.read()
            self.send_response(200)
            self._add_cors()
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(body)
            return

        # DELETE /assets/delete/{id}
        if sub.startswith("/delete/") and self.command == "DELETE":
            asset_id = sub[8:]
            if "/" in asset_id or ".." in asset_id:
                self.send_error(400); return
            path = os.path.join(ASSETS_DIR, asset_id)
            if os.path.exists(path): os.remove(path)
            with _ASSETS_LOCK:
                m = [a for a in load_meta() if a["id"] != asset_id]
                save_meta(m)
            sys.stderr.write(f"[assets] deleted {asset_id}\n")
            json_resp({"ok": True})
            return

        # GET /assets/meta/{key} — read JSON KV entry
        if sub.startswith('/meta/') and self.command == 'GET':
            key = sub[6:]
            if not re.match(r'^[a-zA-Z0-9_-]+$', key):
                self.send_error(400); return
            path = os.path.join(ASSETS_DIR, f'_kv_{key}.json')
            data = open(path, 'rb').read() if os.path.exists(path) else b'null'
            self.send_response(200)
            self._add_cors()
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        # POST /assets/meta/{key} — write JSON KV entry
        if sub.startswith('/meta/') and self.command == 'POST':
            key = sub[6:]
            if not re.match(r'^[a-zA-Z0-9_-]+$', key):
                self.send_error(400); return
            length = int(self.headers.get('Content-Length', '0') or '0')
            data = self.rfile.read(length) if length else b'null'
            path = os.path.join(ASSETS_DIR, f'_kv_{key}.json')
            with _ASSETS_LOCK:
                with open(path, 'wb') as f: f.write(data)
            json_resp({'ok': True})
            return

        self.send_error(404)

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
