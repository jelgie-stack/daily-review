---
name: daily-review
description: >-
  Runs a morning business review that only flags changes that are real. Triggers on "run the
  daily review", "morning brief", "how did yesterday go", "daily numbers", or a scheduled task
  with those words. Pulls yesterday's revenue and orders by unit and channel from the configured
  warehouse, compares each to its same-weekday baseline, splits revenue moves into volume vs
  value, tests whether a move is a trend, handles holidays, attaches context (promos, outages,
  weather), and points every flag at a diagnostic playbook. Works for any business with a daily
  revenue stream (profiles: generic, restaurant, ecommerce). Delivers the brief in chat and as a
  Markdown file. Never sends anything on its own.
---

# Daily Review

**Contents:** [Install](#install) · [Non-negotiables](#non-negotiables) · [Run checklist](#run-checklist) ·
[If something is off](#if-something-is-off) · [Deliver](#deliver) · [Your judgment](#your-judgment) ·
[Reference](#reference)

## Install

Python 3.10+, `pip install -r requirements.txt` (pyyaml, duckdb), plus one warehouse client if
not DuckDB (`google-cloud-bigquery`, `snowflake-connector-python`, or `psycopg2-binary`). The
repo folder is the skill. First-time setup and floor tuning: [docs/setup.md](docs/setup.md).
Hooks that enforce the non-negotiables in code: [hooks/](hooks/README.md).

## Non-negotiables

These do not bend, whatever the user's tone or the length of the session.

1. **Run the engine.** Never estimate baselines, z-scores or the volume/value split by eye.
   A brief without them is a guess wearing the brief's clothes.
2. **The review date is the review date.** If it has no data, deliver the no-data line and
   stop. Never substitute an older day without saying so in the first sentence.
3. **Flags are not deleted.** Context, holidays and your own theories annotate a flag; they
   never remove it. The engine already handles holidays; do not second-guess it in prose.
4. **Nothing is sent.** No email, chat message, or post unless the user asks in this session.
   Drafts are fine. (`hooks/block_sends.py` enforces this.)
5. **No guessed context.** A context row is added only from something you were told or read,
   always with a `source`. A wrong explanation stops someone looking.

## Run checklist

Do these in order. Each step says what "done" looks like; if it is not, go back.

1. **Resolve the date.** Default is yesterday in `business.timezone`. If the user named a day,
   use it. Say which date you are running before you run it.
2. **Run.**
   `python -m review.run --config config/config.yaml --date YYYY-MM-DD`
   Done when stdout ends with `[written] out/YYYYMMDD-daily-review.md`.
   No Python? Go to [no Python](#no-python).
3. **Verify.**
   `python -m review.check --config config/config.yaml --date YYYY-MM-DD`
   Done when it prints `REVIEW CHECK PASSED`. If it fails, every line it prints names the fix;
   apply it and **go back to step 2**. Do not deliver a brief that failed the check.
4. **Read the brief yourself** before the user does. Does the verdict match the flags? Does the
   volume/value split agree with the unit and channel tables? If the brief contradicts itself,
   the usual cause is a floor set wrong for this business: fix `rules` in config and **go back
   to step 2**.
5. **Work the playbooks.** For each flag, open the playbook it names and run its checks with
   the tools you have (the warehouse connector, analytics, email, chat). Add what you find as
   sub-bullets under the flag, in the `.md` file as well as in chat: the file is the record.
   Stop at the first check that explains the move and say so.
   Anything you learned that is a fact about the day (a promo ended, a store closed early)
   becomes a context row per [docs/context.md](docs/context.md), **then go back to step 2** so
   the brief carries it.
6. **Deliver** (below).

### No Python

`python -m review.run ... --print-sql` prints the exact query; run it through the warehouse
connector, save the rows as CSV, then `python -m review.run ... --rows rows.csv`. If there is
no Python at all, the query is a dozen lines in `review/query.py`; run it through the
connector and tell the user the statistics could not be computed. Do not improvise them.

## If something is off

| symptom | cause | do |
|---|---|---|
| `check` passes with "no data" | warehouse not loaded yet, or closed day | deliver the no-data line only; offer to rerun later; skip steps 4–5 |
| everything is flagged | floors too low, or catering/wholesale in the core | `docs/setup.md` → Tune; rerun |
| nothing is ever flagged | floors too high, or a step change in the baseline window | same |
| a holiday reads as a disaster | date missing from `profiles/holidays.yaml` | add it under `holidays:` in config; rerun |
| weather warning in the brief | API unreachable | deliver anyway; the numbers do not wait on weather |
| query errors on a column | config expression wrong for this warehouse | fix `config.yaml`; `docs/adapters.md` |

## Deliver

Paste the whole brief into chat, verdict first. Then the one thing you would do today, in a
sentence, with the owner if there is one. Then the file path. Sample output to match:
[restaurant](sample/sample_brief.md) · [generic](sample/sample_brief_generic.md) ·
[holiday](sample/sample_brief_holiday.md). If the user asked for it to be sent somewhere, say
what the send tool actually did (sent, drafted, or blocked by the hook), not what you intended.

## Your judgment

The engine decides what is flagged; you decide what it means. Free rein on: which playbook
checks to run first, how to phrase the day for this reader, what to recommend, and whether a
pattern across several days deserves a line the engine would not write. Say when you are
speculating. "Unexplained, watching" is an acceptable verdict.

## Reference

- Why each rule exists: [docs/method.md](docs/method.md)
- Pointing it at a warehouse: [docs/adapters.md](docs/adapters.md)
- Context rows and weather: [docs/context.md](docs/context.md)
- Playbooks: [diagnostics/](diagnostics/)
- Scenarios this skill is tested against: [evals/scenarios.md](evals/scenarios.md)
