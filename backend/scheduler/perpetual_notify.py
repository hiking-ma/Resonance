"""交易日 10:00：510300 择时 → 永续组合全仓买卖飞书提醒。"""
from datetime import datetime, timedelta

from config import (
    FEISHU_PERPETUAL_HOUR, FEISHU_PERPETUAL_MIN, FEISHU_WEBHOOK_URL,
)
from notify.feishu import send_feishu_text
from store.calendar_repo import get_last_trading_day
from store.notification_repo import mark_notified, was_notified

NOTIFY_TIME = f"{FEISHU_PERPETUAL_HOUR:02d}:{FEISHU_PERPETUAL_MIN:02d}"
CODE = "510300"
NAME = "华泰柏瑞沪深300ETF"


def _previous_signal_date(now: datetime | None = None) -> str:
    now = now or datetime.now()
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    return get_last_trading_day(yesterday)


def _load_trades() -> list[dict]:
    from api.resonance import resonance_trades
    return list(resonance_trades(CODE).get("trades") or [])


def _advice(trades: list[dict], signal_date: str) -> tuple[str, str, dict | None]:
    """返回 (今日建议, 仓位状态, 最新信号)。"""
    if not trades:
        return "暂无 510300 买卖信号，永续组合先观望。", "未知", None
    last = trades[-1]
    action = last.get("action")
    fresh = last.get("date") == signal_date
    if action == "BUY":
        state = "应持仓（全仓）"
        advice = (
            "今日建议：全仓买入永续组合（按最新权重一次性建仓）。"
            if fresh else
            "今日建议：保持永续组合全仓，无需调仓。"
        )
        return advice, state, last
    if action == "SELL":
        state = "应空仓"
        advice = (
            "今日建议：全仓卖出永续组合（一次性清仓）。"
            if fresh else
            "今日建议：继续空仓观望，等待下一次买入信号。"
        )
        return advice, state, last
    return "今日建议：信号异常，请手动核对。", "未知", last


def _message(signal_date: str, advice: str, state: str, last: dict | None) -> str:
    lines = [
        f"📌 {NOTIFY_TIME} 永续组合 · 510300 择时提醒",
        f"信号参考日：{signal_date}",
        f"仓位状态：{state}",
    ]
    if last:
        lines.append(
            f"最新信号：{last.get('action')} {last.get('date')} "
            f"@ {last.get('price')} · {last.get('reason') or '—'}"
        )
    lines.extend([
        advice,
        f"标的说明：以 {NAME}（{CODE}）买卖点驱动永续组合全进全出。",
        "请到 iFund「永续组合 / 联合回测 / 实盘」核对后手动执行；本消息不构成投资建议。",
    ])
    return "\n".join(lines)


def task_notify_perpetual_timing() -> dict:
    if not FEISHU_WEBHOOK_URL:
        print("[FEISHU] FEISHU_WEBHOOK_URL not configured, perpetual skipped")
        return {"status": "disabled", "sent": 0}
    today = datetime.now().strftime("%Y-%m-%d")
    event_key = f"perpetual-510300:{today}:{NOTIFY_TIME}"
    if was_notified(event_key):
        return {"status": "duplicate", "sent": 0}
    signal_date = _previous_signal_date()
    trades = _load_trades()
    advice, state, last = _advice(trades, signal_date)
    text = _message(signal_date, advice, state, last)
    if not send_feishu_text(FEISHU_WEBHOOK_URL, text):
        return {"status": "failed", "sent": 0}
    mark_notified(event_key, "feishu")
    print(f"[FEISHU] {NOTIFY_TIME} perpetual timing sent ({today}, {state})")
    return {
        "status": "ok",
        "sent": 1,
        "state": state,
        "signal_date": signal_date,
        "last_action": (last or {}).get("action"),
        "last_date": (last or {}).get("date"),
    }
