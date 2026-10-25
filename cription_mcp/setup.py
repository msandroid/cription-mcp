"""Install local client connections and manage Cription's private ChatGPT tunnel."""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile


CLIENT_PATHS = {
    "gemini": ".gemini/settings.json",
    "cursor": ".cursor/mcp.json",
    "antigravity": ".gemini/config/mcp_config.json",
    "antigravity-legacy": ".gemini/antigravity/mcp_config.json",
    "claude-desktop": "Library/Application Support/Claude/claude_desktop_config.json",
    "claude-code": ".claude.json",
}


def server_config():
    # Absolute paths also work in GUI apps with a minimal PATH and from a wheel.
    return {"command": sys.executable,
            "args": [str(Path(__file__).resolve().with_name("server.py"))]}


def install_json(path, config, replace=False):
    path = Path(path).expanduser()
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
        raise ValueError("Expected a JSON object containing an mcpServers object: %s" % path)
    servers = data.setdefault("mcpServers", {})
    if servers.get("cription") == config:
        return None
    if "cription" in servers and not replace:
        raise ValueError("Cription is already configured; use --replace to update it: %s" % path)
    servers["cription"] = config
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = path.with_name(path.name + ".cription-" + stamp + ".bak")
        shutil.copy2(path, backup)
        backup.chmod(0o600)
    fd, temporary = tempfile.mkstemp(prefix=".cription-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return backup


def tunnel_binary():
    binary = shutil.which("tunnel-client")
    if not binary:
        local = Path.home() / ".local/bin/tunnel-client"
        if local.is_file() and os.access(local, os.X_OK):
            binary = str(local)
    if not binary:
        managed = Path.home() / ".local/share/cription-mcp/tunnel-client-v0.0.18/tunnel-client-runtime-cloudflared"
        if managed.is_file() and os.access(managed, os.X_OK):
            binary = str(managed)
    if not binary:
        raise ValueError("Install OpenAI tunnel-client from https://github.com/openai/tunnel-client/releases/latest")
    return binary


def tunnel_command(args):
    binary = tunnel_binary()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.profile):
        raise ValueError("Profile names may contain only letters, numbers, underscores and hyphens")
    key_file = getattr(args, "key_file", None)
    key_ref = "env:CONTROL_PLANE_API_KEY"
    if key_file:
        path = Path(key_file).expanduser().resolve()
        if not path.is_file() or not path.stat().st_size:
            raise ValueError("Runtime key file does not exist or is empty: %s" % path)
        if path.stat().st_mode & 0o077:
            raise ValueError("Runtime key file must be private; run chmod 600 on it: %s" % path)
        key_ref = "file:" + str(path)
    if args.action == "init":
        tunnel_id = args.tunnel_id or os.environ.get("CONTROL_PLANE_TUNNEL_ID", "")
        if not re.fullmatch(r"tunnel_[A-Za-z0-9_-]+", tunnel_id):
            raise ValueError("Set --tunnel-id (or CONTROL_PLANE_TUNNEL_ID) to your existing OpenAI tunnel ID")
        config = server_config()
        command = shlex.join([config["command"]] + config["args"])
        return [binary, "init", "--sample", "sample_mcp_stdio_local", "--profile", args.profile,
                "--tunnel-id", tunnel_id, "--mcp-command", command,
                "--control-plane-api-key-ref", key_ref,
                "--health-listen-addr", "127.0.0.1:0"]
    if not key_file and not os.environ.get("CONTROL_PLANE_API_KEY"):
        raise ValueError("Set CONTROL_PLANE_API_KEY locally or use --key-file with a runtime key with Tunnels Read + Use; never paste keys into chat")
    command = [binary, args.action, "--profile", args.profile]
    if key_file:
        command += ["--control-plane.api-key", key_ref]
    if args.action == "doctor":
        command.append("--explain")
    return command


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("config", "install"):
        p = sub.add_parser(name, help="Print or install a local MCP client configuration")
        p.add_argument("client", choices=list(CLIENT_PATHS) + ["codex"])
        if name == "install":
            p.add_argument("--replace", action="store_true", help="Replace an existing Cription entry (JSON files are backed up)")
    p = sub.add_parser("chatgpt", help="Configure or run OpenAI Secure MCP Tunnel; no public listener")
    p.add_argument("action", choices=["connect", "key", "init", "doctor", "run"])
    p.add_argument("--profile", default="cription")
    p.add_argument("--tunnel-id", help="Existing tunnel ID; also reads CONTROL_PLANE_TUNNEL_ID")
    p.add_argument("--key-file", help="Private (chmod 600) runtime key file; only its path is passed to tunnel-client")
    p.add_argument("--no-browser", action="store_true", help="Print URLs without opening a browser")
    p.add_argument("--wait", type=int, default=60, help="Wait up to this many seconds for managed runtime readiness")
    args = parser.parse_args(argv)
    try:
        if args.command == "chatgpt":
            if args.action == "connect":
                try:
                    from .tunnel_setup import connect
                except ImportError:
                    raise ValueError("Run as an installed command or python -m cription_mcp.setup")
                if not 0 <= args.wait <= 600:
                    raise ValueError("--wait must be 0–600 seconds")
                return connect(args)
            if args.action == "key":
                try:
                    from .key_setup import serve
                except ImportError:  # Direct source-checkout invocation.
                    from key_setup import serve
                return serve(args.key_file or str(Path.home() / ".config/cription-mcp/runtime-key"))
            return subprocess.call(tunnel_command(args))
        config = server_config()
        if args.command == "config":
            if args.client == "codex":
                print("[mcp_servers.cription]\ncommand = %s\nargs = %s" %
                      (json.dumps(config["command"]), json.dumps(config["args"])))
            else:
                print(json.dumps({"mcpServers": {"cription": config}}, indent=2))
            return 0
        if args.client == "codex":
            binary = shutil.which("codex")
            if not binary:
                raise ValueError("codex is not on PATH; use 'config codex' for a manual configuration")
            existing = subprocess.run([binary, "mcp", "get", "cription", "--json"], capture_output=True, text=True)
            if existing.returncode == 0:
                transport = json.loads(existing.stdout).get("transport", {})
                if all(transport.get(k) == v for k, v in config.items()):
                    print("Cription is already configured for Codex")
                    return 0
                if not args.replace:
                    raise ValueError("Cription is already configured for Codex; use --replace to update it")
            path = Path.home() / ".codex/config.toml"
            if path.exists():
                backup = path.with_name(path.name + ".cription-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".bak")
                shutil.copy2(path, backup)
                backup.chmod(0o600)
            return subprocess.call([binary, "mcp", "add", "cription", "--", config["command"]] + config["args"])
        path = Path.home() / CLIENT_PATHS[args.client]
        backup = install_json(path, config, args.replace)
        print("Configured %s: %s" % (args.client, path))
        if backup:
            print("Backup: %s" % backup)
        return 0
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print("cription-mcp-setup: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
