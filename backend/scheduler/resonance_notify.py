from datetime import datetime

from analysis.resonance import compute_live_resonance, compute_resonance
from analysis.sentiment import enrich_turnover
from config import ETFS, FEISHU_RETRY_COOLDOWN_SEC, FEISHU_WEBHOOK_URL
from notify.feishu import send_feishu_text
from store.calendar_repo import get_last_trading_day
from store.daily_repo import get_by_code
from store.notification_repo import mark_notified, was_notified
from store.sentiment_repo import get_margin_series, get_turnover_series

ALERT_VERDICTS = {"危险共振": "🔴", "机会共振": "🟢"}
STATE_ICON = {"red": "🔴", "green": "🟢"}
_last_attempt: dict[str, datetime] = {}


def _load_resonance(code: str, turnover: list[dict], margin: list[dict]) -> dict:
    etf_rows = list(reversed(get_by_code(code)))
    usable = [row for row in etf_rows if row.get("composite_prob") is not None]
    return compute_resonance(code, usable, turnover, margin)


def _event_key(result: dict) -> str:
    return f"resonance:{result['date']}:{result['code']}:{result['verdict']}"


def _message(result: dict) -> str:
    verdict = result["verdict"]
    state = "red" if verdict == "危险共振" else "green"
    triggered = [
        f"{item['name']}{STATE_ICON[state]}"
        for item in result["indicators"]
        if item["state"] == state
    ]
    icon = ALERT_VERDICTS[verdict]
    time_line = (
        f"盘中时间：{result['timestamp'].replace('T', ' ')}"
        if result.get("timestamp") else f"数据日期：{result['date']}"
    )
    return "\n".join([
        f"{icon} {verdict}预警 · {result['name']}（{result['code']}）",
        time_line,
        (
            f"红灯 {result['red_count']} / 绿灯 {result['green_count']} / "
            f"灰灯 {result['gray_count']}"
        ),
        f"触发指标：{'、'.join(triggered)}",
        "本消息为量化监测结果，不构成投资建议。",
    ])


def _send_result(result: dict) -> bool:
    key = _event_key(result)
    if was_notified(key):
        return False
    now = datetime.now()
    attempted = _last_attempt.get(key)
    if attempted and (now - attempted).total_seconds() < FEISHU_RETRY_COOLDOWN_SEC:
        return False
    _last_attempt[key] = now
    if not send_feishu_text(FEISHU_WEBHOOK_URL, _message(result)):
        return False
    mark_notified(key, "feishu")
    print(f"[FEISHU] notified {result['code']} {result['verdict']} ({result['date']})")
    return True


def task_notify_intraday_resonance(signals: list[dict]) -> dict:
    if not FEISHU_WEBHOOK_URL:
        return {"status": "disabled", "sent": 0}
    turnover = enrich_turnover(get_turnover_series())
    margin = get_margin_series()
    sent = 0
    for signal in signals:
        code = signal.get("code")
        timestamp = signal.get("timestamp")
        if code not in ETFS or not timestamp:
            continue
        result = compute_live_resonance(code, signal, turnover, margin, timestamp)
        if result["verdict"] in ALERT_VERDICTS and _send_result(result):
            sent += 1
    return {"status": "ok", "sent": sent}


def task_notify_resonance() -> dict:
    if not FEISHU_WEBHOOK_URL:
        print("[FEISHU] FEISHU_WEBHOOK_URL not configured, skipped")
        return {"status": "disabled", "sent": 0}

    today = datetime.now().strftime("%Y-%m-%d")
    target_date = get_last_trading_day(today)
    turnover = enrich_turnover(get_turnover_series())
    margin = get_margin_series()
    sent = 0

    for code in ETFS:
        result = _load_resonance(code, turnover, margin)
        if result["verdict"] not in ALERT_VERDICTS or result["date"] != target_date:
            continue
        if _send_result(result):
            sent += 1

    return {"status": "ok", "date": target_date, "sent": sent}
