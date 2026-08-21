"""Dark-theme reverse proxy for the OpenCode web UI.

Forwards every request 1:1 to the OpenCode web server (default 127.0.0.1:4096)
and injects, into HTML responses only:
  - a bootstrap script that pins localStorage to the dark color scheme before
    the app's own preload script runs
  - a stylesheet forcing monospace rendering on code/diff/terminal surfaces

Run: python scripts/opencode_dark_proxy.py [--port 8096] [--target http://127.0.0.1:4096]
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlsplit

TARGET = "http://127.0.0.1:4096"

THEME_SCRIPT = (
    "<script>"
    "try{localStorage.setItem('opencode-color-scheme','dark');"
    "localStorage.setItem('opencode-theme-id','oc-2');}catch(e){}"
    "</script>"
)

MONO_STYLE = (
    "<style id='atlas-dark-mono'>"
    "html{background:#080808!important}"
    "pre,code,kbd,samp,.font-mono,[class*='mono']{"
    "font-family:ui-monospace,'Cascadia Code','Cascadia Mono',Consolas,'Courier New',monospace!important;"
    "font-variant-ligatures:none!important}"
    "</style>"
)


def _deep_link_script(path: str) -> str:
    """OpenCode's official deep-entry protocol: window.__OPENCODE__.deepLinks.

    When the page is loaded with ?directory=<path>, inject a new-session deep
    link so the SPA boots straight into that workspace instead of its
    session-picker portal. Without the query param, inject nothing.
    """
    directory = (parse_qs(urlsplit(path).query).get("directory") or [""])[0]
    if not directory:
        return ""
    link = f"opencode://new-session?directory={quote(directory, safe='')}"
    return (
        "<script>window.__OPENCODE__=Object.assign({},window.__OPENCODE__,"
        f"{{deepLinks:[{json.dumps(link)}]}});</script>"
    )


def _patch_html(html: str, extra: str = "") -> str:
    head = "<head>"
    inject = THEME_SCRIPT + MONO_STYLE + extra
    if head in html:
        return html.replace(head, head + inject, 1)
    return inject + html


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _forward(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        req = urlrequest.Request(
            TARGET + self.path,
            data=body,
            method=self.command,
            headers={
                key: value
                for key, value in self.headers.items()
                if key.lower() not in {"host", "connection", "accept-encoding"}
            },
        )
        req.add_header("Accept-Encoding", "identity")
        try:
            with urlrequest.urlopen(req, timeout=30) as upstream:
                payload = upstream.read()
                content_type = upstream.headers.get("Content-Type", "application/octet-stream")
                status = upstream.status
        except HTTPError as exc:
            payload = exc.read()
            content_type = exc.headers.get("Content-Type", "text/plain")
            status = exc.code
        except URLError:
            payload = b"OpenCode web UI is not reachable."
            content_type = "text/plain"
            status = 502

        if "text/html" in content_type:
            text = payload.decode("utf-8", errors="replace")
            payload = _patch_html(text, _deep_link_script(self.path)).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _forward

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        pass


def main() -> int:
    global TARGET
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8096)
    parser.add_argument("--target", default=TARGET)
    args = parser.parse_args()
    TARGET = args.target.rstrip("/")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), ProxyHandler)
    print(f"opencode dark proxy: http://127.0.0.1:{args.port} -> {TARGET}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
