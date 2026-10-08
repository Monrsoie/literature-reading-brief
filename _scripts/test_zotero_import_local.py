import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import zotero_import_local as zotero


class ZoteroImportTests(unittest.TestCase):
    def test_existing_local_file_upload_short_circuits_when_zotero_already_has_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / 'formal.pdf'
            pdf.write_bytes(b'%PDF-formal-version')
            with patch.object(zotero, 'local_form_post', return_value={'exists': 1}) as form, \
                    patch.object(zotero.urllib.request, 'urlopen') as urlopen:
                zotero.upload_local_file('ATTACH', pdf, {'Zotero-API-Key': 'hidden'})
            self.assertEqual(form.call_count, 1)
            urlopen.assert_not_called()

    def test_existing_local_file_upload_runs_authorize_bytes_and_register(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / 'formal.pdf'
            pdf.write_bytes(b'%PDF-formal-version')
            response = Mock()
            response.read.return_value = b''
            context = Mock()
            context.__enter__ = Mock(return_value=response)
            context.__exit__ = Mock(return_value=False)
            with patch.object(zotero, 'local_form_post', side_effect=[
                    {'url': '/api/local/uploads/UPLOAD', 'uploadKey': 'UPLOAD',
                     'contentType': 'application/pdf', 'prefix': '', 'suffix': ''},
                    {},
                ]) as form, patch.object(zotero.urllib.request, 'urlopen', return_value=context) as urlopen:
                zotero.upload_local_file('ATTACH', pdf, {'Zotero-API-Key': 'hidden'})
            self.assertEqual(form.call_count, 2)
            self.assertEqual(form.call_args_list[-1].args[1], {'upload': 'UPLOAD'})
            request = urlopen.call_args.args[0]
            self.assertEqual(request.full_url, 'http://127.0.0.1:23119/api/local/uploads/UPLOAD')

    def test_failed_existing_item_upload_removes_only_created_empty_attachment(self):
        daily = Mock()
        daily.request.side_effect = [
            ({'itemType': 'attachment', 'linkMode': 'imported_file'}, {}),
            ({'successful': {'0': {'key': 'ATTACH'}}}, {}),
            ({'key': 'ATTACH', 'version': 3,
              'data': {'itemType': 'attachment', 'version': 3}}, {}),
            ({}, {}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / 'formal.pdf'
            pdf.write_bytes(b'%PDF-formal-version')
            with patch.object(zotero, 'local_write_context',
                              return_value=(daily, {'Zotero-API-Key': 'hidden'})), \
                    patch.object(zotero, 'upload_local_file', side_effect=SystemExit('upload failed')):
                with self.assertRaisesRegex(SystemExit, 'upload failed'):
                    zotero.attach_pdf_to_existing('PARENT', pdf, {'title': 'Formal'})
        delete_call = daily.request.call_args_list[-1]
        self.assertEqual(delete_call.args[:3], ('/users/0/items/ATTACH', 'DELETE', None))

    def test_existing_item_gets_target_membership_and_current_formal_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            day = '2026-09-22'
            pdf = root / 'Literature/pdfs/formal.pdf'
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b'%PDF-formal-version')
            brief = root / '_data/daily-briefs' / f'{day}.json'
            brief.parent.mkdir(parents=True)
            brief.write_text(json.dumps({'selected': {'title': 'Formal', 'doi': '10.1234/formal'},
                                         'top_candidates': [{'title': 'Formal', 'doi': '10.1234/formal'}]}), encoding='utf-8')
            status_path = root / '_data/zotero-imports' / f'{day}-formal.json'
            status_path.parent.mkdir(parents=True)
            status_path.write_text(json.dumps({
                'date': day, 'paper_index': 1, 'paper_key': 'formal', 'doi': '10.1234/formal',
                'pdf_path': str(pdf), 'pdf_status': 'local_pdf_verified', 'obsidian_note': '',
            }), encoding='utf-8')
            selected = {'name': 'Other', 'id': 'OTHER',
                        'targets': [{'name': '每日文献阅读', 'id': 'CTARGET'}]}
            existing = {'key': 'ITEM', 'version': 2,
                        'data': {'DOI': '10.1234/formal', 'collections': []}}
            with patch.object(zotero, 'ensure_zotero_running'), \
                    patch.object(zotero, 'connector_post', return_value=selected), \
                    patch.object(zotero, 'find_local_collection_key', return_value='TARGETKEY'), \
                    patch.object(zotero, 'find_zotero_item_by_doi', return_value=existing), \
                    patch.object(zotero, 'ensure_collection_membership') as membership, \
                    patch.object(zotero, 'item_has_pdf_attachment', side_effect=[False, True]), \
                    patch.object(zotero, 'attach_pdf_to_existing') as attach, \
                    patch('sys.argv', ['zotero', '--vault', str(root), '--date', day,
                                       '--target-collection-name', '每日文献阅读']):
                self.assertEqual(zotero.main(), 0)
            membership.assert_called_once_with(existing, 'TARGETKEY')
            attach.assert_called_once_with('ITEM', pdf, {'title': 'Formal', 'doi': '10.1234/formal'})
            status = json.loads(status_path.read_text(encoding='utf-8'))
            self.assertEqual(status['zotero_attachment_status'], 'attached')
            self.assertEqual(status['zotero_collection'], '每日文献阅读')
            self.assertEqual(status['zotero_collection_key'], 'TARGETKEY')

    def test_collection_key_never_falls_back_to_connector_target_id(self):
        with self.assertRaisesRegex(SystemExit, 'Local API collection key is missing'):
            zotero.target_collection_key({'name': '每日文献阅读', 'id': 'C25'})


if __name__ == '__main__':
    unittest.main()
