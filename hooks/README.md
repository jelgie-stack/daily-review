# Hooks

Two rules in this skill are not negotiable, so they are enforced by code that runs before a
tool call, not by a sentence the model might lose in a long context.

| hook | rule it enforces |
|---|---|
| `check_context_csv.py` | Every context row has a date (not in the future), scope, kind and source. Blocks the write otherwise. |
| `block_sends.py` | Nothing is sent or posted during a review unless the user asked (`DAILY_REVIEW_ALLOW_SEND=1`). Drafts pass. |

`settings.example.json` shows the Claude Code wiring (`PreToolUse`). Merge it into your
project's `.claude/settings.json`. Both scripts read the hook payload on stdin and exit 2 with a
reason to block, 0 to allow, so they port to any harness that supports pre-tool hooks.

Test them without a harness:

```bash
echo '{"tool_name":"Write","tool_input":{"file_path":"context.csv","content":"date,scope,kind,note,source\n2026-10-08,all,promo,BOGO ended,"}}' | python3 hooks/check_context_csv.py; echo "exit $?"
echo '{"tool_name":"mcp__Gmail__send_message","tool_input":{}}' | python3 hooks/block_sends.py; echo "exit $?"
```
