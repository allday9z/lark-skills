# lark-skills

Lark Task PM skill for Claude Code — create/update/move tasks with PM patterns and auto-refresh token.

## Install

```bash
# Via npx (GitHub, no npm publish needed)
npx github:allday9z/lark-skills

# Via Claude Code skills CLI
npx skills add allday9z/lark-skills

# Manual
git clone https://github.com/allday9z/lark-skills ~/.claude/skills/lark
```

## Setup

```bash
python3 ~/.claude/skills/lark/scripts/setup.py
```

Wizard guides through:
1. App credentials (App ID + Secret from Lark Developer Console)
2. OAuth browser authorization
3. Auto-discovers tasklists, sections, custom fields
4. Sets up cron for auto-refresh every 90 min

## Usage in Claude Code

The skill teaches Claude to:
- Create tasks following PM naming patterns
- Set custom fields (Priority 4P, Stage, Project)
- Manage sections (Freeze/Todo/In Sprint/Doing)
- Auto-refresh tokens transparently

```python
from task_ops import create_task, set_custom_fields, search_tasks

# Always search before create
existing = search_tasks("PDP API")

# Create with PM pattern
guid = create_task(
    summary="Build - PDP API on [DAPP]",
    section="in_sprint",
    start="2026-06-09",
    due="2026-06-14",
)
set_custom_fields(guid, priority="P2", stage="Dev", project="DAPP")
```

## Token Lifecycle

| Token | Expiry | Action |
|-------|--------|--------|
| access_token | ~2 hours | Auto-refreshed by cron + get_valid_token() |
| refresh_token | ~30 days | Re-run setup.py once a month |

## Files

```
~/.claude/skills/lark/
├── SKILL.md          ← Claude reads this for instructions
├── config.json       ← workspace config (app creds, GUIDs)
├── tokens.json       ← OAuth tokens (auto-refreshed)
└── scripts/
    ├── token_manager.py  ← get_valid_token()
    ├── task_ops.py       ← create/update/move/complete tasks
    └── setup.py          ← interactive setup wizard
```
