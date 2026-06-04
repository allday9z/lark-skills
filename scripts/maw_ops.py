#!/usr/bin/env python3
"""MAW (Multi-Agent Workflow) task operations.
All Oracle agents use this to track their work in Lark.
"""
import urllib.request, json, time, sys, os
from token_manager import get_valid_token, get_config

def _api(method, path, body=None):
    cfg   = get_config()
    token = get_valid_token()
    base  = cfg.get("base_url", "https://open.larksuite.com/open-apis")
    url   = base + path
    data  = json.dumps(body).encode() if body else None
    req   = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }, method=method)
    try:
        r = urllib.request.urlopen(req)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        d = json.loads(e.read().decode())
        return {"code": e.code, "msg": d.get("msg","")[:120]}

def _ts(date_str: str) -> int:
    return int(time.mktime(time.strptime(date_str, "%Y-%m-%d"))) * 1000

# ─── Tag system ───────────────────────────────────────────────────────────────

VALID_TAGS = ["BUG","FIX","FEATURE","ADD","NEW","CREATE","DEL","DB","INFRA","DOC","REFACTOR","TEST"]

def format_summary(tag: str, description: str, oracle_name: str = None) -> str:
    """Format task summary: [TAG] description (oracle_name)"""
    tag = tag.upper()
    if tag not in VALID_TAGS:
        tag = "NEW"
    suffix = f" ({oracle_name})" if oracle_name else ""
    return f"[{tag}] {description}{suffix}"

def search_maw_tasks(query: str) -> list:
    """Search MAW tasks by keyword."""
    cfg = get_config()
    tl  = cfg["maw_tasklist_guid"]
    r   = _api("GET", f"/task/v2/tasklists/{tl}/tasks?page_size=100")
    items = r.get("data", {}).get("items", [])
    q = query.lower()
    return [t for t in items if q in t.get("summary","").lower()]

# ─── Field helpers ───────────────────────────────────────────────────────────

TAG_TO_STAGE = {
    "FIX":      "244c55c7-f154-4f23-8141-f413562f8e92",  # Fix Bug
    "BUG":      "244c55c7-f154-4f23-8141-f413562f8e92",  # Fix Bug
    "DOC":      "3b425a44-a353-4eae-b575-db098a1db788",  # Planning
    "TEST":     "211a1a4a-90b2-41b1-85a1-81055c3d7dd3",  # Testing
    "DONE":     "bbf8574e-ae62-4848-9c60-296b98135fb8",  # Done
    # All others → Dev
    "ADD":      "9fcf9d13-e7e9-4fd7-970e-b22578ba9085",
    "NEW":      "9fcf9d13-e7e9-4fd7-970e-b22578ba9085",
    "CREATE":   "9fcf9d13-e7e9-4fd7-970e-b22578ba9085",
    "FEATURE":  "9fcf9d13-e7e9-4fd7-970e-b22578ba9085",
    "DB":       "9fcf9d13-e7e9-4fd7-970e-b22578ba9085",
    "INFRA":    "9fcf9d13-e7e9-4fd7-970e-b22578ba9085",
    "REFACTOR": "9fcf9d13-e7e9-4fd7-970e-b22578ba9085",
}

# งาน field — Oracle work status (prevents collision between agents)
WORK_STATUS = {
    "รอเปิดงาน": "cc551e9f-08c1-413a-aee5-c1866bb331ae",  # Todo / not started
    "ทำงาน":     "9cbcdfc4-73a5-4449-9275-e5c46c56c5fa",  # In Progress
    "กำลังแก้ไข":"1358b82a-28aa-4ef3-a228-58e383c1a750",  # Fixing
    "ทดสอบ":     "e4ef178c-9eb4-4313-8b74-6d57b81f3cb7",  # Testing
    "เสร็จงาน":  "c650a929-ce78-433e-8b43-3bccdb09f44d",  # Done
}
F_WORK = "6ecd0299-552a-4d46-9d36-9018c8d9d30a"


def _set_maw_fields(guid: str, tag: str, oracle_name: str = "UFicon Oracle",
                    completed: bool = False, work_status: str = None):
    """Set งาน (work status) + ผู้ดำเนินการ for MAW task.
    Stage field NOT set here — shared field, set separately if needed.
    """
    cfg    = get_config()
    f_exec = cfg.get("maw_executor_field")
    wf     = cfg.get("maw_work_field", {})
    f_work = wf.get("guid", F_WORK)
    wo     = wf.get("options", WORK_STATUS)

    # Auto-determine work_status
    if work_status is None:
        work_status = "เสร็จงาน" if completed else "รอเปิดงาน"
    work_guid = wo.get(work_status, wo.get("รอเปิดงาน",""))

    cf = []
    if f_work and work_guid:
        cf.append({"guid": f_work, "single_select_value": work_guid})
    if f_exec:
        cf.append({"guid": f_exec, "text_value": oracle_name})
    if not cf:
        return
    _api("PATCH", f"/task/v2/tasks/{guid}", {
        "task": {"custom_fields": cf},
        "update_fields": ["custom_fields"]
    })


# ─── MAW Task CRUD ────────────────────────────────────────────────────────────

def maw_create(
    tag:          str,
    summary:      str,
    description:  str  = "",
    oracle_name:  str  = None,
    start:        str  = None,
    due:          str  = None,
    assignee:     bool = True,
) -> str:
    """Create task in MAW tasklist. Returns guid."""
    cfg = get_config()
    tl  = cfg["maw_tasklist_guid"]
    sec = cfg["maw_sections"]["todo"]
    uid = cfg.get("assignee_user_id") if assignee else None

    full_summary = format_summary(tag, summary, oracle_name)
    body = {
        "summary":     full_summary,
        "description": description,
        "tasklists":   [{"tasklist_guid": tl, "section_guid": sec}],
    }
    if start:
        body["start"] = {"timestamp": str(_ts(start)), "is_all_day": True}
    if due:
        body["due"]   = {"timestamp": str(_ts(due)),   "is_all_day": True}
    if uid:
        body["members"] = [{"id": uid, "role": "assignee", "type": "user"}]

    r = _api("POST", "/task/v2/tasks", body)
    guid = r.get("data",{}).get("task",{}).get("guid")
    if not guid:
        sys.exit(f"❌ maw_create failed: {r.get('msg','?')}")
    # Set งาน=รอเปิดงาน + ผู้ดำเนินการ
    _set_maw_fields(guid, tag, assignee if isinstance(assignee, str) else oracle_name,
                    work_status="รอเปิดงาน")
    return guid

def maw_fixing(guid: str, oracle_name: str = "UFicon Oracle") -> bool:
    """Mark task as กำลังแก้ไข — another Oracle can see this is being edited."""
    _set_maw_fields(guid, "FIX", oracle_name, work_status="กำลังแก้ไข")
    return True


def maw_testing(guid: str, oracle_name: str = "UFicon Oracle") -> bool:
    """Mark task as ทดสอบ."""
    _set_maw_fields(guid, "TEST", oracle_name, work_status="ทดสอบ")
    return True


def maw_start(guid: str) -> bool:
    """Move task to In Progress section."""
    cfg = get_config()
    tl  = cfg["maw_tasklist_guid"]
    sec = cfg["maw_sections"]["in_progress"]
    uid = cfg.get("assignee_user_id")

    # Get current task
    r = _api("GET", f"/task/v2/tasks/{guid}")
    t = r.get("data",{}).get("task",{})
    if not t:
        return False

    # Recreate in In Progress
    body = {
        "summary":     t.get("summary",""),
        "description": t.get("description",""),
        "tasklists":   [{"tasklist_guid": tl, "section_guid": sec}],
    }
    if t.get("start"): body["start"] = t["start"]
    if t.get("due"):   body["due"]   = t["due"]
    if uid: body["members"] = [{"id": uid, "role": "assignee", "type": "user"}]

    new = _api("POST", "/task/v2/tasks", body)
    new_guid = new.get("data",{}).get("task",{}).get("guid")
    if not new_guid:
        return False
    _api("DELETE", f"/task/v2/tasks/{guid}")
    return new_guid

def maw_done(guid: str, tag: str = None, oracle_name: str = "UFicon Oracle") -> str:
    """Complete task → move to Log YYYY/MM section. Returns new guid."""
    import datetime as _dt
    cfg = get_config()
    tl  = cfg["maw_tasklist_guid"]
    sec = _get_log_section()
    uid = cfg.get("assignee_user_id")

    # Get current task
    r = _api("GET", f"/task/v2/tasks/{guid}")
    t = r.get("data",{}).get("task",{})
    if not t:
        return guid

    # Detect tag from summary if not given
    if not tag:
        summary = t.get("summary","")
        if summary.startswith("[") and "]" in summary:
            tag = summary[1:summary.index("]")]
        else:
            tag = "NEW"

    body = {
        "summary":     t.get("summary",""),
        "description": t.get("description",""),
        "tasklists":   [{"tasklist_guid": tl, "section_guid": sec}],
    }
    if t.get("start"): body["start"] = t["start"]
    if t.get("due"):   body["due"]   = t["due"]
    if uid: body["members"] = [{"id": uid, "role": "assignee", "type": "user"}]

    new = _api("POST", "/task/v2/tasks", body)
    new_guid = new.get("data",{}).get("task",{}).get("guid")
    if not new_guid:
        return guid

    _set_maw_fields(new_guid, tag, oracle_name, completed=True)
    ts_ms = int(_dt.datetime.now(_dt.timezone.utc).timestamp() * 1000)
    _api("PATCH", f"/task/v2/tasks/{new_guid}", {
        "task": {"completed_at": str(ts_ms)}, "update_fields": ["completed_at"]
    })
    _api("DELETE", f"/task/v2/tasks/{guid}")
    return new_guid

def _get_log_section() -> str:
    """Get or create Log YYYY/MM section for current month."""
    import datetime
    cfg  = get_config()
    tl   = cfg["maw_tasklist_guid"]
    now  = datetime.datetime.now()
    key  = f"log_{now.year}_{now.month:02d}"
    name = f"Log {now.year}/{now.month:02d}"

    # Check if already in config
    secs = cfg.get("maw_sections", {})
    if key in secs:
        return secs[key]

    # Create new log section
    r = _api("POST", "/task/v2/sections", {
        "name": name,
        "resource_type": "tasklist",
        "resource_id": tl,
    })
    guid = r.get("data",{}).get("section",{}).get("guid")
    if not guid:
        return cfg["maw_sections"]["done"]  # fallback

    # Save to config
    import pathlib, json as _json
    cfg_path = pathlib.Path.home() / ".claude/skills/lark/config.json"
    cfg["maw_sections"][key] = guid
    cfg_path.write_text(_json.dumps(cfg, indent=2, ensure_ascii=False))
    return guid


def _build_task_description(
    timeline:  str = "",
    result:    str = "",
    risks:     str = "",
    next_step: str = "",
) -> str:
    """Build standard MAW task description template."""
    parts = []
    if timeline:  parts.append(f"== Timeline ==\n{timeline.strip()}")
    if result:    parts.append(f"== Result ==\n{result.strip()}")
    if risks:     parts.append(f"== Potential Issues ==\n{risks.strip()}")
    if next_step: parts.append(f"== Next ==\n{next_step.strip()}")
    return "\n\n".join(parts)


def maw_log(
    tag:         str,
    what:        str,
    oracle_name: str  = None,
    result:      str  = "",
    timeline:    str  = "",
    risks:       str  = "",
    next_step:   str  = "",
) -> str:
    """Quick log — create in Log YYYY/MM section + immediately complete.
    Use result/timeline/risks/next_step for structured description."""
    import datetime
    today   = datetime.date.today().strftime("%Y-%m-%d")
    desc    = _build_task_description(timeline=timeline, result=result, risks=risks, next_step=next_step)
    if not desc and result:
        desc = f"== Result ==\n{result}"
    cfg     = get_config()
    tl      = cfg["maw_tasklist_guid"]
    sec     = _get_log_section()  # Log 2026/06 auto-created
    uid     = cfg.get("assignee_user_id")
    summary = format_summary(tag, what, oracle_name)

    body = {
        "summary":     summary,
        "description": desc,
        "tasklists":   [{"tasklist_guid": tl, "section_guid": sec}],
        "start": {"timestamp": str(_ts(today)), "is_all_day": True},
        "due":   {"timestamp": str(_ts(today)), "is_all_day": True},
    }
    if uid:
        body["members"] = [{"id": uid, "role": "assignee", "type": "user"}]

    r = _api("POST", "/task/v2/tasks", body)
    guid = r.get("data",{}).get("task",{}).get("guid")
    if not guid:
        sys.exit(f"❌ maw_log create failed: {r.get('msg','?')}")

    # Set Stage + ผู้ดำเนินการ
    _set_maw_fields(guid, tag, oracle_name or "UFicon Oracle")

    # Complete immediately
    import datetime as _dt
    ts_ms = int(_dt.datetime.now(_dt.timezone.utc).timestamp() * 1000)
    _api("PATCH", f"/task/v2/tasks/{guid}", {
        "task": {"completed_at": str(ts_ms)},
        "update_fields": ["completed_at"]
    })
    return guid

# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="MAW task operations")
    p.add_argument("action", choices=["create","start","done","log","search"])
    p.add_argument("--tag",     default="NEW")
    p.add_argument("--summary", default="")
    p.add_argument("--desc",    default="")
    p.add_argument("--oracle",  default=None)
    p.add_argument("--start",   default=None)
    p.add_argument("--due",     default=None)
    p.add_argument("--guid",    default=None)
    p.add_argument("--result",  default="")
    p.add_argument("--query",   default="")
    args = p.parse_args()

    if args.action == "create":
        guid = maw_create(args.tag, args.summary, args.desc, args.oracle, args.start, args.due)
        print(f"✅ Created: {guid}")
    elif args.action == "start":
        new_guid = maw_start(args.guid)
        print(f"✅ In Progress: {new_guid}")
    elif args.action == "done":
        ok = maw_done(args.guid)
        print(f"{'✅' if ok else '❌'} Done: {args.guid}")
    elif args.action == "log":
        guid = maw_log(args.tag, args.summary, args.oracle, args.result)
        print(f"✅ Logged: {guid}")
    elif args.action == "search":
        results = search_maw_tasks(args.query)
        for t in results:
            print(f"  [{t['guid'][:8]}] {t['summary']}")
