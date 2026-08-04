import json
import urllib.error
import urllib.request

from config import FEISHU_NOTIFY_TIMEOUT_SEC


def send_feishu_text(webhook_url: str, text: str) -> bool:
    payload = json.dumps({
        "msg_type": "text",
        "content": {"text": text},
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=FEISHU_NOTIFY_TIMEOUT_SEC,
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
        if result.get("code") == 0:
            return True
        print(f"[FEISHU] rejected: code={result.get('code')}, msg={result.get('msg')}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"[FEISHU] send failed: {exc}")
    return False
