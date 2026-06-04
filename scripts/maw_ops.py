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

def _set_maw_fields(guid: str, tag: str, oracle_name: str = "UFicon Oracle"):
    """Set only ผู้ดำเนินการ (text) — NOT Stage field (shared with DEV JOBS, don't corrupt it).
    Tag is embedded in summary as [TAG] prefix instead."""
    cfg    = get_config()
    f_exec = cfg.get("maw_executor_field")
    if not f_exec:
        return
    _api("PATCH", f"/task/v2/tasks/{guid}", {
        "task": {"custom_fields": [{"guid": f_exec, "text_value": oracle_name}]},
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
    return guid

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

    _set_maw_fields(new_guid, tag, oracle_name)
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


def maw_log(
    tag:         str,
    what:        str,
    oracle_name: str  = None,
    result:      str  = "",
) -> str:
    """Quick log — create in Log YYYY/MM section + immediately complete."""
    import datetime
    today   = datetime.date.today().strftime("%Y-%m-%d")
    desc    = f"ทำแล้ว: {result}" if result else ""
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
