#!/usr/bin/env python3
"""PreToolUse hook: block tools that send or post while the daily review is running.

The skill says "never send the brief anywhere unless the user asks in that session". A hook
makes that true even if the instruction is lost in a long context. Set DAILY_REVIEW_ALLOW_SEND=1
in the session when the user has asked for the brief to be sent.
"""
import json
import os
import re
import sys

SEND = re.compile(r"(send|reply|forward|post|publish|create_event|tweet|message)", re.I)


def main() -> int:
    if os.environ.get("DAILY_REVIEW_ALLOW_SEND") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    name = payload.get("tool_name") or ""
    if name.startswith("mcp__") and SEND.search(name.split("__")[-1]) and "draft" not in name.lower():
        print(f"blocked during daily review: {name}. Drafts are fine; sending needs the user to ask. "
              "Set DAILY_REVIEW_ALLOW_SEND=1 once they have.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
