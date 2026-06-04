#!/usr/bin/env python3
"""Token manager — auto-refresh Lark access token."""
import urllib.request, json, time, pathlib, sys, os

SKILL_DIR   = pathlib.Path.home() / ".claude/skills/lark"
CONFIG_PATH = SKILL_DIR / "config.json"
TOKENS_PATH = SKILL_DIR / "tokens.json"
BUFFER_SECS = 600  # refresh if < 10 min remaining


def get_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit("❌ Lark skill not configured. Run: python3 ~/.claude/skills/lark/scripts/setup.py")
    return json.loads(CONFIG_PATH.read_text())


def _post(url, body, headers=None):
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=h, method="POST")
    r = urllib.request.urlopen(req)
    return json.loads(r.read())


def _get_app_token(cfg: dict) -> str:
    base = cfg.get("base_url", "https://open.larksuite.com/open-apis")
    d = _post(f"{base}/auth/v3/app_access_token/internal",
              {"app_id": cfg["app_id"], "app_secret": cfg["app_secret"]})
    return d["app_access_token"]


def _refresh(cfg: dict, refresh_token: str) -> dict:
    base = cfg.get("base_url", "https://open.larksuite.com/open-apis")
    app_token = _get_app_token(cfg)
    d = _post(
        f"{base}/authen/v1/oidc/refresh_access_token",
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {app_token}"},
    )
    if "data" not in d:
        raise RuntimeError(f"Refresh failed: {d}")
    tok = d["data"]
    tokens = {
        "access_token":  tok["access_token"],
        "refresh_token": tok["refresh_token"],
        "expires_at":    time.time() + tok["expires_in"],
    }
    tokens_path = pathlib.Path(os.path.expanduser(cfg.get("tokens_path", str(TOKENS_PATH))))
    tokens_path.write_text(json.dumps(tokens, indent=2))
    return tokens


def get_valid_token() -> str:
    """Return valid access token, auto-refreshing if needed."""
    cfg = get_config()
    tokens_path = pathlib.Path(os.path.expanduser(cfg.get("tokens_path", str(TOKENS_PATH))))
    if not tokens_path.exists():
        sys.exit("❌ tokens.json not found. Run: python3 ~/.claude/skills/lark/scripts/setup.py")
    tokens = json.loads(tokens_path.read_text())
    remaining = tokens["expires_at"] - time.time()
    if remaining > BUFFER_SECS:
        return tokens["access_token"]
    print(f"[lark] token expires in {int(remaining)}s — refreshing...", file=sys.stderr)
    new = _refresh(cfg, tokens["refresh_token"])
    print(f"[lark] ✅ new token valid for {int(new['expires_at'] - time.time())}s", file=sys.stderr)
    return new["access_token"]


if __name__ == "__main__":
    t = get_valid_token()
    print(f"✅ {t[:25]}...")
