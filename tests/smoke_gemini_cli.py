"""Test an already configured Gemini CLI; requires the user's own authentication.

python tests/smoke_gemini_cli.py --model YOUR_MODEL --log /private/test.log
Only speech_languages is approved. No notes or recordings are read.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--timeout', type=int, default=90)
    parser.add_argument('--log', required=True)
    args = parser.parse_args()
    binary = shutil.which('gemini')
    if not binary:
        raise SystemExit('Install Gemini CLI first')
    path = Path(args.log).expanduser()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with tempfile.TemporaryDirectory(prefix='cription-gemini-test-') as folder, os.fdopen(fd, 'w') as log:
        process = subprocess.Popen([binary, '--skip-trust', '--model', args.model,
            '--allowed-mcp-server-names', 'cription', '--allowed-tools', 'mcp_cription_speech_languages',
            '--output-format', 'stream-json', '--prompt',
            'Call Cription speech_languages exactly once and report whether Japanese is supported. Do not read notes or files.'],
            cwd=folder, stdout=log, stderr=log, start_new_session=True)
        try:
            code = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            code = 124
    output = path.read_text()
    for name in ('GEMINI_API_KEY', 'GOOGLE_API_KEY'):
        if os.environ.get(name):
            output = output.replace(os.environ[name], '[REDACTED]')
    path.write_text(output)
    events = []
    for line in output.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    calls = [e for e in events if e.get('type') == 'tool_use' and 'speech_languages' in e.get('tool_name', e.get('name', ''))]
    results = [e for e in events if e.get('type') == 'tool_result' and e.get('status') == 'success']
    success = code == 0 and bool(calls) and bool(results)
    print(json.dumps({'exit_code': code, 'model': args.model, 'speech_languages_called': bool(calls),
                      'successful_tool_result': bool(results), 'verified': success, 'private_log': str(path)}))
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
