"""Validation for optional workload and interval-tracking records."""
from datetime import date, timedelta
import json


def validate_time_state(state, goals, sessions, plans, foundation):
    from scripts.check import require, timestamp, number, references
    from exy.scheduling import parse_time
    def read(name):
        path = state / name
        if not path.exists():
            return []
        text = path.read_text()
        return [json.loads(line) for line in text.splitlines() if line.strip()] if name.endswith('.jsonl') else json.loads(text)
    timers, entries, events = read('timers.json'), read('time-entries.jsonl'), read('time-events.jsonl')
    session_ids = {s['id'] for s in sessions}
    for name, values in [('timer', timers), ('time entry', entries), ('time event', events), ('workload', read('workload-log.jsonl'))]:
        require(isinstance(values, list), f'{name} records must be a list')
        ids = [v['id'] for v in values]
        require(len(ids) == len(set(ids)), f'Duplicate {name} ID')
    require(sum(t['status'] == 'running' for t in timers) <= 1, 'Multiple timers are running')
    seen, replaced = {}, set()
    for entry in entries:
        for key in ('started_at', 'ended_at', 'recorded_at'):
            timestamp(entry[key], 'time entry')
        require(parse_time(entry['started_at']) < parse_time(entry['ended_at']) <= parse_time(entry['recorded_at']), 'Invalid time interval')
        if entry['goal_id']:
            references([entry['goal_id']], goals, 'time entry')
        require(entry['session_id'] is None or entry['session_id'] in session_ids, 'Unknown time-entry session')
        if entry['supersedes']:
            old = seen.get(entry['supersedes'])
            require(old is not None and old['id'] not in replaced and entry['reason'], 'Invalid time correction')
            require((old['goal_id'], old['session_id']) == (entry['goal_id'], entry['session_id']), 'Correction changes time attribution')
            replaced.add(old['id'])
        seen[entry['id']] = entry
    current = sorted((e for e in entries if e['id'] not in replaced), key=lambda e: parse_time(e['started_at']))
    for previous, following in zip(current, current[1:]):
        require(parse_time(previous['ended_at']) <= parse_time(following['started_at']), 'Overlapping time entries')
    for timer in timers:
        require(timer['status'] in {'running', 'paused', 'stopped'}, 'Invalid timer status')
        require(type(timer['version']) is int and timer['version'] > 0 and timer['owner'], 'Invalid timer version or owner')
        if timer['goal_id']:
            references([timer['goal_id']], goals, 'timer')
        require(timer['session_id'] is None or timer['session_id'] in session_ids, 'Unknown timer session')
        timestamp(timer['started_at'], 'timer'); timestamp(timer['updated_at'], 'timer')
        if timer['status'] == 'running':
            timestamp(timer['running_since'], 'timer')
            require(all(parse_time(e['ended_at']) <= parse_time(timer['running_since']) for e in current), 'Running timer overlaps recorded time')
        else:
            require(timer['running_since'] is None, 'Stopped/paused timer has a running interval')
        related = [e for e in events if e['timer_id'] == timer['id']]
        require(related and related[-1]['result'] == timer, 'Timer does not match its history')
    requests = [event['request_id'] for event in events]
    require(len(requests) == len(set(requests)), 'Duplicate time request ID')
    for session in sessions:
        if session.get('time_tracking') == 'intervals':
            actual = sum((parse_time(e['ended_at'])-parse_time(e['started_at'])).total_seconds()/60
                         for e in current if e['session_id'] == session['id'])
            require(abs(actual-session['actual_minutes']) < 1e-6, 'Session total differs from its interval ledger')
    for plan in plans.values():
        if 'daily_hours' not in plan:
            continue
        daily = plan['daily_hours']
        require(isinstance(daily, dict) and len(daily) == 7, 'Daily plan must cover all seven dates of its week')
        expected = {(date.fromisoformat(plan['week_id'])+timedelta(days=i)).isoformat() for i in range(7)}
        require(set(daily) == expected, 'Daily plan dates do not match the planned week')
        for hours in daily.values():
            number(hours, 'daily hours', nullable=False)
            require(hours <= 24, 'Daily plan exceeds 24 hours')
        require(plan['budget_hours'] is not None and abs(sum(daily.values())-plan['budget_hours']) < 1e-5,
                'Daily allocations must sum to the weekly budget')
    workload = read('workload-log.jsonl')
    if foundation.get('workload_analysis_id'):
        require(any(a['id'] == foundation['workload_analysis_id'] for a in workload), 'Unknown foundation workload analysis')
    for analysis in workload:
        require(analysis['status'] in {'insufficient_evidence', 'estimated'}, 'Unknown workload status')
        timestamp(analysis['created_at'], 'workload analysis')
        require(analysis['is_user_commitment'] is False, 'A recommendation is not a user commitment')
    requests = [event['request_id'] for event in read('rpc-log.jsonl')]
    require(len(requests) == len(set(requests)), 'Duplicate MCP request ID')
