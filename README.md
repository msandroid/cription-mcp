# Cription MCP

On-device audio/video transcription and read-only access to your Cription notes, for **Claude, Codex, Antigravity, ChatGPT and other MCP clients**.

**Current release: [v0.3.1](https://github.com/msandroid/cription-mcp/releases/tag/v0.3.1).** [日本語のインストール手順](docs/INSTALL.ja.md) · [Plugins and skills](https://github.com/msandroid/cription-plugins)

Audio recognition runs on your Mac using Apple SpeechAnalyzer. Returned transcripts and notes are shared with your AI client and are subject to that service's data policies. The server has no Python runtime dependencies.

## Requirements

- **macOS 26+** for transcription. Notes can be read on older macOS.
- Python 3.9+ and Xcode Command Line Tools (`xcode-select --install`). The Swift helper is compiled on the first transcription or language query.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for the commands below. You can also install the wheel from Releases with `pip`.
- The Cription Mac app and locally stored notes for note access. Transcription works without the app. iPhone notes must first be available on the Mac.

## Install the server once

```bash
uv tool install --from git+https://github.com/msandroid/cription-mcp@v0.3.1 cription-mcp
uv tool update-shell
```

Reopen your terminal, then check `cription-mcp-setup --help`. If the command is not on PATH yet, use `"$(uv tool dir --bin)/cription-mcp-setup"` instead. This installs a persistent environment; the client settings will not depend on a source checkout or the current directory.

Choose **one** MCP connection per client: the plugin or a standalone server configuration, to avoid duplicate tools.

### Claude Code

Plugin, including the server and summary skills:

```text
/plugin marketplace add msandroid/cription-plugins
/plugin install cription@cription
```

Alternatively, use the installed server without skills:

```bash
cription-mcp-setup install claude-code
claude mcp get cription
```

### Claude Desktop

Download **[cription-0.3.1.mcpb](https://github.com/msandroid/cription-mcp/releases/download/v0.3.1/cription-0.3.1.mcpb)** and open it in Claude Desktop. Python and the Command Line Tools are still required.

Alternatively, after installing the server with uv:

```bash
cription-mcp-setup install claude-desktop
```

Restart Claude Desktop. In its developer/MCP settings, check that Cription is running.

### Codex

```bash
cription-mcp-setup install codex
codex mcp get cription
```

Optional summary skills:

```bash
codex plugin marketplace add msandroid/cription-plugins --ref v0.3.1
codex plugin add cription@cription
```

Restart Codex or start a new chat after changing plugins. The Codex plugin supplies skills; the standalone MCP registration above supplies the tools.

### Antigravity

```bash
cription-mcp-setup install antigravity
```

Restart Antigravity. Under **Customizations → Installed → MCP Servers**, check **cription — 8 tools enabled**. Older IDE installations can use `install antigravity-legacy` instead.

A plugin with the same skills is also available in [cription-plugins](https://github.com/msandroid/cription-plugins#antigravity). Use either its MCP server or the standalone registration above.

### Cursor and other stdio MCP clients

Use `cription-mcp-setup config claude-desktop` to print a standard `mcpServers` entry with absolute executable paths. Merge the `cription` entry into your client's configuration, for example `.cursor/mcp.json`. Do not replace unrelated settings.

For an on-demand Git install, use this entry instead. Replace `uvx` with the absolute output of `command -v uvx` if your GUI app cannot find it.

```json
{
  "mcpServers": {
    "cription": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/msandroid/cription-mcp@v0.3.1", "cription-mcp"]
    }
  }
}
```

## Cursor

For MCP only, run `cription-mcp-setup install cursor`. This adds absolute executable paths to `~/.cursor/mcp.json`, preserving other servers and backing up changes. Reload Cursor and check the Cription tools.

For the native Cursor plugin (MCP + three skills), clone [cription-plugins v0.4.0](https://github.com/msandroid/cription-plugins/tree/v0.4.0) and run `python3 scripts/install_cursor.py`. It installs in Cursor's documented local plugin directory and resolves uvx to an absolute path. Use either the plugin or standalone MCP to avoid duplicate tools. See the [Japanese guide](docs/INSTALL.ja.md) for installation, update and removal.

## ChatGPT: private Secure MCP Tunnel

Each user runs their **own** Cription server and OpenAI Tunnel on their Mac. The repository does not provide a shared hosted server, shared API key, or access to another user's Mac. This GitHub release is not a ChatGPT public-directory listing.

After installing Cription, run:

```bash
cription-mcp-setup chatgpt connect
```

This installs official tunnel-client v0.0.18 when missing (pinned SHA-256), opens Platform for Tunnel creation/workspace association, receives the Tunnel ID, opens a local password form for a Read + Use runtime key, starts the managed runtime, and checks readiness. The key is saved with mode 600. Existing running aliases are reused without changes. Use `--tunnel-id tunnel_YOUR_ID` to skip ID input, `--key-file /absolute/path/to/key` for an existing private key, and `--no-browser` to print instructions without opening pages. Run again after reboot; login-time autostart is not installed.

Account login, Tunnel creation/workspace association, key issuance and ChatGPT registration/consent remain account-side actions. In **ChatGPT Plugins → Add → Add custom MCP server**, choose Tunnel, your displayed ID, and No authentication for Cription, then review permissions and connect. The Tunnel itself authenticates with your runtime key. Keep the Mac awake and renew expiring keys. See the [official Tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

Try `speech_languages`, then transcription with an absolute path on your Mac. Browser attachments are not automatically local files. The earlier `key`, `init`, `doctor` and foreground `run` commands remain available.

For long transcripts, call `read_transcript` with the returned `transcriptId` and `nextOffset` until `nextOffset` is null. ChatGPT can summarize the returned text using a normal prompt; the local plugin skill files are for Claude, Codex and Antigravity.

## First-use check

Ask your AI client:

> Use Cription's speech_languages tool, then transcribe /absolute/path/to/test.m4a with locale ja-JP. Do not open any other notes or files.

A successful connection advertises **8 tools**. `speech_languages` may take longer on first use while Swift compiles. The first transcription for a locale may download Apple's speech assets. A client model quota/login error is separate from an MCP connection error.

## Tools

| Tool | Purpose |
|---|---|
| `transcribe_audio` | Local audio/video to text. Supports locale, contextual terms, timestamps and optional `save_to`. |
| `read_transcript` | Page through long generated transcripts without arbitrary file access. |
| `speech_languages` | Supported and installed Apple speech locales. |
| `list_notes` | Notes, newest first; filter by folder/date. |
| `search_notes` | Search titles, summaries, transcripts and memos. |
| `get_note` | Transcript, speaker labels already saved by the app, summary, memos and bookmarks. |
| `list_folders` | Folders and note counts. |
| `cription_status` | macOS, transcription support and local note-store availability. |

## Update, remove and troubleshoot

See [日本語ガイド](docs/INSTALL.ja.md#更新と削除) for all client paths and cleanup steps. To update the persistent install to this release:

```bash
uv tool install --force --from git+https://github.com/msandroid/cription-mcp@v0.3.1 cription-mcp
```

Restart your AI clients and Tunnel after upgrading. The setup command backs up JSON settings and preserves unrelated entries. To replace an existing Cription registration intentionally, use `install CLIENT --replace`.

## Privacy and limits

The server reads the requested audio/video and Cription's local plist/per-note JSON stores. It writes its compiled helper and transcript cache under `~/Library/Caches/cription-mcp` (or `CLAUDE_PLUGIN_DATA`), plus any explicit `save_to` destination. Setup commands also write the selected client's configuration and, when requested, the local key file. Notes remain read-only.

SpeechAnalyzer locales differ from the Cription app's additional engines. New transcriptions do not yet include speaker diarization. Audio recognition is local; transcripts and notes returned to an AI service leave the Mac through that client. Secret keys, real recordings and personal Tunnel IDs are not distributed in the release.

## Development

```bash
python3 -m unittest discover -s tests -v
uv run --no-project --with mcp --python 3.12 tests/smoke_mcp.py --audio /path/to/test.aiff
uv run --no-project --with mcp --python 3.12 tests/smoke_mcp.py --audio /path/to/test.aiff --tunnel-client /path/to/tunnel-client
uv build
npx -y @anthropic-ai/mcpb pack . dist/cription-0.3.1.mcpb
```

Smoke tests use synthetic notes. The local Tunnel test does not by itself prove a live ChatGPT conversation. On the release-validation Mac, ChatGPT and Codex completed real tool calls; Claude and Antigravity completed connection/discovery checks, with their model calls limited by account quotas. Keep versions synchronized across `pyproject.toml`, `manifest.json` and `server.py`.

## License

MIT

## Local models: Ollama and llama.cpp

Use `cription-local ollama --model qwen3:0.6b --prompt "Call speech_languages"` with a running Ollama server, or `cription-local llama-cpp --model local --prompt "Call speech_languages"` with a tool-capable `llama-server --jinja` on port 8080. The bridge executes Cription tools and returns their results to the local model. It accepts loopback HTTP IP addresses only, bypasses proxies and rejects redirects. Select a local Ollama model, not a cloud model. Use `--tools` to restrict access. See the [Japanese setup guide](docs/INSTALL.ja.md#4a-ollamallamacppローカルllm) for full commands.

ChatGPT guided setup: `cription-mcp-setup chatgpt connect` installs a verified official tunnel-client when needed, opens the setup/key pages, starts a managed runtime and verifies readiness. Account login, workspace association, key creation and ChatGPT consent still require account-side actions.
