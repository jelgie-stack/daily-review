#!/usr/bin/env python3
"""PreToolUse hook: refuse writes to a context CSV that break the format.

Non-negotiable rules enforced in code, not prose:
  - every row has a parseable date, a scope, a kind, and a non-empty source
  - no row is dated in the future (a guessed explanation for a day that has not happened)

Reads the hook payload on stdin (Claude Code's PreToolUse JSON), finds the file being
written, validates the proposed content, and exits 2 with a message to block the write.
Exits 0 for anything that is not a context CSV.
"""
import csv
import datetime as dt
import io
import json
import sys

REQUIRED = ("date", "scope", "kind", "note", "source")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not path.endswith("context.csv"):
        return 0
    content = tool_input.get("content") or tool_input.get("new_string") or ""
    if not content.strip():
        return 0
    problems = []
    # For an Edit we only see the new fragment; validate any complete rows in it.
    rows = list(csv.reader(io.StringIO(content)))
    header = rows[0] if rows and rows[0] and rows[0][0] == "date" else list(REQUIRED) + ["severity"]
    for i, r in enumerate(rows):
        if not r or r == header or r[0] == "date":
            continue
        rec = dict(zip(header, r))
        try:
            d = dt.date.fromisoformat(rec.get("date", "").strip())
            if d > dt.date.today():
                problems.append(f"row {i + 1}: date {d} is in the future")
        except ValueError:
            problems.append(f"row {i + 1}: bad date '{rec.get('date')}'")
        for col in ("scope", "kind", "source"):
            if not rec.get(col, "").strip():
                problems.append(f"row {i + 1}: missing {col}")
    if problems:
        print("context.csv write blocked:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
