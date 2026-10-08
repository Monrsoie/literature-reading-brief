"""Generate a daily brief and gate delivery on formal-PDF Zotero intake."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET_COLLECTION = '每日文献阅读'
ATTACHED_STATES = {'attached', 'attached_existing'}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def brief_ready(day: str) -> bool:
    brief = ROOT / 'maps/daily-briefs' / f'{day}.md'
    data = ROOT / '_data/daily-briefs' / f'{day}.json'
    if not (brief.exists() and data.exists()):
        return False
    read_json(data)
    return bool(brief.read_text(encoding='utf-8').strip())


def matching_import_status(day: str) -> tuple[Path | None, dict[str, Any] | None]:
    brief_path = ROOT / '_data/daily-briefs' / f'{day}.json'
    if not brief_path.exists():
        return None, None
    selected = read_json(brief_path).get('selected') or {}
    selected_doi = str(selected.get('doi') or '').lower()
    imports_dir = ROOT / '_data/zotero-imports'
    if not imports_dir.exists():
        return None, None
    for path in sorted(imports_dir.glob(f'{day}-*.json')):
        status = read_json(path)
        if selected_doi and str(status.get('doi') or '').lower() != selected_doi:
            continue
        return path, status
    return None, None


def intake_complete(day: str) -> bool:
    _, status = matching_import_status(day)
    if not status:
        return False
    raw_pdf_path = str(status.get('pdf_path') or '')
    return bool(
        raw_pdf_path
        and status.get('pdf_status') == 'local_pdf_verified'
        and Path(raw_pdf_path).is_file()
        and status.get('zotero_status') == 'linked'
        and status.get('zotero_collection') == TARGET_COLLECTION
        and status.get('zotero_item_key')
        and status.get('zotero_attachment_status') in ATTACHED_STATES
    )


def run(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, env=env, check=False, capture_output=True, text=True, timeout=600)


def generate_brief(day: str, env: dict[str, str]) -> None:
    state = ROOT / '_data/daily-delivery'
    state.mkdir(parents=True, exist_ok=True)
    lock = state / f'{day}.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit('Generation locked. Inspect running process before removing a stale lock.')
    os.close(fd)
    try:
        subprocess.run([sys.executable, str(ROOT / '_scripts/daily_literature_brief.py'),
                        '--vault', str(ROOT), '--date', day], env=env, check=True, timeout=600)
    finally:
        lock.unlink(missing_ok=True)


def perform_intake(day: str, direct: bool, env: dict[str, str]) -> dict[str, Any]:
    workflow_path = ROOT / '_data/daily-delivery' / f'{day}.workflow.json'
    status_path, status = matching_import_status(day)
    if intake_complete(day):
        result = {'date': day, 'status': 'ready',
                  'brief': str(ROOT / 'maps/daily-briefs' / f'{day}.md'),
                  'zotero_status': str(status_path), 'collection': TARGET_COLLECTION,
                  'pdf_path': str(status.get('pdf_path') or '')}
        write_json(workflow_path, result)
        return result
    runtime = ROOT / 'tools/scansci-pdf-env/Scripts/python.exe'
    if not runtime.exists():
        result = {'date': day, 'status': 'manual_pdf_required', 'reason': 'scansci_runtime_missing',
                  'message': '自动正式版下载环境不可用，请手动提供有权限使用的正式版 PDF。'}
        write_json(workflow_path, result)
        return result

    download_command = [str(runtime), '-X', 'utf8', str(ROOT / '_scripts/download_brief_pdf.py'), '--date', day]
    if direct:
        download_command.append('--direct')
    download_result = run(download_command, env)
    report_path = ROOT / '_data/pdf-downloads' / f'{day}.json'
    report = read_json(report_path) if report_path.exists() else {}
    if (download_result.returncode or report.get('status') != 'verified'
            or report.get('version_status') != 'formal_published'):
        result = {
            'date': day,
            'status': 'manual_pdf_required',
            'reason': report.get('version_status') or report.get('error_type') or 'formal_pdf_unavailable',
            'message': '未取得可核验的正式发表版 PDF，请手动提供有权限使用的正式版全文。',
            'download_report': str(report_path),
        }
        write_json(workflow_path, result)
        return result

    raw_pdf_path = str(report.get('pdf_path') or '')
    pdf_path = Path(raw_pdf_path) if raw_pdf_path else None
    if not pdf_path or not pdf_path.is_file():
        result = {'date': day, 'status': 'manual_pdf_required', 'reason': 'verified_pdf_missing',
                  'message': '核验后的正式版 PDF 文件已不可用，请手动提供有权限使用的正式版 PDF。'}
        write_json(workflow_path, result)
        return result

    intake_command = [sys.executable, '-X', 'utf8', str(ROOT / '_scripts/intake_selected_paper.py'),
                      '--vault', str(ROOT), '--date', day, '--paper-index', '1',
                      '--pdf-path', str(pdf_path), '--overwrite']
    intake_result = run(intake_command, env)
    if intake_result.returncode:
        result = {'date': day, 'status': 'failed', 'stage': 'intake',
                  'error': intake_result.stderr.strip() or intake_result.stdout.strip()}
        write_json(workflow_path, result)
        return result

    status_path, _ = matching_import_status(day)
    if not status_path:
        result = {'date': day, 'status': 'failed', 'stage': 'intake', 'error': 'status_missing'}
        write_json(workflow_path, result)
        return result

    import_command = [sys.executable, '-X', 'utf8', str(ROOT / '_scripts/zotero_import_local.py'),
                      '--vault', str(ROOT), '--date', day,
                      '--target-collection-name', TARGET_COLLECTION]
    import_result = run(import_command, env)
    if import_result.returncode or not intake_complete(day):
        result = {'date': day, 'status': 'failed', 'stage': 'zotero_import',
                  'error': import_result.stderr.strip() or import_result.stdout.strip()
                           or 'Zotero item, collection, or PDF attachment could not be verified.'}
        write_json(workflow_path, result)
        return result

    result = {'date': day, 'status': 'ready',
              'brief': str(ROOT / 'maps/daily-briefs' / f'{day}.md'),
              'zotero_status': str(status_path), 'collection': TARGET_COLLECTION,
              'pdf_path': str(pdf_path)}
    write_json(workflow_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('status', 'generate', 'mark-delivered'))
    parser.add_argument('--direct', action='store_true')
    args = parser.parse_args()
    day = dt.date.today().isoformat()
    state = ROOT / '_data/daily-delivery'
    receipt = state / f'{day}.json'
    brief = ROOT / 'maps/daily-briefs' / f'{day}.md'
    if receipt.exists():
        print(json.dumps({'date': day, 'status': 'delivered', 'receipt': str(receipt)}, ensure_ascii=False))
        return

    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    if args.direct:
        for key in list(env):
            if key.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
                del env[key]
        env['NO_PROXY'] = '*'

    if args.command == 'generate':
        if not brief_ready(day):
            generate_brief(day, env)
        result = perform_intake(day, args.direct, env) if brief_ready(day) else {'date': day, 'status': 'missing'}
        print(json.dumps(result, ensure_ascii=False))
        return

    ready = brief_ready(day) and intake_complete(day)
    if args.command == 'mark-delivered':
        if not ready:
            raise SystemExit('Cannot mark delivery before a formal PDF is attached in Zotero collection 每日文献阅读.')
        state.mkdir(parents=True, exist_ok=True)
        with receipt.open('x', encoding='utf-8') as stream:
            json.dump({'date': day, 'delivered_at': dt.datetime.now().astimezone().isoformat(),
                       'channel': 'codex-thread', 'brief': str(brief),
                       'zotero_collection': TARGET_COLLECTION}, stream, ensure_ascii=False, indent=2)
        status = 'delivered'
    else:
        workflow = state / f'{day}.workflow.json'
        status = 'ready' if ready else (read_json(workflow).get('status') if workflow.exists() else 'missing')
    print(json.dumps({'date': day, 'status': status, 'brief': str(brief)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
