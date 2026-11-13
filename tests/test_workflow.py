"""Exercise the public CLI in temporary instances, including restarts and failures."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from exy.scheduling import advance
from exy.store import Store

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/tutor.py'
DAY = '2030-01-07'


class PilotWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.state = self.path / 'state'
        self.cli('init')

    def cli(self, *args, at=DAY + 'T10:00:00+00:00', ok=True):
        result = subprocess.run([sys.executable, str(CLI), '--state', str(self.state), '--at', at, *args],
                                capture_output=True, text=True, cwd=self.path)
        self.assertEqual(result.returncode, 0 if ok else 1, result.stdout + result.stderr)
        return json.loads(result.stdout) if ok else result.stderr

    def template(self, name):
        return json.loads((ROOT / 'templates' / f'{name}.json').read_text())

    def file(self, data):
        path = self.path / 'input.json'
        path.write_text(json.dumps(data))
        return str(path)

    def read(self, name):
        path = self.state / name
        if name.endswith('.jsonl'):
            return [json.loads(s) for s in path.read_text().splitlines() if s]
        return json.loads(path.read_text())

    def setup_pilot(self):
        foundation = self.template('foundation')
        foundation.update(status='confirmed', objective='Apply a selected method independently',
                          success_criteria=['Solve a new problem'], weekly_hours=6, timezone='UTC',
                          confirmed_at=DAY + 'T09:00:00+00:00', confirmation_quote='Test fixture: agreed.')
        foundation['scope']['included'] = ['Selected method']
        self.cli('foundation', 'save', '--file', self.file(foundation))
        self.cli('configure', '--file', self.file({'review_budget_minutes_per_session': 2, 'max_new_cards_per_session': 1}))
        for identifier in ('goal-001', 'goal-002'):
            goal = self.template('goal')
            goal.update(id=identifier, title='Apply method ' + identifier, status='ready')
            goal['criteria'] = [{'id': 'criterion-1', 'description': 'Solve a new problem independently', 'verification': 'Executable artifact'}]
            self.cli('goal', 'add', '--file', self.file(goal))
        plan = self.template('plan')
        item = plan['items'][0]
        item.update(expected_result='Independent solution', success_criteria=['Correct result'],
                    assistance_policy='Documentation only', activities=['Worked example, then a fresh problem'], estimated_hours=2)
        plan['items'].append(dict(item, goal_id='goal-002'))
        plan.update(week_id=DAY, budget_hours=6, review_hours=0.5, assessment_hours=0.5, buffer_hours=1)
        self.cli('plan', 'save', '--file', self.file(plan))
        for number in (1, 2):
            card = self.template('card')
            card.update(id=f'card-00{number}', prompt=f'What is condition {number}?', answer=f'Answer {number}',
                        source='fixture:verified-note', status='active', verified_at=DAY + 'T09:00:00+00:00')
            self.cli('card', 'add', '--file', self.file(card))
        return self.cli('session', 'start', '--week', DAY)['session']['id']

    def review(self, day=DAY):
        shown = self.cli('review', 'next', at=day+'T10:01:00+00:00')
        self.assertNotIn('answer', shown)
        self.cli('review', 'answer', '--response', 'My attempted answer', at=day+'T10:02:00+00:00')
        return self.cli('review', 'rate', 'good', '--seconds', '60', at=day+'T10:03:00+00:00')

    def test_complete_week_resume_fsrs_and_carryover(self):
        session = self.setup_pilot()
        before = deepcopy(self.read('cards.json')[0])
        result = self.review()
        settings = self.read('settings.json')
        expected, _ = advance(before, 'good', datetime(2030, 1, 7, 10, 3, tzinfo=timezone.utc), 60, settings)
        self.assertEqual(result['due_at'], expected['due'])
        self.assertEqual(self.read('cards.json')[0]['scheduler'], expected)
        self.cli('session', 'checkpoint', '--note', 'Continue with the independent problem', '--minutes', '20',
                 at=DAY+'T10:25:00+00:00')
        resumed = self.cli('session', 'resume', at=DAY+'T10:26:00+00:00')
        self.assertEqual(resumed['session']['id'], session)
        self.assertEqual(resumed['next_step'], 'Continue with the independent problem')
        assessment = self.template('assessment')
        assessment.update(task='Fresh problem', rubric='Correct independent solution', assistance_policy='Documentation only',
                          assistance='allowed_tools', result='passed', artifact='fixture:solution', duration_minutes=20)
        self.cli('assessment', 'add', '--file', self.file(assessment), '--session', session, '--complete',
                 at=DAY+'T10:50:00+00:00')
        self.cli('session', 'end', '--note', 'Work on the second goal next', '--minutes', '60', at=DAY+'T11:00:00+00:00')
        baseline = (self.state / f'plans/{DAY}.r1.json').read_bytes()
        report = self.cli('week', 'close', '--week', DAY, at='2030-01-14T10:00:00+00:00')
        self.assertEqual(report['actual_hours'], 1)
        self.assertEqual(report['completed'], ['goal-001'])
        self.assertEqual(report['assessment_ids'], ['assessment-001'])
        carry = self.cli('plan', 'carry', '--from-week', DAY, '--to-week', '2030-01-14')
        self.assertEqual([i['goal_id'] for i in carry['items']], ['goal-002'])
        self.cli('plan', 'save', '--file', self.file(carry))
        resumed = self.cli('session', 'start', '--week', '2030-01-14', at='2030-01-14T10:00:00+00:00')
        self.assertEqual(resumed['next_step'], 'Work on the second goal next')
        self.assertEqual(resumed['review_queue']['cards'][0]['id'], 'card-001')
        self.assertEqual((self.state / f'plans/{DAY}.r1.json').read_bytes(), baseline)
        self.cli('check')

    def test_answer_first_budget_and_new_card_limits(self):
        self.setup_pilot()
        self.assertEqual(len(self.cli('review', 'queue')['cards']), 1)
        self.cli('review', 'next')
        self.assertIn('before rating', self.cli('review', 'rate', 'good', '--seconds', '60', ok=False))
        self.cli('review', 'answer', '--response', 'I cannot recall it')
        self.cli('review', 'rate', 'again', '--seconds', '120', at=DAY+'T10:03:00+00:00')
        queue = self.cli('review', 'queue', at=DAY+'T11:00:00+00:00')
        self.assertEqual(queue['cards'], [])
        self.assertEqual(queue['remaining_seconds'], 0)
        self.assertEqual(len(self.read('card-review-log.jsonl')), 1)
        self.cli('review', 'rate', 'good', '--seconds', '10', ok=False)
        self.assertEqual(len(self.read('card-review-log.jsonl')), 1)

    def test_invalid_goal_completion_rolls_back_every_file(self):
        session = self.setup_pilot()
        before = {str(p): p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
        assessment = self.template('assessment')
        assessment.update(task='Task', rubric='Rubric', assistance_policy='No hints', assistance='hints',
                          result='passed', artifact='fixture:answer')
        self.cli('assessment', 'add', '--file', self.file(assessment), '--session', session, '--complete', ok=False)
        after = {str(p): p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_interrupted_multifile_commit_recovers(self):
        self.setup_pilot()
        self.cli('review', 'next')
        self.cli('review', 'answer', '--response', 'Answer')
        from exy import engine
        original_apply = Store.apply_file
        writes = []
        def interrupt(store, name, content):
            original_apply(store, name, content)
            writes.append(name)
            if len(writes) == 1:
                raise KeyboardInterrupt('Simulated process interruption')
        with self.assertRaises(KeyboardInterrupt):
            with Store(self.state) as store:
                engine.review_rate(store, None, 'good', 60, datetime(2030, 1, 7, 10, 3, tzinfo=timezone.utc))
                with patch.object(Store, 'apply_file', interrupt):
                    store.commit()
        self.assertTrue((self.state / '.pending-transaction.json').exists())
        self.cli('check')
        self.assertFalse((self.state / '.pending-transaction.json').exists())
        self.assertEqual(len(self.read('card-review-log.jsonl')), 1)
        self.assertEqual(self.read('cards.json')[0]['scheduler'], self.read('card-review-log.jsonl')[0]['after'])
        self.assertIsNone(self.read('sessions.json')[0]['pending_review'])

    def test_old_history_and_plan_revisions_are_protected(self):
        self.setup_pilot()
        self.review()
        original = (self.state / 'card-review-log.jsonl').read_bytes()
        with Store(self.state) as store:
            store.put('card-review-log.jsonl', [])
            with self.assertRaisesRegex(ValueError, 'append-only'):
                store.commit()
        self.assertEqual((self.state / 'card-review-log.jsonl').read_bytes(), original)
        plan = self.read(f'plans/{DAY}.r1.json')
        plan.update(budget_hours=7, change_reason='More time available')
        revised = self.cli('plan', 'save', '--file', self.file(plan))
        self.assertEqual(revised['plan']['revision'], 2)
        self.assertEqual(self.read(f'plans/{DAY}.r1.json')['budget_hours'], 6)
        with Store(self.state) as store:
            store.put(f'plans/{DAY}.r1.json', plan)
            with self.assertRaisesRegex(ValueError, 'immutable'):
                store.commit()

    def test_unconfirmed_foundation_cannot_schedule_week(self):
        plan = self.template('plan')
        plan['week_id'] = DAY
        self.assertIn('foundation', self.cli('plan', 'save', '--file', self.file(plan), ok=False))

    def test_suspension_skip_and_duplicate_cards(self):
        self.setup_pilot()
        self.cli('review', 'next')
        self.cli('card', 'status', 'card-001', 'suspended')
        self.cli('review', 'answer', '--response', 'Answer', ok=False)
        self.cli('review', 'skip')
        self.assertEqual(self.read('card-review-log.jsonl'), [])
        self.assertEqual(self.cli('review', 'next')['card_id'], 'card-002')
        duplicate = self.template('card')
        duplicate.update(id=None, prompt='What is condition 2?')
        self.cli('card', 'add', '--file', self.file(duplicate), ok=False)

    def test_concurrent_writers_serialize_without_lost_updates(self):
        code = """import sys,time
from exy.store import Store
with Store(sys.argv[1]) as s:
 d=s.get('objective.json')
 d['constraints'].append(sys.argv[2])
 time.sleep(0.1)
 s.put('objective.json',d)
 s.commit()
"""
        processes = [subprocess.Popen([sys.executable, '-c', code, str(self.state), label], cwd=ROOT,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE) for label in ('first', 'second')]
        for process in processes:
            _, error = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, error.decode())
        self.assertEqual(set(self.read('objective.json')['constraints']), {'first', 'second'})


if __name__ == '__main__':
    unittest.main()
