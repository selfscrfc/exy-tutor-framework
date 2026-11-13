# Exy Tutor Framework

A personal learning framework: an objective, a tree of measurable outcomes, progressively detailed planning, weekly feedback, and knowledge review.

The current version provides a file structure, instructions, templates, and an integrity checker. No curriculum has been defined yet. Automated tutoring, exercise discovery, a user interface, and a working review scheduler are not implemented. A specific curriculum, including preparation for an ML internship, will be added in a separate change.

## Getting started

1. Read the [workflow](docs/workflow.md) and [data model](docs/data-model.md). Agents must also read [AGENTS.md](AGENTS.md).
2. Fill in `state/objective.json`: the intended outcome, success criteria, constraints, weekly hours, and time zone. Leave unknown values as `null`.
3. Run an initial assessment. Record attempts in `state/assessment-log.jsonl`; an unassessed skill is not evidence of zero knowledge.
4. Build the outcome tree in `state/goals.json` using `templates/goal.json`. Duration estimates are hypotheses.
5. Prepare the next weekly plan in `state/plans/` using the template. Define assessment criteria before starting and commit the plan.
6. Follow the workflow. Record cards and attempts as they happen; review the week when the calendar week ends.
7. Run the checks before committing:

```sh
python3 scripts/check.py
python3 -m unittest discover -s tests -v
```

Run these commands from the repository root. They do not modify learning data. The checker requires no third-party Python packages. To check a copy of the state, use `python3 scripts/check.py --state /absolute/path/to/state`.

## Structure

| Path | Purpose |
| --- | --- |
| `state/objective.json` | Overall objective, constraints, and time budget |
| `state/goals.json` | Outcome tree and prerequisite links |
| `state/plans/` | Weekly plan revisions |
| `state/weekly-reviews/` | Weekly results and replanning decisions |
| `state/cards.json` | Shared card registry, including scheduler state |
| `state/assessment-log.jsonl` | History of practical assessments |
| `state/card-review-log.jsonl` | History of card reviews |
| `templates/` | Record templates with empty values |
| `docs/` | Instructions and storage rules |
| `scripts/check.py` | Structure and reference integrity checks |

All paths are relative to the repository root. `state/` is intentionally tracked in Git to preserve learning history. Store secrets and materials containing personal information in the ignored `private/` directory. Publishing the repository requires a separate user decision.

## Next steps

- Integrate a library implementation of FSRS and a review command that saves the event and updated card state atomically.
- Add queue selection that respects time limits, overdue reviews, and new cards.
- Add automatic saving, protection against concurrent writes, and checks for changes to historical events.
- Automate exercise selection, weekly reports, and proposed plan adjustments.
- Add PDF import for study notes and written learning materials, preserving source and page references for use in lessons, exercises, and cards.
- Add a subject-specific curriculum in a separate change after the initial assessment and agreement on the objective.

## Foundations and limitations

The workflow uses spaced review, retrieval practice, explanatory questions, and alternating worked examples with independent exercises: [IES / What Works Clearinghouse](https://ies.ed.gov/ncee/wwc/PracticeGuide/1). Card scheduling will use [FSRS](https://open-spaced-repetition.github.io/ts-fsrs/).

These sources support individual methods. The effectiveness of this particular framework has not yet been evaluated. Evaluate it through independent solutions to new problems, delayed assessments, and time spent maintaining the system.
