import tempfile
import unittest
from pathlib import Path
from research_brain import create, dashboard, locate, read, write


class BrainTests(unittest.TestCase):
    def test_unicode_persistence_and_done_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = create(root, 'tasks', '跟驰安全研究', '证据与下一步', status='open')
            record = read(path)
            self.assertEqual(record['body'], '证据与下一步')
            self.assertEqual(len(dashboard(root)['tasks']), 1)
            record['meta']['status'] = 'done'
            write(path, record)
            self.assertEqual(dashboard(root)['tasks'], [])
            self.assertEqual(locate(root, 'tasks', record['meta']['id']), path)

    def test_reject_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                locate(Path(tmp), 'tasks', '../outside')


if __name__ == '__main__':
    unittest.main()
