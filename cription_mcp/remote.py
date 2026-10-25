"""Authenticated loopback Streamable HTTP MCP for cloud AI clients."""
import argparse
import contextlib
import copy
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse

from . import server

CLIENTS = ('notion', 'manus', 'grok', 'gemini-api')
MAX_BODY = 1024 * 1024
DISPATCH_LOCK = threading.Lock()


def profile_path(client):
    if client not in CLIENTS:
        raise ValueError('Choose a supported client: ' + ', '.join(CLIENTS))
    return Path.home() / '.config/cription-mcp' / ('remote-' + client + '.json')


def private_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def load_profile(client):
    path = profile_path(client)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError('Initialize a private profile first; permissions must be 600: %s' % path)
    data = json.loads(path.read_text())
    if not isinstance(data.get('token'), str) or len(data['token']) < 32:
        raise ValueError('Invalid profile token')
    tools = data.get('tools')
    if not isinstance(tools, list) or not tools or not all(isinstance(t, str) and t in server.TOOL_BY_NAME for t in tools):
        raise ValueError('Invalid profile tools')
    return data


def dispatch(message, allowed):
    """Share the stdio handlers without redirecting stdout in other threads."""
    if not isinstance(message, dict):
        return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid request'}}
    method = message.get('method')
    if method == 'tools/list':
        advertised = [copy.deepcopy({k: v for k, v in t.items() if k != 'handler'})
                      for t in server.TOOLS if t['name'] in allowed]
        for tool in advertised:
            tool.get('inputSchema', {}).get('properties', {}).pop('save_to', None)
        return {'jsonrpc': '2.0', 'id': message.get('id'), 'result': {'tools': advertised}}
    if method == 'tools/call':
        params = message.get('params')
        if not isinstance(params, dict) or not isinstance(params.get('name'), str) or params.get('name') not in allowed:
            return {'jsonrpc': '2.0', 'id': message.get('id'), 'error': {'code': -32602, 'message': 'Tool is not enabled for this connection'}}
        # Remote transcription can read audio; arbitrary writes on the Mac are disabled.
        arguments = params.get('arguments', {})
        if isinstance(arguments, dict) and arguments.get('save_to'):
            return {'jsonrpc': '2.0', 'id': message.get('id'), 'error': {'code': -32602, 'message': 'save_to is disabled over remote MCP'}}
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        server.handle(message)
    value = output.getvalue().strip()
    return json.loads(value) if value else None


class Bridge(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, profile):
        self.profile = profile
        self.public_url = ''
        self.setup_nonce = secrets.token_urlsafe(32)
        self.dispatch_lock = DISPATCH_LOCK
        super().__init__(address, Handler)

    @property
    def local_url(self):
        return 'http://127.0.0.1:%s' % self.server_port

    @property
    def connection_url(self):
        return (self.public_url or self.local_url) + '/mcp'


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'Cription'

    def log_message(self, *_args):
        pass  # Never log paths, tokens, transcripts or request bodies.

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def respond(self, status, data=None, content_type='application/json', headers=None):
        if isinstance(data, str):
            body = data.encode('utf-8')
        elif data is None:
            body = b''
        else:
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; form-action 'none'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def local_host(self):
        return self.headers.get('Host') == '127.0.0.1:%s' % self.server.server_port

    def allowed_host(self):
        public = urllib.parse.urlsplit(self.server.public_url).netloc
        return self.local_host() or bool(public and self.headers.get('Host') == public)

    def auth(self):
        if not self.allowed_host():
            self.respond(403, {'error': 'Host rejected'})
            return False
        origin = self.headers.get('Origin')
        if origin and origin not in (self.server.local_url, self.server.public_url):
            self.respond(403, {'error': 'Origin rejected'})
            return False
        value = self.headers.get('Authorization', '')
        if not secrets.compare_digest(value.encode(), ('Bearer ' + self.server.profile['token']).encode()):
            self.respond(401, {'error': 'Bearer token required'}, headers={'WWW-Authenticate': 'Bearer realm="Cription"'})
            return False
        return True

    def do_GET(self):
        if self.path == '/connect/' + self.server.setup_nonce:
            if not self.local_host() or self.client_address[0] != '127.0.0.1':
                self.respond(404)
                return
            url = html.escape(self.server.connection_url, quote=True)
            token = html.escape(self.server.profile['token'], quote=True)
            text = '<!doctype html><html lang="ja"><meta charset="utf-8"><title>Cription connection</title><h1>Cription %s</h1><p>このMacの接続設定。キーは他人に共有しないでください。</p><label>MCP URL <input id="mcp-url" value="%s" readonly size="85"></label><p><label>Authorization <input id="authorization" type="password" value="Bearer %s" readonly size="85"></label></p><p>Tools: %s</p></html>' % (html.escape(self.server.profile['client']), url, token, ', '.join(self.server.profile['tools']))
            self.respond(200, text, 'text/html; charset=utf-8')
        elif self.path == '/health' and self.allowed_host():
            self.respond(200, {'ok': True, 'version': server.VERSION})
        elif self.path == '/mcp':
            if self.auth():
                self.respond(405, headers={'Allow': 'POST'})
        else:
            self.respond(404)

    def do_DELETE(self):
        if self.path != '/mcp':
            self.respond(404)
        elif self.auth():
            self.respond(405, headers={'Allow': 'POST'})  # Stateless: no sessions to delete.

    def do_POST(self):
        if self.path != '/mcp':
            self.respond(404)
            return
        if not self.auth():
            return
        if self.headers.get_content_type() != 'application/json' or self.headers.get('Transfer-Encoding'):
            self.respond(415)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                self.respond(413)
                return
            message = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError):
            self.respond(400, {'error': 'Invalid JSON'})
            return
        protocol = self.headers.get('MCP-Protocol-Version')
        if protocol and protocol not in server.PROTOCOL_VERSIONS:
            self.respond(400, {'error': 'Unsupported MCP protocol version'})
            return
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'), str):
            self.respond(400, {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid request'}})
            return
        if 'id' not in message:
            self.respond(202)
            return
        # stdout capture and Apple helper work are serialized; parallel clients
        # cannot mix JSON responses or run unbounded recognition jobs.
        if not self.server.dispatch_lock.acquire(blocking=False):
            self.respond(429, {'error': 'Another tool is running; retry shortly'}, headers={'Retry-After': '2'})
            return
        try:
            result = dispatch(message, set(self.server.profile['tools']))
            self.respond(200, result)
        finally:
            self.server.dispatch_lock.release()


def run_tunnel(http, binary, timeout=45):
    process = subprocess.Popen([binary, 'tunnel', '--url', http.local_url, '--no-autoupdate', '--protocol', 'http2'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + timeout
    # Read in a separate thread so a stalled tunnel cannot block the timeout.
    ready = threading.Event()
    def read_log():
        for line in process.stderr:
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
            if match:
                http.public_url = match.group(0)
                ready.set()
    threading.Thread(target=read_log, daemon=True).start()
    while not ready.wait(.1):
        if process.poll() is not None or time.monotonic() > deadline:
            process.terminate()
            process.wait(timeout=10)
            raise ValueError('Cloudflare tunnel did not become ready; check Internet access')
    return process


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'serve', 'config'])
    parser.add_argument('client', choices=CLIENTS)
    parser.add_argument('--tools', nargs='+', choices=['all'] + list(server.TOOL_BY_NAME), default=['speech_languages'])
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--tunnel', action='store_true', help='Start an authenticated temporary HTTPS endpoint using installed cloudflared')
    parser.add_argument('--public-url', help='HTTPS origin provided by your own reverse proxy')
    args = parser.parse_args(argv)
    try:
        if args.action == 'init':
            path = profile_path(args.client)
            tools = list(server.TOOL_BY_NAME) if args.tools == ['all'] else args.tools
            if 'all' in tools:
                raise ValueError('Use --tools all alone')
            private_json(path, {'client': args.client, 'token': secrets.token_urlsafe(48), 'tools': tools})
            print('Created private connection profile: %s\nEnabled tools: %s' % (path, ', '.join(tools)))
            return 0
        profile = load_profile(args.client)
        if args.action == 'config':
            print('Private profile: %s\nEnabled tools: %s\nRun serve to display the local connection form. Tokens are never printed.' % (profile_path(args.client), ', '.join(profile['tools'])))
            return 0
        if not 0 <= args.port <= 65535:
            raise ValueError('Invalid port')
        if args.tunnel and args.public_url:
            raise ValueError('Choose --tunnel or --public-url, not both')
        if args.public_url:
            parsed = urllib.parse.urlsplit(args.public_url)
            if parsed.scheme != 'https' or not parsed.netloc or parsed.path not in ('', '/') or parsed.username is not None or parsed.query or parsed.fragment:
                raise ValueError('--public-url must be an HTTPS origin without path, credentials or query')
        with Bridge(('127.0.0.1', args.port), profile) as http:
            process = None
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                if args.tunnel:
                    binary = shutil.which('cloudflared')
                    if not binary:
                        raise ValueError('Install cloudflared first: brew install cloudflared')
                    process = run_tunnel(http, binary)
                elif args.public_url:
                    http.public_url = args.public_url.rstrip('/')
                print('MCP URL: %s\nOpen locally: %s/connect/%s\nEnabled tools: %s\nKeep this process and Mac running. Ctrl-C stops this connection.' % (http.connection_url, http.local_url, http.setup_nonce, ', '.join(profile['tools'])), flush=True)
                while True:
                    if process and process.poll() is not None:
                        raise ValueError("Cloudflare tunnel stopped; restart serve and reconnect using the new URL")
                    time.sleep(1)
            finally:
                if process:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait()
                http.shutdown()
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError) as error:
        print('cription-mcp-remote: %s' % error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
