#!/usr/bin/env python3
"""Interactive setup wizard for lark-skills.
Guides through: app credentials → OAuth → tasklist discovery → custom fields discovery → config save.
"""
import urllib.request, json, time, pathlib, sys, os, http.server, threading, urllib.parse

SKILL_DIR   = pathlib.Path.home() / ".claude/skills/lark"
CONFIG_PATH = SKILL_DIR / "config.json"
TOKENS_PATH = SKILL_DIR / "tokens.json"
BASE        = "https://open.larksuite.com/open-apis"
PORT        = 9988

def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val or default

def post(url, body, headers=None):
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=h, method="POST")
    r = urllib.request.urlopen(req)
    return json.loads(r.read())

def get_req(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    r = urllib.request.urlopen(req)
    return json.loads(r.read())

def setup_cron(skill_dir):
    """Add/update cron job for auto-refresh."""
    import subprocess
    script = str(skill_dir / "scripts/token_manager.py")
    cron_line = f"*/90 * * * * /usr/bin/python3 {script} >> /tmp/lark-refresh.log 2>&1"
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = result.stdout if result.returncode == 0 else ""
    # Remove old lark entries, add new
    lines = [l for l in existing.splitlines() if "lark" not in l and "token_manager" not in l]
    lines.append(cron_line)
    new_cron = "\n".join(lines) + "\n"
    proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE)
    proc.communicate(new_cron.encode())
    print(f"✅ Cron installed: refresh every 90 min")

def main():
    print("\n🔧 Lark Skills Setup Wizard\n")
    SKILL_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing config if any
    existing = {}
    if CONFIG_PATH.exists():
        existing = json.loads(CONFIG_PATH.read_text())
        print(f"Found existing config. Press Enter to keep values.\n")

    # App credentials
    print("── Step 1: Lark App Credentials ──")
    print("Get from: https://open.larksuite.com/app → Your App → Credentials")
    app_id     = ask("App ID",     existing.get("app_id"))
    app_secret = ask("App Secret", existing.get("app_secret"))
    base_url   = ask("Base URL",   existing.get("base_url", "https://open.larksuite.com/open-apis"))

    # Get app_access_token
    print("\nVerifying credentials...")
    try:
        d = post(f"{base_url}/auth/v3/app_access_token/internal",
                 {"app_id": app_id, "app_secret": app_secret})
        app_token = d["app_access_token"]
        print("✅ App credentials valid")
    except Exception as e:
        sys.exit(f"❌ Invalid credentials: {e}")

    # OAuth user token
    print("\n── Step 2: OAuth Authorization ──")
    REDIRECT = f"http://localhost:{PORT}/callback"
    scopes = (
        "task:task:read task:task:write "
        "task:tasklist:read task:tasklist:write "
        "task:section:read task:section:write "
        "task:custom_field:read task:custom_field:write "
        "contact:user.base:readonly "
        "calendar:calendar:readonly "
        "im:message:send_as_bot"
    )
    auth_url = (
        f"https://open.larksuite.com/open-apis/authen/v1/authorize"
        f"?app_id={app_id}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT)}"
        f"&scope={urllib.parse.quote(scopes)}"
        f"&state=lark_skill_setup"
    )
    print(f"\nOpen this URL in browser:\n{auth_url}\n")
    print(f"Waiting for OAuth callback on port {PORT}...")

    code_holder = [None]
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code_holder[0] = p.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>✅ Lark skill authorized! Close this tab.</h2>".encode())
        def log_message(self, *a): pass

    srv = http.server.HTTPServer(("localhost", PORT), Handler)
    th  = threading.Thread(target=srv.handle_request, daemon=True)
    th.start()
    th.join(180)

    if not code_holder[0]:
        sys.exit("❌ Timeout — no OAuth callback received")

    # Exchange code for token
    d2 = post(f"{base_url}/authen/v1/oidc/access_token",
              {"grant_type": "authorization_code", "code": code_holder[0]},
              headers={"Authorization": f"Bearer {app_token}", "Content-Type": "application/json"})
    tok = d2["data"]
    tokens = {
        "access_token":  tok["access_token"],
        "refresh_token": tok["refresh_token"],
        "expires_at":    time.time() + tok["expires_in"],
    }
    TOKENS_PATH.write_text(json.dumps(tokens, indent=2))
    print(f"✅ Token saved (valid {tok['expires_in']}s)")
    user_token = tok["access_token"]

    # Discover tasklist
    print("\n── Step 3: Tasklist Discovery ──")
    r3 = get_req(f"{base_url}/task/v2/tasklists?page_size=50", user_token)
    lists = r3.get("data", {}).get("items", [])
    if lists:
        print("Found tasklists:")
        for i, tl in enumerate(lists):
            print(f"  [{i}] {tl['name']} — {tl['guid']}")
        idx = ask("Select index", "0")
        tl_guid = lists[int(idx)]["guid"]
    else:
        tl_guid = ask("Tasklist GUID (manual)")

    # Discover sections
    r4 = get_req(f"{base_url}/task/v2/sections?resource_type=tasklist&resource_id={tl_guid}&page_size=50", user_token)
    sec_items = r4.get("data", {}).get("items", [])
    print("\nSections found:")
    sections_raw = {}
    for s in sec_items:
        print(f"  {s['name']}: {s['guid']}")
        sections_raw[s["name"]] = s["guid"]

    # Map section names to standard keys
    sections = existing.get("sections", {})
    print("\nMap sections to keys (freeze/todo/in_sprint/doing). Press Enter to skip.")
    for key in ["freeze","todo","in_sprint","doing"]:
        default_guid = sections.get(key, "")
        # Try to auto-detect
        for name, guid in sections_raw.items():
            nl = name.lower()
            if key == "freeze" and "freeze" in nl: default_guid = guid
            elif key == "todo"     and "todo"   in nl: default_guid = guid
            elif key == "in_sprint"and "sprint" in nl: default_guid = guid
            elif key == "doing"    and "doing"  in nl: default_guid = guid
        val = ask(f"  {key} section GUID", default_guid)
        if val:
            sections[key] = val

    # Add log sections dynamically
    for name, guid in sections_raw.items():
        if "log" in name.lower() or "success" in name.lower():
            key = name.lower().replace(" ","_").replace("-","_")
            sections[key] = guid

    # Discover custom fields
    print("\n── Step 4: Custom Fields ──")
    r5 = get_req(f"{base_url}/task/v2/custom_fields?resource_type=tasklist&resource_id={tl_guid}&page_size=50", user_token)
    cf_items = r5.get("data", {}).get("items", [])
    custom_fields = existing.get("custom_fields", {})

    FIELD_MAP = {
        "Priority 4P":   "priority_4p",
        "Priority Task": "priority_task",
        "Stage":         "stage",
        "Project":       "project",
    }
    for field in cf_items:
        fname = field.get("name", "")
        fguid = field["guid"]
        key   = FIELD_MAP.get(fname)
        if not key:
            continue
        options = {o["name"]: o["guid"]
                   for o in field.get("single_select_setting",{}).get("options",[])}
        custom_fields[key] = {"guid": fguid, "options": options}
        print(f"  ✅ {fname}: {len(options)} options")

    # Assignee
    print("\n── Step 5: Default Assignee ──")
    assignee_id = ask("Your Lark user_id (ou_xxx)", existing.get("assignee_user_id",""))

    # Save config
    config = {
        "app_id":            app_id,
        "app_secret":        app_secret,
        "base_url":          base_url,
        "tasklist_guid":     tl_guid,
        "assignee_user_id":  assignee_id,
        "sections":          sections,
        "custom_fields":     custom_fields,
        "tokens_path":       str(TOKENS_PATH),
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    print(f"\n✅ Config saved: {CONFIG_PATH}")

    # Setup cron
    print("\n── Step 6: Auto-refresh Cron ──")
    setup_cron(SKILL_DIR)

    print(f"\n🎉 Setup complete! Test with:\n   python3 {SKILL_DIR}/scripts/token_manager.py\n")

if __name__ == "__main__":
    main()
