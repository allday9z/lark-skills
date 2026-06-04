---
name: lark
description: "Lark Task PM — create/update/move tasks, set custom fields, manage sections with auto-refresh token"
---

# Lark Task PM Skill

Manage Lark tasks as a Project Manager. Create, update, search, and organize tasks with proper PM patterns.

## Setup

```bash
# 1. Install skill
npx skills add allday9z/lark-skills

# 2. First-time config (OAuth + workspace setup)
python3 ~/.claude/skills/lark/scripts/setup.py

# 3. Verify
python3 ~/.claude/skills/lark/scripts/refresh.py
```

Config stored at: `~/.claude/skills/lark/config.json`

## Token Management

**Always use `get_valid_token()` — never read tokens.json directly.**

```python
import sys
sys.path.insert(0, '/Users/YOUR_USER/.claude/skills/lark/scripts')
from token_manager import get_valid_token, get_config

TOKEN = get_valid_token()   # auto-refreshes if < 10 min remaining
cfg   = get_config()        # loads config.json
```

Token lifecycle:
- access_token: ~2 hours (auto-refreshed via cron + get_valid_token())
- refresh_token: ~30 days (need browser OAuth once a month)

Cron installed by setup.py: `*/90 * * * *` runs refresh silently.

## PM Patterns

### Task Naming
```
<Prefix> - <ชื่องาน> on [<PROJECT>]
```

| Prefix | ใช้เมื่อ | Priority | Stage |
|--------|---------|---------|-------|
| Fix | Bug fix / hotfix | P1–P2 | Dev/Fix Bug |
| AddOn | Feature เพิ่มเติม | P2–P3 | Dev |
| Build | สร้างใหม่ | P2–P3 | Dev |
| Module | New API/module | P2 | Dev |
| UAT | User testing | P2 | UAT |
| Meeting | ประชุม | P3 | Planning |
| Research | ศึกษา/วิเคราะห์ | P3 | Planning |
| Sub | Sub-task ของ task หลัก | same | same |

### Dates — Agile Sequential
```python
# ❌ Wrong: all tasks start = end
# ✅ Correct: sequential, duration ≥ 1 day

# Fix: today → +1 day
# UAT: today → today
# Build/AddOn: today → +7–14 days
# Sub-tasks: stagger by dependency (finish → start next)
```

### Task Create Template
```python
from task_ops import create_task, set_custom_fields

guid = create_task(
    summary="Build - PDP API on [DAPP]",
    description="...",
    section="in_sprint",     # freeze|todo|in_sprint|doing|log_MMYY
    start="2026-06-09",
    due="2026-06-14",
    assignee=True,           # True = M2Dev (from config), or "user_id"
)
set_custom_fields(guid,
    priority="P2",           # P0|P1|P2|P3|P4
    priority_task="Schedule",# Do first|Schedule|Delegate|Eliminate
    stage="Dev",             # Dev|Fix Bug|UAT|Deploy|Done
    project="DAPP",          # key from config projects map
)
```

### Search Before Create
```python
from task_ops import search_tasks

# Always check first
existing = search_tasks("PDP API")
if existing:
    print(f"Already exists: {existing[0]['summary']} [{existing[0]['guid']}]")
    # Update existing, don't create duplicate
```

## API Patterns

```python
import urllib.request, json

BASE = "https://open.larksuite.com/open-apis"

def api(method, path, body=None, token=None):
    if token is None:
        from token_manager import get_valid_token
        token = get_valid_token()
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }, method=method)
    try:
        r = urllib.request.urlopen(req)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"code": e.code, "msg": json.loads(e.read().decode()).get("msg","")[:100]}

# Create task
r = api("POST", "/task/v2/tasks", body={...})
guid = r["data"]["task"]["guid"]

# Update task
api("PATCH", f"/task/v2/tasks/{guid}", body={
    "task": {"summary": "new summary"},
    "update_fields": ["summary"]
})

# Set custom fields (single_select_value = option guid as plain string)
api("PATCH", f"/task/v2/tasks/{guid}", body={
    "task": {"custom_fields": [
        {"guid": field_guid, "single_select_value": option_guid}
    ]},
    "update_fields": ["custom_fields"]
})

# Add member
api("POST", f"/task/v2/tasks/{guid}/add_members", body={
    "members": [{"id": user_id, "role": "assignee", "type": "user"}]
})

# Delete task (for section move = delete + recreate)
api("DELETE", f"/task/v2/tasks/{guid}")

# Get sections
api("GET", f"/task/v2/sections?resource_type=tasklist&resource_id={TL}&page_size=50")

# Get custom fields
api("GET", f"/task/v2/custom_fields?resource_type=tasklist&resource_id={TL}&page_size=50")
```

## Known Gotchas

| Issue | Fix |
|-------|-----|
| `single_select_value` type error | ใส่เป็น plain string (option_guid) ไม่ใช่ object |
| Section move 404 | ไม่มี API ย้าย section โดยตรง → DELETE + recreate ใน section ใหม่ |
| `members` ใน update_fields | ไม่ supported → ใช้ `POST /add_members` แทน |
| Token expired 401 | `get_valid_token()` จัดการเอง แต่ถ้า refresh_token หมด → รัน `setup.py` |
| Custom fields 400 | ต้องมี scope `task:custom_field:read task:custom_field:write` |
| `task:task_field` 20043 | Enterprise-only — ใช้ `task:custom_field` แทน |

## Config Schema

`~/.claude/skills/lark/config.json`:
```json
{
  "app_id": "cli_xxx",
  "app_secret": "xxx",
  "base_url": "https://open.larksuite.com/open-apis",
  "tasklist_guid": "xxx",
  "assignee_user_id": "ou_xxx",
  "sections": {
    "freeze": "guid",
    "todo": "guid",
    "in_sprint": "guid",
    "doing": "guid"
  },
  "custom_fields": {
    "priority_4p": {"guid": "...", "options": {"P0":"guid","P1":"guid","P2":"guid","P3":"guid","P4":"guid"}},
    "priority_task": {"guid": "...", "options": {"Do first":"guid","Schedule":"guid","Delegate":"guid","Eliminate":"guid"}},
    "stage": {"guid": "...", "options": {"Dev":"guid","Fix Bug":"guid","UAT":"guid","Deploy":"guid","Done":"guid"}},
    "project": {"guid": "...", "options": {"DAPP":"guid","EDUCATION":"guid","iSTUDIO":"guid"}}
  },
  "tokens_path": "~/.claude/skills/lark/tokens.json"
}
```
