"""Download the selected daily paper through formal-only ScanSci sources."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
MARKER = '\n## 全文下载与核验\n'
PREPRINT_MARKERS = ('arxiv', 'biorxiv', 'medrxiv', 'chemrxiv', 'researchsquare', 'preprints.org')
FORMAL_SOURCE_MARKERS = (
    'publisherdirect', 'naturedirect', 'naturebrowser', 'mdpidirect', 'mdpi_cdn',
    'elsevierapi', 'elsevier_api', 'elsevierbrowser', 'wileybrowser',
    'sciencedirect', 'sciencebrowser', 'pnasdirect', 'oxfordbrowser', 'acsbrowser',
    'springertdm', 'springer_tdm', 'springerbrowser', 'apsbrowser', 'iopbrowser',
    'plosdirect', 'frontiersdirect', 'bmcdirect', 'rscbrowser', 'aipbrowser',
    'acmbrowser', 'ieeebrowser', 'tandfbrowser', 'sagebrowser', 'ascebrowser',
    'crossrefpage', 'instsci', 'carsi', 'webvpn', 'ezproxy', 'institutional:browser',
)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def validate_pdf(path: Path, paper: dict) -> dict:
    import pymupdf
    with path.open('rb') as stream:
        if stream.read(5) != b'%PDF-':
            raise ValueError('not_pdf')
    with pymupdf.open(path) as doc:
        text = '\n'.join(doc[index].get_text() for index in range(min(len(doc), 3)))
        normalize = lambda value: re.sub(r'[^a-z0-9]', '', value.lower())
        title = normalize(paper.get('title', ''))
        doi = normalize(str(paper.get('doi') or '').removeprefix('https://doi.org/').removeprefix('http://doi.org/'))
        normalized = normalize(text)
        title_match = bool(title and title in normalized)
        doi_match = bool(doi and doi in normalized)
        match = title_match and (doi_match if doi else True)
        return {'pages': len(doc), 'text_chars': len(text), 'title_match': title_match,
                'doi_match': doi_match, 'identity_match': match,
                'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def formal_source_verdict(result: dict) -> dict:
    """Accept only sources that identify a publisher or authenticated publisher route."""
    source = str(result.get('source') or result.get('mcp', {}).get('source') or '').strip()
    source_url = str(result.get('source_url') or result.get('mcp', {}).get('source_url') or '').strip()
    fingerprint = re.sub(r'[^a-z0-9:._-]', '', f'{source} {source_url}'.lower())
    if any(marker in fingerprint for marker in PREPRINT_MARKERS):
        return {'accepted': False, 'version_status': 'preprint', 'source': source,
                'reason': 'preprint_source'}
    normalized_source = re.sub(r'[^a-z0-9:_-]', '', source.lower())
    if any(marker in normalized_source for marker in FORMAL_SOURCE_MARKERS):
        return {'accepted': True, 'version_status': 'formal_published', 'source': source,
                'reason': 'publisher_or_authenticated_source'}
    return {'accepted': False, 'version_status': 'unverified_version', 'source': source,
            'reason': 'source_does_not_prove_formal_version'}


def formal_download(paper: dict, output: Path) -> dict:
    """Run ScanSci with only publisher and authenticated publisher routes enabled."""
    import scansci_pdf.sources as sources

    original_builder = sources._build_free_sources

    def build_formal_sources(doi: str, config: dict) -> list:
        return [(source_fn, label) for source_fn, label in original_builder(doi, config)
                if formal_source_verdict({'source': label})['accepted']]

    sources._build_free_sources = build_formal_sources
    try:
        return sources.download(
            paper['doi'], str(output), scihub_enabled=False, use_tor=False,
            use_vpnsci=False, bibtex=False, strategy='legal_only',
        )
    finally:
        sources._build_free_sources = original_builder


def worker(day: str, result_path: Path, direct: bool) -> int:
    data = json.loads((ROOT / '_data/daily-briefs' / f'{day}.json').read_text(encoding='utf-8'))
    paper = data['selected']
    output = ROOT / 'Literature/pdfs/scansci' / day
    output.mkdir(parents=True, exist_ok=True)
    config_dir = ROOT / 'tools/scansci-state'
    write_json(config_dir / 'config.json', {
        'download_strategy': 'legal_only', 'scihub_enabled': False,
        'use_tor_for_scihub': False, 'progress_bar_auto': False,
        'auto_relogin': False, 'batch_workers': 1, 'auto_rename': False,
        'vpnsci_enabled': False, 'carsi_enabled': False, 'ezproxy_enabled': False,
    })
    env = dict(os.environ, SCANSCI_PDF_DATA_DIR=str(config_dir), PYTHONIOENCODING='utf-8')
    if direct:
        for key in list(env):
            if key.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
                del env[key]
        env['NO_PROXY'] = '*'
    os.environ.clear()
    os.environ.update(env)
    report = {'date': day, 'doi': paper.get('doi'), 'title': paper.get('title'),
              'strategy': 'legal_only', 'status': 'failed', 'engine': 'scansci-pdf',
              'attempted_at': dt.datetime.now().astimezone().isoformat()}
    try:
        result = formal_download(paper, output)
        report['mcp'] = result
        if result.get('success') and result.get('file'):
            path = Path(result['file']).resolve()
            if not path.is_relative_to(output.resolve()):
                raise ValueError('file_outside_output')
            verdict = formal_source_verdict(result)
            report.update(source=verdict['source'], source_url=result.get('source_url') or result.get('url') or '',
                          version_status=verdict['version_status'], version_reason=verdict['reason'])
            if not verdict['accepted']:
                path.unlink(missing_ok=True)
                report.update(status='rejected_nonformal', manual_action_required=True)
            else:
                report['validation'] = validate_pdf(path, paper)
                if report['validation']['identity_match'] and report['validation']['pages'] > 0:
                    report.update(status='verified', pdf_path=str(path))
                else:
                    report['status'] = 'needs_identity_review'
    except Exception as exc:
        report['error_type'] = type(exc).__name__
    write_json(result_path, report)
    return 0 if report['status'] == 'verified' else 1


def publish(day: str, report: dict) -> None:
    path = ROOT / 'maps/daily-briefs' / f'{day}.md'
    text = path.read_text(encoding='utf-8').split(MARKER)[0].rstrip()
    if report['status'] == 'verified':
        pdf = Path(report['pdf_path']).as_posix()
        detail = f"已下载并验证：{report['validation']['pages']} 页。\n\n[打开本地 PDF](<{pdf}>)"
        if report.get('source_url'):
            detail += f"\n\n来源：[开放 PDF 直链](<{report['source_url']}>)"
    else:
        version = report.get('version_status') or 'unknown'
        detail = (f"本次未取得可核验的正式发表版全文（{report['status']} / {version}）。"
                  "不会保存或导入预印本；请手动提供有权限使用的正式版 PDF。")
    path.write_text(text + MARKER + '\n' + detail + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', default=dt.date.today().isoformat())
    parser.add_argument('--direct', action='store_true')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--attempt', help=argparse.SUPPRESS)
    args = parser.parse_args()
    day = dt.date.fromisoformat(args.date).isoformat()
    result_path = ROOT / '_data/pdf-downloads' / f'{day}.json'
    if args.worker:
        attempt = str(uuid.UUID(args.attempt))
        return worker(day, result_path.parent / 'attempts' / f'{day}-{attempt}.json', args.direct)
    paper = json.loads((ROOT / '_data/daily-briefs' / f'{day}.json').read_text(encoding='utf-8'))['selected']
    if result_path.exists():
        previous = json.loads(result_path.read_text(encoding='utf-8'))
        verdict = formal_source_verdict(previous)
        if (previous.get('status') == 'verified' and previous.get('doi') == paper.get('doi')
                and previous.get('version_status') == 'formal_published' and verdict['accepted']):
            try:
                cached_path = Path(previous['pdf_path']).resolve()
                if not cached_path.is_relative_to((ROOT / 'Literature/pdfs/scansci' / day).resolve()):
                    raise ValueError('cache_outside_output')
                validation = validate_pdf(cached_path, paper)
                if validation['identity_match'] and validation['pages'] > 0:
                    previous['validation'] = validation
                    publish(day, previous)
                    print(json.dumps(previous, ensure_ascii=False))
                    return 0
            except (OSError, ValueError, KeyError, RuntimeError):
                pass
    result_path.parent.mkdir(parents=True, exist_ok=True)
    lock = result_path.with_suffix('.lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print('Download already running; inspect process before clearing stale lock.')
        return 1
    os.close(fd)
    attempt = str(uuid.uuid4())
    attempt_path = result_path.parent / 'attempts' / f'{day}-{attempt}.json'
    runtime = ROOT / 'tools/scansci-pdf-env/Scripts/python.exe'
    command = [str(runtime), '-X', 'utf8', str(Path(__file__).resolve()), '--worker', '--date', day,
               '--attempt', attempt]
    if args.direct:
        command.append('--direct')
    report = {'date': day, 'status': 'failed', 'error_type': 'worker_incomplete'}
    # The parent imposes a hard process budget, including MCP startup and cleanup.
    try:
        with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as process:
            try:
                code = process.wait(timeout=240)
            except subprocess.TimeoutExpired:
                # Kill only this invocation's worker/MCP tree, not other Python sessions.
                stop_worker(process)
                raise
        if not attempt_path.exists():
            raise RuntimeError('worker_no_result')
        report = json.loads(attempt_path.read_text(encoding='utf-8'))
        if code and report.get('status') == 'verified':
            raise RuntimeError('worker_exit_error')
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        report = {'date': day, 'status': 'failed', 'error_type': type(exc).__name__}
    finally:
        try:
            write_json(result_path, report)
            publish(day, report)
        finally:
            lock.unlink(missing_ok=True)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['status'] == 'verified' else 1


def stop_worker(process) -> None:
    try:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       capture_output=True, timeout=15, check=False)
    finally:
        process.kill()


if __name__ == '__main__':
    raise SystemExit(main())
