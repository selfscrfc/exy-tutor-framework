# Data model

## General rules

The original record format remains version 1. `settings.json` identifies the operational runtime and pinned scheduler; `init` adds missing operational files without replacing existing records. JSON uses UTF-8; each JSONL log contains one JSON object per line. Empty arrays and logs are valid before learning starts. Templates contain unfilled values and are not themselves live state.

IDs are stable and unique within each type: `goal-001`, `card-001`, `assessment-001`, `review-001`. Event timestamps use ISO 8601 with a time zone, such as `2030-01-07T18:30:00+03:00`. A week is identified by its start date, `YYYY-MM-DD`.

## Entities

| File | Data and relationships |
| --- | --- |
| `foundation.json` | Draft or confirmed learning agreement, evidence gaps, and user confirmation |
| `settings.json` | Runtime version and serialized FSRS settings |
| `sessions.json` | Session state, actual minutes, pending review, and continuation point |
| `session-log.jsonl` | Append-only session snapshots |
| `objective.json` | Overall objective, success criteria, constraints, and workload settings |
| `goals.json` | Array of nodes: parent, prerequisites, criteria, estimated hours, status, and evidence references |
| `plans/*.json` | Weekly plan revision: goal IDs, expected outcomes and criteria, activities, and budget |
| `weekly-reviews/*.json` | Weekly report: plan references, actual results, attempt and card IDs, reasons for deviations, and decisions |
| `cards.json` | Shared registry: prompt, answer/rubric, source, related goals, status, and scheduler state |
| `assessment-log.jsonl` | Practical attempts: goal, covered criteria, permitted assistance, result, artifact, and errors |
| `card-review-log.jsonl` | Reviews: card ID, answer rating, timestamp, duration, and scheduler version |

See `templates/` for exact fields. Cards link to goals through `goal_ids`. Reverse lists on goals are derived rather than duplicated. Weekly reports store only `card_ids` and `assessment_ids`, not copies of card state.

## States

Goals: `draft`, `ready`, `active`, `blocked`, `completed`, `dropped`. A `blocked` goal requires a reason in `notes`. A leaf has outcome criteria with local IDs and a verification method. A branch may remain broad and have no criteria until refined; completion requires criteria.

Cards: `draft`, `active`, `suspended`, `archived`. An active card has a prompt, answer/rubric, source, and verification timestamp. `scheduler` contains the serialized FSRS card and `due_at` mirrors its due date. The CLI initializes both. `created_at` records registry creation; migrated cards also record `imported_at`. If the knowledge being tested changes substantially, create a new card and archive the old one; do not transfer memory history to different content.

Practical attempts: `unknown`, `passed`, `partial`, `failed`. Values for `assistance`: `none`, `allowed_tools`, `hints`, `solution_shown`. Attempts with `none` or `allowed_tools` may count as independent if the conditions were defined before assessment. `rubric` preserves a snapshot of the criterion at the time of the attempt; changing the current goal does not rewrite history.

## History and changes

Logs are append-only; do not edit historical events. To correct an event, append a new event with `supersedes` pointing to the previous event of the same type and for the same goal/card. Events that have not been superseded are current. A new attempt after further learning is not a correction and does not use `supersedes`.

Weekly plans and reports are saved as revisions. File names must follow `YYYY-MM-DD.rN.json`. Plan revision 1 remains the comparison baseline; later revisions include a reason for the change. The CLI rejects overwrites of published plans and reports and edits to historical log prefixes. Git preserves committed revisions. Direct file edits bypass these command-level protections.

When splitting a leaf, preserve its ID and make it a parent. Existing cards and attempts remain linked to it; add more specific links when needed. Revisit a completed parent if its children are incomplete.

## What check.py verifies

The checker reads actual state and validates container formats, required keys, IDs, references, parent/prerequisite cycles, numeric constraints, weekly file revisions, and evidence supporting `completed` status. Superseded events cannot be used as current evidence. A failed check returns a nonzero exit code.

The checker does not judge answer correctness, exercise quality, card suitability, or whether recorded time is accurate. It validates the FSRS state/history chain but does not judge a self-assigned rating or guarantee that directly edited Git history is unchanged. A successful structural check does not establish any of these properties.

## Transactions and recovery

All CLI readers and writers acquire an exclusive POSIX file lock (`.lock`). Proposed changes are validated in an isolated staging directory before touching live records. A durable `.pending-transaction.json` records the complete write set and previous hashes. Files are replaced atomically, then the journal is removed. After an interruption, the next CLI command finishes the recorded transaction under the same lock. Conflicting external edits stop recovery instead of silently overwriting data.

This provides consistent reads for CLI clients and recoverable commits across multiple files. An external editor reading raw files during a commit can see an intermediate state. Do not edit files while a command is running. Do not delete a pending journal: it is the recovery record. The checker may create a lock or finish an interrupted transaction; ordinary checks leave learning records unchanged.

Scheduled review events include the attempted response, session ID, previous and next FSRS state, library review log, and scheduler settings. Scheduled reviews cannot be corrected by changing the historical rating in place; a replay-based correction command is not yet implemented. Assessment corrections use `supersedes`; a failed correction reopens a completed goal. Assessment criteria snapshots prevent changed criteria from reusing stale completion evidence.

`init` upgrades legacy cards by replaying their current manual review events through FSRS without changing the old logs. Unknown schema or scheduler versions fail explicitly; upgrading the pinned library requires a deliberate migration. Keep using the pinned version during the pilot.
