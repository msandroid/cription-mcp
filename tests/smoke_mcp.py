"""Exercise Cription through the official MCP client, with synthetic notes only.

Run: uv run --no-project --with mcp --python 3.12 tests/smoke_mcp.py --audio /path/to/test.aiff
"""

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


@asynccontextmanager
async def transport(params, tunnel_client, folder):
    if not tunnel_client:
        async with stdio_client(params) as streams:
            yield streams
        return
    import shlex
    url_file = folder / "tunnel-url.json"
    with open(folder / "tunnel.log", "w") as log:
        process = subprocess.Popen([
            tunnel_client, "dev", "proxy", "--mcp-command", shlex.join([params.command] + params.args),
            "--duration", "90s", "--url-file", str(url_file)], env=params.env, stdout=log, stderr=log)
        try:
            for _ in range(200):
                if url_file.exists():
                    break
                if process.poll() is not None:
                    raise RuntimeError((folder / "tunnel.log").read_text()[-2000:])
                await asyncio.sleep(0.1)
            if not url_file.exists():
                raise TimeoutError("Local tunnel proxy did not become ready")
            url = json.loads(url_file.read_text())["mcp_url"]
            async with streamable_http_client(url) as streams:
                yield streams[:2]
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


async def run(audio=None, locale="en-US", tunnel_client=None, server_command=None):
    with tempfile.TemporaryDirectory(prefix="cription-smoke-") as tmp:
        folder = Path(tmp)
        note = {"id": "cription-smoke-note", "title": "Synthetic cedar meeting",
                "timestamp": 814492800, "text": "Cedar seven is the synthetic project code.",
                "summary": "Integration fixture only.", "duration": 5, "folder": "Tests"}
        notes = folder / "notes"
        notes.mkdir()
        (notes / "note.json").write_text(json.dumps(note))
        transcripts = folder / "cache/transcripts"
        transcripts.mkdir(parents=True)
        transcript_id = "a" * 32
        (transcripts / (transcript_id + ".txt")).write_text("Synthetic cached transcript. " * 2000)
        env = dict(os.environ, CRIPTION_NOTES_DIR=str(notes),
                   CRIPTION_NOTES_PLIST=str(folder / "absent.plist"), CLAUDE_PLUGIN_DATA=str(folder / "cache"))
        server = Path(__file__).resolve().parents[1] / "cription_mcp/server.py"
        command = server_command or [sys.executable, str(server)]
        params = StdioServerParameters(command=command[0], args=command[1:], env=env)
        async with transport(params, tunnel_client, folder) as (read, write), ClientSession(read, write) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            assert len(tools.tools) == 8
            checked = []

            async def call(name, arguments):
                result = (await session.call_tool(name, arguments)).model_dump(by_alias=True)
                assert not result.get("isError", False), (name, result.get("content"))
                checked.append(name)
                return result["structuredContent"]

            status = await call("cription_status", {})
            assert status["notes"] == 1
            languages = await call("speech_languages", {})
            assert languages["supported"]
            listing = await call("list_notes", {})
            assert listing["count"] == 1
            search = await call("search_notes", {"query": "cedar"})
            assert search["count"] == 1
            detail = await call("get_note", {"id": "cription-smoke-note"})
            assert "Cedar seven" in detail["transcript"]
            folders = await call("list_folders", {})
            assert folders["folders"] == [{"name": "Tests", "notes": 1}]
            page = await call("read_transcript", {"transcript_id": transcript_id, "offset": 0, "limit": 16000})
            assert len(page["transcript"]) == 16000 and page["nextOffset"] == 16000
            bad = await session.call_tool("get_note", {"id": "does-not-exist"})
            assert bad.model_dump(by_alias=True)["isError"]
            invalid = await session.call_tool("read_transcript", {"transcript_id": "../../etc/hosts"})
            assert invalid.model_dump(by_alias=True)["isError"]
            info = initialized.model_dump(by_alias=True)
            result = {"server": info["serverInfo"], "protocol": info["protocolVersion"],
                      "transport": "official-tunnel-local-proxy" if tunnel_client else "stdio",
                      "toolsDiscovered": len(tools.tools), "supportedLocales": len(languages["supported"]),
                      "toolsCalled": checked, "errorResponses": "passed", "syntheticNotes": True}
            if audio:
                transcription = await call("transcribe_audio", {"path": str(Path(audio).resolve()), "locale": locale})
                assert transcription["transcript"].strip()
                result["transcription"] = transcription
            print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio")
    parser.add_argument("--locale", default="en-US")
    parser.add_argument("--tunnel-client", help="Test the official local Tunnel HTTP-to-stdio path without credentials")
    parser.add_argument("--server-command", nargs="+", help="Test an installed server executable instead of this source checkout")
    args = parser.parse_args()
    asyncio.run(run(args.audio, args.locale, args.tunnel_client, args.server_command))
