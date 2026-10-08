import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import pymupdf
import download_brief_pdf as download


class DownloadTests(unittest.TestCase):
    def test_preprint_and_ambiguous_repository_sources_are_not_formal_fulltext(self):
        for source in ('arXiv', 'bioRxiv', 'OpenAlexOA', 'Unpaywall', 'SemanticScholar',
                       'oa_url', 'Crossref', 'DOAJ', 'InstitutionalRepository'):
            with self.subTest(source=source):
                verdict = download.formal_source_verdict({'source': source})
                self.assertFalse(verdict['accepted'])

    def test_publisher_and_authenticated_sources_are_formal_fulltext(self):
        for source in ('MDPIDirect', 'ElsevierAPI', 'SpringerTDM', 'CrossrefPage', 'InstSci', 'CARSI'):
            with self.subTest(source=source):
                verdict = download.formal_source_verdict({'source': source})
                self.assertTrue(verdict['accepted'])

    def test_cleanup_kills_worker_when_taskkill_times_out(self):
        process = Mock(pid=123)
        with patch.object(download.subprocess, 'run', side_effect=download.subprocess.TimeoutExpired('taskkill', 15)):
            with self.assertRaises(download.subprocess.TimeoutExpired):
                download.stop_worker(process)
        process.kill.assert_called_once()

    def test_missing_new_result_never_uses_old_success(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(download, 'ROOT', Path(tmp)):
            root = Path(tmp)
            day = '2026-09-15'
            download.write_json(root / '_data/daily-briefs' / f'{day}.json',
                                {'selected': {'doi': '10.1234/new', 'title': 'New'}})
            result = root / '_data/pdf-downloads' / f'{day}.json'
            download.write_json(result, {'doi': '10.1234/old', 'status': 'verified'})
            process = Mock()
            process.wait.return_value = 0
            with patch.object(download.subprocess, 'Popen') as popen, patch.object(download, 'publish'), patch('sys.argv', ['download', '--date', day]):
                popen.return_value.__enter__.return_value = process
                self.assertEqual(download.main(), 1)
            self.assertEqual(json.loads(result.read_text(encoding='utf-8'))['status'], 'failed')

    def test_reject_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fake.pdf'
            path.write_text('<html>login</html>', encoding='utf-8')
            with self.assertRaises(ValueError):
                download.validate_pdf(path, {'doi': '10.1234/test'})

    def test_identity_and_wrong_paper(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'paper.pdf'
            with pymupdf.open() as doc:
                doc.new_page().insert_text((72, 72), 'Traffic Safety Study DOI: 10.1234/test')
                doc.save(path)
            result = download.validate_pdf(path, {'title': 'Traffic Safety Study', 'doi': '10.1234/test'})
            self.assertTrue(result['identity_match'])
            self.assertTrue(result['doi_match'])
            self.assertEqual(result['pages'], 1)
            self.assertFalse(download.validate_pdf(path, {'title': 'Another Study', 'doi': '10.1234/test'})['identity_match'])
            self.assertFalse(download.validate_pdf(path, {'title': 'Another Study', 'doi': '10.1234/tes'})['identity_match'])

    def test_matching_title_without_doi_is_not_enough(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'paper.pdf'
            with pymupdf.open() as doc:
                doc.new_page().insert_text((72, 72), 'Traffic Safety Study')
                doc.save(path)
            result = download.validate_pdf(path, {'title': 'Traffic Safety Study', 'doi': '10.1234/test'})
            self.assertTrue(result['title_match'])
            self.assertFalse(result['doi_match'])
            self.assertFalse(result['identity_match'])

    def test_publish_idempotent_and_failure_explicit(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(download, 'ROOT', Path(tmp)):
            path = Path(tmp) / 'maps/daily-briefs/2026-09-15.md'
            path.parent.mkdir(parents=True)
            path.write_text('# Original brief\n', encoding='utf-8')
            for _ in range(2):
                download.publish('2026-09-15', {'status': 'failed'})
            text = path.read_text(encoding='utf-8')
            self.assertEqual(text.count(download.MARKER), 1)
            self.assertIn('未取得可核验的正式发表版全文', text)
            self.assertIn('请手动提供有权限使用的正式版 PDF', text)
            self.assertTrue(text.startswith('# Original brief'))

    def test_publish_verified_publisher_pdf(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(download, 'ROOT', Path(tmp)):
            path = Path(tmp) / 'maps/daily-briefs/2026-09-15.md'
            path.parent.mkdir(parents=True)
            path.write_text('# Brief\n', encoding='utf-8')
            report = {'status': 'verified', 'pdf_path': str(Path(tmp) / 'paper.pdf'),
                      'validation': {'pages': 17}, 'source_url': 'https://publisher.example/paper.pdf'}
            download.publish('2026-09-15', report)
            text = path.read_text(encoding='utf-8')
            self.assertIn('## 全文下载与核验', text)
            self.assertIn('[开放 PDF 直链](<https://publisher.example/paper.pdf>)', text)


if __name__ == '__main__':
    unittest.main()
