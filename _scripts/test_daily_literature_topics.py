import json
import datetime as dt
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import daily_literature_brief as brief


CONFIG_PATH = Path(__file__).resolve().parents[1] / '_references' / 'research-topics.yml'


class TopicConfigTests(unittest.TestCase):
    def test_current_queries_follow_the_selected_subtopic(self):
        config = brief.load_config(CONFIG_PATH)
        self.assertIn('单车风险', config['topic_name'])
        topics = [brief.parse_subtopic(item) for item in config['subtopics']]
        for topic in topics:
            queries = brief.build_queries(config, topic)
            self.assertEqual(len(queries), 4, topic['id'])
            self.assertEqual(len(queries), len(set(queries)))
            self.assertTrue(all('|' not in query for query in queries))
        self.assertIn('pre-crash vehicle trajectories traffic conflict measures',
                      brief.build_queries(config, topics[0]))
        self.assertNotIn('large language model traffic safety risk assessment connected automated vehicles',
                         brief.build_queries(config, topics[0]))

    def test_nontraffic_topic_uses_its_own_queries_and_scoring_terms(self):
        config = {
            'topic_name': 'marine ecology',
            'core_terms': ['coral reef'],
            'method_terms': ['satellite imagery'],
            'idea_terms': ['restoration'],
            'quality_sources': ['Marine Ecology'],
            'query_templates': [
                'all|marine biodiversity survey',
                'reef|coral reef satellite imagery restoration',
                'other|seagrass genetics',
            ],
        }
        topic = {'id': 'reef', 'label': 'reef', 'keywords': ['coral reef']}
        self.assertEqual(brief.build_queries(config, topic), [
            'marine biodiversity survey', 'coral reef satellite imagery restoration'])

        relevant = brief.Paper(
            title='Coral reef restoration using satellite imagery',
            source='Marine Ecology', year=2025,
            abstract='Satellite imagery maps coral reef restoration outcomes.')
        irrelevant = brief.Paper(
            title='Freeway vehicle trajectory and traffic conflict',
            source='Transportation Research Part C', year=2025,
            abstract='Traffic video predicts crash risk.')
        brief.score_paper(relevant, config, topic)
        brief.score_paper(irrelevant, config, topic)
        self.assertGreater(relevant.total_score, irrelevant.total_score)
        self.assertGreater(relevant.total_score, 8)
        self.assertEqual(relevant.scores['方法启发性'], 1)
        self.assertEqual(relevant.scores['小论文灵感潜力'], 1)
        self.assertTrue(any('当前研究主题相关性不足' in reason for reason in irrelevant.reasons))
        self.assertNotIn('reading_guide', brief.paper_to_dict(relevant))

    def test_representative_paper_titles_match_current_topic(self):
        config = brief.load_config(CONFIG_PATH)
        topics = {topic['id']: topic for topic in
                  [brief.parse_subtopic(item) for item in config['subtopics']]}
        cases = [
            ('individual_risk',
             'Real-time lane-changing crash prediction model at the individual vehicle level',
             'The model uses real-world trajectories and remaining distance.'),
            ('large_model',
             'V2X-LLM: Enhancing V2X Integration and Understanding in Connected Vehicle Corridors',
             'Large language models process vehicle messages.'),
        ]
        for topic_id, title, abstract in cases:
            with self.subTest(topic_id=topic_id):
                paper = brief.Paper(title=title, abstract=abstract, year=2025)
                brief.score_paper(paper, config, topics[topic_id])
                self.assertGreater(paper.total_score, 8)
                self.assertFalse(any('当前研究主题相关性不足' in reason
                                     for reason in paper.reasons))

    def test_unrelated_highly_cited_paper_cannot_be_selected(self):
        config = brief.load_config(CONFIG_PATH)
        topic = brief.parse_subtopic(config['subtopics'][0])
        unrelated = brief.Paper(title='Evolutionary-scale prediction of atomic-level protein structure',
                                source='Science', year=2023, cited_by_count=500)
        related = brief.Paper(title='Real-time lane-changing crash prediction at the individual vehicle level',
                              source='Transportation Research Part C', year=2025, cited_by_count=5,
                              journal_if='8.4', journal_quartile='Q1',
                              journal_metric_year=str(dt.date.today().year - 1),
                              journal_if_source='https://example.org/if',
                              journal_rank_source='https://example.org/rank')
        for paper in (unrelated, related):
            brief.score_paper(paper, config, topic)
        self.assertEqual(brief.rank_candidates([unrelated, related]), [related])

    def test_provider_queries_do_not_pre_sort_by_citations(self):
        with patch.object(brief, 'fetch_json', return_value={'results': [],
                                                             'message': {'items': []}}) as fetch:
            brief.fetch_openalex('lane-changing crash prediction', 2023)
            brief.fetch_crossref('lane-changing crash prediction', 2023)
        for call in fetch.call_args_list:
            params = parse_qs(urlparse(call.args[0]).query)
            self.assertNotIn('sort', params)
            self.assertNotIn('order', params)

    def test_old_topic_history_does_not_affect_new_topic_rotation(self):
        config = {'topic_name': 'new research', 'subtopics': [
            'shared|First|alpha', 'second|Second|beta']}
        old_log = '{"topic": "old research", "subtopic": {"id": "shared"}}\n'
        with patch.object(Path, 'exists', return_value=True), \
                patch.object(Path, 'read_text', return_value=old_log):
            self.assertEqual(brief.choose_subtopic(config, Path('vault'))['id'], 'shared')

    def test_same_day_enrichment_is_not_reused_across_topics(self):
        paper = brief.Paper(title='A shared title', doi='10.1234/shared')
        old_brief = {'topic': 'old research', 'selected': {
            'title': paper.title, 'doi': paper.doi,
            'reading_guide': {'方法': '旧方向固定解读'},
            'title_zh': '旧方向译名'}, 'top_candidates': []}
        with patch.object(Path, 'exists', return_value=True), \
                patch.object(Path, 'read_text', return_value=json.dumps(old_brief)):
            brief.apply_existing_enrichment(Path('vault'), '2026-09-15', paper,
                                            [paper], 'new research')
        self.assertNotIn('reading_guide', brief.paper_to_dict(paper))
        self.assertEqual(paper.title_zh, '')

    def test_verified_venue_requires_source_and_q1_q2_or_cas_one_two(self):
        paper = brief.Paper(title='Example', journal_if='5.4',
                            journal_metric_year=str(dt.date.today().year - 1),
                            journal_if_source='https://example.org/if',
                            journal_rank_source='https://example.org/rank')
        self.assertFalse(brief.verified_venue(paper))
        paper.journal_cas_quartile = '2区'
        self.assertTrue(brief.verified_venue(paper))
        paper.journal_cas_quartile = ''
        paper.journal_quartile = 'Q2'
        self.assertTrue(brief.verified_venue(paper))
        paper.journal_if_source = ''
        self.assertFalse(brief.verified_venue(paper))

    def test_verified_q1_improves_quality_score_without_field_specific_terms(self):
        config = brief.load_config(CONFIG_PATH)
        topic = brief.parse_subtopic(config['subtopics'][0])
        paper = brief.Paper(title='Lane-changing crash prediction at the individual vehicle level',
                            source='Example Journal', year=2026, journal_if='12.7',
                            journal_quartile='Q1', journal_metric_year='2025',
                            journal_if_source='https://example.org/if',
                            journal_rank_source='https://example.org/rank')
        brief.score_paper(paper, config, topic)
        self.assertEqual(paper.scores['期刊会议质量'], 5)

    def test_daily_brief_has_metrics_but_no_pre_reading_outline(self):
        paper = brief.Paper(title='Example', journal_name='Example Journal',
                            journal_if='12.7', journal_quartile='Q1',
                            journal_metric_year='2025',
                            journal_if_source='https://example.org/if',
                            journal_rank_source='https://example.org/rank')
        md = brief.render_markdown('2026-09-15', {'topic_name': 'Example'},
                                   {'id': 'example', 'label': 'Example'}, paper, [paper], None)
        self.assertIn('12.7（2025 JIF）', md)
        self.assertNotIn('20 分钟精读提纲', md)
        self.assertNotIn('待 Codex 实时补写', md)

    def test_current_venues_have_verified_metrics(self):
        path = Path(__file__).resolve().parents[1] / '_references/journal-metrics.yml'
        metrics = brief.load_journal_metrics(path)
        for name in ('Frontiers of Engineering Management',
                     'World Electric Vehicle Journal',
                     'Communications in Transportation Research',
                     'Transportation Research Part C: Emerging Technologies',
                     'Accident Analysis & Prevention',
                     'Analytic Methods in Accident Research',
                     'IEEE Transactions on Intelligent Vehicles'):
            with self.subTest(name=name):
                paper = brief.Paper(title='Test', source=name)
                brief.apply_journal_metrics(paper, metrics)
                self.assertTrue(brief.verified_venue(paper), paper)

    def test_html_encoded_journal_name_matches_verified_metrics(self):
        path = Path(__file__).resolve().parents[1] / '_references/journal-metrics.yml'
        paper = brief.Paper(title='Warning study', source='Accident Analysis &amp; Prevention')
        brief.apply_journal_metrics(paper, brief.load_journal_metrics(path))
        self.assertEqual(paper.journal_if, '7.4')
        self.assertTrue(brief.verified_venue(paper))


if __name__ == '__main__':
    unittest.main()
