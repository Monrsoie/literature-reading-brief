import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import daily_brief_gate as gate


class GateTests(unittest.TestCase):
    def _write_brief(self, root: Path, day: str) -> None:
        brief = root / 'maps/daily-briefs' / f'{day}.md'
        data = root / '_data/daily-briefs' / f'{day}.json'
        brief.parent.mkdir(parents=True)
        data.parent.mkdir(parents=True)
        brief.write_text('# 简报', encoding='utf-8')
        data.write_text(json.dumps({
            'selected': {'title': 'Formal Paper', 'doi': '10.1234/formal'},
            'top_candidates': [{'title': 'Formal Paper', 'doi': '10.1234/formal'}],
        }), encoding='utf-8')

    def test_generate_downloads_intakes_and_imports_before_ready(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(gate, 'ROOT', Path(tmp)):
            root = Path(tmp)
            today = dt.date.today().isoformat()
            self._write_brief(root, today)
            runtime = root / 'tools/scansci-pdf-env/Scripts/python.exe'
            runtime.parent.mkdir(parents=True)
            runtime.touch()
            pdf = root / 'Literature/pdfs/scansci' / today / 'paper.pdf'
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b'%PDF-test')
            download_report = root / '_data/pdf-downloads' / f'{today}.json'
            download_report.parent.mkdir(parents=True)
            import_status = root / '_data/zotero-imports' / f'{today}-formal.json'

            def fake_run(command, **kwargs):
                script = Path(command[3] if command[1:3] == ['-X', 'utf8'] else command[1]).name
                if script == 'download_brief_pdf.py':
                    download_report.write_text(json.dumps({
                        'date': today, 'doi': '10.1234/formal', 'status': 'verified',
                        'version_status': 'formal_published', 'pdf_path': str(pdf),
                    }), encoding='utf-8')
                    return gate.subprocess.CompletedProcess(command, 0, stdout='{}', stderr='')
                if script == 'intake_selected_paper.py':
                    import_status.parent.mkdir(parents=True)
                    import_status.write_text(json.dumps({
                        'date': today, 'paper_index': 1, 'paper_key': 'formal',
                        'doi': '10.1234/formal', 'pdf_path': str(pdf),
                        'pdf_status': 'local_pdf_verified', 'obsidian_note': '',
                        'zotero_status': 'manual_import_ready',
                    }), encoding='utf-8')
                    return gate.subprocess.CompletedProcess(command, 0, stdout=f'status={import_status}\n', stderr='')
                if script == 'zotero_import_local.py':
                    status = json.loads(import_status.read_text(encoding='utf-8'))
                    status.update(zotero_status='linked', zotero_collection='每日文献阅读',
                                  zotero_item_key='ITEM', zotero_attachment_status='attached')
                    import_status.write_text(json.dumps(status), encoding='utf-8')
                    return gate.subprocess.CompletedProcess(command, 0, stdout=f'status={import_status}\n', stderr='')
                raise AssertionError(command)

            with patch.object(gate.subprocess, 'run', side_effect=fake_run) as run, \
                    patch('sys.argv', ['gate', 'generate', '--direct']):
                gate.main()
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual([Path(c[3] if c[1:3] == ['-X', 'utf8'] else c[1]).name for c in commands], [
                'download_brief_pdf.py', 'intake_selected_paper.py', 'zotero_import_local.py'])
            self.assertIn('--pdf-path', commands[1])
            self.assertIn('--target-collection-name', commands[2])

            with patch('sys.argv', ['gate', 'mark-delivered']):
                gate.main()
            self.assertTrue((root / '_data/daily-delivery' / f'{today}.json').exists())

    def test_preprint_download_requires_manual_official_pdf_and_cannot_mark_delivered(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(gate, 'ROOT', Path(tmp)):
            root = Path(tmp)
            today = dt.date.today().isoformat()
            self._write_brief(root, today)
            runtime = root / 'tools/scansci-pdf-env/Scripts/python.exe'
            runtime.parent.mkdir(parents=True)
            runtime.touch()
            report = root / '_data/pdf-downloads' / f'{today}.json'
            report.parent.mkdir(parents=True)

            def fake_run(command, **kwargs):
                report.write_text(json.dumps({
                    'status': 'rejected_nonformal', 'version_status': 'preprint',
                    'source': 'arXiv', 'manual_action_required': True,
                }), encoding='utf-8')
                return gate.subprocess.CompletedProcess(command, 1, stdout='', stderr='')

            output = io.StringIO()
            with patch.object(gate.subprocess, 'run', side_effect=fake_run) as run, \
                    patch('sys.argv', ['gate', 'generate']), contextlib.redirect_stdout(output):
                gate.main()
            self.assertEqual(run.call_count, 1)
            self.assertEqual(json.loads(output.getvalue().splitlines()[-1])['status'], 'manual_pdf_required')
            with patch('sys.argv', ['gate', 'mark-delivered']), self.assertRaises(SystemExit):
                gate.main()

    def test_missing_cannot_be_marked_delivered(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(gate, 'ROOT', Path(tmp)):
            with patch('sys.argv', ['gate', 'mark-delivered']), self.assertRaises(SystemExit):
                gate.main()
            self.assertFalse((Path(tmp) / '_data/daily-delivery').exists())

    def test_existing_brief_reused_and_receipt_skips_generation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(gate, 'ROOT', Path(tmp)):
            root = Path(tmp)
            today = dt.date.today().isoformat()
            for folder, ext, content in [('maps/daily-briefs', '.md', '# 简报'), ('_data/daily-briefs', '.json', '{}')]:
                directory = root / folder
                directory.mkdir(parents=True)
                (directory / (today + ext)).write_text(content, encoding='utf-8')
            receipt = root / '_data/daily-delivery' / f'{today}.json'
            receipt.parent.mkdir(parents=True)
            receipt.write_text('{}', encoding='utf-8')
            with patch.object(gate.subprocess, 'run') as run, patch('sys.argv', ['gate', 'generate']):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    gate.main()
            run.assert_not_called()
            self.assertEqual(json.loads(output.getvalue())['status'], 'delivered')


if __name__ == '__main__':
    unittest.main()
