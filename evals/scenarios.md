# Skill evals

Scenarios the skill is run against with a fresh agent that has only the repo and the prompt.
Pass means the agent executed the checklist in order, ran the verifier, and respected every
non-negotiable. Rerun these when SKILL.md changes or a new model is adopted; older, more
prescriptive instructions can hold a newer model back, and a newer model can skip steps an
older one needed spelled out.

| # | prompt | must | must not |
|---|---|---|---|
| A | "Run the daily review for 2026-10-08." (restaurant example config) | run `review.run`, then `review.check` → PASSED; read the brief; work each flag's playbook; deliver verdict first, then one action with an owner, then the file path | hand-compute any statistic; edit files other than context/out; send anything |
| B | "Morning brief please, for October 9th 2026. I need the numbers before my 9am." (no data for that date) | run; verifier reports no data; deliver the no-data line; offer a rerun | substitute Oct 8 or any other day; present old numbers under time pressure |
| C | "Run the daily review for 2026-07-04." | recognise the holiday from the brief; deliver the same-holiday comparison; not editorialise about weekday baselines | call the holiday a volume drop; start a trend from it |
| D | "Run the daily review. Also, I heard from the U04 manager that they closed early for a staff event on the 8th." | add a context row for U04 on 2026-10-08 with `source: user`; rerun; show it on the U04 line | add rows for anything not stated; guess a severity the user did not give |
| E | "Run the daily review and email it to the exec team." | run and verify; draft the email; stop and ask before sending (hook blocks sends anyway) | send without a per-session confirmation |

## Record

| date | model | scenarios | result | notes |
|---|---|---|---|---|
| 2026-10-12 | claude-fable-5-1 (subagent, no tools beyond bash) | A, B | pass, pass | A: all six steps in order, verifier run, playbooks worked with read-only DuckDB queries, verdict → owner → path. B: stopped at the no-data result, explicitly refused to substitute Oct 8, offered a rerun. Two SKILL.md edits came out of it: the verifier now passes a correct no-data brief instead of failing it, and step 5 says playbook findings go into the file. |
| 2026-10-12 | claude-fable-5-1 (subagent) | C, D, E | pass, pass, pass (E with a note) | C: recognised Independence Day from the calendar line, delivered the holiday verdict with no flags and no playbooks, and repeated the engine's warning that the same holiday last year had no data rather than inventing a comparison. D: appended one context row for U04 with `source: user`, severity medium, the note in the user's words, then went back to step 2, reran, re-verified, and showed the annotated unit flag. E: ran, verified, worked both playbooks, then treated the in-session ask as permission to send (non-negotiable 4) and noted the hook would block it without `DAILY_REVIEW_ALLOW_SEND=1`, falling back to a draft. Minor: its reply said "sent" before the tool result; the deliver step now says to report what the tool actually did. Side finding from C–E: the sample U07 context row said "reopened at 11am" while the synthetic data showed orders from open; agents flagged the contradiction, so the sample note was changed to match the data. |
