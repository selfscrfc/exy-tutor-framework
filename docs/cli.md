# Pilot CLI

## Setup

Python 3.11 or newer on macOS/Linux is required. Storage uses POSIX file locks. From the framework repository:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/tutor.py init
.venv/bin/python scripts/tutor.py check
.venv/bin/python -m unittest discover -s tests -v
```

Only `requirements.txt` is needed for normal use; the development file also installs the skill validator dependency. FSRS is pinned to a tested library release. Scheduler parameters are stored with the instance; fuzzing is disabled for reproducible reviews.

Create a separate instance with an empty or nonexistent destination:

```sh
.venv/bin/python scripts/create_instance.py ../my-learning --objective "My learning objective"
```

The creator initializes a local Git repository, copies the goal-clarification skill, and creates empty state. It refuses a nonempty destination and does not publish anything. Within that instance, use `python3 tutor.py` instead of the framework command. Its wrapper always selects its own state. Dependencies and code are shared; learning data is not.

All examples below use the instance wrapper. Each command returns JSON. Errors use stderr and a nonzero exit code. Global `--at` accepts a time-zone-aware timestamp for isolated rehearsals; omit it for real sessions. To inspect another state directly, use the framework's `scripts/tutor.py --state <directory>`.

## Clarify the objective

Use `$exy-clarify-goal` in the instance. The skill gathers existing information, asks focused follow-ups, saves draft answers, and presents a concrete agreement for confirmation.

```sh
python3 tutor.py template foundation > /tmp/foundation.json
# Fill the template with actual user answers. Leave status as draft until confirmed.
python3 tutor.py foundation save --file /tmp/foundation.json
python3 tutor.py status
```

A confirmed foundation synchronizes the objective, success criteria, target date, weekly hours, time zone, and constraints. Confirmation requires the user's actual response, not an agent-generated approval. Reopen the foundation as `draft` before changing an agreed objective. Pending diagnostics remain explicitly pending.

Set review capacity separately using an objective patch. For example, after agreeing on these limits:

```json
{"review_budget_minutes_per_session": 15, "max_new_cards_per_session": 3}
```

Save that JSON to a file and run `python3 tutor.py configure --file <file>`. These values are examples, not assumed user preferences.

## Outcomes and plans

Use `template goal` and `template plan` to prepare input files. For new records, set `id` to `null` for a generated ID, or provide a unique stable ID.

```sh
python3 tutor.py goal add --file /tmp/goal.json
python3 tutor.py goal update --file /tmp/updated-goal.json
python3 tutor.py plan save --file /tmp/week.json
```

Goal updates take the complete record. A planned outcome needs success criteria, activities, an assistance policy, and an hour estimate. Set review, assessment, and buffer hours explicitly, including zero if intentional. Their sum plus activity hours must fit the weekly budget. Keep activity estimates exclusive of the separate assessment/review allocations to avoid double counting.

`plan save` assigns the next revision automatically. Later revisions need `change_reason`. Original plans remain immutable. You can plan a later outcome before its prerequisites are completed, but a session cannot select that outcome until the prerequisites are complete. Select only ready goals with `session start --goals <id> ...` when the week contains dependent work.

## Sessions and evidence

```sh
python3 tutor.py session start --week YYYY-MM-DD --goals goal-id
python3 tutor.py session resume
python3 tutor.py session checkpoint --minutes 25 --note "Continue with the independent exercise"
python3 tutor.py assessment add --file /tmp/assessment.json --session session-id --complete
python3 tutor.py session end --minutes 60 --note "Next: review the error and solve a fresh example"
```

`YYYY-MM-DD` is the plan's week-start date in the agreed time zone. A session must start within that week. `resume` returns its saved plan, current plan revision, selected goals, recent assessments, review queue, and continuation note. It also works after a session ends; use `start` to begin a new one.

Minutes are actual cumulative session time supplied by the learner, not elapsed wall-clock time. Reviews are included in that total. Assessments can be recorded without a session for initial diagnostics. `--complete` is optional and only succeeds when all goal criteria have independent supporting evidence. Record permitted tools, actual assistance, a rubric, and an artifact. The program checks consistency, not whether an answer is genuinely correct.

To correct an assessment, add a new event with `supersedes` pointing to the old ID. A correction removes the old event from current completion evidence; historical records stay visible. Changing a criterion requires new evidence for that criterion.

## Cards and FSRS

Prepare cards using `template card`. Supply verified prompts, answers, sources, goal IDs, and a verification timestamp before setting `status: active`. Unverified cards remain drafts. The card-creation skill and PDF importer are still backlog items.

```sh
python3 tutor.py card add --file /tmp/card.json
python3 tutor.py review queue
python3 tutor.py review next
python3 tutor.py review answer --response "My answer before seeing the reference"
python3 tutor.py review rate good --seconds 45
```

The first display hides the answer. `answer` saves the attempted response and reveals the reference; `rate` saves the event and new schedule in the same recoverable transaction. Ratings are `again`, `hard`, `good`, and `easy`. Forgotten answers are `again`. A skipped review does not change the schedule and is deferred for the rest of the current session:

```sh
python3 tutor.py review skip
python3 tutor.py card status card-id suspended
```

Due cards come before new cards, across all learning goals. New-card limits apply per session; resuming the session does not reset them. Queue size uses a stored per-card duration estimate and actual time already spent. A final review may take longer than estimated; the next queue then stops when the budget is exhausted. It is a workload guide, not a real-time timer. Review operations cannot proceed after the session ends.

Each review stores the exact FSRS state before and after it. The current version does not support retroactively changing a scheduled rating; that would require replaying subsequent events. Do not edit FSRS state manually.

## Weekly review and carryover

After the calendar week ends and its sessions have ended:

```sh
python3 tutor.py week close --week YYYY-MM-DD --notes-file /tmp/weekly-notes.json
python3 tutor.py plan carry --from-week YYYY-MM-DD --to-week YYYY-MM-DD > /tmp/next-week.json
# Review the proposed carryover, add appropriate work, and adjust estimates.
python3 tutor.py plan save --file /tmp/next-week.json
```

The optional notes file accepts `deviations`, `decisions`, `next_focus` (goal IDs), and `change_reason` (required for later report revisions). The report derives actual hours from session records, links evidence and cards, and compares actual time with the original budget. Its goal-status snapshot is explicitly taken when the report is generated. `carry` outputs a proposal without saving or rewriting anything; it excludes completed and dropped goals. If no work remains, choose new outcomes before saving a plan.

## Storage and recovery

Run `python3 tutor.py check` before committing state. Commands serialize access through a local lock. An interrupted commit leaves a recovery journal; the next command finishes it. If recovery detects conflicting external edits, preserve the journal and investigate the conflict. Do not run a Git operation or manual edit concurrently with a CLI mutation.

The supported pilot is one local learner on a macOS/Linux filesystem. Multi-device synchronization, hosted users, and shared network filesystems have not been validated.
