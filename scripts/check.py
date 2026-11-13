#!/usr/bin/env python3
"""Read-only structural checks for the framework's file-backed state."""
import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def shape(value, sample, label):
    if sample is None:
        return
    require(type(value) is type(sample), f'{label}: invalid type')
    if isinstance(sample, dict):
        for key, expected in sample.items():
            require(key in value, f'{label}: missing {key}')
            shape(value[key], expected, f'{label}.{key}')
    elif isinstance(sample, list) and sample:
        for i, item in enumerate(value):
            shape(item, sample[0], f'{label}[{i}]')


def number(value, label, nullable=True):
    if value is None and nullable:
        return
    require(type(value) in (int, float) and value >= 0 and value < float('inf'),
            f'{label}: expected a finite nonnegative number')


def timestamp(value, label, nullable=False):
    if value is None and nullable:
        return
    require(isinstance(value, str), f'{label}: expected a timestamp with a time zone')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None, f'{label}: missing time zone')


def records(state, filename, template, journal=False):
    path = state / filename
    items = ([json.loads(line) for line in path.read_text().splitlines() if line.strip()]
             if journal else read_json(path))
    require(isinstance(items, list), f'{filename}: expected an array')
    sample = read_json(ROOT / 'templates' / f'{template}.json')
    result = {}
    for item in items:
        shape(item, sample, filename)
        identifier = item['id']
        require(bool(identifier.strip()) and identifier not in result,
                f'{filename}: empty or duplicate ID {identifier!r}')
        result[identifier] = item
    return result


def references(ids, registry, label):
    require(isinstance(ids, list) and all(isinstance(x, str) for x in ids),
            f'{label}: expected a list of IDs')
    require(len(ids) == len(set(ids)), f'{label}: duplicate references')
    for identifier in ids:
        require(identifier in registry, f'{label}: unknown reference {identifier}')


def acyclic(graph, label):
    visiting, visited = set(), set()

    def visit(node):
        require(node not in visiting, f'{label}: cycle at {node}')
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)
    for node in graph:
        visit(node)


def current_events(events, entity_key):
    seen, replaced = {}, set()
    for identifier, event in events.items():
        timestamp(event['occurred_at'], identifier)
        old = event['supersedes']
        if old is not None:
            require(isinstance(old, str) and old in seen and old not in replaced,
                    f'{identifier}: a correction must reference an earlier current event')
            require(seen[old][entity_key] == event[entity_key],
                    f'{identifier}: correction refers to a different entity')
            replaced.add(old)
        seen[identifier] = event
    return {key: event for key, event in events.items() if key not in replaced}


def weekly_files(state, directory, template):
    require((state / directory).is_dir(), f'Missing directory {directory}')
    sample = read_json(ROOT / 'templates' / f'{template}.json')
    result = {}
    for path in sorted((state / directory).glob('*.json')):
        item = read_json(path)
        shape(item, sample, str(path))
        require(date.fromisoformat(item['week_id']).isoformat() == item['week_id'],
                f'{path.name}: invalid week date')
        revision = item['revision']
        require(revision >= 1, f'{path.name}: revision must be positive')
        require(path.name == f"{item['week_id']}.r{revision}.json", f'{path.name}: invalid file name')
        if revision > 1:
            require(isinstance(item['change_reason'], str) and item['change_reason'].strip(),
                    f'{path.name}: a change reason is required')
        result[path.name] = item
    for name, item in result.items():
        for revision in range(1, item['revision']):
            require(f"{item['week_id']}.r{revision}.json" in result,
                    f'{name}: missing previous revision')
    return result


def check(state):
    runtime = (state / 'settings.json').exists()
    objective = read_json(state / 'objective.json')
    shape(objective, read_json(ROOT / 'templates/objective.json'), 'objective')
    require(objective['schema_version'] == 1, 'Unknown format version')
    for key in ['weekly_hours', 'review_budget_minutes_per_session', 'max_new_cards_per_session']:
        number(objective[key], key)
    horizon = objective['planning']
    require(0 < horizon['detailed_weeks'] <= horizon['weekly_outcomes_weeks'], 'Invalid planning horizons')
    goals = records(state, 'goals.json', 'goal')
    cards = records(state, 'cards.json', 'card')
    assessments = records(state, 'assessment-log.jsonl', 'assessment', journal=True)
    reviews = records(state, 'card-review-log.jsonl', 'card-review', journal=True)
    active_assessments = current_events(assessments, 'goal_id')
    current_events(reviews, 'card_id')
    children = {identifier: [] for identifier in goals}
    for identifier, goal in goals.items():
        require(bool(goal['title'].strip()), f'{identifier}: empty title')
        require(goal['status'] in {'draft', 'ready', 'active', 'blocked', 'completed', 'dropped'},
                f'{identifier}: unknown status')
        if goal['status'] == 'blocked':
            require(bool(goal['notes'].strip()), f'{identifier}: a blocking reason is required')
        if goal['parent_id'] is not None:
            references([goal['parent_id']], goals, identifier)
            children[goal['parent_id']].append(identifier)
        references(goal['depends_on'], goals, identifier)
        references(goal['evidence_ids'], active_assessments, identifier)
        criterion_ids = [c['id'] for c in goal['criteria']]
        require(all(criterion_ids) and len(set(criterion_ids)) == len(criterion_ids),
                f'{identifier}: duplicate or empty criteria')
        for bound in ['min', 'max']:
            number(goal['estimate_hours'][bound], identifier)
        low, high = goal['estimate_hours']['min'], goal['estimate_hours']['max']
        require(low is None or high is None or low <= high, f'{identifier}: invalid hour range')
    acyclic({key: children[key] + goal['depends_on'] for key, goal in goals.items()},
            'Outcome tree and prerequisites')
    for identifier, event in assessments.items():
        references([event['goal_id']], goals, identifier)
        require(event['result'] in {'unknown', 'passed', 'partial', 'failed'}, f'{identifier}: invalid result')
        require(event['assistance'] in {'none', 'allowed_tools', 'hints', 'solution_shown'},
                f'{identifier}: unknown assistance type')
        number(event['duration_minutes'], identifier)
        # Historical criteria may differ from current ones; rubric preserves the snapshot.
    for identifier, goal in goals.items():
        events = [active_assessments[key] for key in goal['evidence_ids']]
        require(all(event['goal_id'] == identifier for event in events), f'{identifier}: evidence belongs to a different goal')
        if goal['status'] == 'completed':
            require(goal['criteria'] and all(c['description'].strip() and c['verification'].strip()
                                            for c in goal['criteria']), f'{identifier}: completion criteria are required')
            supported = set()
            for event in events:
                if (event['result'] == 'passed' and event['assistance'] in {'none', 'allowed_tools'}
                        and event['artifact'].strip() and event['rubric'].strip()
                        and event['assistance_policy'].strip()):
                    supported.update(event['criterion_ids'])
            require(all(c['id'] in supported for c in goal['criteria']),
                    f'{identifier}: not all criteria have independent supporting evidence')
            require(all(goals[child]['status'] in {'completed', 'dropped'} for child in children[identifier]),
                    f'{identifier}: some child goals are incomplete')
    for identifier, card in cards.items():
        references(card['goal_ids'], goals, identifier)
        require(card['status'] in {'draft', 'active', 'suspended', 'archived'}, f'{identifier}: invalid status')
        timestamp(card['verified_at'], identifier, nullable=True)
        timestamp(card['due_at'], identifier, nullable=True)
        if card['status'] == 'active':
            require(card['goal_ids'] and all(card[key].strip() for key in ['prompt', 'answer', 'source'])
                    and card['verified_at'], f'{identifier}: active card is unverified or incomplete')
        if not runtime:
            require(card['scheduler'] is None and card['due_at'] is None,
                    f'{identifier}: FSRS is not integrated yet; scheduler state must be null')
    for identifier, event in reviews.items():
        references([event['card_id']], cards, identifier)
        require(event['rating'] in {'again', 'hard', 'good', 'easy'}, f'{identifier}: unknown rating')
        if not runtime:
            require(event['scheduler_version'] is None, f'{identifier}: FSRS is not integrated yet')
        number(event['duration_seconds'], identifier)
    plans = weekly_files(state, 'plans', 'plan')
    for name, plan in plans.items():
        number(plan['budget_hours'], name)
        total = 0
        for item in plan['items']:
            references([item['goal_id']], goals, name)
            number(item['estimated_hours'], name)
            total += item['estimated_hours'] or 0
        for key in ['review_hours', 'assessment_hours', 'buffer_hours']:
            number(plan[key], name)
            total += plan[key] or 0
        require(plan['budget_hours'] is None or total <= plan['budget_hours'] + 1e-9,
                f'{name}: plan exceeds the budget')
    for name, report in weekly_files(state, 'weekly-reviews', 'weekly-review').items():
        references([report['baseline_plan']], plans, name)
        references([report['effective_plan']], plans, name)
        require(report['baseline_plan'] == f"{report['week_id']}.r1.json", f'{name}: invalid baseline plan')
        require(plans[report['effective_plan']]['week_id'] == report['week_id'], f'{name}: plan belongs to a different week')
        references(report['assessment_ids'], assessments, name)
        references(report['card_ids'], cards, name)
        references(report['completed'], goals, name)
        references(report['next_focus'], goals, name)
        number(report['actual_hours'], name)
    if runtime:
        from exy.validation import validate_runtime
        validate_runtime(state, objective, goals, cards, assessments, reviews, plans)
    return f'{len(goals)} goals, {len(cards)} cards, {len(assessments)} assessments, {len(reviews)} reviews, {len(plans)} plans'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=ROOT / 'state')
    args = parser.parse_args()
    try:
        sys.path.insert(0, str(ROOT))
        from exy.store import Store
        with Store(args.state) as store:
            summary = check(store.path)
    except (ValueError, OSError, KeyError, TypeError, AttributeError, RecursionError, ModuleNotFoundError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    print(f'OK: {summary}. Structure checked; learning quality is not evaluated.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
