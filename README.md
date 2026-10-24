# Cription MCP

On-device audio/video transcription and read-only access to your Cription notes, for **Claude, Codex, Antigravity, ChatGPT and other MCP clients**.

**Current release: [v0.2.0](https://github.com/msandroid/cription-mcp/releases/tag/v0.2.0).** [日本語のインストール手順](docs/INSTALL.ja.md) · [Plugins and skills](https://github.com/msandroid/cription-plugins)

Audio recognition runs on your Mac using Apple SpeechAnalyzer. Returned transcripts and notes are shared with your AI client and are subject to that service's data policies. The server has no Python runtime dependencies.

## Requirements

- **macOS 26+** for transcription. Notes can be read on older macOS.
- Python 3.9+ and Xcode Command Line Tools (`xcode-select --install`). The Swift helper is compiled on the first transcription or language query.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for the commands below. You can also install the wheel from Releases with `pip`.
- The Cription Mac app and locally stored notes for note access. Transcription works without the app. iPhone notes must first be available on the Mac.

## Install the server once

```bash
uv tool install --from git+https://github.com/msandroid/cription-mcp@v0.2.0 cription-mcp
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

Download **[cription-0.2.0.mcpb](https://github.com/msandroid/cription-mcp/releases/download/v0.2.0/cription-0.2.0.mcpb)** and open it in Claude Desktop. Python and the Command Line Tools are still required.

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
codex plugin marketplace add msandroid/cription-plugins --ref v0.3.0
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
      "args": ["--from", "git+https://github.com/msandroid/cription-mcp@v0.2.0", "cription-mcp"]
    }
  }
}
```

## ChatGPT: private Secure MCP Tunnel

Each user runs their **own** Cription server and OpenAI Tunnel on their Mac. The repository does not provide a shared hosted server, shared API key, or access to another user's Mac. This GitHub release is not a ChatGPT public-directory listing.

1. Install the Cription server as above and the official [OpenAI tunnel-client](https://github.com/openai/tunnel-client/releases/latest). See the [official Tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).
2. Create or reuse a tunnel in [Platform tunnel settings](https://platform.openai.com/settings/organization/tunnels) and associate it with your ChatGPT workspace. Creating a tunnel needs **Tunnels Read + Manage**. Connecting it needs the applicable ChatGPT workspace permissions.
3. Create a **runtime key** with **Tunnels Read + Use**. Do not use an admin key. Save it without terminal echo using the one-time local form:

```bash
cription-mcp-setup chatgpt key
```

Open the printed loopback URL on the same Mac and enter the runtime key. The form closes after saving it to `~/.config/cription-mcp/runtime-key` with mode 600. Existing key files are never overwritten. The key is not written to logs or this repository. To choose another destination, use `--key-file /absolute/path/to/key`.

4. Configure and validate your tunnel. Replace `tunnel_YOUR_ID` with your own ID:

```bash
cription-mcp-setup chatgpt init --tunnel-id tunnel_YOUR_ID --key-file "$HOME/.config/cription-mcp/runtime-key"
cription-mcp-setup chatgpt doctor --key-file "$HOME/.config/cription-mcp/runtime-key"
cription-mcp-setup chatgpt run --key-file "$HOME/.config/cription-mcp/runtime-key"
```

Keep the foreground process running for discovery and every tool call. The MCP server does not listen on a public port. If you prefer environment-based secrets, set `CONTROL_PLANE_API_KEY` locally and omit `--key-file` from **all three commands**, including `init`. Choose a separate profile with `--profile` if one already exists; `init` does not silently replace profiles.

For a managed local runtime, the official CLI also supports `tunnel-client runtimes connect`; consult `tunnel-client help quickstart` and verify `runtimes status` before relying on it. Keep the runtime key valid and renew it before its expiration.

5. In ChatGPT **Plugins → Add → Add custom MCP server**, enter a name, choose **Tunnel**, select your tunnel ID, and choose **No authentication** for the local Cription MCP server. The Tunnel itself uses your runtime key and workspace permissions. Review the warning, create the private plugin and connect it.
6. Choose **Try in chat**, then ask it to call `speech_languages`. Test transcription using an **absolute path on your Mac**, such as `/Users/yourname/Downloads/meeting.m4a`. Uploading a browser attachment does not automatically put that file on the Mac.

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
uv tool install --force --from git+https://github.com/msandroid/cription-mcp@v0.2.0 cription-mcp
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
npx -y @anthropic-ai/mcpb pack . dist/cription-0.2.0.mcpb
```

Smoke tests use synthetic notes. The local Tunnel test does not by itself prove a live ChatGPT conversation. On the release-validation Mac, ChatGPT and Codex completed real tool calls; Claude and Antigravity completed connection/discovery checks, with their model calls limited by account quotas. Keep versions synchronized across `pyproject.toml`, `manifest.json` and `server.py`.

## License

MIT
