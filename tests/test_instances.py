"""Instance isolation and non-destructive legacy upgrades."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from exy import engine
from exy.store import Store

ROOT = Path(__file__).resolve().parents[1]


class InstanceTests(unittest.TestCase):
    def test_creation_is_isolated_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / 'learner'
            original = (ROOT / 'state/objective.json').read_bytes()
            command = [sys.executable, str(ROOT / 'scripts/create_instance.py'), str(destination),
                       '--objective', 'Prepare for a technical internship']
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((destination / '.git').is_dir())
            self.assertTrue((destination / '.agents/skills/exy-clarify-goal/SKILL.md').is_file())
            result = subprocess.run([sys.executable, str(destination / 'tutor.py'), 'status'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            state = json.loads(result.stdout)
            self.assertEqual(state['foundation']['status'], 'draft')
            self.assertIsNone(state['objective']['weekly_hours'])
            self.assertEqual(state['goal_counts'], {})
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('will not be overwritten', result.stderr)
            self.assertEqual((ROOT / 'state/objective.json').read_bytes(), original)
            result = subprocess.run([sys.executable, str(destination / 'tutor.py'), '--state', str(ROOT / 'state'), 'status'],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_legacy_upgrade_preserves_manual_history(self):
        with tempfile.TemporaryDirectory() as name:
            state = Path(name)
            for folder in ('plans', 'weekly-reviews'):
                (state / folder).mkdir()
            def template(kind):
                return json.loads((ROOT / 'templates' / f'{kind}.json').read_text())
            goal = template('goal')
            goal['title'] = 'Known method'
            card = template('card')
            card.update(prompt='Question', answer='Answer', source='fixture', status='active',
                        verified_at='2030-01-07T09:00:00+00:00')
            review = template('card-review')
            review.update(occurred_at='2030-01-07T10:00:00+00:00', rating='good')
            for filename, content in [('objective.json', template('objective')), ('goals.json', [goal]), ('cards.json', [card])]:
                (state / filename).write_text(json.dumps(content))
            (state / 'assessment-log.jsonl').write_text('')
            (state / 'card-review-log.jsonl').write_text(json.dumps(review)+'\n')
            before = (state / 'card-review-log.jsonl').read_bytes()
            with Store(state) as store:
                engine.init(store)
                store.commit()
            self.assertEqual((state / 'card-review-log.jsonl').read_bytes(), before)
            imported = json.loads((state / 'cards.json').read_text())[0]
            self.assertEqual(imported['scheduler']['last_review'], review['occurred_at'])
            self.assertIn('imported_at', imported)
            with Store(state) as store:
                engine.init(store)
                store.commit()
            self.assertEqual(json.loads((state / 'cards.json').read_text())[0], imported)


if __name__ == '__main__':
    unittest.main()
