# Data model

## General rules

Format version 1. JSON uses UTF-8; each JSONL log contains one JSON object per line. Empty arrays and logs are valid before learning starts. Templates contain unfilled values and are not themselves live state.

IDs are stable and unique within each type: `goal-001`, `card-001`, `assessment-001`, `review-001`. Event timestamps use ISO 8601 with a time zone, such as `2030-01-07T18:30:00+03:00`. A week is identified by its start date, `YYYY-MM-DD`.

## Entities

| File | Data and relationships |
| --- | --- |
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

Cards: `draft`, `active`, `suspended`, `archived`. An active card has a prompt, answer/rubric, source, and verification timestamp. `scheduler` and `due_at` remain `null` until a real scheduler is integrated. If the knowledge being tested changes substantially, create a new card and archive the old one; do not transfer memory history to different content.

Practical attempts: `unknown`, `passed`, `partial`, `failed`. Values for `assistance`: `none`, `allowed_tools`, `hints`, `solution_shown`. Attempts with `none` or `allowed_tools` may count as independent if the conditions were defined before assessment. `rubric` preserves a snapshot of the criterion at the time of the attempt; changing the current goal does not rewrite history.

## History and changes

Logs are append-only; do not edit historical events. To correct an event, append a new event with `supersedes` pointing to the previous event of the same type and for the same goal/card. Events that have not been superseded are current. A new attempt after further learning is not a correction and does not use `supersedes`.

Weekly plans and reports are saved as revisions. File names must follow `YYYY-MM-DD.rN.json`. Plan revision 1 remains the comparison baseline; later revisions include a reason for the change. The workflow and Git preserve history; the skeleton does not automatically prevent overwrites.

When splitting a leaf, preserve its ID and make it a parent. Existing cards and attempts remain linked to it; add more specific links when needed. Revisit a completed parent if its children are incomplete.

## What check.py verifies

The checker reads actual state and validates container formats, required keys, IDs, references, parent/prerequisite cycles, numeric constraints, weekly file revisions, and evidence supporting `completed` status. Superseded events cannot be used as current evidence. A failed check returns a nonzero exit code.

The checker does not judge answer correctness, exercise quality, card suitability, or whether recorded time is accurate. It does not implement FSRS or guarantee that previously committed data remains unchanged. A successful structural check does not establish any of these properties.
