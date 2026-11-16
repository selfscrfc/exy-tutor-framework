---
name: exy-clarify-goal
description: Clarify a learning objective through focused questions and save an agreed foundation for an Exy Tutor instance before creating its curriculum. Use for starting a learning programme, adapting the framework to a goal, or revisiting its scope.
---

# Clarify a learning goal

Produce a foundation that another tutor session can use to make curriculum decisions. Preserve the user's objective; distinguish what they have actually stated from assumptions and what still needs evidence.

## Begin with existing context

Read the instance's `state/foundation.json`, `state/objective.json`, and any materials the user has supplied. If the instance has prior assessments, inspect the relevant ones. Reuse answers already given; do not run a fixed questionnaire from the beginning every time.

Use the instance's `python3 tutor.py` wrapper. In the framework repository, use `.venv/bin/python scripts/tutor.py --state <instance-state>`. `template foundation` prints the data contract. Never write an instance's learning records into the shared framework's `state/`.

## Ask progressively

Ask one to three closely related questions per turn, then wait. Prefer the question whose answer most changes the plan. Briefly explain a tradeoff when offering options. Do not dump the entire checklist below as a single interrogation.

Resolve the dimensions that matter for this use case:

- **Intended outcome and motivation:** what should change, why it matters, and what counts as success. Separate controllable learning outcomes from external outcomes such as a job offer.
- **Scope:** included and excluded topics, target roles or situations, must-have skills, priorities, and acceptable alternatives. For career goals, request representative vacancies if the target remains unclear; research current requirements only when needed and label inferences.
- **Time and capacity:** target date, its flexibility, realistic available hours by day, blackout dates, scheduling constraints, and time zone. Treat no deadline as an explicit choice rather than an unknown date. Available capacity is an input to analysis; do not treat a preferred number of hours as the required workload.
- **Starting point:** experience, completed work, known difficulties, and evidence. Label self-reports as self-reports; a confident answer about experience is not a proficiency assessment.
- **Resources and constraints:** courses, notes, equipment, access, costs, language, and any accessibility needs the user raises. Ask only where the answer could affect the plan.
- **Verification:** how independent work will be assessed, permitted tools, artifacts to keep, and how progress will be checked after a delay.
- **Tradeoffs and feasibility:** if scope exceeds capacity, present concrete options to narrow scope, move the date, or change effort. Do not silently promise all three.

If the user wants to supply plans later, save known information and the remaining questions, then stop the interview. Do not invent a curriculum to fill the gap. If they decline a nonessential detail, record the decision and proceed.

## Analyze required time before asking for a commitment

Separate **required effort**, **available capacity**, and **agreed commitment**. The learner supplies constraints and availability; the tutor analyzes what the objective and deadline require.

Break the scope into provisional leaf outcomes before scheduling weeks. For each remaining outcome, estimate a range of hours from diagnostic evidence, comparable completed work, or a cited curriculum/exercise breakdown. State the rationale, sources, prerequisites, and uncertainty. Do not invent a universal number of hours to reach a role. If a source is unavailable, label the estimate as an assumption and explain what would calibrate it. If key estimates are missing, keep the recommendation unresolved.

Use `template workload`, then `workload analyze --file <prepared-json>` (or MCP `analyze_workload`). Include the start date, deadline, available study days, known blackout dates, optional daily/weekly capacity, and explicit overhead for reviews and assessments. Do not count parent and child effort together or add overhead already included in leaf estimates. Explain any chosen buffer; it is a planning assumption, not a research finding.

Present the calculated total effort range, required weekly hours, hours per study day, and allocation across actual dates. Compare that demand with available capacity. When they conflict, propose concrete scope, deadline, or capacity alternatives. Ask the learner to accept a specific sustainable weekly and daily commitment after seeing that analysis. Store the selected analysis ID as optional `workload_analysis_id` in the foundation. Keep its estimate distinct from the confirmed `weekly_hours` commitment.

After agreement, give each weekly plan an optional `daily_hours` map covering its seven dates and summing to the weekly budget. Track actual focus intervals with `time` commands or MCP. Start a timer only when the learner starts working, pause it for interruptions, and never count agent computation as learner study time. Use `pace` to compare planned time with logged time and independently verified outcomes. Re-estimate remaining effort when evidence changes; do not subtract logged hours as if they automatically completed learning. Show confidence and sample counts when extrapolating observed pace.

## Establish evidence without turning intake into a course

Choose a small diagnostic only after the target is clear enough. Explain which uncertainty it resolves. Obtain actual answers or artifacts before assigning results; record attempts through `assessment add`. Diagnose missing foundations separately from unfamiliarity with a specific tool.

A foundation may be agreed with diagnostics still pending. Keep `baseline.diagnostic_status` explicit. Before committing a detailed curriculum, resolve the diagnostic gaps that materially change placement, or record the user's informed decision to skip them.

## Save and confirm

Maintain `state/foundation.json` through `foundation save --file <prepared-json>` as the interview progresses. Preserve the exact user meaning in structured fields:

- `objective`, `motivation`, `success_criteria`;
- `scope.included`, `scope.excluded`, `priorities`, `tradeoffs`;
- `target_date`, `weekly_hours`, `timezone`, `constraints`, `resources`;
- `baseline.self_report`, `baseline.evidence`, `baseline.diagnostic_status`;
- `open_questions`, `status`, `confirmed_at`, `confirmation_quote`.

Keep unknown values `null` and unanswered material questions in `open_questions`. Store durable constraints, not unnecessary personal details.

Once essential choices are clear, show a concise proposed agreement: objective, success criteria, scope, effort, timing, current evidence, and remaining diagnostic work. Ask the user to confirm or correct that concrete summary. A request to build the framework is not confirmation of an invented personal learning plan. Set `status: confirmed` only after an explicit response; preserve its relevant wording in `confirmation_quote` and the actual confirmation timestamp. The command synchronizes the agreed objective settings.

A confirmed foundation requires an objective, success criteria, included scope, weekly hours, time zone, no unresolved blocking questions, and explicit confirmation. Optional details may remain unset with their disposition explained. Stop asking when additional answers would not materially change the plan.

After confirmation, hand off the foundation and evidence gaps to curriculum planning. Do not imply that the intake itself establishes mastery or guarantees the external outcome. If circumstances change later, reopen the foundation as `draft`, discuss the affected decisions, and reconfirm the revised agreement.
