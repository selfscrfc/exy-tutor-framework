# Workload recommendations and time tracking

## Required effort, capacity, and commitment

These are separate quantities:

- Required effort is an estimated range supported by diagnostic results, comparable work, or cited curriculum and exercise breakdowns.
- Capacity is the time the learner can realistically allocate, including day-specific constraints and unavailable dates.
- Commitment is the schedule the learner accepts after comparing the first two.

The goal-clarification skill now gathers evidence and computes a recommendation before asking the learner to commit. The calculation is deterministic; the quality of the recommendation still depends on the underlying scope and effort estimates. Source references and rationales are preserved for review. This is an estimate, not a scientifically guaranteed time-to-mastery model.

## Analyze a workload

In an instance:

```sh
python3 tutor.py template workload > /tmp/workload.json
python3 tutor.py workload analyze --file /tmp/workload.json
python3 tutor.py workload latest
```

Fill `start_date`, `deadline`, `timezone`, and `study_days` (Monday=0 through Sunday=6). Add unavailable calendar dates if needed. `daily_capacity_hours` is either null or seven numbers, Monday first; `weekly_capacity_hours` is optional. These represent actual availability, not effort estimates.

For every remaining leaf goal, add an `effort` entry:

```json
{
  "goal_id": "goal-001",
  "min_hours": 6,
  "max_hours": 10,
  "basis": "Estimate from the diagnostic exercise and the remaining course exercises",
  "source_refs": ["assessment-001", "materials/course-outline.md#exercises"]
}
```

The numbers above illustrate the format only. Estimate the actual use case. References are recorded but their truth is not verified automatically. Missing ranges or missing leaf estimates produce `insufficient_evidence` with no numeric recommendation. Parent estimates are rejected to prevent counting the same scope twice.

Supply a separate `overhead_hours` range and rationale for review/assessment time, or explicit zeros if it is already included. Choose and explain `buffer_percent`. The formula is:

```text
Total effort range = (remaining leaf effort + explicit overhead) * (1 + buffer / 100)
Weekly requirement = total effort / calendar weeks until the inclusive deadline
Daily requirement = total effort / available study dates
```

The upper estimate is also distributed across concrete dates, weighted by daily availability when known. These are required hours, not a saved schedule: allocations may exceed capacity, which is reported as a conflict. The result includes available capacity, the shortfall, and options to reduce scope, extend the deadline, or increase capacity if sustainable. With no capacity data, feasibility remains unknown.

Analyses are append-only in `state/workload-log.jsonl`. A recommendation never changes `weekly_hours` or confirms the foundation. After the user accepts a commitment, save the optional `workload_analysis_id` in the foundation and add `daily_hours` to weekly plans. This map must cover all seven dates of the week, sum to `budget_hours`, and leave rest days explicitly at zero. Carryover shifts the dates while preserving the original plan.

## Track real work

Timers persist across processes and conversations. They run only between explicit start/resume and pause/stop operations. Each command requires an actor label and a unique request ID; reuse the same request ID only to retry the same operation.

```sh
python3 tutor.py time start --actor tutor --request-id focus-001 --goal goal-001 --session session-id --activity "Independent exercise"
python3 tutor.py time status
python3 tutor.py time pause --actor tutor --request-id focus-002 --timer timer-id --version 1
python3 tutor.py time resume --actor tutor --request-id focus-003 --timer timer-id --version 2
python3 tutor.py time stop --actor tutor --request-id focus-004 --timer timer-id --version 3
python3 tutor.py session end --note "Continue with the next exercise"
```

Use the timer ID and version actually returned by the preceding command. One timer may run per instance. Different actors cannot operate it under a different owner label. These labels support coordination between trusted local agents; they are not authentication. An explicit handoff may reuse the recorded owner identity. Refresh status after a version conflict rather than blindly retrying with a new request ID.

Start timers only for learner work, not for agent research, model generation, or unattended elapsed time. Intervals over four hours require `--confirm-long`; the threshold is an accidental-overrun guard, not a recommended study duration. For an accidentally running timer, stop at the actual end using the CLI's explicit `--at` timestamp, or record a corrected interval with a reason. Ongoing time is shown as uncommitted and excluded from reports until paused or stopped.

For work that was not timed, use `template time-entry` and `time log --file <file> --actor <actor> --request-id <id>`. Supply actual start/end timestamps with offsets. Overlapping entries are rejected. Corrections append a new entry with `supersedes` and `reason`; reports count only the current version. A correction preserves its goal and session attribution. Corrections to ended sessions are not yet supported.

A session linked to intervals derives `actual_minutes` from the ledger; omit `--minutes` when ending it. A session that already has manual cumulative minutes cannot switch to interval tracking because that could count time twice. Legacy manual sessions continue to work. Non-session time can be logged with `session_id: null` and still appears in pace reports.

## Report pace

```sh
python3 tutor.py pace --from-date 2030-01-07 --to-date 2030-01-20
```

Use the dates of the actual pilot. The report includes:

- Actual daily hours split at local midnight, including daylight-saving changes. Before the foundation is confirmed, a known draft time zone may be used and is labelled as such.
- Daily planned hours from the latest weekly plan revisions.
- Adherence for completed calendar days, excluding the unfinished current day.
- Legacy session totals separately, because cumulative minutes do not identify which days were worked.
- Actual-to-estimated effort for independently completed leaf goals with usable original estimates and attributed intervals.
- A provisional historical-attendance projection once at least seven calendar days have been observed.

The effort ratio is descriptive and reports its sample count through the sample list; fewer than three completed goals is labelled insufficient. Even larger samples are provisional because task difficulty varies. The attendance projection is invalidated when the scoped goals change. Re-analyze remaining work from evidence: time spent is not subtracted from remaining effort and is not treated as mastery.

Time tracking is coordinated per learning instance. Separate instances have separate timers; there is no global cross-project calendar or automatic activity monitor. Use one instance for agents collaborating on the same learning goal.
