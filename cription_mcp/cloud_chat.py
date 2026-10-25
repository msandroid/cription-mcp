"""Call Grok or Gemini API with Cription's authenticated remote MCP."""
import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

from . import key_setup, remote

PROVIDERS = {
    'grok': {'endpoint': 'https://api.x.ai/v1/responses', 'env': ('XAI_API_KEY',), 'key': 'xai-api-key'},
    'gemini': {'endpoint': 'https://generativelanguage.googleapis.com/v1beta/interactions',
               'env': ('GEMINI_API_KEY', 'GOOGLE_API_KEY'), 'key': 'gemini-api-key'},
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError('API redirects are disabled')


def key_path(provider):
    return Path.home() / '.config/cription-mcp' / PROVIDERS[provider]['key']


def api_key(provider, explicit=None):
    value = next((os.environ[name] for name in PROVIDERS[provider]['env'] if os.environ.get(name)), '')
    path = Path(explicit).expanduser() if explicit else key_path(provider)
    if explicit or (not value and path.exists()):
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
            raise ValueError('API key file must be a private regular file (chmod 600)')
        value = path.read_text().strip()
    if not value or any(c.isspace() for c in value):
        raise ValueError('Set %s locally or run --setup-key; never paste keys into chat' % PROVIDERS[provider]['env'][0])
    return value


def payload(provider, model, prompt, url, profile, tools=None, max_tokens=512):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or parsed.query or parsed.fragment or parsed.path != '/mcp':
        raise ValueError('MCP URL must be an HTTPS /mcp endpoint without credentials, query or fragment')
    selected = tools or profile['tools']
    if not selected or any(name not in profile['tools'] for name in selected):
        raise ValueError('Requested tools must be enabled in the selected remote profile')
    header = {'Authorization': 'Bearer ' + profile['token']}
    if provider == 'grok':
        return {'model': model, 'input': prompt, 'max_output_tokens': max_tokens,
                'tools': [{'type': 'mcp', 'server_label': 'cription', 'server_url': url,
                           'headers': header, 'allowed_tools': selected}]}
    return {'model': model, 'input': prompt, 'store': False,
            'generation_config': {'max_output_tokens': max_tokens},
            'tools': [{'type': 'mcp_server', 'name': 'cription', 'url': url,
                       'headers': header, 'allowed_tools': [{'mode': 'auto', 'tools': selected}]}]}


def request(provider, body, key, timeout=90):
    headers = {'Content-Type': 'application/json'}
    headers.update({'Authorization': 'Bearer ' + key} if provider == 'grok' else {'x-goog-api-key': key})
    req = urllib.request.Request(PROVIDERS[provider]['endpoint'], json.dumps(body).encode('utf-8'), headers, method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # Provider error bodies may echo credentials or private prompt content.
        raise ValueError('%s API returned HTTP %s; check authentication, model access, quota and MCP reachability. No automatic retry was made.' % (provider, error.code)) from None


def public_result(provider, result):
    """Return text plus tool-call evidence; never echo the original request headers."""
    steps = result.get('output', []) if provider == 'grok' else result.get('steps', result.get('outputs', []))
    text, calls, results = [], [], []
    for step in steps:
        kind = step.get('type', '')
        if kind in ('text', 'text_output') and isinstance(step.get('text'), str):
            text.append(step['text'])
        if kind in ('message', 'model_output'):
            for content in step.get('content', []):
                if content.get('type') in ('output_text', 'text') and isinstance(content.get('text'), str):
                    text.append(content['text'])
        if kind in ('mcp_call', 'mcp_tool_call', 'mcp_server_tool_call', 'function_call'):
            calls.append({'type': kind, 'name': step.get('name') or step.get('tool_name'),
                          'status': step.get('status'), 'has_error': bool(step.get('error'))})
        if kind == 'function_result':
            results.append({'name': step.get('name'), 'has_error': bool(step.get('is_error'))})
    return {'provider': provider, 'id': result.get('id'), 'status': result.get('status'),
            'text': '\n'.join(text), 'tool_calls': calls, 'tool_results': results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('provider', choices=PROVIDERS)
    parser.add_argument('--setup-key', action='store_true', help='Save an existing API key through a local password form')
    parser.add_argument('--key-file', help='Private API key file; environment or managed key file used otherwise')
    parser.add_argument('--url', help='HTTPS /mcp URL printed by cription-mcp-remote serve')
    parser.add_argument('--model', help='Explicit provider model ID; no implicit model or billing choice')
    parser.add_argument('--prompt')
    parser.add_argument('--tools', nargs='+')
    parser.add_argument('--max-tokens', type=int, default=512)
    parser.add_argument('--timeout', type=int, default=90, help='API request timeout in seconds (10–600)')
    parser.add_argument('--dry-run', action='store_true', help='Validate and print a redacted request without contacting the API')
    args = parser.parse_args(argv)
    try:
        if args.setup_key:
            return key_setup.serve(args.key_file or key_path(args.provider), open_browser=True, kind=args.provider)
        if not args.url or not args.model or not args.prompt:
            raise ValueError('Set --url, --model and --prompt')
        if not 10 <= args.timeout <= 600:
            raise ValueError('--timeout must be between 10 and 600')
        if not 1 <= args.max_tokens <= 8192:
            raise ValueError('--max-tokens must be between 1 and 8192')
        profile = remote.load_profile('grok' if args.provider == 'grok' else 'gemini-api')
        body = payload(args.provider, args.model, args.prompt, args.url, profile, args.tools, args.max_tokens)
        if args.dry_run:
            body['tools'][0]['headers']['Authorization'] = 'Bearer [REDACTED]'
            print(json.dumps({'endpoint': PROVIDERS[args.provider]['endpoint'], 'request': body}, ensure_ascii=False, indent=2).replace(profile['token'], '[REDACTED]'))
            return 0
        key = api_key(args.provider, args.key_file)
        result = public_result(args.provider, request(args.provider, body, key, args.timeout))
        # A remote server's output could include a secret. Redact known connection
        # and API credentials before returning even the selected response fields.
        output = json.dumps(result, ensure_ascii=False)
        for secret in (profile['token'], key):
            output = output.replace(secret, '[REDACTED]')
        print(output)
        return 1 if (result.get('status') in ('failed', 'cancelled', 'canceled') or
                     any(item['has_error'] for item in result['tool_calls'] + result['tool_results'])) else 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print('cription-cloud: %s' % error, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
