"""Additional invariants for operational state; legacy skeletons remain readable."""
from datetime import date
from zoneinfo import ZoneInfo
from fsrs import Card, Scheduler

from exy.scheduling import VERSION, parse_time


def validate_runtime(state, objective, goals, cards, assessments, reviews, plans):
    from scripts.check import read_json, require, shape, number, timestamp, references, ROOT
    settings = read_json(state / 'settings.json')
    require(settings['schema_version'] == 1 and settings['scheduler_version'] == VERSION,
            'Unsupported runtime/scheduler version; use the pinned dependencies')
    Scheduler.from_dict(settings['scheduler'])
    number(settings['estimated_review_seconds'], 'estimated_review_seconds', nullable=False)
    require(settings['estimated_review_seconds'] > 0, 'Review duration estimate must be positive')
    for key in ('review_budget_minutes_per_session', 'max_new_cards_per_session'):
        if objective[key] is not None:
            number(objective[key], key, nullable=False)
    require(objective['max_new_cards_per_session'] is None or type(objective['max_new_cards_per_session']) is int,
            'New-card limit must be an integer')
    if objective['timezone'] is not None:
        ZoneInfo(objective['timezone'])
    if objective['target_date'] is not None:
        date.fromisoformat(objective['target_date'])
    foundation = read_json(state / 'foundation.json')
    shape(foundation, read_json(ROOT / 'templates/foundation.json'), 'foundation')
    require(foundation['schema_version'] == 1, 'Unknown foundation schema version')
    require(foundation['status'] in {'draft', 'confirmed'}, 'Invalid foundation status')
    require(foundation['baseline']['diagnostic_status'] in {'pending', 'completed', 'waived'}, 'Invalid diagnostic status')
    number(foundation['weekly_hours'], 'foundation.weekly_hours')
    timestamp(foundation['confirmed_at'], 'foundation.confirmed_at', nullable=True)
    if foundation['status'] == 'confirmed':
        require(foundation['objective'] and foundation['success_criteria'] and foundation['scope']['included']
                and foundation['weekly_hours'] and foundation['timezone'] and not foundation['open_questions']
                and foundation['confirmation_quote'] and foundation['confirmed_at'],
                'A confirmed foundation needs scope, outcomes, capacity, time zone, and an explicit user confirmation')
        ZoneInfo(foundation['timezone'])
    for identifier, card in cards.items():
        require(isinstance(card['scheduler'], dict), f'{identifier}: missing library-generated FSRS state')
        decoded = Card.from_dict(card['scheduler'])
        require(decoded.due.isoformat() == card['due_at'], f'{identifier}: due date differs from scheduler state')
        timestamp(card['created_at'], identifier)
        if decoded.last_review:
            require(decoded.last_review <= decoded.due, f'{identifier}: due date precedes its review')
        related = [r for r in reviews.values() if r['card_id'] == identifier and r['scheduler_version'] is not None]
        previous = None
        for review in related:
            require(review['scheduler_version'] == VERSION and review['supersedes'] is None,
                    'Scheduled reviews cannot be superseded without replaying the schedule')
            require(review['after']['last_review'] == review['occurred_at'], 'Review timestamp differs from FSRS state')
            if previous:
                require(review['before'] == previous['after'], 'Broken FSRS review history chain')
                require(parse_time(review['occurred_at']) > parse_time(previous['occurred_at']), 'Review history is not chronological')
            previous = review
        if related:
            require(card['scheduler'] == related[-1]['after'], f'{identifier}: scheduler differs from the last review')
    sessions = read_json(state / 'sessions.json')
    require(isinstance(sessions, list), 'sessions must be an array')
    session_ids = [s['id'] for s in sessions]
    require(len(session_ids) == len(set(session_ids)), 'Duplicate session ID')
    require(sum(s['ended_at'] is None for s in sessions) <= 1, 'Only one session may be active')
    for session in sessions:
        references(session['goal_ids'], goals, session['id'])
        references([session['plan_file']], plans, session['id'])
        require(session['week_id'] == plans[session['plan_file']]['week_id'], 'Session plan belongs to another week')
        require(set(session['goal_ids']) <= {i['goal_id'] for i in plans[session['plan_file']]['items']}, 'Session goals are outside its plan')
        timestamp(session['started_at'], session['id'])
        timestamp(session['ended_at'], session['id'], nullable=True)
        if session['ended_at']:
            require(parse_time(session['ended_at']) >= parse_time(session['started_at']), 'Session ends before it starts')
        number(session['actual_minutes'], session['id'], nullable=False)
        spent = sum(r['duration_seconds'] for r in reviews.values() if r.get('session_id') == session['id'])
        if session['ended_at']:
            require(session['actual_minutes'] * 60 >= spent, 'Total session time cannot be shorter than its reviews')
        if session['pending_review']:
            pending = session['pending_review']
            references([pending['card_id']], cards, session['id'])
            timestamp(pending['presented_at'], 'pending review')
            timestamp(pending['revealed_at'], 'revealed answer', nullable=True)
    for event in list(assessments.values()) + list(reviews.values()):
        if event.get('session_id'):
            require(event['session_id'] in session_ids, 'Event references an unknown session')
    snapshots, times, event_ids = {}, {}, set()
    log_path = state / 'session-log.jsonl'
    import json
    for line in log_path.read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        require(event['id'] not in event_ids, 'Duplicate session event ID')
        event_ids.add(event['id'])
        identifier = event['session_id']
        require(identifier in session_ids, 'Session log references an unknown session')
        occurred = parse_time(event['occurred_at'])
        require(identifier not in times or occurred >= times[identifier], 'Session events must be chronological')
        times[identifier] = occurred
        require(event['snapshot']['id'] == identifier, 'Session event snapshot refers to another session')
        snapshots[identifier] = event['snapshot']
    require(all(snapshots.get(s['id']) == s for s in sessions), 'Session state differs from the last saved event')
    for goal in goals.values():
        if goal['status'] == 'completed':
            for evidence_id in goal['evidence_ids']:
                event = assessments[evidence_id]
                if 'criteria_snapshot' in event:
                    for criterion in event['criteria_snapshot']:
                        require(criterion in goal['criteria'], 'Completion evidence refers to an older criterion; reassess or reopen the goal')
