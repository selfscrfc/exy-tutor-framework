"""Domain operations shared by the CLI and conversational tutor."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from exy.scheduling import VERSION, advance, default_settings, initial, parse_time
from exy.store import ROOT


def need(condition, message):
    if not condition:
        raise ValueError(message)


def uid(prefix):
    return f'{prefix}-{uuid4().hex[:12]}'


def template(name):
    return json.loads((ROOT / 'templates' / f'{name}.json').read_text())


def lookup(items, identifier):
    for item in items:
        if item['id'] == identifier:
            return item
    raise ValueError(f'Unknown ID: {identifier}')


def fingerprint(item):
    return hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()


def init(store):
    for directory in ('plans', 'weekly-reviews'):
        (store.path / directory).mkdir(exist_ok=True)
    defaults = {'objective.json': template('objective'), 'goals.json': [], 'cards.json': [],
                'assessment-log.jsonl': [], 'card-review-log.jsonl': [],
                'sessions.json': [], 'session-log.jsonl': [], 'settings.json': default_settings(),
                'foundation.json': template('foundation')}
    for name, value in defaults.items():
        if name not in store.files:
            store.put(name, value)
    cards = store.get('cards.json')
    events = store.get('card-review-log.jsonl')
    replaced = {event['supersedes'] for event in events if event['supersedes']}
    for card in cards:
        if card['scheduler'] is None:
            now = datetime.now(timezone.utc)
            history = [event for event in events if event['card_id'] == card['id'] and event['id'] not in replaced]
            history.sort(key=lambda event: parse_time(event['occurred_at']))
            start = parse_time(history[0]['occurred_at']) if history else now
            card['scheduler'] = initial(card['id'], start)
            card['created_at'] = now.isoformat()
            card['imported_at'] = now.isoformat()
            for event in history:
                updated, _ = advance(card, event['rating'], parse_time(event['occurred_at']),
                                     event['duration_seconds'] or 0, store.get('settings.json'))
                card['scheduler'] = updated
            card['due_at'] = card['scheduler']['due']
    if cards:
        store.put('cards.json', cards)
    return {'initialized': str(store.path), 'scheduler_version': store.get('settings.json')['scheduler_version']}


def foundation_save(store, data):
    previous = store.get('foundation.json')
    foundation = deepcopy(data)
    if previous and previous['status'] == 'confirmed' and foundation != previous:
        need(foundation['status'] == 'draft', 'Reopen the foundation as a draft before changing a confirmed agreement')
    store.put('foundation.json', foundation)
    if foundation['status'] == 'confirmed':
        configure(store, {'title': foundation['objective'], 'success_criteria': foundation['success_criteria'],
                          'target_date': foundation['target_date'], 'weekly_hours': foundation['weekly_hours'],
                          'timezone': foundation['timezone'], 'constraints': foundation['constraints']})
    return foundation


def configure(store, patch):
    current = store.get('objective.json')
    need(isinstance(patch, dict) and set(patch) <= set(current), 'Unknown objective settings')
    foundation = store.get('foundation.json')
    if foundation and foundation['status'] == 'confirmed':
        fields = {'title': 'objective', 'success_criteria': 'success_criteria', 'target_date': 'target_date',
                  'weekly_hours': 'weekly_hours', 'timezone': 'timezone', 'constraints': 'constraints'}
        need(all(key not in patch or patch[key] == foundation[source] for key, source in fields.items()),
             'Reopen and update the confirmed foundation before changing agreed objective settings')
    current.update(patch)
    store.put('objective.json', current)
    return current


def goal_save(store, data, update=False):
    goals = store.get('goals.json')
    goal = deepcopy(data)
    goal['id'] = goal.get('id') or uid('goal')
    if update:
        previous = lookup(goals, goal['id'])
        need(set(goal) == set(previous), 'Use a complete goal record when updating')
        goals[goals.index(previous)] = goal
    else:
        need(all(g['id'] != goal['id'] for g in goals), 'Goal ID already exists')
        goals.append(goal)
    store.put('goals.json', goals)
    return goal


def save_plan(store, data):
    foundation = store.get('foundation.json')
    need(foundation and foundation['status'] == 'confirmed', 'Clarify and confirm the foundation before scheduling a week')
    plan = deepcopy(data)
    week = plan['week_id']
    date.fromisoformat(week)
    prior = [store.get(k) for k in store.files if k.startswith(f'plans/{week}.r')]
    plan['revision'] = max((p['revision'] for p in prior), default=0) + 1
    need(plan['budget_hours'] is not None and plan['budget_hours'] > 0, 'Set a positive weekly budget')
    for key in ('review_hours', 'assessment_hours', 'buffer_hours'):
        need(plan[key] is not None, f'Set {key}, including zero if intentional')
    need(plan['items'], 'A plan needs at least one outcome')
    for item in plan['items']:
        goal = lookup(store.get('goals.json'), item['goal_id'])
        need(goal['status'] not in {'dropped', 'completed'}, 'Do not schedule a dropped or completed goal')
        need(item['expected_result'].strip() and item['success_criteria'] and item['assistance_policy'].strip()
             and item['activities'] and item['estimated_hours'] is not None,
             'Each planned outcome needs criteria, assistance policy, activities, and estimated hours')
        item['goal_criteria_snapshot'] = deepcopy(goal['criteria'])
    filename = f'{week}.r{plan["revision"]}.json'
    store.put('plans/' + filename, plan)
    return {'file': filename, 'plan': plan}


def latest_plan(store, week):
    plans = [store.get(k) for k in store.files if k.startswith(f'plans/{week}.r')]
    need(plans, f'No plan for {week}')
    return max(plans, key=lambda p: p['revision'])


def carry_plan(store, source, target):
    need(date.fromisoformat(target) >= date.fromisoformat(source) + timedelta(days=7),
         'Carryover must target a later, non-overlapping week')
    plan = deepcopy(latest_plan(store, source))
    goals = store.get('goals.json')
    plan.update(week_id=target, revision=1, change_reason=None)
    plan['items'] = [item for item in plan['items'] if lookup(goals, item['goal_id'])['status'] not in {'completed', 'dropped'}]
    plan['carried_from'] = source
    return plan


def assessment_add(store, data, now, session_id=None, complete=False):
    event = deepcopy(data)
    event.update(id=event.get('id') or uid('assessment'), occurred_at=event.get('occurred_at') or now.isoformat())
    goals = store.get('goals.json')
    goal = lookup(goals, event['goal_id'])
    need(event['criterion_ids'] and set(event['criterion_ids']) <= {c['id'] for c in goal['criteria']},
         'Assessment criteria must belong to the goal')
    need(event['task'].strip() and event['rubric'].strip() and event['assistance_policy'].strip(),
         'Record the task, rubric, and assistance policy')
    need(parse_time(event['occurred_at']) <= now, 'Cannot record a future assessment')
    if event['result'] != 'unknown':
        need(event['artifact'].strip(), 'An assessed result needs an artifact reference')
    event['criteria_snapshot'] = [deepcopy(c) for c in goal['criteria'] if c['id'] in event['criterion_ids']]
    if session_id:
        session = current_session(store, session_id)
        need(event['goal_id'] in session['goal_ids'], 'Assessment goal is not in this session')
        need(parse_time(event['occurred_at']) >= parse_time(session['started_at']), 'Assessment predates the session')
        event['session_id'] = session_id
    events = store.get('assessment-log.jsonl')
    need(all(e['id'] != event['id'] for e in events), 'Assessment ID already exists')
    if event['supersedes']:
        old = lookup(events, event['supersedes'])
        need(old['goal_id'] == goal['id'], 'Correction refers to a different goal')
        goal['evidence_ids'] = [i for i in goal['evidence_ids'] if i != old['id']]
        if goal['status'] == 'completed':
            goal['status'] = 'active'
    if event['result'] == 'passed' and event['assistance'] in {'none', 'allowed_tools'}:
        goal['evidence_ids'].append(event['id'])
    if complete:
        goal['status'] = 'completed'
    store.append('assessment-log.jsonl', event)
    store.put('goals.json', goals)
    return event


def card_add(store, data, now):
    cards = store.get('cards.json')
    card = deepcopy(data)
    card.update(id=card.get('id') or uid('card'), created_at=now.isoformat())
    active = [session for session in store.get('sessions.json') if session['ended_at'] is None]
    if active:
        card['session_id'] = active[0]['id']
    need(all(c['id'] != card['id'] for c in cards), 'Card ID already exists')
    prompt = ' '.join(card['prompt'].casefold().split())
    need(prompt and not any(' '.join(c['prompt'].casefold().split()) == prompt
                            and c['status'] != 'archived' for c in cards), 'Empty or duplicate card prompt')
    card['scheduler'] = initial(card['id'], now)
    card['due_at'] = card['scheduler']['due']
    cards.append(card)
    store.put('cards.json', cards)
    return card


def card_status(store, identifier, status):
    cards = store.get('cards.json')
    card = lookup(cards, identifier)
    card['status'] = status
    store.put('cards.json', cards)
    return card


def current_session(store, identifier=None):
    sessions = store.get('sessions.json')
    if identifier:
        session = lookup(sessions, identifier)
    else:
        active = [s for s in sessions if s['ended_at'] is None]
        need(active, 'No active session; use session start')
        session = active[-1]
    need(session['ended_at'] is None, 'Session has ended')
    return session


def save_session(store, session, now, action):
    need(now >= parse_time(session['started_at']), 'Session event predates its start')
    sessions = store.get('sessions.json')
    previous = next((s for s in sessions if s['id'] == session['id']), None)
    if previous:
        sessions[sessions.index(previous)] = session
    else:
        sessions.append(session)
    store.put('sessions.json', sessions)
    store.append('session-log.jsonl', {'id': uid('session-event'), 'session_id': session['id'],
                                     'occurred_at': now.isoformat(), 'action': action, 'snapshot': deepcopy(session)})


def queue(store, session, now):
    objective = store.get('objective.json')
    budget = objective['review_budget_minutes_per_session']
    limit = objective['max_new_cards_per_session']
    need(budget is not None and limit is not None, 'Configure review minutes and the new-card limit first')
    reviews = [e for e in store.get('card-review-log.jsonl') if e.get('session_id') == session['id']]
    remaining = max(0, budget * 60 - sum(e['duration_seconds'] for e in reviews))
    used_new = sum(e.get('was_new', False) for e in reviews)
    cards = [c for c in store.get('cards.json') if c['status'] == 'active'
             and c['id'] not in session.get('skipped_card_ids', []) and parse_time(c['due_at']) <= now]
    due = sorted([c for c in cards if c['scheduler']['last_review'] is not None], key=lambda c: c['due_at'])
    new = sorted([c for c in cards if c['scheduler']['last_review'] is None], key=lambda c: c['created_at'])
    new = new[:max(0, limit - used_new)]
    estimated = store.get('settings.json')['estimated_review_seconds']
    count = int(remaining // estimated)
    return {'cards': [{'id': c['id'], 'prompt': c['prompt'], 'due_at': c['due_at'],
                       'new': c['scheduler']['last_review'] is None} for c in (due + new)[:count]],
            'remaining_seconds': remaining, 'overdue_or_due_count': len(due),
            'new_slots_remaining': max(0, limit - used_new)}


def context(store, session, now):
    goals = store.get('goals.json')
    assessments = store.get('assessment-log.jsonl')
    replaced = {a['supersedes'] for a in assessments if a['supersedes']}
    recent = [a for a in assessments if a['goal_id'] in session['goal_ids'] and a['id'] not in replaced][-10:]
    return {'session': session, 'objective': store.get('objective.json'),
            'plan': latest_plan(store, session['week_id']),
            'session_plan': store.get('plans/' + session['plan_file']),
            'goals': [lookup(goals, i) for i in session['goal_ids']], 'recent_assessments': recent,
            'review_queue': queue(store, session, now),
            'next_step': session['continuation']}


def session_start(store, week, now, goal_ids=None):
    need(not any(s['ended_at'] is None for s in store.get('sessions.json')), 'Resume or end the active session first')
    need(store.get('foundation.json')['status'] == 'confirmed', 'Confirm the foundation before starting a planned session')
    objective = store.get('objective.json')
    need(objective['title'] and objective['weekly_hours'] and objective['timezone'], 'Configure the objective, weekly hours, and time zone first')
    local_date = now.astimezone(ZoneInfo(objective['timezone'])).date()
    need(date.fromisoformat(week) <= local_date < date.fromisoformat(week) + timedelta(days=7),
         'Session must start within its planned week')
    plan = latest_plan(store, week)
    selected = goal_ids or [i['goal_id'] for i in plan['items']
                            if lookup(store.get('goals.json'), i['goal_id'])['status'] not in {'completed', 'dropped'}]
    need(selected and set(selected) <= {i['goal_id'] for i in plan['items']}, 'Select goals from the current plan')
    for identifier in selected:
        goal = lookup(store.get('goals.json'), identifier)
        need(goal['status'] in {'ready', 'active'}, f'{identifier}: goal must be ready or active')
        need(all(lookup(store.get('goals.json'), p)['status'] == 'completed' for p in goal['depends_on']),
             f'{identifier}: prerequisites are incomplete')
    previous = store.get('sessions.json')
    session = {'id': uid('session'), 'week_id': week, 'plan_file': f'{week}.r{plan["revision"]}.json',
               'goal_ids': selected, 'started_at': now.isoformat(), 'ended_at': None,
               'actual_minutes': 0, 'continuation': previous[-1]['continuation'] if previous else 'Begin the planned activity.',
               'pending_review': None, 'skipped_card_ids': []}
    save_session(store, session, now, 'start')
    return context(store, session, now)


def session_resume(store, identifier, now):
    sessions = store.get('sessions.json')
    need(sessions, 'No session has been recorded')
    session = lookup(sessions, identifier) if identifier else sessions[-1]
    return context(store, session, now)


def session_finish(store, identifier, note, minutes, now, end):
    session = current_session(store, identifier)
    need(note.strip(), 'Save a concrete continuation note')
    need(minutes >= session['actual_minutes'], 'Cumulative actual minutes cannot decrease')
    if end:
        need(session['pending_review'] is None, 'Rate or skip the pending card before ending the session')
    session.update(continuation=note, actual_minutes=minutes)
    if end:
        session['ended_at'] = now.isoformat()
    save_session(store, session, now, 'end' if end else 'checkpoint')
    return session


def review_next(store, identifier, now):
    session = current_session(store, identifier)
    if session['pending_review']:
        pending = session['pending_review']
        card = lookup(store.get('cards.json'), pending['card_id'])
        need(fingerprint(card) == pending['card_fingerprint'], 'Card changed; skip the pending attempt and start again')
    else:
        available = queue(store, session, now)
        if not available['cards']:
            return {'card': None, **available}
        card = lookup(store.get('cards.json'), available['cards'][0]['id'])
        pending = {'card_id': card['id'], 'card_fingerprint': fingerprint(card),
                   'presented_at': now.isoformat(), 'response': None, 'revealed_at': None}
        session['pending_review'] = pending
        save_session(store, session, now, 'review-presented')
    result = {'card_id': card['id'], 'prompt': card['prompt'], 'response_saved': pending['response'] is not None}
    if pending['revealed_at']:
        result.update(answer=card['answer'], source=card['source'], response=pending['response'])
    return result


def review_answer(store, identifier, response, now):
    session = current_session(store, identifier)
    pending = session['pending_review']
    need(pending is not None, 'Use review next first')
    need(pending['response'] is None, 'Response already saved; rate or skip this attempt')
    need(response.strip(), 'Record your answer, or explicitly say that you could not recall it')
    need(now >= parse_time(pending['presented_at']), 'Answer predates the question')
    card = lookup(store.get('cards.json'), pending['card_id'])
    need(fingerprint(card) == pending['card_fingerprint'], 'Card changed; skip this attempt')
    pending.update(response=response, revealed_at=now.isoformat())
    save_session(store, session, now, 'review-answered')
    return {'card_id': card['id'], 'answer': card['answer'], 'source': card['source'], 'response': response}


def review_rate(store, identifier, rating, seconds, now):
    session = current_session(store, identifier)
    pending = session['pending_review']
    need(pending and pending['revealed_at'], 'Record an answer before rating the card')
    need(now >= parse_time(pending['revealed_at']), 'Rating predates the answer')
    need(seconds > 0, 'Review duration must be positive')
    cards = store.get('cards.json')
    card = lookup(cards, pending['card_id'])
    need(fingerprint(card) == pending['card_fingerprint'], 'Card changed; skip this attempt')
    need(card['status'] == 'active', 'Only active cards can be reviewed')
    was_new = card['scheduler']['last_review'] is None
    before = deepcopy(card['scheduler'])
    settings = store.get('settings.json')
    updated, log = advance(card, rating, now, seconds, settings)
    card.update(scheduler=updated, due_at=updated['due'])
    event = dict(template('card-review'), id=uid('review'), card_id=card['id'], occurred_at=now.isoformat(),
                 rating=rating, duration_seconds=seconds, scheduler_version=VERSION, session_id=session['id'],
                 response=pending['response'], was_new=was_new, before=before, after=updated,
                 fsrs_log=log, scheduler_settings=deepcopy(settings['scheduler']))
    store.put('cards.json', cards)
    store.append('card-review-log.jsonl', event)
    session['pending_review'] = None
    save_session(store, session, now, 'review-rated')
    return {'review_id': event['id'], 'card_id': card['id'], 'due_at': card['due_at']}


def review_skip(store, identifier, now):
    session = current_session(store, identifier)
    need(session['pending_review'], 'No pending review')
    session.setdefault('skipped_card_ids', []).append(session['pending_review']['card_id'])
    session['pending_review'] = None
    save_session(store, session, now, 'review-skipped')
    return {'skipped': True, 'schedule_changed': False}


def week_close(store, week, notes, now):
    plan = latest_plan(store, week)
    baseline = store.get(f'plans/{week}.r1.json')
    sessions = [s for s in store.get('sessions.json') if s['week_id'] == week]
    need(sessions and all(s['ended_at'] for s in sessions), 'Finish at least one session and end all sessions for the week')
    zone = ZoneInfo(store.get('objective.json')['timezone'])
    end_date = date.fromisoformat(week) + timedelta(days=7)
    need(now.astimezone(zone).date() >= end_date, 'Close the week after its calendar boundary')
    session_ids = {s['id'] for s in sessions}
    assessments = [a for a in store.get('assessment-log.jsonl') if a.get('session_id') in session_ids]
    reviews = [r for r in store.get('card-review-log.jsonl') if r.get('session_id') in session_ids]
    goals = store.get('goals.json')
    completed = [i['goal_id'] for i in plan['items'] if lookup(goals, i['goal_id'])['status'] == 'completed']
    actual = sum(s['actual_minutes'] for s in sessions) / 60
    revisions = [store.get(k)['revision'] for k in store.files if k.startswith(f'weekly-reviews/{week}.r')]
    report = dict(template('weekly-review'), week_id=week, revision=max(revisions, default=0) + 1,
                  baseline_plan=f'{week}.r1.json', effective_plan=f'{week}.r{plan["revision"]}.json',
                  actual_hours=actual, completed=completed, assessment_ids=[a['id'] for a in assessments],
                  card_ids=sorted({r['card_id'] for r in reviews} | {c['id'] for c in store.get('cards.json') if c.get('session_id') in session_ids}), closed_at=now.isoformat(),
                  session_ids=sorted(session_ids), goal_status_snapshot={i['goal_id']: lookup(goals, i['goal_id'])['status'] for i in plan['items']},
                  baseline_budget_hours=baseline['budget_hours'], effective_budget_hours=plan['budget_hours'],
                  hours_vs_baseline=actual - baseline['budget_hours'])
    need(set(notes) <= {'deviations', 'decisions', 'next_focus', 'change_reason'}, 'Unsupported weekly report notes')
    report.update(notes)
    if not report['next_focus']:
        report['next_focus'] = [i['goal_id'] for i in plan['items'] if lookup(goals, i['goal_id'])['status'] not in {'completed', 'dropped'}]
    name = f'{week}.r{report["revision"]}.json'
    store.put('weekly-reviews/' + name, report)
    return report
