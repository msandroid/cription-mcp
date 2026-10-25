"""Provider schema, credential boundaries and safe result rendering."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cription_mcp import cloud_chat as cloud, key_setup, setup


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.profile = {'token': 'private-bridge-token', 'tools': ['speech_languages']}

    def test_provider_specific_mcp_payloads(self):
        grok = cloud.payload('grok', 'explicit-model', 'fixture', 'https://example.com/mcp', self.profile)
        self.assertEqual(grok['tools'][0]['allowed_tools'], ['speech_languages'])
        gemini = cloud.payload('gemini', 'explicit-model', 'fixture', 'https://example.com/mcp', self.profile)
        self.assertEqual(gemini['tools'][0]['allowed_tools'], [{'mode': 'auto', 'tools': ['speech_languages']}])
        self.assertFalse(gemini['store'])
        self.assertEqual(gemini['tools'][0]['headers']['Authorization'], 'Bearer private-bridge-token')
        for url in ('http://example.com/mcp', 'https://user:pass@example.com/mcp', 'https://example.com/mcp?key=secret', 'https://example.com/other'):
            with self.assertRaises(ValueError):
                cloud.payload('gemini', 'model', 'fixture', url, self.profile)
        with self.assertRaises(ValueError):
            cloud.payload('grok', 'model', 'fixture', 'https://example.com/mcp', self.profile, ['get_note'])

    def test_dry_run_has_no_credentials_or_network_call(self):
        output = io.StringIO()
        with patch.object(cloud.remote, 'load_profile', return_value=self.profile), patch.object(cloud, 'request') as request, contextlib.redirect_stdout(output):
            self.assertEqual(cloud.main(['grok', '--url', 'https://example.com/mcp', '--model', 'model', '--prompt', 'fixture', '--dry-run']), 0)
            request.assert_not_called()
        self.assertNotIn(self.profile['token'], output.getvalue())
        self.assertIn('[REDACTED]', output.getvalue())

    def test_private_api_keys_and_no_overwrite(self):
        for provider, key in [('gemini', 'AIza'+'a'*35), ('grok', 'xai-'+'a'*40)]:
            with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
                path = Path(folder)/'key'
                key_setup.save_key(path, key, kind=provider)
                self.assertEqual(cloud.api_key(provider, str(path)), key)
                with self.assertRaises(ValueError):
                    key_setup.save_key(path, key, kind=provider)
                path.chmod(0o644)
                with self.assertRaises(ValueError):
                    cloud.api_key(provider, str(path))

    def test_response_selection_does_not_echo_authentication(self):
        response = cloud.public_result('gemini', {'id': 'test', 'headers': {'Authorization': 'secret'}, 'steps': [
            {'type': 'model_output', 'content': [{'type': 'text', 'text': 'Japanese supported'}]},
            {'type': 'function_call', 'name': 'speech_languages'},
            {'type': 'function_result', 'name': 'speech_languages', 'is_error': False, 'result': {'private': 'not echoed'}}]})
        self.assertEqual(response['text'], 'Japanese supported')
        self.assertEqual(response['tool_calls'][0]['name'], 'speech_languages')
        self.assertNotIn('secret', json.dumps(response))
        self.assertNotIn('not echoed', json.dumps(response))
        self.assertEqual(response['tool_results'], [{'name': 'speech_languages', 'has_error': False}])
        grok = cloud.public_result('grok', {'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'ok'}]}, {'type': 'mcp_call', 'name': 'speech_languages', 'status': 'completed'}]})
        self.assertEqual(grok['text'], 'ok')
        self.assertEqual(grok['tool_calls'][0]['status'], 'completed')

    def test_gemini_settings_merge_preserves_other_configuration(self):
        self.assertEqual(setup.CLIENT_PATHS['gemini'], '.gemini/settings.json')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'settings.json'
            path.write_text(json.dumps({'theme': 'existing', 'mcpServers': {'other': {'command': 'other'}}}))
            backup = setup.install_json(path, {'command': '/absolute/python', 'args': ['server.py']})
            self.assertEqual(json.loads(path.read_text())['theme'], 'existing')
            self.assertIn('other', json.loads(path.read_text())['mcpServers'])
            self.assertTrue(backup.is_file())
            self.assertIsNone(setup.install_json(path, {'command': '/absolute/python', 'args': ['server.py']}))


if __name__ == '__main__':
    unittest.main()
