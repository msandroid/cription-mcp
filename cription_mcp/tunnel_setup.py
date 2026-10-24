"""Guided, repeatable setup using OpenAI's managed native runtime."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import tempfile
import time
import urllib.request
import webbrowser
import zipfile

VERSION = "v0.0.18"
DIGESTS = {"arm64": "d4f165712e9599322191b8a0c2c7f3b91eabfa014fe6520ef6a0e49709782371",
           "x86_64": "400a3b5199838196eda6a09d2306cb28ad394fe5a27683742eaa392b43896b87"}


def install_binary():
    machine = platform.machine()
    if platform.system() != "Darwin" or machine not in DIGESTS:
        raise ValueError("Automatic tunnel-client installation supports macOS arm64/x86_64")
    arch = "arm64" if machine == "arm64" else "amd64"
    name = "tunnel-client-runtime-cloudflared-%s-darwin-%s.zip" % (VERSION, arch)
    url = "https://github.com/openai/tunnel-client/releases/download/%s/%s" % (VERSION, name)
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != DIGESTS[machine]:
        raise ValueError("Official tunnel-client archive checksum mismatch")
    root = Path.home() / ".local/share/cription-mcp"
    root.mkdir(parents=True, exist_ok=True)
    destination = root / ("tunnel-client-" + VERSION)
    if not destination.exists():
        with tempfile.TemporaryDirectory(dir=str(root)) as temporary:
            stage = Path(temporary) / "bundle"
            stage.mkdir()
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for member in archive.infolist():
                    if member.is_dir() or Path(member.filename).name != member.filename:
                        raise ValueError("Unexpected archive path")
                    (stage / member.filename).write_bytes(archive.read(member))
            for executable in ("tunnel-client-runtime-cloudflared", "cloudflared"):
                (stage / executable).chmod(0o755)
            stage.rename(destination)
    return str(destination / "tunnel-client-runtime-cloudflared")


def status(binary, alias):
    result = subprocess.run([binary, "runtimes", "status", alias, "--json"], capture_output=True, text=True, timeout=30)
    if result.returncode:
        return {}
    return json.loads(result.stdout)


def connect(args):
    from .setup import server_config, tunnel_binary
    from .key_setup import serve
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.profile):
        raise ValueError("Use letters, digits, underscores or hyphens for --profile")
    try:
        binary = tunnel_binary()
    except ValueError:
        print("Installing verified official tunnel-client %s…" % VERSION, flush=True)
        binary = install_binary()
    alias = args.profile
    current = status(binary, alias)
    tunnel_id = args.tunnel_id or os.environ.get("CONTROL_PLANE_TUNNEL_ID") or current.get("tunnel_id")
    if not tunnel_id:
        url = "https://platform.openai.com/settings/organization/tunnels"
        print("Create a Tunnel and link your ChatGPT workspace: " + url, flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        if not os.isatty(0):
            raise ValueError("Provide --tunnel-id tunnel_… after creating a Tunnel")
        tunnel_id = input("Tunnel ID (not an API key): ").strip()
    if not re.fullmatch(r"tunnel_[A-Za-z0-9_-]+", tunnel_id):
        raise ValueError("Invalid Tunnel ID")
    if current.get("tunnel_id") and current["tunnel_id"] != tunnel_id:
        raise ValueError("This alias belongs to another Tunnel; choose a different --profile")
    if not (current.get("ready") and current.get("process_running")):
        path = Path(args.key_file or Path.home() / ".config/cription-mcp/runtime-key").expanduser().resolve()
        if not path.exists():
            print("Create a runtime key with only Tunnels Read + Use, then save it in the local form.", flush=True)
            if not args.no_browser:
                webbrowser.open("https://platform.openai.com/api-keys")
            serve(path, open_browser=not args.no_browser)
        if not path.is_file() or path.stat().st_size == 0 or path.stat().st_mode & 0o077:
            raise ValueError("Runtime key must be a nonempty private file (chmod 600): %s" % path)
        config = server_config()
        command = [binary, "runtimes", "connect", "--alias", alias, "--profile", alias + "-managed",
                   "--tunnel-id", tunnel_id, "--runtime-api-key", "file:" + str(path),
                   "--mcp-command", shlex.join([config["command"]] + config["args"]), "--json"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if result.returncode:
            # CLI output can contain diagnostics and credential references; keep it out of logs.
            raise ValueError("Managed runtime connection failed; inspect 'tunnel-client runtimes status %s' locally" % alias)
        deadline = time.monotonic() + args.wait
        while True:
            current = status(binary, alias)
            if current.get("ready") and current.get("process_running"):
                break
            if time.monotonic() >= deadline:
                raise ValueError("Tunnel is not ready yet. Check workspace association, key permissions and expiry; rerun connect")
            time.sleep(2)
    print("Tunnel ready: %s\nManaged runtime: %s (continues after this command exits)" % (tunnel_id, alias))
    print("ChatGPT: Plugins → Add → Add custom MCP server\nName: Cription\nConnection: Tunnel\nTunnel ID: %s\nAuthentication: No authentication\nReview permissions and connect. Keep this Mac awake; rerun connect after reboot." % tunnel_id)
    print("Status: %s runtimes status %s\nStop: %s runtimes stop %s" % (shlex.quote(binary), alias, shlex.quote(binary), alias))
    if not args.no_browser:
        webbrowser.open("https://chatgpt.com/plugins")
    return 0
