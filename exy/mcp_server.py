"""Local stdio MCP API for explicitly registered learning instances."""
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from exy import engine, timekeeping, workload
from exy.store import Store
from exy.instances import InstanceService

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def tool_errors(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ValueError, KeyError, TypeError) as error:
            raise ToolError(str(error)) from error
    return wrapped


def build_server(registry):
    registry = Path(registry).expanduser().resolve()
    server = MCPServer('exy-tutor', instructions=(
        'Use list_instances, then get_context to obtain a state_revision. Work only in the intended instance. '
        'Workload recommendations must use evidenced estimates, not invented proficiency or generic hours. '
        'Confirm a proposed commitment with the learner before changing the foundation or plan. '
        'Start timers only when actual learner work starts, not while agents research or generate answers. '
        'Reuse request_id for retries. Refresh context after a stale-revision error. Actor labels are audit labels, not authentication.'),
        log_level='WARNING')

    service = InstanceService(registry)
    mapping, state_for = service.mapping, service.state_for
    revision, mutate = service.revision, service.mutate

    @server.tool(annotations=READ, structured_output=True)
    @tool_errors
    def list_instances() -> dict[str, Any]:
        """List registered instance names. Other filesystem paths cannot be supplied to tools."""
        return {'instances': sorted(mapping())}

    @server.tool(annotations=READ, structured_output=True)
    @tool_errors
    def get_context(instance: str) -> dict[str, Any]:
        """Read the foundation, goals, latest session, workload analysis, timers, and optimistic-concurrency revision."""
        with Store(state_for(instance)) as store:
            store.validate()
            plans = {}
            for name in store.files:
                if name.startswith('plans/'):
                    plan = store.get(name)
                    if plan['revision'] > plans.get(plan['week_id'], {}).get('revision', 0):
                        plans[plan['week_id']] = plan
            return {'instance': instance, 'state_revision': revision(store), 'foundation': store.get('foundation.json'),
                    'latest_plans': plans, 'recent_assessments': store.get('assessment-log.jsonl')[-10:],
                    'objective': store.get('objective.json'), 'goals': store.get('goals.json'),
                    'latest_session': (store.get('sessions.json') or [None])[-1],
                    'timers': timekeeping.timer_status(store, datetime.now(timezone.utc)),
                    'workload_analysis': workload.latest(store)}

    @server.tool(annotations=READ, structured_output=True)
    @tool_errors
    def get_input_template(instance: str, name: Literal['workload', 'time-entry', 'goal', 'plan', 'foundation', 'assessment', 'card']) -> dict[str, Any]:
        """Get a blank input record. Unknown values must be filled with evidence or left explicitly unknown."""
        state_for(instance)
        return engine.template(name)

    @server.tool(annotations=WRITE, structured_output=True)
    @tool_errors
    def analyze_workload(instance: str, data: dict, request_id: str, expected_revision: str) -> dict[str, Any]:
        """Save an evidence-labelled workload analysis with effort ranges, deadline, study days and optional capacity; does not change commitments."""
        return mutate(instance, request_id, 'analyze_workload', data, expected_revision,
                      lambda store, now: workload.analyze(store, data, now))

    @server.tool(annotations=READ, structured_output=True)
    @tool_errors
    def get_pace(instance: str, from_date: str, to_date: str) -> dict[str, Any]:
        """Report timezone-aware daily time, plan adherence and evidence-based pace; hours alone do not establish mastery."""
        with Store(state_for(instance)) as store:
            store.validate()
            return workload.pace(store, from_date, to_date, datetime.now(timezone.utc))

    @server.tool(annotations=WRITE, structured_output=True)
    @tool_errors
    def manage_timer(instance: str, action: Literal['start', 'pause', 'resume', 'stop'], actor: str,
                     request_id: str, timer_id: str | None = None, expected_version: int | None = None,
                     goal_id: str | None = None, session_id: str | None = None,
                     activity: str | None = None, confirm_long: bool = False) -> dict[str, Any]:
        """Track actual learner focus, excluding pauses. Use current timer version and owner; reuse request_id on retry. Long intervals require confirmation."""
        data = dict(action=action, actor=actor, timer_id=timer_id, expected_version=expected_version,
                    goal_id=goal_id, session_id=session_id, activity=activity, confirm_long=confirm_long)
        return mutate(instance, request_id, 'manage_timer', data, None,
                      lambda store, now: timekeeping.mutate_timer(store, request_id=request_id, now=now, **data))

    @server.tool(annotations=WRITE, structured_output=True)
    @tool_errors
    def record_time(instance: str, data: dict, actor: str, request_id: str) -> dict[str, Any]:
        """Record an actual start/end interval or a correction with supersedes and reason. Overlaps are rejected."""
        return mutate(instance, request_id, 'record_time', {'entry': data, 'actor': actor}, None,
                      lambda store, now: timekeeping.log_time(store, data, actor, request_id, now))

    @server.tool(annotations=WRITE, structured_output=True)
    @tool_errors
    def tutor_action(instance: str,
                     action: Literal['foundation_save', 'configure', 'goal_add', 'goal_update', 'plan_save',
                                     'assessment_add', 'card_add', 'session_start', 'session_checkpoint',
                                     'session_end', 'review_next', 'review_answer', 'review_rate', 'review_skip', 'week_close'],
                     data: dict, request_id: str, expected_revision: str) -> dict[str, Any]:
        """Use the shared tutor workflow. Record-shaped actions take a template record. Session/review actions take their named fields. Refresh context before writes; never fabricate learner confirmation or results."""
        def apply(store, now):
            if action == 'foundation_save': return engine.foundation_save(store, data)
            if action == 'configure': return engine.configure(store, data)
            if action in {'goal_add', 'goal_update'}: return engine.goal_save(store, data, action == 'goal_update')
            if action == 'plan_save': return engine.save_plan(store, data)
            if action == 'assessment_add': return engine.assessment_add(store, data['assessment'], now, data.get('session_id'), data.get('complete', False))
            if action == 'card_add': return engine.card_add(store, data, now)
            if action == 'session_start': return engine.session_start(store, data['week'], now, data.get('goal_ids'))
            if action in {'session_checkpoint', 'session_end'}:
                return engine.session_finish(store, data.get('session_id'), data['note'], data.get('minutes'), now, action == 'session_end')
            if action == 'review_next': return engine.review_next(store, data.get('session_id'), now)
            if action == 'review_answer': return engine.review_answer(store, data.get('session_id'), data['response'], now)
            if action == 'review_rate': return engine.review_rate(store, data.get('session_id'), data['rating'], data['seconds'], now)
            if action == 'review_skip': return engine.review_skip(store, data.get('session_id'), now)
            if action == 'week_close': return engine.week_close(store, data['week'], data.get('notes', {}), now)
            raise ValueError('Unsupported tutor action')
        return mutate(instance, request_id, action, data, expected_revision, apply)

    return server
