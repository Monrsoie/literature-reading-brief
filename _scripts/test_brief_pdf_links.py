import unittest
from daily_literature_brief import Paper, render_markdown


class CandidateLinkTests(unittest.TestCase):
    def test_open_pdf_is_clickable(self):
        paper = Paper(title='Example', pdf_url='https://example.org/paper.pdf')
        text = render_markdown('2026-09-15', {}, {'id': 'test', 'label': 'test'}, paper, [paper], None)
        self.assertIn('[开放 PDF](<https://example.org/paper.pdf>)', text)


if __name__ == '__main__':
    unittest.main()
