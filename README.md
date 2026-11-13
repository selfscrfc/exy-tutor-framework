# Exy Tutor Framework

A personal learning framework: an objective, a tree of measurable outcomes, progressively detailed planning, weekly feedback, and knowledge review.

The pilot runtime supports validated state updates, recoverable transactions, weekly plans and reports, FSRS reviews, and sessions that resume from saved state. A goal-clarification skill establishes the agreement before a curriculum is scheduled. Teaching and assessment remain conversational; the program records evidence and checks consistency.

## Getting started

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/tutor.py init
.venv/bin/python scripts/tutor.py check
.venv/bin/python -m unittest discover -s tests -v
```

Python 3.11+ and macOS/Linux are required. Normal runtime installation only needs `requirements.txt`. Use the [CLI guide](docs/cli.md) for the complete command sequence and the [workflow](docs/workflow.md) for learning decisions. Agents also read [AGENTS.md](AGENTS.md).

Create an isolated use case instead of putting personal learning data in this shared repository:

```sh
.venv/bin/python scripts/create_instance.py ../my-learning --objective "My learning objective"
```

Inside that workspace, use `python3 tutor.py` and ask for `$exy-clarify-goal`. It saves partial answers and a concrete agreement for confirmation before weekly planning. Its unknowns remain explicit until supplied or diagnosed. The `exy-ml` workspace is being prepared separately; no ML proficiency, availability, or curriculum is assumed.

## Structure

| Path | Purpose |
| --- | --- |
| `state/foundation.json` | Goal clarification, open questions, and confirmed agreement |
| `state/settings.json` | Pinned FSRS settings |
| `state/sessions.json` | Sessions and continuation points |
| `state/session-log.jsonl` | Session history |
| `state/objective.json` | Overall objective, constraints, and time budget |
| `state/goals.json` | Outcome tree and prerequisite links |
| `state/plans/` | Weekly plan revisions |
| `state/weekly-reviews/` | Weekly results and replanning decisions |
| `state/cards.json` | Shared card registry, including scheduler state |
| `state/assessment-log.jsonl` | History of practical assessments |
| `state/card-review-log.jsonl` | History of card reviews |
| `templates/` | Record templates with empty values |
| `docs/` | Instructions and storage rules |
| `scripts/check.py` | Locked integrity check and interrupted-transaction recovery |
| `scripts/tutor.py` | Public CLI for planning, sessions, evidence, and reviews |
| `.agents/skills/exy-clarify-goal/` | Goal-clarification skill |

All paths are relative to the repository root. `state/` is intentionally tracked in Git to preserve learning history. Store secrets and materials containing personal information in the ignored `private/` directory. Publishing the repository requires a separate user decision.

## Pilot readiness

Implemented: safe writes with interruption recovery, concurrent-writer serialization, immutable weekly revisions, append-only event history, weekly reports and carryover proposals, FSRS scheduling with review budgets and new-card limits, answer-before-reveal review flow, and fresh-session continuation. The integration tests exercise the public CLI in isolated workspaces.

Before the real two-week pilot, the learner still needs to supply goals and plans, confirm the foundation, and complete any diagnostic work needed for placement. The tutor can then prepare the initial roadmap and the first two weekly plans. No simulated assessment is recorded as real progress.

## Next steps

- Run the two-week pilot and evaluate learning outcomes, retention, and maintenance effort.
- Automate exercise discovery and evidence-based roadmap adjustment after observing the pilot.
- Add replay-based correction of historical FSRS ratings and explicit scheduler-version migrations.
- Add PDF import for study notes and written learning materials, preserving source and page references for use in lessons, exercises, and cards.
- Add a card-creation skill that turns study notes and learned topics into focused review cards, verifies answers against sources, links cards to learning goals, and checks for duplicates before adding them to the shared registry.
- Add a subject-specific curriculum in the separate instance after goal clarification and placement.

## Foundations and limitations

The workflow uses spaced review, retrieval practice, explanatory questions, and alternating worked examples with independent exercises: [IES / What Works Clearinghouse](https://ies.ed.gov/ncee/wwc/PracticeGuide/1). Card scheduling uses the pinned [Python FSRS implementation](https://github.com/open-spaced-repetition/py-fsrs).

These sources support individual methods. The effectiveness of this particular framework has not yet been evaluated. Evaluate it through independent solutions to new problems, delayed assessments, and time spent maintaining the system.
