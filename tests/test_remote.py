"""HTTP authentication, MCP boundaries and Notion export regression tests."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from cription_mcp import remote, notion_export as notion, server, key_setup


class RemoteTests(unittest.TestCase):
    def setUp(self):
        self.http = remote.Bridge(('127.0.0.1', 0), {'client': 'manus', 'token': 'a'*48, 'tools': ['cription_status']})
        self.http.public_url = 'https://example.test'
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()

    def send(self, body=None, headers=None, path='/mcp', method='POST'):
        connection = http.client.HTTPConnection('127.0.0.1', self.http.server_port, timeout=5)
        h = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + 'a'*48}
        h.update(headers or {})
        connection.request(method, path, body, h)
        response = connection.getresponse()
        status, data = response.status, response.read()
        connection.close()
        return status, data

    def rpc(self, method, params=None):
        return json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})

    def test_auth_host_origin_and_notification(self):
        self.assertEqual(self.send(self.rpc('ping'), {'Authorization': ''})[0], 401)
        self.assertEqual(self.send(self.rpc('ping'), {'Host': 'evil.test'})[0], 403)
        self.assertEqual(self.send(self.rpc('ping'), {'Origin': 'https://evil.test'})[0], 403)
        self.assertEqual(self.send(self.rpc('ping'), {'Host': 'example.test'})[0], 200)
        self.assertEqual(self.send(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'})), (202, b''))
        self.assertEqual(self.send(method='GET')[0], 405)

    def test_allowlist_protocol_and_invalid_messages(self):
        status, data = self.send(self.rpc('initialize', {'protocolVersion': '2025-06-18'}))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)['result']['serverInfo']['version'], server.VERSION)
        tools = json.loads(self.send(self.rpc('tools/list'))[1])['result']['tools']
        self.assertEqual([t['name'] for t in tools], ['cription_status'])
        for params in ({'name': 'list_notes'}, {'name': []}, {'name': 'cription_status', 'arguments': {'save_to': '/tmp/no'}}):
            self.assertEqual(json.loads(self.send(self.rpc('tools/call', params))[1])['error']['code'], -32602)
        self.assertEqual(self.send('{')[0], 400)
        self.assertEqual(self.send('[]')[0], 400)
        self.assertEqual(self.send(self.rpc('ping'), {'MCP-Protocol-Version': 'invalid'})[0], 400)
        self.assertEqual(self.send('', {'Content-Length': str(remote.MAX_BODY+1)})[0], 413)

    def test_setup_secret_only_local_and_no_arbitrary_write_advertisement(self):
        path = '/connect/' + self.http.setup_nonce
        self.assertIn(b'Bearer ' + b'a'*48, self.send(path=path, method='GET')[1])
        self.assertEqual(self.send(path=path, method='GET', headers={'Host': 'example.test'})[0], 404)
        listing = remote.dispatch({'id': 1, 'method': 'tools/list'}, set(server.TOOL_BY_NAME))
        for tool in listing['result']['tools']:
            self.assertNotIn('save_to', tool.get('inputSchema', {}).get('properties', {}))
        self.assertIn('save_to', server.TOOL_BY_NAME['transcribe_audio']['inputSchema']['properties'])

    def test_private_profile(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(remote, 'profile_path', return_value=Path(directory)/'profile.json'):
            path = remote.profile_path('manus')
            remote.private_json(path, {'token': 'a'*48, 'tools': ['cription_status']})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(remote.load_profile('manus')['tools'], ['cription_status'])
            with self.assertRaises(FileExistsError):
                remote.private_json(path, {})
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                remote.load_profile('manus')


class NotionTests(unittest.TestCase):
    def test_notion_token_does_not_change_openai_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory)/'notion-key'
            value = 'ntn_' + 'a'*40
            with self.assertRaises(ValueError):
                key_setup.save_key(key, value)
            key_setup.save_key(key, value, kind='notion')
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            self.assertEqual(key.read_text(), value)

    def test_block_types_and_unicode_preserved(self):
        text = 'あ😀'*12000
        result = notion.blocks('# Title\n- [x] Done\n- item\n> quote\n'+text)
        self.assertEqual([b['type'] for b in result[:4]], ['heading_1', 'to_do', 'bulleted_list_item', 'quote'])
        restored = ''.join(r['text']['content'] for b in result[4:] for r in b['paragraph']['rich_text'])
        self.assertEqual(restored, text)
        self.assertTrue(all(len(r['text']['content'].encode('utf-16-le'))//2 <= 2000 for b in result for r in b[b['type']]['rich_text']))

    def test_export_paginates_by_count_and_payload_bytes(self):
        calls = []
        def request(method, path, body, token):
            calls.append((method, path, body))
            return {'id': 'abc', 'url': 'https://notion.so/abc'}
        for markdown in ('line\n'*205, ('あ😀'*4400+'\n')*25):
            calls.clear()
            with patch.object(notion, 'request', side_effect=request):
                notion.export_page('00000000-0000-0000-0000-000000000001', 'Test', markdown, 'secret')
            self.assertGreater(len(calls), 1)
            self.assertTrue(all(len(body['children']) <= 100 and len(json.dumps(body).encode()) < 500000 for _, _, body in calls))
            self.assertEqual(sum(len(body['children']) for _, _, body in calls), len(notion.blocks(markdown)))

    def test_partial_write_reports_page_without_secret(self):
        with patch.object(notion, 'request', side_effect=[{'id': 'abc', 'url': 'https://notion.so/abc'}, ValueError('secret')]):
            with self.assertRaisesRegex(ValueError, 'https://notion.so/abc') as error:
                notion.export_page('00000000-0000-0000-0000-000000000001', 'Test', 'line\n'*101, 'secret')
            self.assertNotIn('secret', str(error.exception))

    def test_dry_run_never_sends_and_private_output(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(notion, 'request') as request:
            source, output = Path(directory)/'source.md', Path(directory)/'export.json'
            source.write_text('## Transcript\nHello', encoding='utf-8')
            self.assertEqual(notion.main(['--file', str(source), '--dry-run', '--output', str(output)]), 0)
            request.assert_not_called()
            self.assertEqual(json.loads(output.read_text())['content'], source.read_text())
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
