#!/usr/bin/env python3
"""
Send a local file (e.g. a markdown article) to a Feishu chat via the Open API.

Usage:
    python3 send_feishu.py <file_path> [--text "accompanying message"] [--to RECEIVE_ID] [--type RECEIVE_ID_TYPE]

Required env vars:
    FEISHU_APP_ID          app id, starts with cli_
    FEISHU_APP_SECRET      app secret
    FEISHU_RECEIVE_ID      target chat/user id (oc_... for chat_id, ou_... for open_id)
    FEISHU_RECEIVE_ID_TYPE one of: open_id | user_id | union_id | email | chat_id  (default: chat_id)

Exit codes:
    0  success (prints JSON with message_id)
    1  API error (prints JSON error)
    2  missing configuration

Note: custom-bot webhooks CANNOT send files — an app with im:file + im:message
permissions is required. See references/feishu-setup.md.
"""

import argparse
import json
import mimetypes
import os
import sys

BASE = "https://open.feishu.cn/open-apis"


def fail(msg, code=1, **extra):
    print(json.dumps({"ok": False, "error": msg, **extra}, ensure_ascii=False))
    sys.exit(code)


def get_token(app_id, app_secret):
    import requests
    r = requests.post(f"{BASE}/auth/v3/tenant_access_token/internal",
                      json={"app_id": app_id, "app_secret": app_secret}, timeout=30)
    data = r.json()
    if data.get("code") != 0:
        fail(f"token error {data.get('code')}: {data.get('msg')}")
    return data["tenant_access_token"]


def upload_file(token, path):
    import requests
    name = os.path.basename(path)
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        r = requests.post(
            f"{BASE}/im/v1/files",
            headers={"Authorization": f"Bearer {token}"},
            data={"file_type": "stream", "file_name": name},
            files={"file": (name, f, mime)},
            timeout=120,
        )
    data = r.json()
    if data.get("code") != 0:
        fail(f"upload error {data.get('code')}: {data.get('msg')}",
             hint="check im:file permission and bot membership in the chat")
    return data["data"]["file_key"]


def send_message(token, receive_id, receive_id_type, msg_type, content_dict):
    import requests
    r = requests.post(
        f"{BASE}/im/v1/messages",
        params={"receive_id_type": receive_id_type},
        headers={"Authorization": f"Bearer {token}"},
        json={
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": json.dumps(content_dict, ensure_ascii=False),
        },
        timeout=30,
    )
    data = r.json()
    if data.get("code") != 0:
        fail(f"send error {data.get('code')}: {data.get('msg')}",
             hint="99991663/99991672 => wrong receive_id_type or bot not in chat")
    return data["data"]["message_id"]


def main():
    p = argparse.ArgumentParser(description="Send a file to Feishu")
    p.add_argument("file", help="local file path to send")
    p.add_argument("--text", default=None, help="optional text message sent before the file")
    p.add_argument("--to", default=None, help="override FEISHU_RECEIVE_ID")
    p.add_argument("--type", dest="rtype", default=None,
                   help="override FEISHU_RECEIVE_ID_TYPE")
    args = p.parse_args()

    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    receive_id = args.to or os.environ.get("FEISHU_RECEIVE_ID")
    rtype = args.rtype or os.environ.get("FEISHU_RECEIVE_ID_TYPE", "chat_id")

    missing = [k for k, v in [("FEISHU_APP_ID", app_id), ("FEISHU_APP_SECRET", app_secret),
                              ("FEISHU_RECEIVE_ID", receive_id)] if not v]
    if missing:
        fail(f"missing env vars: {', '.join(missing)}. See references/feishu-setup.md", code=2)
    if not os.path.isfile(args.file):
        fail(f"file not found: {args.file}", code=2)

    try:
        import requests  # noqa: F401
    except ImportError:
        fail("requests not installed. Run: uv pip install requests", code=2)

    token = get_token(app_id, app_secret)

    text_mid = None
    if args.text:
        text_mid = send_message(token, receive_id, rtype, "text", {"text": args.text})

    file_key = upload_file(token, args.file)
    file_mid = send_message(token, receive_id, rtype, "file", {"file_key": file_key})

    print(json.dumps({"ok": True, "message_id": file_mid, "text_message_id": text_mid,
                      "file": os.path.abspath(args.file)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
