from datetime import datetime

from analysis.resonance import compute_live_resonance
from config import (
    ETFS, FEISHU_RESONANCE_HOUR, FEISHU_RESONANCE_MIN, FEISHU_WEBHOOK_URL,
)
from notify.feishu import send_feishu_text
from store.notification_repo import mark_notified, was_notified
from store.realtime_repo import get_latest_snapshot

ALERT_VERDICTS = {"危险共振": "🔴", "机会共振": "🟢"}
SNAPSHOT_TIME = f"{FEISHU_RESONANCE_HOUR:02d}:{FEISHU_RESONANCE_MIN:02d}"


def _result_line(result: dict) -> str:
    verdict = result["verdict"]
    state = "red" if verdict == "危险共振" else "green"
    indicators = [
        item["name"] for item in result["indicators"] if item["state"] == state
    ]
    icon = ALERT_VERDICTS[verdict]
    return (
        f"{icon} {result['name']}（{result['code']}）：{verdict} "
        f"[红{result['red_count']}/绿{result['green_count']}] "
        f"{'、'.join(indicators)}"
    )


def _snapshot_message(timestamp: str, results: list[dict]) -> str:
    alerts = [item for item in results if item["verdict"] in ALERT_VERDICTS]
    lines = [
        f"📊 {SNAPSHOT_TIME} 多指标共振快照",
        f"快照时间：{timestamp.replace('T', ' ')}",
    ]
    if alerts:
        lines.extend(_result_line(item) for item in alerts)
    else:
        lines.append("当前无 ETF 触发机会共振或危险共振。")
    lines.extend([
        "当日成交额与融资数据尚未完成，两个市场指标记为灰灯，不参与计数。",
        "本消息为盘中快照，收盘前仍可能变化，不构成投资建议。",
    ])
    return "\n".join(lines)


def _status_message(today: str) -> str:
    return "\n".join([
        f"⚠️ {SNAPSHOT_TIME} 多指标共振快照未生成",
        f"日期：{today}",
        "原因：当日实时行情快照未就绪。",
    ])


def task_notify_resonance_snapshot() -> dict:
    if not FEISHU_WEBHOOK_URL:
        return {"status": "disabled", "sent": 0}
    today = datetime.now().strftime("%Y-%m-%d")
    event_key = f"resonance-snapshot:{today}:{SNAPSHOT_TIME}"
    if was_notified(event_key):
        return {"status": "duplicate", "sent": 0}
    signals = get_latest_snapshot()
    timestamp = signals[0]["timestamp"] if signals else ""
    if not timestamp.startswith(today):
        text = _status_message(today)
        status, alert_count = "stale", 0
    else:
        results = [
            compute_live_resonance(
                row["code"], row, [], [], row["timestamp"],
            )
            for row in signals if row["code"] in ETFS
        ]
        text = _snapshot_message(timestamp, results)
        status = "ok"
        alert_count = sum(
            item["verdict"] in ALERT_VERDICTS for item in results
        )
    if not send_feishu_text(FEISHU_WEBHOOK_URL, text):
        return {"status": "failed", "sent": 0}
    mark_notified(event_key, "feishu")
    print(f"[FEISHU] {SNAPSHOT_TIME} resonance snapshot sent ({today})")
    return {"status": status, "sent": 1, "alerts": alert_count}
