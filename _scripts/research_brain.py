"""Local Markdown memory for research tasks, checkpoints and session links."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import uuid

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / '_data' / 'brain'
KINDS = ('tasks', 'findings', 'decisions', 'progress', 'goals', 'statuses')


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec='seconds')


def read(path: Path) -> dict:
    text = path.read_text(encoding='utf-8')
    _, header, body = text.split('---', 2)
    return {'meta': json.loads(header), 'body': body.strip()}


def write(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = '---\n' + json.dumps(record['meta'], ensure_ascii=False, indent=2) + '\n---\n\n' + record['body'] + '\n'
    fd, temp = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def locate(root: Path, kind: str, key: str) -> Path:
    if not key or any(c not in '0123456789abcdef-' for c in key):
        raise ValueError('Use the exact generated record ID.')
    path = root / kind / f'{key}.md'
    if not path.is_file():
        raise ValueError(f'Unknown {kind} ID: {key}')
    return path


def create(root: Path, kind: str, title: str, body: str, **fields) -> Path:
    key = uuid.uuid4().hex
    meta = {'id': key, 'type': kind, 'title': title, 'created': now(), 'updated': now(), **fields}
    path = root / kind / f'{key}.md'
    write(path, {'meta': meta, 'body': body})
    return path


def dashboard(root: Path) -> dict:
    result = {}
    today = dt.date.today().isoformat()
    for kind in KINDS:
        rows = []
        for path in (root / kind).glob('*.md'):
            meta = read(path)['meta']
            if kind == 'tasks' and meta.get('status') == 'done':
                continue
            if kind == 'goals' and not (meta.get('week_start', '') <= today <= meta.get('week_end', '')):
                continue
            rows.append({**meta, 'path': str(path)})
        result[kind] = sorted(rows, key=lambda r: r['updated'], reverse=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    subs = parser.add_subparsers(dest='command', required=True)
    subs.add_parser('dashboard')
    add = subs.add_parser('add')
    add.add_argument('kind', choices=KINDS[:-1])
    add.add_argument('--title', required=True)
    add.add_argument('--body', default='')
    add.add_argument('--task')
    add.add_argument('--session', default='unknown')
    add.add_argument('--priority', choices=('high', 'medium', 'low'), default='medium')
    checkpoint = subs.add_parser('checkpoint')
    checkpoint.add_argument('task')
    checkpoint.add_argument('--stopped', required=True)
    checkpoint.add_argument('--next', required=True)
    checkpoint.add_argument('--status', choices=('open', 'blocked', 'done'), default='open')
    checkpoint.add_argument('--session', default='unknown')
    link = subs.add_parser('link')
    link.add_argument('task')
    link.add_argument('--session', required=True)
    link.add_argument('--state', choices=('active', 'idle', 'blocked', 'done'), default='active')
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == 'dashboard':
        print(json.dumps(dashboard(root), ensure_ascii=False, indent=2))
        return
    if args.command == 'add':
        fields = {'session_id': args.session}
        if args.task:
            locate(root, 'tasks', args.task)
            fields['task_id'] = args.task
        if args.kind == 'tasks':
            fields.update(status='open', priority=args.priority, where_stopped='', next_action='')
        if args.kind == 'goals':
            today = dt.date.today()
            start = today - dt.timedelta(days=today.weekday())
            fields.update(week_start=start.isoformat(), week_end=(start + dt.timedelta(days=6)).isoformat(), status='active')
        if args.kind == 'progress':
            fields['date'] = dt.date.today().isoformat()
        path = create(root, args.kind, args.title, args.body, **fields)
    elif args.command == 'checkpoint':
        path = locate(root, 'tasks', args.task)
        record = read(path)
        record['meta'].update(where_stopped=args.stopped, next_action=args.next,
                              status=args.status, updated=now(), session_id=args.session)
        write(path, record)
        create(root, 'progress', record['meta']['title'], args.stopped + '\n\n下一步：' + args.next,
               task_id=args.task, session_id=args.session, date=dt.date.today().isoformat())
    else:
        locate(root, 'tasks', args.task)
        matches = [p for p in (root / 'statuses').glob('*.md') if read(p)['meta'].get('session_id') == args.session]
        if len(matches) > 1:
            raise ValueError('Conflicting session records; inspect before updating.')
        if matches:
            path = matches[0]
            record = read(path)
            record['meta'].update(task_id=args.task, status=args.state, updated=now())
            write(path, record)
        else:
            path = create(root, 'statuses', '会话关联', '', task_id=args.task, session_id=args.session, status=args.state)
    print(json.dumps({'path': str(path), 'id': read(path)['meta']['id']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
