"""JSON CLI for the pilot workflow. Use --help on a command group for details."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from exy import engine as e
from exy.scheduling import parse_time
from exy.store import ROOT, Store


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state', type=Path, default=ROOT / 'state')
    p.add_argument('--at', help='Explicit ISO timestamp for deterministic rehearsals; defaults to now')
    commands = p.add_subparsers(dest='command', required=True)
    commands.add_parser('init', help='Initialize or upgrade an instance without replacing existing data')
    commands.add_parser('check', help='Validate state under the storage lock')
    commands.add_parser('status', help='Show objective, active session, and goal counts')
    templates = commands.add_parser('template', help='Print a blank input record')
    templates.add_argument('name', choices=[path.stem for path in (ROOT / 'templates').glob('*.json')])
    configure = commands.add_parser('configure', help='Apply an objective settings patch')
    configure.add_argument('--file', required=True, type=Path)
    for group, actions in [('goal', ['add', 'update']), ('assessment', ['add']), ('card', ['add']),
                           ('plan', ['save']), ('foundation', ['save'])]:
        sub = commands.add_parser(group).add_subparsers(dest='action', required=True)
        for action in actions:
            item = sub.add_parser(action)
            item.add_argument('--file', required=True, type=Path)
            if group == 'assessment':
                item.add_argument('--session')
                item.add_argument('--complete', action='store_true')
        if group == 'card':
            item = sub.add_parser('status')
            item.add_argument('id')
            item.add_argument('status', choices=['draft', 'active', 'suspended', 'archived'])
        if group == 'plan':
            item = sub.add_parser('carry', help='Output a proposed carryover plan; save after reviewing it')
            item.add_argument('--from-week', required=True)
            item.add_argument('--to-week', required=True)
    sessions = commands.add_parser('session').add_subparsers(dest='action', required=True)
    start = sessions.add_parser('start')
    start.add_argument('--week', required=True)
    start.add_argument('--goals', nargs='+')
    resume = sessions.add_parser('resume')
    resume.add_argument('--session')
    for action in ('checkpoint', 'end'):
        item = sessions.add_parser(action)
        item.add_argument('--session')
        item.add_argument('--note', required=True)
        item.add_argument('--minutes', type=float, required=True, help='Cumulative actual session minutes')
    reviews = commands.add_parser('review').add_subparsers(dest='action', required=True)
    for action in ('queue', 'next', 'answer', 'rate', 'skip'):
        item = reviews.add_parser(action)
        item.add_argument('--session')
        if action == 'answer':
            item.add_argument('--response', required=True)
        if action == 'rate':
            item.add_argument('rating', choices=['again', 'hard', 'good', 'easy'])
            item.add_argument('--seconds', required=True, type=float)
    weeks = commands.add_parser('week').add_subparsers(dest='action', required=True)
    close = weeks.add_parser('close')
    close.add_argument('--week', required=True)
    close.add_argument('--notes-file', type=Path, help='Optional deviations, decisions, and next_focus')
    return p


def read(path):
    return json.loads(path.read_text())


def execute(s, a, now):
    if a.command == 'template':
        return e.template(a.name)
    if a.command == 'init':
        return e.init(s)
    e.need('settings.json' in s.files, 'Run init to upgrade this instance first')
    s.validate()
    if a.command == 'check':
        return {'ok': True, 'summary': s.validate()}
    if a.command == 'status':
        goals = s.get('goals.json')
        return {'objective': s.get('objective.json'), 'foundation': s.get('foundation.json'),
                'goal_counts': {status: sum(g['status'] == status for g in goals) for status in sorted({g['status'] for g in goals})},
                'active_sessions': [x for x in s.get('sessions.json') if x['ended_at'] is None]}
    if a.command == 'configure':
        return e.configure(s, read(a.file))
    if a.command == 'foundation':
        return e.foundation_save(s, read(a.file))
    if a.command == 'goal':
        return e.goal_save(s, read(a.file), a.action == 'update')
    if a.command == 'assessment':
        return e.assessment_add(s, read(a.file), now, a.session, a.complete)
    if a.command == 'card':
        return e.card_add(s, read(a.file), now) if a.action == 'add' else e.card_status(s, a.id, a.status)
    if a.command == 'plan':
        return e.save_plan(s, read(a.file)) if a.action == 'save' else e.carry_plan(s, a.from_week, a.to_week)
    if a.command == 'session':
        if a.action == 'start':
            return e.session_start(s, a.week, now, a.goals)
        if a.action == 'resume':
            return e.session_resume(s, a.session, now)
        return e.session_finish(s, a.session, a.note, a.minutes, now, a.action == 'end')
    if a.command == 'review':
        if a.action == 'queue':
            return e.queue(s, e.current_session(s, a.session), now)
        if a.action == 'next':
            return e.review_next(s, a.session, now)
        if a.action == 'answer':
            return e.review_answer(s, a.session, a.response, now)
        if a.action == 'rate':
            return e.review_rate(s, a.session, a.rating, a.seconds, now)
        return e.review_skip(s, a.session, now)
    if a.command == 'week':
        return e.week_close(s, a.week, read(a.notes_file) if a.notes_file else {}, now)
    raise ValueError('Unsupported command')


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        now = parse_time(args.at) if args.at else datetime.now(timezone.utc)
        with Store(args.state) as store:
            result = execute(store, args, now)
            store.commit()
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, AttributeError, AssertionError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
