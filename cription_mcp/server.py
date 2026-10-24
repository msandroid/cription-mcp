#!/usr/bin/env python3
"""Cription MCP server — on-device transcription and Cription notes for AI agents.

Works with Claude Code, Claude Desktop, Codex, Cursor and any MCP client (stdio).
Everything runs on this Mac: audio is transcribed with Apple SpeechAnalyzer
(the engine Cription uses for its best-scoring languages) and notes are read
from the Cription app's local storage. Nothing is sent over the network.

Tools
  transcribe_audio  audio/video file -> transcript with timestamps (macOS 26+)
  speech_languages  locales the on-device engine supports / has installed
  list_notes, search_notes, get_note, list_folders   Cription app notes (read-only)
  cription_status   what is available on this Mac

Python 3.9+ standard library only. The Swift helper (cription_speech.swift)
is compiled with swiftc on first use and cached.
"""

import datetime
import glob
import hashlib
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
import uuid

VERSION = "0.3.0"
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "cription", "version": VERSION}
APPLE_EPOCH = datetime.datetime(2001, 1, 1, tzinfo=datetime.timezone.utc)
HERE = os.path.dirname(os.path.abspath(__file__))
SWIFT_SOURCE = os.path.join(HERE, "cription_speech.swift")
INLINE_TRANSCRIPT_LIMIT = 40000

INSTRUCTIONS = (
    "Cription tools run fully on this Mac. Use transcribe_audio for any local audio or video "
    "file the user mentions (pass locale, e.g. ja-JP, when the language is known; pass domain "
    "terms to improve spelling). Use search_notes/list_notes then get_note to read the user's "
    "Cription recordings. Transcripts are private: quote only what the task needs."
)


class ToolError(Exception):
    pass


# ---------- on-device speech ----------

def cache_dir():
    base = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.expanduser("~/Library/Caches/cription-mcp")
    os.makedirs(base, exist_ok=True)
    return base


def macos_major():
    try:
        return int(platform.mac_ver()[0].split(".")[0])
    except (ValueError, IndexError):
        return 0


def speech_helper():
    """Path to the compiled helper, building it on first use."""
    if sys.platform != "darwin":
        raise ToolError("On-device transcription needs macOS 26 or later (Apple SpeechAnalyzer).")
    if macos_major() < 26:
        raise ToolError("On-device transcription needs macOS 26 or later; this Mac runs %s." % platform.mac_ver()[0])
    with open(SWIFT_SOURCE, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()[:12]
    binary = os.path.join(cache_dir(), "cription-speech-" + digest)
    if os.path.isfile(binary) and os.access(binary, os.X_OK):
        return binary
    swiftc = shutil.which("swiftc") or "/usr/bin/swiftc"
    if not os.path.exists(swiftc):
        raise ToolError("swiftc not found. Install the Xcode Command Line Tools: xcode-select --install")
    arch = "arm64" if platform.machine() == "arm64" else "x86_64"
    tmp = binary + ".tmp"
    proc = subprocess.run(
        [swiftc, "-O", "-target", "%s-apple-macos26.0" % arch, SWIFT_SOURCE, "-o", tmp],
        capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise ToolError("Building the speech helper failed:\n" + proc.stderr[-2000:])
    os.replace(tmp, binary)
    return binary


def run_helper(args, timeout):
    proc = subprocess.run([speech_helper()] + args, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise ToolError((proc.stderr or "speech helper failed").strip()[-2000:])
    try:
        return json.loads(proc.stdout)
    except ValueError:
        raise ToolError("unexpected helper output: " + proc.stdout[:500])


def tool_transcribe_audio(args):
    path = os.path.expanduser((args.get("path") or "").strip())
    if not path:
        raise ToolError("path is required")
    if not os.path.isfile(path):
        raise ToolError("file not found: %s" % path)
    helper_args = ["transcribe", path]
    if args.get("locale"):
        helper_args += ["--locale", str(args["locale"])]
    terms = [str(t).strip() for t in (args.get("terms") or []) if str(t).strip()]
    terms_file = None
    try:
        if terms:
            fd, terms_file = tempfile.mkstemp(prefix="cription-terms-", suffix=".txt")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("\n".join(terms))
            helper_args += ["--terms", terms_file]
        result = run_helper(helper_args, timeout=3600)
    finally:
        if terms_file:
            os.unlink(terms_file)

    segments = result.get("segments") or []
    if args.get("timestamps", True):
        transcript = "\n".join("[%s] %s" % (clock(s.get("start")), s.get("text", "")) for s in segments)
    else:
        transcript = result.get("text") or ""
    out = {
        "file": path,
        "engine": result.get("engine"),
        "locale": result.get("locale"),
        "duration": clock(result.get("duration")),
        "processingSeconds": round(result.get("elapsed") or 0, 1),
        "segments": len(segments),
    }
    save_to = args.get("save_to")
    if save_to or len(transcript) > INLINE_TRANSCRIPT_LIMIT:
        if not save_to:
            stem = os.path.splitext(os.path.basename(path))[0]
            save_to = os.path.join(cache_dir(), "transcripts", stem + ".txt")
        save_to = os.path.expanduser(save_to)
        os.makedirs(os.path.dirname(os.path.abspath(save_to)), exist_ok=True)
        with open(save_to, "w", encoding="utf-8") as f:
            f.write(transcript + "\n")
        out["savedTo"] = save_to
        if len(transcript) > INLINE_TRANSCRIPT_LIMIT:
            transcript_id = uuid.uuid4().hex
            directory = os.path.join(cache_dir(), "transcripts")
            os.makedirs(directory, exist_ok=True)
            with open(os.path.join(directory, transcript_id + ".txt"), "w", encoding="utf-8") as f:
                f.write(transcript)
            out.update({"transcriptId": transcript_id, "transcriptCharacters": len(transcript),
                        "nextOffset": 4000})
            out["note"] = "Transcript is long. Use read_transcript with transcriptId and nextOffset to read the rest."
            transcript = transcript[:4000] + "\n…"
    out["transcript"] = transcript
    return out


def tool_read_transcript(args):
    """Read only transcripts generated by this server, including from remote clients."""
    transcript_id = args.get("transcript_id") or ""
    if not isinstance(transcript_id, str) or len(transcript_id) != 32 or any(c not in "0123456789abcdef" for c in transcript_id):
        raise ToolError("transcript_id must be a transcriptId returned by transcribe_audio")
    offset = args.get("offset", 0)
    limit = args.get("limit", 12000)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 16000:
        raise ToolError("offset must be >= 0 and limit must be between 1 and 16000")
    path = os.path.join(cache_dir(), "transcripts", transcript_id + ".txt")
    if not os.path.isfile(path) or os.path.islink(path):
        raise ToolError("Transcript not found; run transcribe_audio again if the cache was cleared")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    end = min(offset + limit, len(text))
    return {"transcriptId": transcript_id, "offset": offset, "transcript": text[offset:end],
            "totalCharacters": len(text), "nextOffset": end if end < len(text) else None}


def tool_speech_languages(args):
    return run_helper(["locales"], timeout=120)


# ---------- Cription notes ----------


def plist_paths():
    env = os.environ.get("CRIPTION_NOTES_PLIST")
    if env:
        return [os.path.expanduser(p) for p in env.split(":") if p]
    home = os.path.expanduser("~")
    paths = [
        os.path.join(home, "Library/Containers/Cription/Data/Library/Preferences/Cription.plist"),
        os.path.join(home, "Library/Preferences/Cription.plist"),
    ]
    if os.environ.get("CRIPTION_NOTES_INCLUDE_SIM") == "1":
        paths += glob.glob(os.path.join(
            home, "Library/Developer/CoreSimulator/Devices/*/data/Containers/Data/Application/*/"
                  "Library/Preferences/Cription.plist"))
    return paths


def notes_dirs():
    """Cription 1.x later keeps one JSON file per note in Application Support/Notes."""
    env = os.environ.get("CRIPTION_NOTES_DIR")
    if env:
        return [os.path.expanduser(p) for p in env.split(":") if p]
    home = os.path.expanduser("~")
    dirs = [os.path.join(home, "Library/Containers/Cription/Data/Library/Application Support/Notes")]
    if os.environ.get("CRIPTION_NOTES_INCLUDE_SIM") == "1":
        dirs += glob.glob(os.path.join(
            home, "Library/Developer/CoreSimulator/Devices/*/data/Containers/Data/Application/*/"
                  "Library/Application Support/Notes"))
    return dirs


def source_label(path):
    if "CoreSimulator" in path:
        return "simulator:" + path.split("/Devices/")[1].split("/")[0][:8]
    if "/Containers/" in path:
        return "mac-app"
    return "mac-debug"


def note_version(note):
    modified = note.get("modifiedAt")
    return modified if isinstance(modified, (int, float)) else note.get("timestamp", 0)


def load_notes():
    notes = {}

    def keep(item, path):
        if not isinstance(item, dict) or "id" not in item:
            return
        item["_source"] = source_label(path)
        prev = notes.get(item["id"])
        if prev is None or note_version(item) >= note_version(prev):
            notes[item["id"]] = item

    for path in plist_paths():
        try:
            with open(path, "rb") as f:
                prefs = plistlib.load(f)
            raw = prefs.get("HistoryItems")
            if not raw:
                continue
            items = json.loads(raw if isinstance(raw, (bytes, str)) else bytes(raw))
        except Exception:
            continue
        for item in items:
            keep(item, path)
    for directory in notes_dirs():
        for path in glob.glob(os.path.join(directory, "*.json")):
            try:
                with open(path, "rb") as f:
                    keep(json.load(f), path)
            except Exception:
                continue
    return sorted(notes.values(), key=lambda n: n.get("timestamp", 0), reverse=True)


# ---------- formatting ----------

def note_date(note):
    ts = note.get("timestamp")
    if not isinstance(ts, (int, float)):
        return None
    return (APPLE_EPOCH + datetime.timedelta(seconds=ts)).astimezone()


def note_title(note):
    title = (note.get("title") or "").strip()
    if title:
        return title
    text = " ".join((note.get("text") or "").split())
    return (text[:40] + "…") if len(text) > 40 else (text or "(empty)")


def clock(seconds):
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return "%d:%02d:%02d" % (h, m, s) if h else "%02d:%02d" % (m, s)


def speaker_name(note, index):
    if index is None:
        return None
    names = note.get("speakerNames") or {}
    return names.get(str(index)) or "Speaker %d" % (index + 1)


def summary_row(note):
    date = note_date(note)
    return {
        "id": note["id"],
        "title": note_title(note),
        "date": date.isoformat(timespec="minutes") if date else None,
        "duration": clock(note.get("duration")),
        "language": note.get("language"),
        "folder": note.get("folder"),
        "hasSummary": bool(note.get("summary")),
        "source": note.get("_source"),
    }


def transcript_with_timestamps(note):
    segments = note.get("segments") or []
    if not segments:
        return note.get("text") or ""
    lines = []
    for seg in segments:
        who = speaker_name(note, seg.get("speaker"))
        prefix = "[%s] " % clock(seg.get("start"))
        lines.append(prefix + ("%s: " % who if who else "") + (seg.get("text") or ""))
    return "\n".join(lines)


def snippet(text, query, width=80):
    i = text.lower().find(query.lower())
    if i < 0:
        return None
    start = max(0, i - width)
    end = min(len(text), i + len(query) + width)
    return ("…" if start else "") + " ".join(text[start:end].split()) + ("…" if end < len(text) else "")


def parse_since(value):
    if not value:
        return None
    try:
        d = datetime.datetime.fromisoformat(value)
    except ValueError:
        raise ToolError("since must be an ISO date like 2026-10-01")
    if d.tzinfo is None:
        d = d.astimezone()
    return d


# ---------- tools ----------

def tool_list_notes(args):
    limit = int(args.get("limit") or 20)
    folder = args.get("folder")
    since = parse_since(args.get("since"))
    rows = []
    for note in load_notes():
        if folder and note.get("folder") != folder:
            continue
        date = note_date(note)
        if since and date and date < since:
            continue
        rows.append(summary_row(note))
        if len(rows) >= limit:
            break
    return {"count": len(rows), "notes": rows}


def tool_search_notes(args):
    query = (args.get("query") or "").strip()
    if not query:
        raise ToolError("query is required")
    limit = int(args.get("limit") or 10)
    hits = []
    for note in load_notes():
        fields = [
            ("title", note.get("title") or ""),
            ("summary", note.get("summary") or ""),
            ("transcript", note.get("text") or ""),
            ("memos", "\n".join((m.get("text") or "") for m in (note.get("memos") or []) if isinstance(m, dict))),
        ]
        for field, text in fields:
            snip = snippet(text, query)
            if snip:
                row = summary_row(note)
                row.update({"matchedIn": field, "snippet": snip})
                hits.append(row)
                break
        if len(hits) >= limit:
            break
    return {"query": query, "count": len(hits), "results": hits}


def tool_get_note(args):
    note_id = (args.get("id") or "").strip()
    notes = load_notes()
    match = []
    if note_id:
        match = ([n for n in notes if n["id"] == note_id]
                 or [n for n in notes if n["id"].lower().startswith(note_id.lower())])
    if not match:
        raise ToolError("no note with id %r (use list_notes or search_notes)" % note_id)
    note = match[0]
    result = summary_row(note)
    if args.get("timestamps", True):
        result["transcript"] = transcript_with_timestamps(note)
    else:
        result["transcript"] = note.get("text") or ""
    if note.get("summary"):
        result["summary"] = note["summary"]
        result["checkedItems"] = note.get("checkedItems") or []
    memos = [m.get("text") for m in (note.get("memos") or []) if isinstance(m, dict) and m.get("text")]
    if memos:
        result["memos"] = memos
    if note.get("bookmarks"):
        result["bookmarks"] = [clock(b) for b in note["bookmarks"]]
    if note.get("speakerNames"):
        result["speakers"] = note["speakerNames"]
    result["model"] = note.get("model")
    return result


def tool_list_folders(args):
    counts = {}
    for note in load_notes():
        key = note.get("folder") or "(none)"
        counts[key] = counts.get(key, 0) + 1
    return {"folders": [{"name": k, "notes": v} for k, v in sorted(counts.items())]}


def tool_cription_status(args):
    notes_sources = [{"path": p, "exists": os.path.isfile(p)} for p in plist_paths()]
    notes_sources += [{"path": d, "exists": os.path.isdir(d)} for d in notes_dirs()]
    status = {
        "version": VERSION,
        "macOS": platform.mac_ver()[0] or None,
        "onDeviceTranscription": sys.platform == "darwin" and macos_major() >= 26,
        "swiftc": bool(shutil.which("swiftc") or os.path.exists("/usr/bin/swiftc")),
        "criptionMacApp": bool(glob.glob("/Applications/Cription*.app")),
        "noteSources": notes_sources,
        "notes": len(load_notes()),
    }
    return status


READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}

TOOLS = [
    {
        "name": "read_transcript",
        "description": "Read the next part of a long transcript generated by transcribe_audio. "
                       "Use its transcriptId and nextOffset; works without local file access.",
        "inputSchema": {"type": "object", "required": ["transcript_id"], "properties": {
            "transcript_id": {"type": "string", "description": "transcriptId returned by transcribe_audio."},
            "offset": {"type": "integer", "minimum": 0, "description": "Character offset; use nextOffset from the previous response."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 16000, "description": "Maximum characters (default 12000)."},
        }},
        "annotations": READ_ONLY,
        "handler": tool_read_transcript,
    },
    {
        "name": "transcribe_audio",
        "description": "Transcribe a local audio or video file on-device with Apple SpeechAnalyzer (macOS 26+). "
                       "Returns the transcript with [mm:ss] timestamps. Audio is processed locally; results are returned to the AI client.",
        "inputSchema": {"type": "object", "required": ["path"], "properties": {
            "path": {"type": "string", "description": "Absolute path to the file (wav, m4a, mp3, aiff, caf, mp4, mov, …)."},
            "locale": {"type": "string", "description": "Spoken language, e.g. ja-JP, en-US, zh-CN. Default: the Mac's locale."},
            "terms": {"type": "array", "items": {"type": "string"},
                      "description": "Names and jargon to spell correctly (contextual vocabulary)."},
            "timestamps": {"type": "boolean", "description": "Prefix each segment with [mm:ss] (default true)."},
            "save_to": {"type": "string", "description": "Also write the transcript to this file path."},
        }},
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
        "handler": tool_transcribe_audio,
    },
    {
        "name": "speech_languages",
        "description": "List the locales the on-device speech engine supports and which are already installed.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": READ_ONLY,
        "handler": tool_speech_languages,
    },
    {
        "name": "list_notes",
        "description": "List the user's Cription notes (newest first) with id, title, date, duration, language and folder.",
        "inputSchema": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "Max notes to return (default 20)."},
            "folder": {"type": "string", "description": "Only notes in this folder."},
            "since": {"type": "string", "description": "Only notes recorded on/after this ISO date, e.g. 2026-10-01."},
        }},
        "annotations": READ_ONLY,
        "handler": tool_list_notes,
    },
    {
        "name": "search_notes",
        "description": "Full-text search over Cription note titles, summaries, transcripts and memos. Returns matches with a snippet.",
        "inputSchema": {"type": "object", "required": ["query"], "properties": {
            "query": {"type": "string", "description": "Case-insensitive substring (works for Japanese/Chinese)."},
            "limit": {"type": "integer", "description": "Max results (default 10)."},
        }},
        "annotations": READ_ONLY,
        "handler": tool_search_notes,
    },
    {
        "name": "get_note",
        "description": "Get one Cription note: transcript with timestamps and speaker names, summary, to-dos, memos, bookmarks.",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {
            "id": {"type": "string", "description": "Note id from list_notes/search_notes (a unique prefix is enough)."},
            "timestamps": {"type": "boolean", "description": "Include per-segment timestamps and speakers (default true)."},
        }},
        "annotations": READ_ONLY,
        "handler": tool_get_note,
    },
    {
        "name": "list_folders",
        "description": "List Cription note folders with how many notes each holds.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": READ_ONLY,
        "handler": tool_list_folders,
    },
    {
        "name": "cription_status",
        "description": "Report what this Mac supports: macOS version, on-device transcription, Cription app and note sources.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": READ_ONLY,
        "handler": tool_cription_status,
    },
]
TOOL_BY_NAME = {t["name"]: t for t in TOOLS}


# ---------- JSON-RPC over stdio ----------

def reply(msg_id, result=None, error=None):
    out = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(msg):
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        reply(None, error={"code": -32600, "message": "invalid request"})
        return
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}
    if not isinstance(params, dict):
        if msg_id is not None:
            reply(msg_id, error={"code": -32602, "message": "params must be an object"})
        return
    if msg_id is None:  # notifications
        return
    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        reply(msg_id, {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": INSTRUCTIONS,
        })
    elif method == "ping":
        reply(msg_id, {})
    elif method == "tools/list":
        reply(msg_id, {"tools": [{k: v for k, v in t.items() if k != "handler"} for t in TOOLS]})
    elif method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            reply(msg_id, error={"code": -32602, "message": "name must be a string and arguments must be an object"})
            return
        tool = TOOL_BY_NAME.get(name)
        if tool is None:
            reply(msg_id, error={"code": -32602, "message": "unknown tool %r" % params.get("name")})
            return
        try:
            data = tool["handler"](arguments)
            text = json.dumps(data, ensure_ascii=False, indent=1)
            reply(msg_id, {"content": [{"type": "text", "text": text}], "structuredContent": data, "isError": False})
        except (ToolError, subprocess.TimeoutExpired) as e:
            reply(msg_id, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        except Exception as e:
            reply(msg_id, {"content": [{"type": "text", "text": "%s: %s" % (type(e).__name__, e)}], "isError": True})
    elif method in ("resources/list", "prompts/list"):
        reply(msg_id, {method.split("/")[0]: []})
    else:
        reply(msg_id, error={"code": -32601, "message": "method not found: %s" % method})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply(None, error={"code": -32700, "message": "parse error"})
            continue
        for item in (msg if isinstance(msg, list) else [msg]):
            try:
                handle(item)
            except Exception as e:
                reply(item.get("id") if isinstance(item, dict) else None,
                      error={"code": -32603, "message": str(e)})


if __name__ == "__main__":
    main()
