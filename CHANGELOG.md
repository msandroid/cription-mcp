# Changelog

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
