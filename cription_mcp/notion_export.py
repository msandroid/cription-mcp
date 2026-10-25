"""Export a chosen Cription note or UTF-8 transcript to a Notion page."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
import uuid

from . import server
from .remote import private_json
from . import key_setup


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError('Notion API redirects are disabled')


def note_markdown(note):
    parts = ['Source: Cription note ' + str(note['id'])]
    if note.get('summary'):
        parts += ['## Summary', str(note['summary'])]
    if note.get('transcript'):
        parts += ['## Transcript', str(note['transcript'])]
    if note.get('memos'):
        parts += ['## Memos'] + [str(value) for value in note['memos']]
    return '\n\n'.join(parts)


def rich_text(text):
    # Conservative chunks also fit Notion's 2,000-character limit with emoji.
    return [{'type': 'text', 'text': {'content': text[i:i+900]}} for i in range(0, len(text), 900)]


def blocks(markdown):
    result = []
    for line in markdown.splitlines():
        if not line.strip():
            continue
        kind, content, extra = 'paragraph', line, {}
        heading = re.match(r'^(#{1,3})\s+(.+)$', line)
        todo = re.match(r'^- \[([ xX])\]\s*(.*)$', line)
        if heading:
            kind, content = 'heading_' + str(len(heading[1])), heading[2]
        elif todo:
            kind, content, extra = 'to_do', todo[2], {'checked': todo[1].lower() == 'x'}
        elif line.startswith('- '):
            kind, content = 'bulleted_list_item', line[2:]
        elif line.startswith('> '):
            kind, content = 'quote', line[2:]
        # Keep each block's rich-text array small; long transcript lines become
        # sequential paragraphs without losing any characters.
        for offset in range(0, max(1, len(content)), 9000):
            part = content[offset:offset+9000]
            result.append({'object': 'block', 'type': kind, kind: dict(rich_text=rich_text(part), **extra)})
    return result


def request(method, path, body, token):
    req = urllib.request.Request('https://api.notion.com/v1/' + path, json.dumps(body).encode('utf-8'),
                                 {'Authorization': 'Bearer ' + token, 'Notion-Version': '2022-06-28',
                                  'Content-Type': 'application/json'}, method=method)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise ValueError('Notion API returned HTTP %s; check token, shared parent page and permissions' % error.code) from None


def export_page(parent, title, markdown, token):
    parent = str(uuid.UUID(parent.replace('-', '')))
    children = blocks(markdown)
    if len(title.encode('utf-16-le')) // 2 > 2000:
        raise ValueError('Notion title exceeds 2,000 characters; choose a shorter --title')
    batches, batch, size = [], [], 0
    for block in children:
        weight = len(json.dumps(block).encode('utf-8')) + 2
        if batch and (len(batch) == 100 or size + weight > 450000):
            batches.append(batch)
            batch, size = [], 0
        batch.append(block)
        size += weight
    if batch:
        batches.append(batch)
    body = {'parent': {'page_id': parent}, 'properties': {'title': {'type': 'title', 'title': rich_text(title)}},
            'children': batches[0] if batches else []}
    page = request('POST', 'pages', body, token)
    try:
        for batch in batches[1:]:
            request('PATCH', 'blocks/' + page['id'] + '/children', {'children': batch}, token)
    except (ValueError, OSError):
        raise ValueError('Page was created but not all content was saved: %s. Inspect it before retrying to avoid duplicates' % page.get('url', page['id'])) from None
    return {'id': page['id'], 'url': page.get('url'), 'blocks': len(children)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--setup-token', action='store_true', help='Open a local password form and save your Notion integration token with mode 600')
    source.add_argument('--note-id', help='Chosen Cription note ID')
    source.add_argument('--file', help='Chosen UTF-8 transcript or Markdown file')
    parser.add_argument('--title', help='Page title; defaults to the note title or file stem')
    parser.add_argument('--parent-page', help='ID of a Notion page shared with your integration')
    parser.add_argument('--token-file', help='Private API token file (chmod 600); otherwise uses NOTION_API_KEY')
    parser.add_argument('--dry-run', action='store_true', help='Prepare the content without sending it to Notion')
    parser.add_argument('--output', help='Save dry-run title/content JSON in a new private file')
    args = parser.parse_args(argv)
    try:
        default_token = Path.home() / '.config/cription-mcp/notion-api-key'
        if args.setup_token:
            return key_setup.serve(args.token_file or default_token, open_browser=True, kind='notion')
        if args.note_id:
            note = server.tool_get_note({'id': args.note_id})
            title, markdown = args.title or note.get('title') or 'Cription note', note_markdown(note)
        else:
            path = Path(args.file).expanduser()
            title, markdown = args.title or path.stem, path.read_text(encoding='utf-8')
        if not title.strip() or not markdown.strip():
            raise ValueError('Title and transcript must not be empty')
        if args.dry_run:
            value = {'title': title, 'content': markdown}
            if args.output:
                private_json(Path(args.output).expanduser(), value)
                print('Prepared private export: %s' % args.output)
            else:
                print(json.dumps(value, ensure_ascii=False, indent=2))
            return 0
        if args.output:
            raise ValueError('--output is only supported with --dry-run')
        if not args.parent_page:
            raise ValueError('Set --parent-page to a page shared with your Notion integration')
        token = os.environ.get('NOTION_API_KEY', '')
        if args.token_file or (not token and default_token.exists()):
            path = Path(args.token_file).expanduser() if args.token_file else default_token
            if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
                raise ValueError('Token file must be a private regular file (chmod 600)')
            token = path.read_text().strip()
        if not token or any(c.isspace() for c in token):
            raise ValueError('Set NOTION_API_KEY locally or use --token-file; never paste keys into chat')
        print(json.dumps(export_page(args.parent_page, title, markdown, token), ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, server.ToolError) as error:
        print('cription-notion: %s' % error, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
