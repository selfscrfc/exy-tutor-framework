# Workflow

## 1. Start

Use the goal-clarification skill and `foundation save` to record and confirm the learning agreement. See [CLI guide](cli.md) for all state-changing commands. The user supplies actual constraints and confirms the proposed foundation before a weekly plan is published.

Record the overall objective and an observable success criterion. Distinguish outcomes within the learner's control from external conditions. Record available weekly hours, constraints, and a target date if one exists. Then run an initial assessment using small independent tasks. Confirm gaps through attempts; do not replace an unknown proficiency level with a guess.

The tree describes the outcomes needed for the objective. The weekly plan describes the work currently selected. A leaf is usually estimated to take about one week of available study time, but the calendar does not define the tree structure. Several small outcomes can fit into one week; one outcome can continue into the next.

The tree uses `parent_id`. Prerequisites use `depends_on`: dependencies may cross branches but must not form cycles. Choose the next outcome based on its contribution to the overall objective, prerequisite readiness, observed gaps, and available time.

## 2. Progressive planning

- The next two weeks: specific outcomes, criteria, activities, and estimated hours.
- Subsequent weeks through week eight: approximately weekly outcomes with prerequisites; activities can be refined later.
- Beyond that: broad outcomes with effort ranges and explicit uncertainties.

These are initial settings, not mandatory pedagogical constants. Shift the planning window and refine the immediate plan weekly. Revisit distant branches monthly. Review sooner if the objective, available time, or assessment results change substantially.

After the first few weeks, compare actual hours with estimates for comparable tasks. Distinguish insufficient time, underestimated difficulty, and missing prerequisites. One unsuccessful week is not a reason to automatically change the entire forecast.

## 3. Weekly plan

Create `state/plans/YYYY-MM-DD.r1.json`, using the week's start date in the chosen time zone. Record expected outcomes, success criteria, permitted assistance, practical activities, and a budget. Allocate part of the total budget to reviews, practical assessments, and a small buffer; do not fill all available time with new material in advance.

Once the week begins, do not edit the original plan. If the scope changes, create `r2`, fill in `change_reason`, and preserve `r1`. Compare actual results with the original plan in the weekly report and explain changes separately.

Select activities from a suitable course, documentation, or exercise bank, or have the agent create them with a verified solution. Record the source and expected outcome. Exercise discovery remains conversational; the runtime does not search for or generate exercises automatically.

## 4. Learning session

Use `session start` or `session resume`; use `session checkpoint` during work and `session end` with actual cumulative minutes and a continuation note. A fresh conversation resumes from these records.

1. Read the current plan, its related goals, and recent errors.
2. Use `review queue` and `review next` for scheduled cards, `review answer` to record recall before revealing the answer, and `review rate` to save the rating and schedule.
3. For new material, work through an example and then give an independent exercise.
4. Examine the actual solution. Record assistance, the result, and an artifact reference in the assessment log.
5. Create a small number of useful cards from important ideas and errors. Verify answers and sources; suspend redundant cards rather than deleting their history.
6. Save the facts and the point from which to continue. Do not require a weekly report after every session.

Practice exercises and completion assessments serve different purposes: define assessment criteria in advance, and use tasks that test transfer to a new case. For code, prefer real execution and tests; an AI rating does not replace checking the result.

## 5. End of week

Create `state/weekly-reviews/YYYY-MM-DD.r1.json`: the original plan, the effective revision, actual time, completed work, assessment results, errors, and reasons for deviations. Reference card and attempt IDs from the week. Update the immediate plan using this evidence.

The calendar closes the week. Criteria close the goal. `completed` means the outcome was demonstrated in the referenced assessment, not permanent mastery. A later assessment may reveal that the goal needs more work: change its status while keeping the original successful attempt in the log.

To complete a goal, successful independent attempts must cover all its criteria, with artifacts and a defined assistance policy. A parent goal requires completion of its current child outcomes; if an integrated outcome is needed, assess it separately against the parent's criteria.

## 6. Reviews and workload

The card registry is separate from the tree. A card may relate to several goals. Record the recall attempt before showing the answer; do not rate a forgotten answer as `hard`. Ratings: `again` means not recalled, `hard` means recalled with difficulty, `good` means recalled, and `easy` means recalled easily.

The pinned Python FSRS scheduler takes the actual rating and timestamp and returns updated state and a review date. Its settings are saved in `state/settings.json` and recorded with each scheduled review. Apply session time limits on top of the schedule: overdue and due reviews first, then new cards if the budget allows. Missed reviews do not count as completed.

If the queue grows, reduce new cards and reconsider their usefulness and difficulty. Repeated errors should lead back to an explanation and exercise. Fix or suspend a poor card instead of making the learner repeatedly guess its answer.

For practical skills, also schedule delayed tasks covering several topics. Report card recall, plan completion, and independent problem solving separately. Do not derive a single subject-mastery percentage from these numbers.

## 7. Evaluate the system

After two weeks, check whether it is easier to choose the next activity, whether outcomes have been demonstrated, what is retained after a delay, and how many minutes maintenance takes. Remove fields and procedures that do not help make decisions. Compare the quality of solutions to new tasks rather than the number of checked-off items.
