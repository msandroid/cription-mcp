"""Protocol, transcript pagination and client setup regression tests (no AI account)."""

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse
import urllib.request

from cription_mcp import key_setup, server, setup


class ProtocolTests(unittest.TestCase):
    def test_invalid_messages_do_not_kill_server(self):
        messages = ["not json", "null", "42", '"text"', '{}',
                    json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                "params": {"name": [], "arguments": {}}}),
                    json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                "params": {"name": "cription_status", "arguments": [1]}}),
                    json.dumps({"jsonrpc": "2.0", "id": 4, "method": "ping"})]
        p = subprocess.run([sys.executable, server.__file__], input="\n".join(messages) + "\n",
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = [json.loads(line) for line in p.stdout.splitlines()]
        self.assertTrue(all("error" in row for row in rows[:-1]))
        self.assertEqual(rows[-1]["result"], {})

    def test_initialize_and_tools(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2025-06-18"}})
            server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
            server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["result"]["serverInfo"]["version"], server.VERSION)
        self.assertEqual(len(rows[1]["result"]["tools"]), 8)
        self.assertTrue(all("handler" not in t for t in rows[1]["result"]["tools"]))

    def test_bundle_tool_list_and_version_match_server(self):
        manifest = json.loads((Path(server.__file__).parents[1] / "manifest.json").read_text())
        self.assertEqual(manifest["version"], server.VERSION)
        self.assertEqual({t["name"] for t in manifest["tools"]}, set(server.TOOL_BY_NAME))


class TranscriptTests(unittest.TestCase):
    def test_remote_client_can_read_whole_long_transcript(self):
        text = "議事録のテスト。" * 7000
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": tmp}):
            audio = Path(tmp) / "input.wav"
            audio.touch()
            with patch.object(server, "run_helper", return_value={"text": text}):
                result = server.tool_transcribe_audio({"path": str(audio), "timestamps": False})
            parts = [result["transcript"][:4000]]
            offset = result["nextOffset"]
            while offset is not None:
                page = server.tool_read_transcript({"transcript_id": result["transcriptId"], "offset": offset})
                parts.append(page["transcript"])
                offset = page["nextOffset"]
            self.assertEqual("".join(parts), text)

    def test_cannot_read_arbitrary_files(self):
        with self.assertRaises(server.ToolError):
            server.tool_read_transcript({"transcript_id": "../../etc/passwd"})
        with self.assertRaises(server.ToolError):
            server.tool_read_transcript({"transcript_id": "a" * 32, "offset": -1})
        with self.assertRaises(server.ToolError):
            server.tool_read_transcript({"transcript_id": "a" * 32, "limit": 16001})
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": tmp}):
            folder = Path(tmp) / "transcripts"
            folder.mkdir()
            (folder / ("a" * 32 + ".txt")).symlink_to("/etc/hosts")
            with self.assertRaises(server.ToolError):
                server.tool_read_transcript({"transcript_id": "a" * 32})


class SetupTests(unittest.TestCase):
    def test_cursor_install_preserves_other_servers_and_repeats_safely(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path, "home", return_value=Path(tmp)):
            path = Path(tmp) / ".cursor/mcp.json"
            path.parent.mkdir()
            original = {"mcpServers": {"other": {"command": "existing"}}, "custom": True}
            path.write_text(json.dumps(original))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(setup.main(["install", "cursor"]), 0)
                self.assertEqual(setup.main(["install", "cursor"]), 0)
            result = json.loads(path.read_text())
            self.assertEqual(result["mcpServers"]["other"], original["mcpServers"]["other"])
            self.assertEqual(result["mcpServers"]["cription"], setup.server_config())
            self.assertTrue(result["custom"])
            self.assertEqual(len(list(path.parent.glob("*.bak"))), 1)


    def test_preserves_existing_settings_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            original = {"mcpServers": {"other": {"command": "other"}}, "theme": "dark"}
            path.write_text(json.dumps(original))
            backup = setup.install_json(path, setup.server_config())
            self.assertEqual(json.loads(backup.read_text()), original)
            data = json.loads(path.read_text())
            self.assertEqual(data["theme"], "dark")
            self.assertEqual(data["mcpServers"]["other"], {"command": "other"})
            self.assertIsNone(setup.install_json(path, setup.server_config()))
            with self.assertRaises(ValueError):
                setup.install_json(path, {"command": "different"})

    def test_invalid_json_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("broken")
            with self.assertRaises(ValueError):
                setup.install_json(path, setup.server_config())
            self.assertEqual(path.read_text(), "broken")

    def test_tunnel_command_quotes_paths_and_stores_only_key_reference(self):
        args = argparse.Namespace(action="init", profile="cription", tunnel_id="tunnel_test")
        with patch.object(setup, "tunnel_binary", return_value="/bin/tunnel-client"), \
                patch.object(setup, "server_config", return_value={"command": "/Python With Spaces/python", "args": ["/a b/server.py"]}):
            command = setup.tunnel_command(args)
        self.assertEqual(__import__("shlex").split(command[command.index("--mcp-command") + 1]),
                         ["/Python With Spaces/python", "/a b/server.py"])
        self.assertIn("env:CONTROL_PLANE_API_KEY", command)
        self.assertIn("127.0.0.1:0", command)

    def test_missing_key_and_tunnel_id_fail_before_launch(self):
        args = argparse.Namespace(action="run", profile="cription", tunnel_id=None)
        with patch.object(setup, "tunnel_binary", return_value="/bin/tunnel-client"), patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "CONTROL_PLANE_API_KEY"):
                setup.tunnel_command(args)
            args.action = "init"
            with self.assertRaisesRegex(ValueError, "tunnel ID"):
                setup.tunnel_command(args)

    def test_private_key_file_is_referenced_without_reading_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime-key"
            path.write_text("synthetic-test-key")
            path.chmod(0o600)
            args = argparse.Namespace(action="doctor", profile="cription", tunnel_id=None, key_file=str(path))
            with patch.object(setup, "tunnel_binary", return_value="/bin/tunnel-client"), patch.dict(os.environ, {}, clear=True):
                command = setup.tunnel_command(args)
                self.assertIn("file:" + str(path.resolve()), command)
                self.assertNotIn("synthetic-test-key", " ".join(command))
                path.chmod(0o644)
                with self.assertRaisesRegex(ValueError, "chmod 600"):
                    setup.tunnel_command(args)


class KeySetupTests(unittest.TestCase):
    def test_private_exclusive_key_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "key"
            key_setup.save_key(path, "sk-synthetic-test-runtime-key")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                key_setup.save_key(path, "sk-replacement-test-runtime-key")
            self.assertEqual(path.read_text(), "sk-synthetic-test-runtime-key")

    def test_browser_form_checks_origin_without_logging_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "key"
            process = subprocess.Popen([sys.executable, "-c",
                "from cription_mcp.key_setup import serve; import sys; serve(sys.argv[1], timeout=5)", str(path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                url = process.stdout.readline().strip().removeprefix("Open locally: ")
                with urllib.request.urlopen(url, timeout=2) as response:
                    self.assertEqual(response.headers["Referrer-Policy"], "same-origin")
                    self.assertIn('type="password"', response.read().decode())
                secret = "sk-synthetic-browser-test-runtime-key"
                body = urllib.parse.urlencode({"key": secret}).encode()
                parsed = urllib.parse.urlsplit(url)
                origin = "%s://%s" % (parsed.scheme, parsed.netloc)
                bad = urllib.request.Request(url, data=body, headers={"Origin": "https://example.com"})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(bad, timeout=2)
                self.assertEqual(caught.exception.code, 403)
                self.assertFalse(path.exists())
                good = urllib.request.Request(url, data=body, headers={"Origin": origin})
                with urllib.request.urlopen(good, timeout=2) as response:
                    self.assertEqual(response.status, 200)
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertNotIn(secret, stdout + stderr)
                self.assertEqual(path.read_text(), secret)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()


if __name__ == "__main__":
    unittest.main()
