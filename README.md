# Cription MCP server

The official [MCP](https://modelcontextprotocol.io) server for **Cription**: on-device transcription and your Cription notes for Claude, Codex, Cursor and any other MCP client.

- 🎙️ **Transcribe** local audio and video files with Apple's on-device SpeechAnalyzer (the engine Cription uses for its best-scoring languages, e.g. Japanese).
- 🔎 **Search and read** the notes you recorded with the Cription Mac app (read-only).
- 🔒 **Private**: everything runs on your Mac. No audio, transcript or note is sent anywhere by this server.
- 📦 **No dependencies**: Python 3.9 standard library plus a small Swift helper compiled on first use.

Looking for skills (minutes templates, etc.) and the Claude Code / Codex plugins? See [msandroid/cription-plugins](https://github.com/msandroid/cription-plugins).

[日本語は下にあります](#日本語)

## Requirements

- macOS 26 or later (for transcription; notes work on older macOS)
- Python 3.9+ (`python3`, bundled with the Xcode Command Line Tools)
- Xcode Command Line Tools (`xcode-select --install`) — the Swift helper is compiled once on first use
- [`uv`](https://docs.astral.sh/uv/) for the `uvx` commands below (or run from a clone, see [Without uv](#without-uv))

## Install

### Claude Code

Plugin with skills (recommended):

```
/plugin marketplace add msandroid/cription-plugins
/plugin install cription@cription
```

MCP server only:

```bash
claude mcp add cription --scope user -- uvx --from git+https://github.com/msandroid/cription-mcp cription-mcp
```

### Claude Desktop

Download `cription-<version>.mcpb` from [Releases](https://github.com/msandroid/cription-mcp/releases) and double-click it (or drag it into Claude → Settings → Extensions).

Or add to `~/Library/Application Support/Claude/claude_desktop_config.json` and restart Claude:

```json
{
  "mcpServers": {
    "cription": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/msandroid/cription-mcp", "cription-mcp"]
    }
  }
}
```

Use the absolute path to `uvx` (`which uvx`) if Claude cannot find it.

### Codex

```bash
codex mcp add cription -- uvx --from git+https://github.com/msandroid/cription-mcp cription-mcp
```

Skills for Codex: `codex plugin marketplace add msandroid/cription-plugins`.

### Cursor and other MCP clients

`.cursor/mcp.json` (or your client's equivalent):

```json
{
  "mcpServers": {
    "cription": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/msandroid/cription-mcp", "cription-mcp"]
    }
  }
}
```

### Without uv

```bash
git clone https://github.com/msandroid/cription-mcp
```

Then use `python3 /path/to/cription-mcp/cription_mcp/server.py` as the server command.

Pin a version with `git+https://github.com/msandroid/cription-mcp@v0.1.0`.

## Tools

| Tool | What it does |
|---|---|
| `transcribe_audio` | Audio/video file → transcript with `[mm:ss]` timestamps. Options: `locale` (e.g. `ja-JP`), `terms` (names/jargon to spell right), `timestamps`, `save_to`. Long transcripts are saved to a file. |
| `speech_languages` | Locales the on-device engine supports and has installed. |
| `list_notes` | Your Cription notes, newest first (`limit`, `folder`, `since`). |
| `search_notes` | Full-text search over titles, summaries, transcripts and memos. |
| `get_note` | One note: transcript with speakers, summary, to-dos, memos, bookmarks. |
| `list_folders` | Note folders and counts. |
| `cription_status` | What this Mac supports and which note stores were found. |

## Privacy

The server only reads files you ask it to transcribe and the Cription app's local preferences (`~/Library/Preferences/Cription.plist` or the app container). It writes only its compiled helper and long transcripts under `~/Library/Caches/cription-mcp` (or `$CLAUDE_PLUGIN_DATA` when run as a plugin). The AI client you use decides what it does with the results.

## Limits

- Supported transcription languages are Apple's SpeechAnalyzer locales (`speech_languages`). Cription the app supports more languages with additional engines.
- No speaker diarization in `transcribe_audio` yet; notes recorded in the app keep their speaker labels.
- Notes recorded on iPhone are visible only once they are on the Mac.

## Development

```bash
python3 cription_mcp/server.py          # stdio MCP server
npx -y @anthropic-ai/mcpb pack . dist/  # build the Claude Desktop bundle
```

Keep the version in sync across `pyproject.toml`, `manifest.json` and `VERSION` in `cription_mcp/server.py`.

---

## 日本語

Cription 公式の MCP サーバーです。Cription の**オンデバイス文字起こし**と**ノート**を、Claude Code・Claude Desktop・Codex・Cursor などの AI エージェントから使えるようにします。

- **文字起こし**：手元の音声・動画ファイルを Apple SpeechAnalyzer でオンデバイスで文字起こしします（日本語で Cription が最も精度の高いエンジン）。
- **ノート検索**：Cription の Mac アプリで録音したノートを読み取り専用で検索・参照します。
- **プライバシー**：すべて Mac の中で処理し、音声・文字起こし・ノートを外部に送りません。

必要なもの：macOS 26 以降（文字起こし）、Xcode Command Line Tools（初回に小さな Swift ヘルパーをビルドします）、`uv`。

議事録テンプレートなどのスキル付きプラグインは [cription-plugins](https://github.com/msandroid/cription-plugins) にあります。Claude Code なら次の2行です。

```
/plugin marketplace add msandroid/cription-plugins
/plugin install cription@cription
```

インストール方法の詳細は上の [Install](#install) を参照してください。

## License

MIT
