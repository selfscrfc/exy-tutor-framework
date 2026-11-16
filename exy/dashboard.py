"""Loopback dashboard over the same validated state and receipts used by MCP."""
from datetime import datetime, timedelta, timezone
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from exy import engine, timekeeping, workload
from exy.instances import InstanceService
from exy.store import ROOT, Store, atomic_write, encode


class Dashboard(InstanceService):
    def connect(self, name, workspace):
        engine.need(isinstance(name, str) and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', name),
                    'Use a short instance name containing letters, numbers, hyphens, or underscores')
        path = Path(workspace).expanduser().resolve()
        if (path / 'state' / 'settings.json').is_file():
            path = path / 'state'
        engine.need((path / 'settings.json').is_file(), 'Choose an initialized workspace or its state directory')
        with Store(path) as store:
            store.validate()
        with self.registry_lock():
            instances = self.mapping() if self.registry.exists() else {}
            engine.need(name not in instances or Path(instances[name]).expanduser().resolve() == path,
                        'This name is already connected to another workspace')
            engine.need(not any(key != name and Path(value).expanduser().resolve() == path for key, value in instances.items()),
                        'This workspace is already connected under another name')
            instances[name] = str(path)
            atomic_write(self.registry, encode({'schema_version': 1, 'instances': instances}))
        return {'name': name}

    def registry_lock(self):
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        lock = self.registry.with_suffix(self.registry.suffix + '.lock').open('a+')
        fcntl.flock(lock, fcntl.LOCK_EX)
        return lock

    def disconnect(self, name, expected_path):
        with self.registry_lock():
            instances = self.mapping()
            engine.need(instances.get(name) == expected_path, 'Connection changed; refresh before disconnecting')
            path = Path(expected_path).expanduser()
            if path.is_dir():
                with Store(path) as store:
                    engine.need(not timekeeping.timer_status(store, datetime.now(timezone.utc)),
                                'Stop running and paused timers before disconnecting this workspace')
            del instances[name]
            atomic_write(self.registry, encode({'schema_version': 1, 'instances': instances}))
        return {'name': name}

    def snapshot(self, instance):
        now = datetime.now(timezone.utc)
        with Store(self.state_for(instance)) as store:
            store.validate()
            objective, foundation = store.get('objective.json'), store.get('foundation.json')
            zone_name = objective['timezone'] or foundation.get('timezone')
            today = now.astimezone(ZoneInfo(zone_name) if zone_name else timezone.utc).date()
            plans = {}
            for name in store.files:
                if name.startswith('plans/'):
                    plan = store.get(name)
                    if plan['revision'] > plans.get(plan['week_id'], {}).get('revision', 0):
                        plans[plan['week_id']] = plan
            active_plan = next((p for day, p in sorted(plans.items(), reverse=True)
                                if datetime.fromisoformat(day).date() <= today <= datetime.fromisoformat(day).date() + timedelta(days=6)), None)
            start = datetime.fromisoformat(active_plan['week_id']).date() if active_plan else today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
            entries = timekeeping.active_entries(store)
            timers = timekeeping.timer_status(store, now)
            for timer in timers:
                timer['saved_seconds'] = sum(timekeeping.seconds(e) for e in entries if e['timer_id'] == timer['id'])
            goal_hours = {}
            for entry in entries:
                if entry['goal_id']:
                    goal_hours[entry['goal_id']] = goal_hours.get(entry['goal_id'], 0) + timekeeping.seconds(entry) / 3600
            return {'name': instance, 'state_revision': self.revision(store), 'server_time': now.isoformat(),
                    'objective': objective, 'foundation': foundation, 'goals': store.get('goals.json'),
                    'plan': active_plan, 'goal_hours': goal_hours, 'timers': timers,
                    'sessions': [s for s in store.get('sessions.json') if s['ended_at'] is None],
                    'week': {'start': start.isoformat(), 'end': end.isoformat(), 'today': today.isoformat(), 'timezone': zone_name},
                    'pace': workload.pace(store, start.isoformat(), end.isoformat(), now) if zone_name else None,
                    'workload': workload.latest(store)}

    def overview(self):
        instances = self.mapping() if self.registry.exists() else {}
        result = []
        for name, path in instances.items():
            try:
                value = self.snapshot(name)
                leaves = [g for g in value['goals'] if not any(c['parent_id'] == g['id'] and c['status'] != 'dropped' for c in value['goals']) and g['status'] != 'dropped']
                result.append({'name': name, 'path': path, 'title': value['objective']['title'],
                               'foundation_status': value['foundation']['status'],
                               'completed': sum(g['status'] == 'completed' for g in leaves), 'total': len(leaves),
                               'timers': value['timers']})
            except (ValueError, OSError, KeyError, TypeError) as error:
                result.append({'name': name, 'path': path, 'error': str(error), 'timers': []})
        return {'instances': result}

    def timer(self, data):
        instance, request_id = data['instance'], data['request_id']
        action = data['action']
        engine.need(action in {'start', 'pause', 'resume', 'stop'}, 'Unknown timer action')
        actor = data.get('actor', 'dashboard')
        engine.need(actor == 'dashboard' or data.get('handoff') is True, 'Confirm control of a timer started by another agent')
        payload = {'action': action, 'actor': actor, 'timer_id': data.get('timer_id'),
                   'expected_version': data.get('expected_version'), 'goal_id': data.get('goal_id'),
                   'session_id': data.get('session_id'), 'activity': data.get('activity'),
                   'confirm_long': data.get('confirm_long', False)}
        return self.mutate(instance, request_id, 'manage_timer', payload, None,
                           lambda store, now: timekeeping.mutate_timer(store, request_id=request_id, now=now, **payload))


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, registry, port=8765):
        super().__init__(('127.0.0.1', port), DashboardHandler)
        self.dashboard = Dashboard(registry)
        self.token = secrets.token_urlsafe(32)
        self.origin = f'http://127.0.0.1:{self.server_port}'


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, value, content_type='application/json; charset=utf-8'):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode() if content_type.startswith('application/json') else value
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def trusted_host(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def do_GET(self):
        if not self.trusted_host():
            return self.reply(403, {'error': 'Use the printed local dashboard address'})
        route = urlsplit(self.path)
        try:
            if route.path == '/api/instances':
                return self.reply(200, self.server.dashboard.overview())
            if route.path == '/api/instance':
                return self.reply(200, self.server.dashboard.snapshot(parse_qs(route.query)['name'][0]))
            assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/style.css': ('style.css', 'text/css; charset=utf-8'), '/favicon.svg': ('favicon.svg', 'image/svg+xml')}
            if route.path not in assets:
                return self.reply(404, {'error': 'Not found'})
            filename, mime = assets[route.path]
            body = (ROOT / 'web' / filename).read_bytes()
            if filename == 'index.html':
                body = body.replace(b'__EXY_TOKEN__', self.server.token.encode())
            return self.reply(200, body, mime)
        except (ValueError, OSError, KeyError, TypeError) as error:
            self.reply(400, {'error': str(error)})

    def do_POST(self):
        if (not self.trusted_host() or self.headers.get('Origin') != self.server.origin or
                not secrets.compare_digest(self.headers.get('X-Exy-Token', ''), self.server.token)):
            return self.reply(403, {'error': 'Reload the local dashboard before making changes'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            engine.need(0 < length <= 32768, 'Request body is missing or too large')
            engine.need(self.headers.get('Content-Type', '').split(';')[0] == 'application/json', 'Expected JSON')
            data = json.loads(self.rfile.read(length))
            engine.need(isinstance(data, dict), 'Expected a JSON object')
            dashboard = self.server.dashboard
            if self.path == '/api/timer':
                result = dashboard.timer(data)
            elif self.path == '/api/connect':
                result = dashboard.connect(data['name'], data['workspace'])
            elif self.path == '/api/disconnect':
                result = dashboard.disconnect(data['name'], data['expected_path'])
            else:
                return self.reply(404, {'error': 'Not found'})
            self.reply(200, result)
        except (ValueError, OSError, KeyError, TypeError) as error:
            self.reply(400, {'error': str(error)})
