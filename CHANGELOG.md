# Changelog

## 0.4.0

- Add per-client authenticated Streamable HTTP MCP for Notion Custom Agents and Manus, with tool allowlists, loopback-only key display and optional Cloudflare Quick Tunnel.
- Add Notion page export CLI, local token setup, dry-run, Unicode-safe blocks and bounded write batches.
- Disable arbitrary `save_to` writes over remote MCP; preserve existing stdio behavior.
- Add HTTP security/protocol tests, official SDK smoke test and Japanese setup guide with account-side verification limits.

## v0.3.1 — 2026-10-24

- Add Cursor MCP config/install commands using ~/.cursor/mcp.json, preserving unrelated settings with backups and idempotent installation.
- Document native Cursor plugin and standalone MCP setup.

## v0.3.0 — 2026-10-24

- Add `cription-local` for Ollama native tool calling and llama.cpp OpenAI-compatible tool calling, sharing all eight Cription tools. Loopback-only transport, disabled proxies/redirects, tool allowlist and bounded tool rounds.
- Add guided `chatgpt connect`: checksum-verified official CLI installation, browser-assisted key storage, managed runtime connection/readiness and safe reuse of existing running aliases.
- Document local model setup and the remaining account-side ChatGPT steps.

## v0.2.0 — 2026-10-24

- Add persistent-install setup commands for Claude Code, Claude Desktop, Codex and Antigravity, preserving unrelated client configuration and creating backups.
- Support private ChatGPT connections through the official OpenAI Secure MCP Tunnel.
- Add a one-time loopback password form to save runtime keys locally with mode 600 without logging their contents.
- Add `read_transcript` to retrieve long transcriptions in pages from clients without local file access.
- Read current Cription per-note JSON stores in addition to older plist stores.
- Handle malformed JSON-RPC messages without terminating the server.
- Publish a Claude Desktop `.mcpb`, Python wheel, source distribution and checksums.
- Add an English quick start, full Japanese installation/update/removal guide, unit tests and official-SDK smoke tests.

The server still uses the Python standard library only. New audio recognition requires macOS 26+ and Xcode Command Line Tools. Tool results are returned to the connected AI service.

## v0.1.0

Initial standalone MCP server and Claude Desktop bundle.
