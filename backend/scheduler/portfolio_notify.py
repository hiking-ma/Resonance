from datetime import datetime, timedelta

from analysis.live_portfolio import build_live_plan, extract_day_signals
from analysis.portfolio_signals import ALL_CODES, build_trades_by_code
from config import (
    ETFS, FEISHU_NOTIFY_HOUR, FEISHU_NOTIFY_MIN, FEISHU_WEBHOOK_URL,
)
from notify.feishu import send_feishu_text
from store.calendar_repo import (
    get_last_trading_day, get_next_trading_day, is_trading_day,
)
from store.daily_repo import get_by_code, get_trading_dates
from store.live_portfolio_repo import (
    create_live_plans, get_live_config, get_live_plans, get_live_positions,
)
from store.notification_repo import mark_notified, was_notified
from store.sentiment_repo import get_margin_series, get_turnover_series

KIND_LABEL = {
    "BUY": "买入至 12.5%",
    "TOPUP": "加仓至 25%",
    "REDUCE": "减仓至 12.5%",
    "SELL": "清仓",
}


def _expected_signal_date(now: datetime) -> str:
    today = now.strftime("%Y-%m-%d")
    cutoff_passed = (now.hour, now.minute) >= (
        FEISHU_NOTIFY_HOUR, FEISHU_NOTIFY_MIN,
    )
    if is_trading_day(today) and not cutoff_passed:
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        return get_last_trading_day(yesterday)
    return get_last_trading_day(today)


def _build_plan(signal_date: str) -> tuple[str, list[dict]]:
    execution_date = get_next_trading_day(signal_date)
    rows_by_code = {
        code: list(reversed(get_by_code(code))) for code in ALL_CODES
    }
    trades = build_trades_by_code(
        rows_by_code, get_turnover_series(), get_margin_series(),
    )
    signals = extract_day_signals(trades, signal_date)
    plan = build_live_plan(
        signals, get_live_positions(), signal_date, execution_date,
    )
    return execution_date, create_live_plans(plan)


def _message(signal_date: str, execution_date: str, plan: list[dict]) -> str:
    lines = [
        "📋 次交易日操作计划",
        f"信号日：{signal_date}",
        f"计划执行日：{execution_date}",
    ]
    for item in plan:
        code = item["code"]
        name = ETFS.get(code, {}).get("name", code)
        label = KIND_LABEL.get(item["kind"], item["kind"])
        lines.append(f"• 计划#{item['id']} {name}（{code}）：{label}")
        lines.append(f"  原因：{item['reason']}")
    lines.extend([
        "执行后请到“我的仓位”页面手动确认；未确认不会改变实际仓位。",
        "本消息为量化策略计划，不构成投资建议。",
    ])
    return "\n".join(lines)


def task_notify_next_day_plan() -> dict:
    if not FEISHU_WEBHOOK_URL:
        print("[FEISHU] FEISHU_WEBHOOK_URL not configured, plan skipped")
        return {"status": "disabled", "sent": 0}
    config = get_live_config()
    if not config:
        return {"status": "not_initialized", "sent": 0}
    existing = get_live_plans("pending")
    if existing:
        signal_date = existing[0]["signal_date"]
        execution_date = existing[0]["execution_date"]
        plan = existing
    else:
        signal_date = _expected_signal_date(datetime.now())
        if signal_date <= config["inception_date"]:
            return {"status": "before_inception", "sent": 0}
        available_dates = get_trading_dates()
        if not available_dates or available_dates[-1] != signal_date:
            return {"status": "stale", "signal_date": signal_date, "sent": 0}
        execution_date, plan = _build_plan(signal_date)
    if not plan:
        return {"status": "no_action", "signal_date": signal_date, "sent": 0}
    event_key = f"live-plan:{signal_date}:{execution_date}"
    if was_notified(event_key):
        return {"status": "duplicate", "signal_date": signal_date, "sent": 0}
    if not send_feishu_text(
        FEISHU_WEBHOOK_URL, _message(signal_date, execution_date, plan),
    ):
        return {"status": "failed", "signal_date": signal_date, "sent": 0}
    mark_notified(event_key, "feishu")
    print(f"[FEISHU] next-day plan sent: {signal_date} -> {execution_date}")
    return {"status": "ok", "signal_date": signal_date, "sent": 1}
