"""Auditable focus intervals with resumable timers and retry-safe mutations."""
from copy import deepcopy
from datetime import datetime, time, timedelta

from exy.engine import fingerprint, lookup, need, save_session, uid
from exy.scheduling import parse_time


def initialize(store):
    for name in ('timers.json', 'time-entries.jsonl', 'time-events.jsonl', 'workload-log.jsonl', 'rpc-log.jsonl'):
        if name not in store.files:
            store.put(name, [])


def active_entries(store):
    entries = store.get('time-entries.jsonl', [])
    replaced = {entry.get('supersedes') for entry in entries if entry.get('supersedes')}
    return [entry for entry in entries if entry['id'] not in replaced]


def seconds(entry):
    return (parse_time(entry['ended_at']) - parse_time(entry['started_at'])).total_seconds()


def check_link(store, goal_id, session_id):
    if goal_id:
        lookup(store.get('goals.json'), goal_id)
    if session_id:
        session = lookup(store.get('sessions.json'), session_id)
        need(session['ended_at'] is None, 'Cannot add time to an ended session')
        need(goal_id is None or goal_id in session['goal_ids'], 'Goal is outside this session')
        previous = [entry for entry in active_entries(store) if entry.get('session_id') == session_id]
        need(previous or session['actual_minutes'] == 0, 'This session already uses manual totals; start a new session to use interval tracking')


def sync_session(store, session_id, now):
    if not session_id:
        return
    session = lookup(store.get('sessions.json'), session_id)
    session['time_tracking'] = 'intervals'
    session['actual_minutes'] = sum(seconds(e) for e in active_entries(store) if e.get('session_id') == session_id) / 60
    save_session(store, session, now, 'time-recorded')


def append_interval(store, start, end, goal_id, session_id, activity, actor, now, timer_id=None,
                    supersedes=None, reason=None):
    need(start < end <= now, 'Time entries need a positive interval ending no later than now')
    need(activity.strip() and actor.strip(), 'Activity and actor are required')
    check_link(store, goal_id, session_id)
    if session_id:
        session = lookup(store.get('sessions.json'), session_id)
        need(start >= parse_time(session['started_at']), 'Time entry predates the session')
    if supersedes:
        old = lookup(active_entries(store), supersedes)
        need(old.get('session_id') == session_id and old.get('goal_id') == goal_id,
             'A correction must preserve its session and goal attribution')
        need(reason and reason.strip(), 'A correction requires a reason')
    for entry in active_entries(store):
        if entry['id'] != supersedes:
            need(end <= parse_time(entry['started_at']) or start >= parse_time(entry['ended_at']),
                 'Time intervals overlap; correct the existing entry instead of counting it twice')
    for timer in store.get('timers.json', []):
        if timer['status'] == 'running' and timer['id'] != timer_id:
            need(end <= parse_time(timer['running_since']), 'Entry overlaps a running timer')
    estimate = deepcopy(lookup(store.get('goals.json'), goal_id)['estimate_hours']) if goal_id else None
    entry = {'id': uid('time'), 'started_at': start.isoformat(), 'ended_at': end.isoformat(),
             'recorded_at': now.isoformat(), 'goal_id': goal_id, 'session_id': session_id,
             'activity': activity, 'actor': actor, 'timer_id': timer_id, 'supersedes': supersedes,
             'reason': reason, 'estimate_hours_snapshot': estimate}
    store.append('time-entries.jsonl', entry)
    sync_session(store, session_id, now)
    return entry


def mutate_timer(store, action, actor, request_id, now, timer_id=None, expected_version=None,
                 goal_id=None, session_id=None, activity=None, confirm_long=False):
    initialize(store)
    need(actor and request_id, 'Actor and a stable request_id are required')
    payload = dict(action=action, actor=actor, timer_id=timer_id, expected_version=expected_version,
                   goal_id=goal_id, session_id=session_id, activity=activity, confirm_long=confirm_long)
    request_hash = fingerprint(payload)
    for event in store.get('time-events.jsonl'):
        if event['request_id'] == request_id:
            need(event['request_hash'] == request_hash, 'request_id was already used with different arguments')
            return event['result']
    timers = store.get('timers.json')
    if action == 'start':
        need(not any(t['status'] == 'running' for t in timers), 'Another timer is already running in this instance')
        need(activity and activity.strip(), 'Describe the activity')
        check_link(store, goal_id, session_id)
        if session_id:
            need(now >= parse_time(lookup(store.get('sessions.json'), session_id)['started_at']), 'Timer predates session')
        need(all(parse_time(entry['ended_at']) <= now for entry in active_entries(store)), 'Timer would overlap a recorded interval')
        timer = {'id': uid('timer'), 'version': 1, 'owner': actor, 'status': 'running',
                 'goal_id': goal_id, 'session_id': session_id, 'activity': activity,
                 'started_at': now.isoformat(), 'updated_at': now.isoformat(), 'running_since': now.isoformat()}
        timers.append(timer)
    else:
        need(timer_id and expected_version is not None, 'timer_id and expected_version are required')
        timer = lookup(timers, timer_id)
        need(timer['owner'] == actor, 'Timer belongs to another actor; use that actor identity only for an explicit handoff')
        need(timer['version'] == expected_version, 'Stale timer version; refresh status before changing it')
        need(now >= parse_time(timer['updated_at']), 'Timer event predates its latest update')
        if action == 'resume':
            need(timer['status'] == 'paused', 'Only a paused timer can resume')
            need(not any(t['status'] == 'running' for t in timers), 'Another timer is already running')
            check_link(store, timer['goal_id'], timer['session_id'])
            need(all(parse_time(e['ended_at']) <= now for e in active_entries(store)), 'Timer would overlap recorded time')
            timer.update(status='running', running_since=now.isoformat())
        elif action in {'pause', 'stop'}:
            need(timer['status'] == 'running' or (action == 'stop' and timer['status'] == 'paused'), 'Invalid timer transition')
            if timer['status'] == 'running':
                start = parse_time(timer['running_since'])
                need((now - start).total_seconds() <= 4 * 3600 or confirm_long,
                     'Timer ran for over four hours; confirm the interval explicitly or correct the stop time')
                append_interval(store, start, now, timer['goal_id'], timer['session_id'], timer['activity'], actor,
                                now, timer_id=timer['id'])
            timer.update(status='paused' if action == 'pause' else 'stopped', running_since=None)
        else:
            raise ValueError('Unknown timer action')
        timer.update(version=timer['version'] + 1, updated_at=now.isoformat())
    store.put('timers.json', timers)
    result = deepcopy(timer)
    store.append('time-events.jsonl', {'id': uid('timer-event'), 'request_id': request_id,
                                      'request_hash': request_hash, 'occurred_at': now.isoformat(),
                                      'timer_id': timer['id'], 'action': action, 'result': result})
    return result


def timer_status(store, now):
    return [{**timer, 'uncommitted_seconds': max(0, (now - parse_time(timer['running_since'])).total_seconds())
             if timer['status'] == 'running' else 0} for timer in store.get('timers.json', []) if timer['status'] != 'stopped']


def log_time(store, data, actor, request_id, now):
    initialize(store)
    need(actor and request_id, 'Actor and request_id are required')
    request_hash = fingerprint({'data': data, 'actor': actor})
    for event in store.get('time-events.jsonl'):
        if event['request_id'] == request_id:
            need(event['request_hash'] == request_hash, 'request_id was already used with different arguments')
            return event['result']
    allowed = {'started_at', 'ended_at', 'goal_id', 'session_id', 'activity', 'supersedes', 'reason'}
    need(set(data) <= allowed, 'Unknown time-entry fields')
    result = append_interval(store, parse_time(data['started_at']), parse_time(data['ended_at']), data.get('goal_id'),
                             data.get('session_id'), data['activity'], actor, now,
                             supersedes=data.get('supersedes'), reason=data.get('reason'))
    store.append('time-events.jsonl', {'id': uid('timer-event'), 'request_id': request_id,
                                      'request_hash': request_hash, 'occurred_at': now.isoformat(),
                                      'timer_id': None, 'action': 'log', 'result': result})
    return result


def daily_totals(store, start_date, end_date, zone):
    result = {}
    current = start_date
    entries = active_entries(store)
    while current <= end_date:
        lo = datetime.combine(current, time.min, zone)
        hi = datetime.combine(current + timedelta(days=1), time.min, zone)
        # Work in UTC to handle days whose wall-clock length is not 24 hours.
        from datetime import timezone
        lo, hi = lo.astimezone(timezone.utc), hi.astimezone(timezone.utc)
        total = sum(max(0, (min(hi, parse_time(e['ended_at'])) - max(lo, parse_time(e['started_at']))).total_seconds()) for e in entries)
        result[current.isoformat()] = round(total / 3600, 6)
        current += timedelta(days=1)
    return result
