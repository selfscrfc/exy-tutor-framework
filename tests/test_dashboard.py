"""Exercise dashboard HTTP, shared CLI state, and local connection management."""
from copy import deepcopy
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import test_workflow as fixtures
from exy.dashboard import DashboardServer

ROOT = Path(__file__).resolve().parents[1]


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.PilotWorkflow(methodName='runTest')
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.h.setup_pilot()
        self.other = self.h.path / 'second' / 'state'
        subprocess.run([sys.executable, str(ROOT / 'scripts/tutor.py'), '--state', str(self.other), 'init'],
                       check=True, capture_output=True)
        self.registry = self.h.path / 'instances.json'
        self.registry.write_text(json.dumps({'schema_version': 1, 'instances': {'first': str(self.h.state)}}))
        self.server = DashboardServer(self.registry, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.origin = self.server.origin
        with urlopen(self.origin) as response:
            self.token = re.search(r'name="exy-token" content="([^"]+)"', response.read().decode())[1]

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path, data=None, status=200, extra_headers=None):
        headers = {'Origin': self.origin, 'X-Exy-Token': self.token, 'Content-Type': 'application/json'}
        headers.update(extra_headers or {})
        request = Request(self.origin + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
        try:
            response = urlopen(request)
        except HTTPError as error:
            response = error
        with response:
            self.assertEqual(response.status, status)
            return json.loads(response.read())

    def test_connect_switch_and_disconnect_preserve_learning_records(self):
        before = deepcopy(self.h.read('goals.json'))
        self.assertEqual(self.request('/api/instance?name=first')['goals'], before)
        self.request('/api/connect', {'name': 'second', 'workspace': str(self.other.parent)})
        self.assertEqual({i['name'] for i in self.request('/api/instances')['instances']}, {'first', 'second'})
        self.assertEqual(self.request('/api/instance?name=second')['goals'], [])
        self.request('/api/connect', {'name': 'duplicate', 'workspace': str(self.other)}, status=400)
        self.request('/api/connect', {'name': 'first', 'workspace': str(self.other)}, status=400)
        self.request('/api/disconnect', {'name': 'second', 'expected_path': str(self.h.state)}, status=400)
        self.request('/api/disconnect', {'name': 'second', 'expected_path': str(self.other.resolve())})
        self.assertTrue((self.other / 'settings.json').is_file())
        self.assertEqual(self.h.read('goals.json'), before)
        self.assertEqual(len(self.request('/api/instances')['instances']), 1)

    def test_timer_reload_retry_cli_handoff_and_stale_version(self):
        request = {'instance': 'first', 'request_id': 'web-start', 'action': 'start', 'goal_id': 'goal-001',
                   'activity': 'Independent exercise', 'actor': 'dashboard'}
        timer = self.request('/api/timer', request)['result']
        self.assertTrue(self.request('/api/timer', request)['replayed'])
        self.assertEqual(self.request('/api/instance?name=first')['timers'][0]['id'], timer['id'])
        self.request('/api/disconnect', {'name': 'first', 'expected_path': str(self.h.state)}, status=400)
        pause = {'instance': 'first', 'request_id': 'web-pause', 'action': 'pause', 'actor': 'dashboard',
                 'timer_id': timer['id'], 'expected_version': 1}
        self.request('/api/timer', pause)
        self.request('/api/timer', dict(pause, request_id='stale'), status=400)
        self.request('/api/timer', dict(pause, action='stop', expected_version=2, request_id='web-stop'))
        self.assertEqual(self.request('/api/instance?name=first')['timers'], [])
        cli = [sys.executable, str(ROOT / 'scripts/tutor.py'), '--state', str(self.h.state)]
        result = subprocess.run(cli + ['time', 'start', '--actor', 'agent', '--request-id', 'agent-start', '--activity', 'Agent-led practice'],
                                capture_output=True, text=True, check=True)
        agent_timer = json.loads(result.stdout)
        self.assertEqual(self.request('/api/instance?name=first')['timers'][0]['owner'], 'agent')
        stop = {'instance': 'first', 'request_id': 'handoff', 'action': 'stop', 'actor': 'agent',
                'timer_id': agent_timer['id'], 'expected_version': 1}
        self.request('/api/timer', stop, status=400)
        self.request('/api/timer', dict(stop, handoff=True))
        self.assertEqual(len(self.h.read('time-entries.jsonl')), 2)
        self.assertGreater(self.request('/api/instance?name=first')['pace']['total_logged_hours'], 0)

    def test_host_origin_token_and_input_boundaries(self):
        body = {'name': 'second', 'workspace': str(self.other)}
        self.request('/api/connect', body, status=403, extra_headers={'Origin': 'https://untrusted.example'})
        self.request('/api/connect', body, status=403, extra_headers={'X-Exy-Token': 'wrong'})
        self.request('/api/instances', status=403, extra_headers={'Host': 'untrusted.example'})
        self.request('/api/connect', {'name': 'second', 'workspace': '/no/such/instance'}, status=400)
        self.request('/api/instance?name=unknown', status=400)
        self.request('/api/timer', [], status=400)
        self.request('/../../state/objective.json', status=404)
        self.assertEqual(len(self.request('/api/instances')['instances']), 1)

    def test_broken_connection_does_not_hide_healthy_workspaces(self):
        data = json.loads(self.registry.read_text())
        data['instances']['missing'] = '/no/such/workspace/state'
        self.registry.write_text(json.dumps(data))
        overview = self.request('/api/instances')['instances']
        self.assertNotIn('error', next(i for i in overview if i['name'] == 'first'))
        self.assertIn('error', next(i for i in overview if i['name'] == 'missing'))
        self.request('/api/disconnect', {'name': 'missing', 'expected_path': '/no/such/workspace/state'})

    @unittest.skipUnless(shutil.which('node'), 'Node is only needed for the browser-pattern regression')
    def test_workspace_name_pattern_is_valid_with_browser_unicode_sets(self):
        # Chrome uses the v flag for HTML patterns. An unescaped hyphen disabled validation.
        html = (ROOT / 'web/index.html').read_text()
        pattern = re.search(r'id="connect-name"[^>]*pattern="([^"]+)"', html)[1]
        result = subprocess.run(['node', '-e',
            "const assert=require('node:assert/strict'); const r=new RegExp('^(?:'+process.argv[1]+')$','v'); "
            "assert(r.test('exy-ml')); assert(r.test('learning_2')); assert(!r.test('bad name'));", pattern],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unknown_timezone_has_no_fabricated_daily_time(self):
        self.request('/api/connect', {'name': 'second', 'workspace': str(self.other)})
        snapshot = self.request('/api/instance?name=second')
        self.assertIsNone(snapshot['week']['timezone'])
        self.assertIsNone(snapshot['pace'])
        self.assertIsNone(snapshot['plan'])
