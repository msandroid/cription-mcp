import contextlib
import io
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import unittest
from unittest.mock import patch

from cription_mcp import local_chat, setup, tunnel_setup


class LocalChatTests(unittest.TestCase):
    def test_both_protocols_execute_real_tool_and_return_result(self):
        for backend in ('ollama', 'llama-cpp'):
            requests = []
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *args): pass
                def do_POST(self):
                    body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    requests.append((self.path, body))
                    call = {'id': 'call_1', 'type': 'function', 'function': {'name': 'speech_languages', 'arguments': {} if backend == 'ollama' else '{}'}}
                    message = {'role': 'assistant', 'content': '', 'tool_calls': [call]} if len(requests) == 1 else {'role': 'assistant', 'content': 'verified'}
                    payload = {'message': message} if backend == 'ollama' else {'choices': [{'message': message}]}
                    data = json.dumps(payload).encode()
                    self.send_response(200); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
            with HTTPServer(('127.0.0.1', 0), Handler) as http:
                thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
                try:
                    with contextlib.redirect_stderr(io.StringIO()):
                        result = local_chat.chat(backend, 'test', 'languages', 'http://127.0.0.1:%s' % http.server_port)
                    self.assertEqual(result, 'verified')
                    self.assertEqual(requests[0][0], '/api/chat' if backend == 'ollama' else '/v1/chat/completions')
                    reply = requests[1][1]['messages'][-1]
                    self.assertEqual(reply['role'], 'tool')
                    self.assertFalse(json.loads(reply['content'])['isError'])
                    self.assertIn('tool_name' if backend == 'ollama' else 'tool_call_id', reply)
                finally:
                    http.shutdown(); thread.join()

    def test_endpoint_and_tool_boundaries(self):
        for url in ('https://example.com', 'http://example.com', 'http://localhost', 'http://127.0.0.1@evil.com', 'http://127.0.0.1/?x=1'):
            with self.assertRaises(ValueError): local_chat.endpoint_url(url, 'ollama')
        self.assertIn('not allowed', local_chat.execute_tool('transcribe_audio', {}, {'speech_languages'}))
        self.assertIn('error', local_chat.execute_tool('speech_languages', '[]', {'speech_languages'}))

    def test_ready_tunnel_reuses_without_key_or_mutation(self):
        current = {'ready': True, 'process_running': True, 'tunnel_id': 'tunnel_test'}
        with patch.object(setup, 'tunnel_binary', return_value='tunnel-client'), patch.object(tunnel_setup, 'status', return_value=current), patch.object(tunnel_setup.subprocess, 'run') as run, patch.object(tunnel_setup.webbrowser, 'open') as browser, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup.main(['chatgpt', 'connect', '--no-browser']), 0)
            run.assert_not_called(); browser.assert_not_called()

    def test_tunnel_conflict_does_not_modify_existing_alias(self):
        with patch.object(setup, 'tunnel_binary', return_value='tunnel-client'), patch.object(tunnel_setup, 'status', return_value={'tunnel_id': 'tunnel_first'}), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(setup.main(['chatgpt', 'connect', '--tunnel-id', 'tunnel_other', '--no-browser']), 1)

    def test_redirect_rejected_before_following(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                self.send_response(307); self.send_header('Location', 'http://example.com/'); self.end_headers()
        with HTTPServer(('127.0.0.1', 0), Handler) as http:
            thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
            try:
                with self.assertRaisesRegex(ValueError, 'redirects'):
                    local_chat.request_json('http://127.0.0.1:%s/' % http.server_port, {}, 2)
            finally:
                http.shutdown(); thread.join()

    def test_cloud_model_rejected(self):
        with self.assertRaisesRegex(ValueError, 'cloud models'):
            local_chat.chat('ollama', 'model:cloud', 'test')

    def test_installer_checksum_failure_leaves_no_binary(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path, 'home', return_value=Path(tmp)), patch.object(tunnel_setup.urllib.request, 'urlopen') as open_url:
            open_url.return_value.__enter__.return_value.read.return_value = b'corrupted'
            with self.assertRaisesRegex(ValueError, 'checksum'):
                tunnel_setup.install_binary()
            self.assertFalse((Path(tmp) / '.local').exists())

    def test_new_tunnel_connection_uses_file_reference_and_waits_for_ready(self):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / 'key'; key.write_text('sk-test-runtime-key-only'); key.chmod(0o600)
            args = SimpleNamespace(profile='test', tunnel_id='tunnel_new', key_file=str(key), no_browser=True, wait=0)
            with patch.object(setup, 'tunnel_binary', return_value='tunnel-client'), patch.object(tunnel_setup, 'status', side_effect=[{}, {'ready': True, 'process_running': True}]), patch.object(tunnel_setup.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(tunnel_setup.connect(args), 0)
                command = run.call_args.args[0]
                self.assertIn('file:' + str(key.resolve()), command)
                self.assertNotIn(key.read_text(), ' '.join(command))
                self.assertIn('--tunnel-id', command)
