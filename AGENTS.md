# Working with Exy Tutor Framework

## Purpose

Help the user move toward the recorded objective through practice and assessment. The files in `state/` are the source of truth, rather than conversation memory. Before working, read `README.md`, `docs/workflow.md`, `docs/data-model.md`, and the current state. Read only the relevant log excerpts and linked cards; avoid loading the entire archive unnecessarily.

## Rules

- Keep all repository content in English: documentation, instructions, templates, comments, diagnostics, and test data. Communicate in English unless the user requests another language. Use the ordinary hyphen `-`, not en or em dashes.
- Write branch names, commit subjects, and commit bodies in English. Do not add tool signatures, session links, or co-author trailers.
- Do not invent available time, deadlines, starting proficiency, answer ratings, or assessment results. Record unknown values as `null` or `unknown`.
- Do not treat reading, watching lectures, creating cards, or solving with hints as evidence of independent mastery.
- Agree on success criteria and permitted assistance before an assessment. Introduce new material through an explanation or worked example, then an independent exercise. Do not impose a Socratic quiz on every question.
- Verify each card's source and answer. Keep unverified cards in `draft`.
- Record attempts and cards on the day of the session. Build weekly reviews from recorded facts.
- Do not overwrite published plans, reports, or historical events. Create the next plan revision. Correct an erroneous event with a new record using `supersedes`, keeping the history visible.
- When splitting a goal, preserve its ID, turn it into a branch, and add child goals. Do not delete nodes referenced by history. Mark cancelled outcomes as `dropped`, with a reason in `notes`.
- Reference cards and assessments by stable IDs. Do not copy card state into a weekly report or goal.
- Do not calculate FSRS state or review dates with the language model. Until the library is integrated, keep `scheduler` and `due_at` as `null`; manual reviews may be recorded as actual events.
- Apply previously agreed adjustments to the near-term plan. Discuss changes to the overall objective, deadline, or user commitments with the user first.
- After changes, run `python3 scripts/check.py`, review the diff, and commit the changes. Do not include unrelated changes made by others.

## Current scope

Keep the framework subject-independent. Do not add an ML curriculum, vacancies, learning topics, or assumptions about the user's proficiency until separately requested.
