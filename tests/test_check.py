"""Check user workflows against isolated copies; never modify real learning data."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FrameworkChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / 'state'
        # Build an empty fixture from the template, independent of future real state.
        self.state.mkdir()
        (self.state / 'plans').mkdir()
        (self.state / 'weekly-reviews').mkdir()
        self.save('objective.json', self.template('objective'))
        self.save('goals.json', [])
        self.save('cards.json', [])
        self.events('assessment-log.jsonl', [])
        self.events('card-review-log.jsonl', [])

    def template(self, name):
        return json.loads((ROOT / 'templates' / f'{name}.json').read_text())

    def save(self, name, data):
        (self.state / name).write_text(json.dumps(data, ensure_ascii=False))

    def events(self, name, events):
        (self.state / name).write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in events))

    def run_check(self, ok=True, contains=None):
        before = {str(p.relative_to(self.state)): p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/check.py'), '--state', str(self.state)],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0 if ok else 1, proc.stdout + proc.stderr)
        if contains:
            self.assertIn(contains, proc.stdout + proc.stderr)
        after = {str(p.relative_to(self.state)): p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
        self.assertEqual(before, after, 'The checker must be read-only')

    def fixture(self):
        objective = self.template('objective')
        objective.update(title='Learn the selected method', weekly_hours=6, timezone='Europe/Moscow',
                         success_criteria=['Solve a new problem independently'],
                         review_budget_minutes_per_session=15, max_new_cards_per_session=3)
        self.save('objective.json', objective)
        goal = self.template('goal')
        goal.update(title='Explain the selected method independently', status='completed',
                    evidence_ids=['assessment-001'])
        goal['criteria'] = [{'id': 'criterion-1', 'description': 'Apply the method to a new case',
                             'verification': 'Independent solution with an explanation'}]
        assessment = self.template('assessment')
        assessment.update(occurred_at='2030-01-07T18:30:00+03:00', task='New practical problem',
                          rubric='Independent solution with an explanation', assistance_policy='No hints',
                          result='passed', artifact='local-note:solution-001')
        card = self.template('card')
        card.update(prompt='When is the method applicable?', answer='When its prerequisites are satisfied.',
                    source='local-note:verified-example', verified_at='2030-01-07T19:00:00+03:00', status='active')
        review = self.template('card-review')
        review.update(occurred_at='2030-01-09T19:00:00+03:00', rating='good')
        plan = self.template('plan')
        plan.update(week_id='2030-01-07', budget_hours=6, review_hours=1, assessment_hours=1, buffer_hours=1)
        plan['items'][0].update(expected_result=goal['title'], success_criteria=['Apply the method'],
                                assistance_policy='No hints', estimated_hours=3)
        report = self.template('weekly-review')
        report.update(week_id='2030-01-07', baseline_plan='2030-01-07.r1.json',
                      effective_plan='2030-01-07.r1.json', actual_hours=5,
                      completed=[goal['id']], assessment_ids=[assessment['id']], card_ids=[card['id']])
        self.save('goals.json', [goal]); self.save('cards.json', [card])
        self.events('assessment-log.jsonl', [assessment]); self.events('card-review-log.jsonl', [review])
        self.save('plans/2030-01-07.r1.json', plan)
        self.save('weekly-reviews/2030-01-07.r1.json', report)
        return goal, assessment, card, plan

    def test_empty_skeleton(self):
        self.run_check()

    def test_week_from_plan_to_evidence_and_manual_review(self):
        self.fixture()
        self.run_check()

    def test_unknown_card_goal_is_rejected(self):
        _, _, card, _ = self.fixture()
        card['goal_ids'] = ['missing']
        self.save('cards.json', [card])
        self.run_check(False, 'unknown reference')

    def test_parent_prerequisite_cycle_is_rejected(self):
        goal, _, _, _ = self.fixture()
        child = copy.deepcopy(goal)
        child.update(id='goal-002', status='draft', parent_id=goal['id'], depends_on=[goal['id']], evidence_ids=[])
        self.save('goals.json', [goal, child])
        self.run_check(False, 'cycle')

    def test_hint_assisted_success_cannot_complete_goal(self):
        _, event, _, _ = self.fixture()
        event['assistance'] = 'hints'
        self.events('assessment-log.jsonl', [event])
        self.run_check(False, 'independent supporting evidence')

    def test_corrected_success_cannot_still_be_used_as_evidence(self):
        goal, event, _, _ = self.fixture()
        correction = dict(event, id='assessment-002', result='failed', supersedes=event['id'])
        self.events('assessment-log.jsonl', [event, correction])
        self.run_check(False, 'unknown reference')
        goal.update(status='active', evidence_ids=[])
        self.save('goals.json', [goal])
        self.run_check()

    def test_replanning_keeps_baseline_and_checks_budget(self):
        _, _, _, plan = self.fixture()
        plan.update(revision=2, change_reason='Updated available study time', budget_hours=7)
        self.save('plans/2030-01-07.r2.json', plan)
        self.run_check()
        plan['budget_hours'] = 2
        self.save('plans/2030-01-07.r2.json', plan)
        self.run_check(False, 'exceeds the budget')

    def test_duplicate_id_is_rejected(self):
        goal, _, _, _ = self.fixture()
        self.save('goals.json', [goal, goal])
        self.run_check(False, 'duplicate ID')

    def test_missing_revision_is_rejected(self):
        _, _, _, plan = self.fixture()
        plan.update(revision=3, change_reason='Change')
        self.save('plans/2030-01-07.r3.json', plan)
        self.run_check(False, 'previous revision')

    def test_fake_scheduler_state_is_rejected(self):
        _, _, card, _ = self.fixture()
        card['scheduler'] = {'stability': 99}
        self.save('cards.json', [card])
        self.run_check(False, 'FSRS is not integrated yet')

    def test_malformed_json_fails_cleanly(self):
        (self.state / 'goals.json').write_text('{broken')
        self.run_check(False, 'ERROR:')


if __name__ == '__main__':
    unittest.main()
