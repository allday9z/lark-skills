#!/usr/bin/env python3
"""Lark Task operations — PM-pattern CRUD."""
import urllib.request, json, time, sys
from token_manager import get_valid_token, get_config

def _api(method, path, body=None):
    cfg   = get_config()
    token = get_valid_token()
    base  = cfg.get("base_url", "https://open.larksuite.com/open-apis")
    url   = base + path
    data  = json.dumps(body).encode() if body else None
    req   = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }, method=method)
    try:
        r = urllib.request.urlopen(req)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        d = json.loads(e.read().decode())
        return {"code": e.code, "msg": d.get("msg", str(d))[:120]}


def _ts(date_str: str) -> int:
    """YYYY-MM-DD → ms timestamp"""
    return int(time.mktime(time.strptime(date_str, "%Y-%m-%d"))) * 1000


def get_section_guid(section_key: str) -> str:
    cfg = get_config()
    sections = cfg.get("sections", {})
    if section_key not in sections:
        available = list(sections.keys())
        sys.exit(f"❌ Unknown section '{section_key}'. Available: {available}")
    return sections[section_key]


def search_tasks(query: str) -> list:
    """Search tasks in all active sections by summary keyword."""
    cfg = get_config()
    tl  = cfg["tasklist_guid"]
    r   = _api("GET", f"/task/v2/tasklists/{tl}/tasks?page_size=100")
    items = r.get("data", {}).get("items", [])
    q = query.lower()
    return [t for t in items if q in t.get("summary", "").lower()]


def create_task(
    summary:     str,
    description: str  = "",
    section:     str  = "todo",
    start:       str  = None,
    due:         str  = None,
    assignee:    bool | str = True,
    parent_guid: str  = None,
) -> str:
    """Create task, return guid."""
    cfg  = get_config()
    tl   = cfg["tasklist_guid"]
    sec  = get_section_guid(section)
    uid  = cfg.get("assignee_user_id") if assignee is True else (assignee or None)

    today_ts = int(time.time()) * 1000
    body = {
        "summary":     summary,
        "description": description,
        "tasklists":   [{"tasklist_guid": tl, "section_guid": sec}],
    }
    if start:
        body["start"] = {"timestamp": str(_ts(start)), "is_all_day": True}
    if due:
        body["due"] = {"timestamp": str(_ts(due)), "is_all_day": True}
    if uid:
        body["members"] = [{"id": uid, "role": "assignee", "type": "user"}]
    if parent_guid:
        body["parent_task_guid"] = parent_guid

    r = _api("POST", "/task/v2/tasks", body)
    guid = r.get("data", {}).get("task", {}).get("guid")
    if not guid:
        sys.exit(f"❌ create_task failed: {r.get('msg','unknown error')}")
    return guid


def update_task(guid: str, **fields):
    """Update task fields. Supported: summary, description, start, due."""
    task_body = {}
    update_fields = []
    for k, v in fields.items():
        if k in ("start", "due") and isinstance(v, str):
            task_body[k] = {"timestamp": str(_ts(v)), "is_all_day": True}
        else:
            task_body[k] = v
        update_fields.append(k)
    r = _api("PATCH", f"/task/v2/tasks/{guid}", {
        "task": task_body,
        "update_fields": update_fields,
    })
    return r.get("code", "?") == 0


def set_custom_fields(
    guid:          str,
    priority:      str = None,   # P0|P1|P2|P3|P4
    priority_task: str = None,   # Do first|Schedule|Delegate|Eliminate
    stage:         str = None,   # Dev|Fix Bug|UAT|Deploy|Done
    project:       str = None,   # key in config.custom_fields.project.options
) -> bool:
    cfg = get_config()
    cf  = cfg.get("custom_fields", {})
    fields = []

    def add(field_key, option_key):
        if not option_key:
            return
        field = cf.get(field_key, {})
        fguid = field.get("guid")
        oguid = field.get("options", {}).get(option_key)
        if not fguid or not oguid:
            print(f"⚠️  {field_key}/{option_key} not found in config", file=sys.stderr)
            return
        fields.append({"guid": fguid, "single_select_value": oguid})

    add("priority_4p",   priority)
    add("priority_task", priority_task)
    add("stage",         stage)
    add("project",       project)

    if not fields:
        return True
    r = _api("PATCH", f"/task/v2/tasks/{guid}", {
        "task": {"custom_fields": fields},
        "update_fields": ["custom_fields"],
    })
    return r.get("code") == 0


def move_section(guid: str, target_section: str, keep_fields: dict = None) -> str:
    """Move task to different section via delete + recreate. Returns new guid."""
    # Get current task data
    r = _api("GET", f"/task/v2/tasks/{guid}")
    t = r.get("data", {}).get("task", {})
    if not t:
        sys.exit(f"❌ Task {guid} not found")

    cfg = get_config()
    sec = get_section_guid(target_section)
    tl  = cfg["tasklist_guid"]
    uid = cfg.get("assignee_user_id")

    body = {
        "summary":     t.get("summary",""),
        "description": t.get("description",""),
        "tasklists":   [{"tasklist_guid": tl, "section_guid": sec}],
    }
    if t.get("start", {}).get("timestamp"):
        body["start"] = t["start"]
    if t.get("due",   {}).get("timestamp"):
        body["due"]   = t["due"]
    if uid:
        body["members"] = [{"id": uid, "role": "assignee", "type": "user"}]
    if keep_fields:
        body.update(keep_fields)

    # Create in new section
    new = _api("POST", "/task/v2/tasks", body)
    new_guid = new.get("data", {}).get("task", {}).get("guid")
    if not new_guid:
        sys.exit(f"❌ recreate failed: {new}")

    # Delete old
    _api("DELETE", f"/task/v2/tasks/{guid}")
    return new_guid


def complete_task(guid: str) -> bool:
    import datetime
    ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
    r = _api("PATCH", f"/task/v2/tasks/{guid}", {
        "task": {"completed_at": str(ts)},
        "update_fields": ["completed_at"],
    })
    return r.get("code") == 0


# ─── Result logging (sub-task + description append) ──────────────────────────

def log_result(
    task_guid:   str,
    result_text: str,
    oracle_name: str = "UFicon Oracle",
    date_str:    str = None,
) -> str:
    """Log work result without editing original task title.
    Creates a completed sub-task + appends to description.
    Returns sub-task guid.
    """
    import datetime
    cfg = get_config()
    tl  = cfg["tasklist_guid"]
    today = date_str or datetime.date.today().strftime("%Y-%m-%d")

    # 1. Append result to description (don't replace)
    r_get = _api("GET", f"/task/v2/tasks/{task_guid}")
    cur   = r_get.get("data",{}).get("task",{}).get("description","")
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    appended = cur + f"\n\n---\n✅ Result ({stamp} by {oracle_name}):\n{result_text}"
    _api("PATCH", f"/task/v2/tasks/{task_guid}", {
        "task": {"description": appended},
        "update_fields": ["description"]
    })

    # 2. Create completed sub-task as work log
    sub = _api("POST", "/task/v2/tasks", {
        "summary":          f"✅ Result — {result_text[:60]}",
        "description":      f"Logged by: {oracle_name}\nDate: {stamp}\n\n{result_text}",
        "tasklists":        [{"tasklist_guid": tl, "section_guid":
                               _api("GET", f"/task/v2/tasks/{task_guid}")
                               .get("data",{}).get("task",{}).get("tasklists",[{}])[0]
                               .get("section_guid","")
                             }],
        "parent_task_guid": task_guid,
        "start": {"timestamp": str(_ts(today)), "is_all_day": True},
        "due":   {"timestamp": str(_ts(today)), "is_all_day": True},
    })
    sub_guid = sub.get("data",{}).get("task",{}).get("guid")
    if sub_guid:
        ts_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
        _api("PATCH", f"/task/v2/tasks/{sub_guid}", {
            "task": {"completed_at": str(ts_ms)},
            "update_fields": ["completed_at"]
        })
    return sub_guid or ""


def create_subtask(
    parent_guid: str,
    summary:     str,
    description: str = "",
    start:       str = None,
    due:         str = None,
    p4p:         str = "P2",
    stage:       str = "Dev",
    project:     str = None,
) -> str:
    """Create a sub-task under parent — NO tasklists, only shows in parent detail panel."""
    cfg = get_config()
    uid = cfg.get("assignee_user_id")

    body = {
        "summary":          summary,
        "description":      description,
        "parent_task_guid": parent_guid,
    }
    if start: body["start"] = {"timestamp": str(_ts(start)), "is_all_day": True}
    if due:   body["due"]   = {"timestamp": str(_ts(due)),   "is_all_day": True}
    if uid:   body["members"] = [{"id": uid, "role": "assignee", "type": "user"}]
    # No "tasklists" — sub-task only visible under parent, not in main list

    r = _api("POST", "/task/v2/tasks", body)
    guid = r.get("data",{}).get("task",{}).get("guid")
    if not guid:
        import sys; sys.exit(f"❌ create_subtask failed: {r.get('msg','?')}")

    # Set custom fields if available
    P4P_MAP = {"P1":"682cab3b","P2":"23dda073","P3":"53d50000"}
    STAGE_MAP = {"Dev":"9fcf9d13","Fix Bug":"244c55c7","UAT":"82a47c17","Deploy":"8a74507e","Done":"bbf8574e","Planning":"3b425a44","Testing":"211a1a4a"}
    cf_data = cfg.get("custom_fields", {})
    cf = []
    if p4p and "priority_4p" in cf_data:
        opt = P4P_MAP.get(p4p)
        if opt: cf.append({"guid": cf_data["priority_4p"]["guid"], "single_select_value": opt})
    if stage and "stage" in cf_data:
        opt = STAGE_MAP.get(stage)
        if opt: cf.append({"guid": cf_data["stage"]["guid"], "single_select_value": opt})
    if project and "project" in cf_data:
        opt = cf_data["project"]["options"].get(project)
        if opt: cf.append({"guid": cf_data["project"]["guid"], "single_select_value": opt})
    if cf:
        _api("PATCH", f"/task/v2/tasks/{guid}", {
            "task": {"custom_fields": cf}, "update_fields": ["custom_fields"]
        })
    return guid
