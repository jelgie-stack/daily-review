"""Verify a finished review before it is delivered. Exit 0 = pass, 1 = fix and rerun.

    python -m review.check --config config/config.yaml --date 2026-10-08

Checks the artefacts the run should have produced, not the numbers themselves (those are the
engine's job and are covered by tests). This is the feedback loop the skill runs after every
review: if any check fails, the brief is not delivered until it passes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from .config import load_config


def check(cfg: dict, review_date: dt.date) -> list[str]:
    problems: list[str] = []
    out_dir = Path(cfg["output"].get("dir", "out"))
    stem = review_date.strftime("%Y%m%d") + "-daily-review"
    md, js = out_dir / f"{stem}.md", out_dir / f"{stem}.json"

    if not md.exists() or not js.exists():
        return [f"Brief files missing for {review_date}: expected {md} and {js}. Run the review first."]

    res = json.loads(js.read_text())
    text = md.read_text()

    # 1. Right day.
    if res.get("review_date") != review_date.isoformat():
        problems.append(f"The brief is for {res.get('review_date')}, not {review_date}.")
    # 2. No data is a valid, deliverable result: the brief is the no-data line and nothing else.
    if not res.get("data_present"):
        if "**No data.**" not in text:
            problems.append("No data for the review date but the brief does not say so.")
        return problems
    # 3. Verdict is the first bold line.
    if not res.get("verdict") or f"**{res['verdict']}**" not in text:
        problems.append("The verdict line is missing from the brief.")
    # 4. Every flag names a playbook that exists.
    root = Path(cfg["_config_path"]).resolve().parent.parent
    for f in res.get("flags", []):
        pb = f.get("playbook")
        if not pb:
            problems.append(f"Flag '{f.get('kind')}' has no playbook.")
        elif not (root / pb).exists():
            problems.append(f"Flag '{f.get('kind')}' points at a playbook that does not exist: {pb}.")
    # 5. Baselines have enough history to mean anything.
    n = (res.get("headline", {}).get("revenue") or {}).get("baseline_n", 0)
    if n < 4:
        problems.append(f"Only {n} baseline days for revenue; the comparison is weak. Say so in the brief or extend the lookback.")
    # 6. Floors look sane relative to the business (a floor larger than a typical day flags nothing, ever).
    base = (res.get("headline", {}).get("revenue") or {}).get("baseline") or 0
    floor = float(res.get("rules", {}).get("min_signal_revenue", 0))
    if base and floor > 0.5 * base:
        problems.append(f"min_signal_revenue ({floor:,.0f}) is more than half a typical day ({base:,.0f}); nothing will ever be flagged.")
    # 7. Context rows carry a source (guessed rows are the one thing worse than no rows).
    for r in res.get("context", {}).get("today", []) + res.get("context", {}).get("yesterday", []):
        if not r.get("source"):
            problems.append(f"Context row on {r.get('date')} ({r.get('kind')}) has no source.")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--date", required=True)
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    problems = check(cfg, dt.date.fromisoformat(args.date))
    js = Path(cfg["output"].get("dir", "out")) / (dt.date.fromisoformat(args.date).strftime("%Y%m%d") + "-daily-review.json")
    if not problems and js.exists() and not json.loads(js.read_text()).get("data_present"):
        print("REVIEW CHECK PASSED (no data for this date: deliver the no-data line only, nothing from another day)")
        return 0
    if problems:
        print("REVIEW CHECK FAILED")
        for p in problems:
            print(f"- {p}")
        return 1
    print("REVIEW CHECK PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
