"""One-time loopback-only form for saving a tunnel runtime key without logging it."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from pathlib import Path
import secrets
import tempfile
import time
from urllib.parse import parse_qs


def save_key(path, value, kind="openai"):
    prefixes = ("ntn_", "secret_") if kind == "notion" else ("sk-",)
    if not isinstance(value, str) or not value.startswith(prefixes) or len(value) < 20 or any(c.isspace() for c in value):
        raise ValueError("Enter a valid %s API key, without whitespace" % kind)
    path = Path(path).expanduser().resolve()
    if path.exists():
        raise ValueError("Key file already exists; choose another --key-file to avoid replacing it")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".runtime-key-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(value)
        # An exclusive hard link preserves mode 600 and cannot overwrite an existing key.
        os.link(temporary, path)
    finally:
        os.unlink(temporary)


def serve(path, timeout=300, open_browser=False, kind="openai"):
    destination = Path(path).expanduser().resolve()
    if destination.exists():
        raise ValueError("Key file already exists: %s" % destination)
    token_path = "/" + secrets.token_urlsafe(32)
    saved = False
    label = "Notion API key" if kind == "notion" else "Runtime key"
    purpose = "NotionでCription専用コネクションを作成し、そのAPIトークンを入力してください。" if kind == "notion" else "TunnelのRead・Use権限だけを持つランタイムキーを入力してください。"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Never log request bodies, headers, credentials or the one-time URL.

        def respond(self, status, text):
            body = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            # Preserve the Origin on same-origin HTML form POSTs. A no-referrer
            # policy makes some browsers send Origin: null, failing CSRF checks.
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'none'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get("Host") == "127.0.0.1:%s" % self.server.server_port

        def do_GET(self):
            if self.path != token_path or not self.valid_host():
                self.respond(404, "Not found")
                return
            self.respond(200, '<!doctype html><html lang="ja"><meta charset="utf-8"><title>Cription key setup</title>'
                         '<h1>Cription用キーをこのMacに保存</h1><p>%s 外部には送信しません。</p>'
                         '<form method="post"><label>%s <input name="key" type="password" '
                         'autocomplete="off" required></label><button type="submit">このMacに保存</button></form></html>' % (purpose, label))

        def do_POST(self):
            nonlocal saved
            expected_origin = "http://127.0.0.1:%s" % self.server.server_port
            if self.path != token_path or not self.valid_host() or self.headers.get("Origin") != expected_origin:
                self.respond(403, "Forbidden")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 4096 or self.headers.get_content_type() != "application/x-www-form-urlencoded":
                    raise ValueError("Invalid form submission")
                value = parse_qs(self.rfile.read(length).decode("utf-8"), strict_parsing=True).get("key", [""])[0]
                save_key(destination, value, kind=kind)
            except (ValueError, OSError, UnicodeError):
                self.respond(400, "保存できませんでした。キーの形式と保存先を確認してください。")
                return
            saved = True
            self.respond(200, "<h1>保存しました</h1><p>権限600でこのMacに保存しました。この画面を閉じてください。</p>")

    with HTTPServer(("127.0.0.1", 0), Handler) as http:
        http.timeout = 1
        print("Open locally: http://127.0.0.1:%s%s" % (http.server_port, token_path), flush=True)
        if open_browser:
            import webbrowser
            webbrowser.open("http://127.0.0.1:%s%s" % (http.server_port, token_path))
        deadline = time.monotonic() + timeout
        while not saved and time.monotonic() < deadline:
            http.handle_request()
    if not saved:
        raise ValueError("Key setup timed out; no key was saved")
    print("Runtime key saved locally with mode 600. Key content was not logged.")
    return 0
