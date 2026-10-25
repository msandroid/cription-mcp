"""Official MCP SDK: HTTP bridge with synthetic notes and optional real audio.

uv run --no-project --with 'mcp>=1.20,<2' --with httpx --python 3.12 python tests/smoke_remote.py --audio /path/test.aiff
Use --client manus --url https://.../mcp for a configured restricted public connection.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cription_mcp import remote, server


async def check(url, profile, audio=None, full=False):
    async with httpx.AsyncClient(headers={'Authorization': 'Bearer ' + profile['token']}, timeout=180) as client:
        async with streamable_http_client(url, http_client=client) as streams:
            async with ClientSession(*streams[:2]) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert {t.name for t in tools.tools} == set(profile['tools'])
                results = {}
                async def call(name, args):
                    result = await session.call_tool(name, args)
                    assert not result.isError, (name, result.content)
                    results[name] = result.structuredContent
                    return result.structuredContent
                languages = await call('speech_languages', {})
                assert languages['supported']
                if full:
                    assert (await call('cription_status', {}))['notes'] == 1
                    assert (await call('list_notes', {}))['count'] == 1
                    assert (await call('search_notes', {'query': 'cedar'}))['count'] == 1
                    assert 'Cedar seven' in (await call('get_note', {'id': 'remote-smoke'}))['transcript']
                    await call('list_folders', {})
                    assert 'Synthetic' in (await call('read_transcript', {'transcript_id': 'a'*32}))['transcript']
                    if audio:
                        transcript = await call('transcribe_audio', {'path': audio, 'locale': 'en-US'})
                        assert transcript.get('transcript'), transcript
                print(json.dumps({'transport': 'streamable-http', 'tools': len(tools.tools), 'checked': list(results),
                                  'audio': bool(audio and full)}, ensure_ascii=False))


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url')
    parser.add_argument('--client', choices=remote.CLIENTS, default='manus')
    parser.add_argument('--audio')
    args = parser.parse_args()
    if args.url:
        await check(args.url, remote.load_profile(args.client))
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        notes = root/'notes'
        notes.mkdir()
        (notes/'fixture.json').write_text(json.dumps({'id': 'remote-smoke', 'title': 'Synthetic cedar', 'text': 'Cedar seven', 'timestamp': 814492800, 'folder': 'Tests'}))
        cache = root/'cache/transcripts'
        cache.mkdir(parents=True)
        (cache/('a'*32+'.txt')).write_text('Synthetic cached transcript')
        env = {'CRIPTION_NOTES_DIR': str(notes), 'CRIPTION_NOTES_PLIST': str(root/'absent.plist'), 'CLAUDE_PLUGIN_DATA': str(root/'cache')}
        profile = {'client': 'manus', 'token': 'synthetic-test-only-'*4, 'tools': list(server.TOOL_BY_NAME)}
        with patch.dict(os.environ, env), remote.Bridge(('127.0.0.1', 0), profile) as bridge:
            threading.Thread(target=bridge.serve_forever, daemon=True).start()
            try:
                await check(bridge.connection_url, profile, args.audio, True)
            finally:
                bridge.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
