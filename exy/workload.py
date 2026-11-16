"""Evidence-labelled effort recommendations and time/learning pace reports."""
from copy import deepcopy
from datetime import date, timedelta
import math
from statistics import median
from zoneinfo import ZoneInfo

from exy.engine import fingerprint, need, uid
from exy.timekeeping import active_entries, daily_totals, initialize, seconds


def nonnegative(value, label):
    need(type(value) in (int, float) and math.isfinite(value) and value >= 0, f'{label} must be a finite nonnegative number')


def analyze(store, data, now):
    initialize(store)
    data = deepcopy(data)
    start, end = date.fromisoformat(data['start_date']), date.fromisoformat(data['deadline'])
    need(start <= end and (end-start).days <= 730, 'Use a planning window of 1 to 731 days')
    zone = ZoneInfo(data['timezone'])
    days = data['study_days']
    need(days and all(type(d) is int and 0 <= d <= 6 for d in days) and len(set(days)) == len(days),
         'study_days must contain distinct weekday numbers, Monday=0')
    unavailable = {date.fromisoformat(d) for d in data.get('unavailable_dates', [])}
    dates = [start + timedelta(days=i) for i in range((end-start).days+1)]
    slots = [d for d in dates if d.weekday() in days and d not in unavailable]
    goals = store.get('goals.json')
    children = {g['parent_id'] for g in goals if g['status'] != 'dropped'}
    scope = {g['id']: g for g in goals if g['id'] not in children and g['status'] not in {'completed', 'dropped'}}
    supplied = data['effort']
    ids = [e['goal_id'] for e in supplied]
    need(len(ids) == len(set(ids)), 'Do not estimate a goal twice')
    need(set(ids) <= set(scope), 'Estimate only remaining leaf goals; parent estimates would double count scope')
    missing = sorted(set(scope) - set(ids))
    blockers = []
    if not scope:
        blockers.append('Create the scoped outcome tree before calculating required effort.')
    if missing:
        blockers.append('Missing remaining-effort estimates: ' + ', '.join(missing))
    if not slots:
        blockers.append('No study days remain in this window.')
    lower = upper = 0
    for entry in supplied:
        need(entry.get('basis') and isinstance(entry.get('source_refs'), list) and entry['source_refs'], 'Every effort estimate needs a rationale and source references')
        need(all(isinstance(s, str) and s.strip() for s in entry['source_refs']), 'Invalid effort source references')
        if entry['min_hours'] is None or entry['max_hours'] is None:
            blockers.append(f"Unresolved effort range: {entry['goal_id']}")
            continue
        nonnegative(entry['min_hours'], 'min_hours'); nonnegative(entry['max_hours'], 'max_hours')
        need(entry['min_hours'] <= entry['max_hours'], 'Reversed effort range')
        lower += entry['min_hours']; upper += entry['max_hours']
    overhead = data['overhead_hours']
    need(overhead.get('basis'), 'Explain the separate review/assessment overhead; avoid counting it twice')
    for bound in ('min', 'max'):
        nonnegative(overhead[bound], f'overhead.{bound}')
    need(overhead['min'] <= overhead['max'], 'Reversed overhead range')
    nonnegative(data['buffer_percent'], 'buffer_percent')
    need(data['buffer_percent'] <= 100, 'Buffer must be between 0 and 100 percent')
    weekly_capacity = data.get('weekly_capacity_hours')
    if weekly_capacity is not None:
        nonnegative(weekly_capacity, 'weekly_capacity_hours')
        need(weekly_capacity <= 168, 'Weekly capacity cannot exceed 168 hours')
    daily_capacity = data.get('daily_capacity_hours')
    if daily_capacity is not None:
        need(isinstance(daily_capacity, list) and len(daily_capacity) == 7, 'daily_capacity_hours needs seven values, Monday first')
        for value in daily_capacity:
            nonnegative(value, 'daily_capacity_hours'); need(value <= 24, 'A day has at most 24 available hours')
        if weekly_capacity is not None:
            need(sum(daily_capacity[d] for d in days) <= weekly_capacity + 1e-6,
                 'Daily availability exceeds stated weekly capacity; reconcile the inputs')
        slots = [d for d in slots if daily_capacity[d.weekday()] > 0]
        if not slots:
            blockers.append('Daily availability provides no usable study time.')
    weeks = len(dates)/7
    result = {'id': uid('workload'), 'created_at': now.isoformat(), 'input': data,
              'scope_snapshot': {key: fingerprint(value) for key, value in scope.items()},
              'status': 'insufficient_evidence' if blockers else 'estimated', 'blockers': blockers,
              'calendar_days': len(dates), 'study_days_available': len(slots),
              'recommendation': None, 'is_user_commitment': False}
    if not blockers:
        total_min = (lower + overhead['min']) * (1 + data['buffer_percent']/100)
        total_max = (upper + overhead['max']) * (1 + data['buffer_percent']/100)
        capacity = sum(daily_capacity[d.weekday()] for d in slots) if daily_capacity is not None else (
            weekly_capacity * weeks if weekly_capacity is not None else None)
        weights = {d: daily_capacity[d.weekday()] if daily_capacity is not None else 1 for d in slots}
        allocations = {d.isoformat(): round(total_max * weight/sum(weights.values()), 6) for d, weight in weights.items()}
        feasibility = ('unknown_capacity' if capacity is None else 'fits_estimate_range' if capacity >= total_max
                       else 'only_optimistic_case_fits' if capacity >= total_min else 'scope_deadline_conflict')
        if any(hours > 24 for hours in allocations.values()):
            feasibility = 'scope_deadline_conflict'
        result['recommendation'] = {'total_hours_min': round(total_min, 4), 'total_hours_max': round(total_max, 4),
            'weekly_hours_min': round(total_min/weeks, 4), 'weekly_hours_max': round(total_max/weeks, 4),
            'hours_per_study_day_min': round(total_min/len(slots), 4), 'hours_per_study_day_max': round(total_max/len(slots), 4),
            'required_daily_hours_for_upper_estimate': allocations, 'available_hours_in_window': capacity,
            'upper_estimate_shortfall_hours': max(0, total_max-capacity) if capacity is not None else None,
            'feasibility': feasibility,
            'alternatives': ['Reduce scope', 'Extend the deadline', 'Increase capacity if sustainable'] if feasibility in {'scope_deadline_conflict', 'only_optimistic_case_fits'} else [],
            'method': 'Sum remaining leaf effort and explicit overhead, apply the stated buffer, and divide by the available window. Daily allocations use availability weights when supplied.'}
    store.append('workload-log.jsonl', result)
    return result


def latest(store):
    analyses = store.get('workload-log.jsonl', [])
    return analyses[-1] if analyses else None


def pace(store, start, end, now):
    start, end = date.fromisoformat(start), date.fromisoformat(end)
    need(start <= end and (end-start).days <= 730, 'Use a report window of 1 to 731 days')
    objective = store.get('objective.json')
    timezone_name = objective['timezone'] or (store.get('foundation.json') or {}).get('timezone')
    need(timezone_name, 'Set the instance or foundation time zone before reporting daily time')
    zone = ZoneInfo(timezone_name)
    daily = daily_totals(store, start, end, zone)
    plans = {}
    for name in store.files:
        if name.startswith('plans/'):
            plan = store.get(name)
            if plan['revision'] > plans.get(plan['week_id'], {}).get('revision', 0):
                plans[plan['week_id']] = plan
    planned = {}
    for plan in plans.values():
        for day, hours in plan.get('daily_hours', {}).items():
            if start <= date.fromisoformat(day) <= end:
                planned[day] = hours
    today = now.astimezone(zone).date()
    completed_days = [d for d in planned if date.fromisoformat(d) < today]
    target = sum(planned[d] for d in completed_days)
    actual_on_planned_days = sum(daily[d] for d in completed_days)
    goals = store.get('goals.json')
    entries = active_entries(store)
    ratios, samples = [], []
    for goal in goals:
        if goal['status'] != 'completed' or any(g['parent_id'] == goal['id'] and g['status'] != 'dropped' for g in goals):
            continue
        rows = [e for e in entries if e['goal_id'] == goal['id']]
        if not rows:
            continue
        estimate = rows[0]['estimate_hours_snapshot']
        if estimate and estimate['min'] is not None and estimate['max'] is not None:
            midpoint = (estimate['min'] + estimate['max'])/2
            actual = sum(seconds(e) for e in rows)/3600
            if midpoint > 0:
                ratios.append(actual/midpoint)
                samples.append({'goal_id': goal['id'], 'logged_hours': round(actual, 4), 'original_estimate_midpoint': midpoint})
    analysis = latest(store)
    forecast = None
    if analysis and analysis['recommendation']:
        changed = [key for key, value in analysis['scope_snapshot'].items()
                   if next((fingerprint(g) for g in goals if g['id'] == key), None) != value]
        known = set(analysis['scope_snapshot'])
        parents = {g['parent_id'] for g in goals if g['status'] != 'dropped'}
        changed += [g['id'] for g in goals if g['id'] not in known and g['id'] not in parents and g['status'] not in {'completed', 'dropped'}]
        forecast = {'analysis_id': analysis['id'], 'changed_goals_since_analysis': changed,
                    'requires_new_remaining_effort_estimates': bool(changed),
                    'note': 'Logged hours are not subtracted from remaining effort. Re-estimate unfinished work from assessment evidence.'}
        elapsed_days = max(0, (min(end, today - timedelta(days=1)) - start).days + 1)
        elapsed_hours = sum(value for day, value in daily.items() if date.fromisoformat(day) < today)
        if elapsed_days >= 7 and elapsed_hours > 0 and not changed:
            capacity_per_week = elapsed_hours * 7/elapsed_days
            forecast['observed_hours_per_week'] = round(capacity_per_week, 4)
            forecast['weeks_needed_for_current_estimate'] = {
                'min': round(analysis['recommendation']['total_hours_min']/capacity_per_week, 2),
                'max': round(analysis['recommendation']['total_hours_max']/capacity_per_week, 2)}
            forecast['note'] += ' The projection uses historical attendance, not a guarantee of mastery.'
    legacy = [s for s in store.get('sessions.json') if s.get('time_tracking') != 'intervals'
              and start <= date.fromisoformat(s['week_id']) <= end]
    return {'from': start.isoformat(), 'to': end.isoformat(), 'timezone': timezone_name,
            'timezone_source': 'objective' if objective['timezone'] else 'draft_foundation',
            'daily_logged_hours': daily, 'total_logged_hours': round(sum(daily.values()), 6),
            'daily_planned_hours': planned, 'past_day_adherence_ratio': actual_on_planned_days/target if target else None,
            'legacy_session_minutes_not_allocated_to_days': sum(s['actual_minutes'] for s in legacy),
            'completed_goal_effort_samples': samples,
            'median_actual_to_estimated_effort': round(median(ratios), 4) if ratios else None,
            'pace_confidence': 'insufficient_samples' if len(ratios) < 3 else 'provisional',
            'forecast': forecast, 'learning_progress': 'Only independently verified goal completion counts as skill progress.'}
