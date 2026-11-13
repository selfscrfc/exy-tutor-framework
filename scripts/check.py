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
    require(type(value) is type(sample), f'{label}: неверный тип')
    if isinstance(sample, dict):
        for key, expected in sample.items():
            require(key in value, f'{label}: отсутствует {key}')
            shape(value[key], expected, f'{label}.{key}')
    elif isinstance(sample, list) and sample:
        for i, item in enumerate(value):
            shape(item, sample[0], f'{label}[{i}]')


def number(value, label, nullable=True):
    if value is None and nullable:
        return
    require(type(value) in (int, float) and value >= 0 and value < float('inf'),
            f'{label}: требуется конечное неотрицательное число')


def timestamp(value, label, nullable=False):
    if value is None and nullable:
        return
    require(isinstance(value, str), f'{label}: требуется дата с часовым поясом')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None, f'{label}: отсутствует часовой пояс')


def records(state, filename, template, journal=False):
    path = state / filename
    items = ([json.loads(line) for line in path.read_text().splitlines() if line.strip()]
             if journal else read_json(path))
    require(isinstance(items, list), f'{filename}: требуется массив')
    sample = read_json(ROOT / 'templates' / f'{template}.json')
    result = {}
    for item in items:
        shape(item, sample, filename)
        identifier = item['id']
        require(bool(identifier.strip()) and identifier not in result,
                f'{filename}: пустой или повторный ID {identifier!r}')
        result[identifier] = item
    return result


def references(ids, registry, label):
    require(isinstance(ids, list) and all(isinstance(x, str) for x in ids),
            f'{label}: требуется список ID')
    require(len(ids) == len(set(ids)), f'{label}: повторные ссылки')
    for identifier in ids:
        require(identifier in registry, f'{label}: неизвестная ссылка {identifier}')


def acyclic(graph, label):
    visiting, visited = set(), set()

    def visit(node):
        require(node not in visiting, f'{label}: цикл у {node}')
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
                    f'{identifier}: исправление должно ссылаться на предыдущее актуальное событие')
            require(seen[old][entity_key] == event[entity_key],
                    f'{identifier}: исправление относится к другой сущности')
            replaced.add(old)
        seen[identifier] = event
    return {key: event for key, event in events.items() if key not in replaced}


def weekly_files(state, directory, template):
    require((state / directory).is_dir(), f'Отсутствует каталог {directory}')
    sample = read_json(ROOT / 'templates' / f'{template}.json')
    result = {}
    for path in sorted((state / directory).glob('*.json')):
        item = read_json(path)
        shape(item, sample, str(path))
        require(date.fromisoformat(item['week_id']).isoformat() == item['week_id'],
                f'{path.name}: неверная дата недели')
        revision = item['revision']
        require(revision >= 1, f'{path.name}: ревизия должна быть положительной')
        require(path.name == f"{item['week_id']}.r{revision}.json", f'{path.name}: неверное имя файла')
        if revision > 1:
            require(isinstance(item['change_reason'], str) and item['change_reason'].strip(),
                    f'{path.name}: нужна причина изменения')
        result[path.name] = item
    for name, item in result.items():
        for revision in range(1, item['revision']):
            require(f"{item['week_id']}.r{revision}.json" in result,
                    f'{name}: отсутствует предыдущая ревизия')
    return result


def check(state):
    objective = read_json(state / 'objective.json')
    shape(objective, read_json(ROOT / 'templates/objective.json'), 'objective')
    require(objective['schema_version'] == 1, 'Неизвестная версия формата')
    for key in ['weekly_hours', 'review_budget_minutes_per_session', 'max_new_cards_per_session']:
        number(objective[key], key)
    horizon = objective['planning']
    require(0 < horizon['detailed_weeks'] <= horizon['weekly_outcomes_weeks'], 'Неверные горизонты плана')
    goals = records(state, 'goals.json', 'goal')
    cards = records(state, 'cards.json', 'card')
    assessments = records(state, 'assessment-log.jsonl', 'assessment', journal=True)
    reviews = records(state, 'card-review-log.jsonl', 'card-review', journal=True)
    active_assessments = current_events(assessments, 'goal_id')
    current_events(reviews, 'card_id')
    children = {identifier: [] for identifier in goals}
    for identifier, goal in goals.items():
        require(bool(goal['title'].strip()), f'{identifier}: пустое название')
        require(goal['status'] in {'draft', 'ready', 'active', 'blocked', 'completed', 'dropped'},
                f'{identifier}: неизвестный статус')
        if goal['status'] == 'blocked':
            require(bool(goal['notes'].strip()), f'{identifier}: укажи причину блокировки')
        if goal['parent_id'] is not None:
            references([goal['parent_id']], goals, identifier)
            children[goal['parent_id']].append(identifier)
        references(goal['depends_on'], goals, identifier)
        references(goal['evidence_ids'], active_assessments, identifier)
        criterion_ids = [c['id'] for c in goal['criteria']]
        require(all(criterion_ids) and len(set(criterion_ids)) == len(criterion_ids),
                f'{identifier}: повторные или пустые критерии')
        for bound in ['min', 'max']:
            number(goal['estimate_hours'][bound], identifier)
        low, high = goal['estimate_hours']['min'], goal['estimate_hours']['max']
        require(low is None or high is None or low <= high, f'{identifier}: неверный диапазон часов')
    acyclic({key: children[key] + goal['depends_on'] for key, goal in goals.items()},
            'Дерево результатов и предпосылки')
    for identifier, event in assessments.items():
        references([event['goal_id']], goals, identifier)
        require(event['result'] in {'unknown', 'passed', 'partial', 'failed'}, f'{identifier}: неверный результат')
        require(event['assistance'] in {'none', 'allowed_tools', 'hints', 'solution_shown'},
                f'{identifier}: неизвестный вид помощи')
        number(event['duration_minutes'], identifier)
        # Старые критерии могут отличаться от текущих: снимок сохраняется в rubric.
    for identifier, goal in goals.items():
        events = [active_assessments[key] for key in goal['evidence_ids']]
        require(all(event['goal_id'] == identifier for event in events), f'{identifier}: чужое доказательство')
        if goal['status'] == 'completed':
            require(goal['criteria'] and all(c['description'].strip() and c['verification'].strip()
                                            for c in goal['criteria']), f'{identifier}: нужны критерии завершения')
            supported = set()
            for event in events:
                if (event['result'] == 'passed' and event['assistance'] in {'none', 'allowed_tools'}
                        and event['artifact'].strip() and event['rubric'].strip()
                        and event['assistance_policy'].strip()):
                    supported.update(event['criterion_ids'])
            require(all(c['id'] in supported for c in goal['criteria']),
                    f'{identifier}: нет самостоятельного подтверждения всех критериев')
            require(all(goals[child]['status'] in {'completed', 'dropped'} for child in children[identifier]),
                    f'{identifier}: есть незавершённые дочерние цели')
    for identifier, card in cards.items():
        references(card['goal_ids'], goals, identifier)
        require(card['status'] in {'draft', 'active', 'suspended', 'archived'}, f'{identifier}: неверный статус')
        timestamp(card['verified_at'], identifier, nullable=True)
        timestamp(card['due_at'], identifier, nullable=True)
        if card['status'] == 'active':
            require(card['goal_ids'] and all(card[key].strip() for key in ['prompt', 'answer', 'source'])
                    and card['verified_at'], f'{identifier}: активная карточка не проверена или не заполнена')
        require(card['scheduler'] is None and card['due_at'] is None,
                f'{identifier}: FSRS ещё не подключён; состояние планировщика должно быть null')
    for identifier, event in reviews.items():
        references([event['card_id']], cards, identifier)
        require(event['rating'] in {'again', 'hard', 'good', 'easy'}, f'{identifier}: неизвестная оценка')
        require(event['scheduler_version'] is None, f'{identifier}: FSRS ещё не подключён')
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
                f'{name}: план превышает бюджет')
    for name, report in weekly_files(state, 'weekly-reviews', 'weekly-review').items():
        references([report['baseline_plan']], plans, name)
        references([report['effective_plan']], plans, name)
        require(report['baseline_plan'] == f"{report['week_id']}.r1.json", f'{name}: неверный исходный план')
        require(plans[report['effective_plan']]['week_id'] == report['week_id'], f'{name}: план другой недели')
        references(report['assessment_ids'], assessments, name)
        references(report['card_ids'], cards, name)
        references(report['completed'], goals, name)
        references(report['next_focus'], goals, name)
        number(report['actual_hours'], name)
    return f'{len(goals)} целей, {len(cards)} карточек, {len(assessments)} проверок, {len(reviews)} повторений, {len(plans)} планов'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=ROOT / 'state')
    args = parser.parse_args()
    try:
        summary = check(args.state)
    except (ValueError, OSError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    print(f'OK: {summary}. Проверена структура, не качество обучения.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
