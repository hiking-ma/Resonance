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
from store.daily_repo import get_by_code, get_trading_dates, shares_complete_for
from store.live_portfolio_repo import (
    create_live_plans, get_live_config, get_live_plans, get_live_positions,
)
from store.notification_repo import mark_notified, was_notified
from store.sentiment_repo import (
    get_margin_latest_date, get_margin_series,
    get_turnover_latest_date, get_turnover_series,
)

KIND_LABEL = {
    "BUY": "买入至 12.5%",
    "TOPUP": "加仓至 25%",
    "REDUCE": "减仓至 12.5%",
    "SELL": "清仓",
}
PLAN_TIME = f"{FEISHU_NOTIFY_HOUR:02d}:{FEISHU_NOTIFY_MIN:02d}"


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


def _data_note(signal_date: str) -> str:
    return (
        f"数据：日线/份额/成交额 {signal_date}；"
        f"融资 {get_margin_latest_date() or '未就绪'}"
    )


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
        _data_note(signal_date),
        "执行后请到“我的仓位”页面手动确认；未确认不会改变实际仓位。",
        "本消息为量化策略计划，不构成投资建议。",
    ])
    return "\n".join(lines)


def _no_action_message(signal_date: str, execution_date: str) -> str:
    return "\n".join([
        "📋 次交易日操作计划 · 无操作",
        f"信号日：{signal_date}",
        f"计划执行日：{execution_date}",
        _data_note(signal_date),
        "当前策略没有产生需要调整实际仓位的操作。",
    ])


def _pending_message(plan: list[dict]) -> str:
    lines = ["⚠️ 实际仓位仍有待确认计划"]
    for item in plan:
        name = ETFS.get(item["code"], {}).get("name", item["code"])
        label = KIND_LABEL.get(item["kind"], item["kind"])
        lines.append(
            f"• 计划#{item['id']} {name}：{label}，执行日 {item['execution_date']}"
        )
    lines.append("请到“我的仓位”确认已执行或跳过；确认前不生成新计划。")
    return "\n".join(lines)


def _data_ready(signal_date: str) -> tuple[bool, str]:
    missing = []
    if not shares_complete_for(signal_date):
        missing.append("ETF份额")
    if get_turnover_latest_date() != signal_date:
        missing.append("当日成交额")
    if missing:
        return False, "、".join(missing)
    return True, ""


def _send_summary(event_key: str, text: str, status: str) -> dict:
    if not send_feishu_text(FEISHU_WEBHOOK_URL, text):
        return {"status": "failed", "sent": 0}
    mark_notified(event_key, "feishu")
    print(f"[FEISHU] {PLAN_TIME} portfolio summary sent ({status})")
    return {"status": status, "sent": 1}


def task_notify_next_day_plan() -> dict:
    if not FEISHU_WEBHOOK_URL:
        print("[FEISHU] FEISHU_WEBHOOK_URL not configured, plan skipped")
        return {"status": "disabled", "sent": 0}
    today = datetime.now().strftime("%Y-%m-%d")
    event_key = f"live-plan-summary:{today}:{PLAN_TIME}"
    if was_notified(event_key):
        return {"status": "duplicate", "sent": 0}
    config = get_live_config()
    if not config:
        text = f"⚠️ {PLAN_TIME} 次日计划未生成\n原因：“我的仓位”尚未初始化。"
        return _send_summary(event_key, text, "not_initialized")
    existing = get_live_plans("pending")
    if existing:
        return _send_summary(event_key, _pending_message(existing), "pending")
    signal_date = _expected_signal_date(datetime.now())
    execution_date = get_next_trading_day(signal_date)
    if signal_date <= config["inception_date"]:
        text = _no_action_message(signal_date, execution_date)
        return _send_summary(event_key, text, "before_inception")
    available_dates = get_trading_dates()
    if not available_dates or available_dates[-1] != signal_date:
        text = (
            f"⚠️ {PLAN_TIME} 次日计划未生成\n信号日：{signal_date}\n"
            "原因：当日策略日线尚未就绪。"
        )
        return _send_summary(event_key, text, "stale")
    ready, missing = _data_ready(signal_date)
    if not ready:
        text = (
            f"⚠️ {PLAN_TIME} 次日计划未生成\n信号日：{signal_date}\n"
            f"原因：{missing}尚未就绪。"
        )
        return _send_summary(event_key, text, "data_incomplete")
    execution_date, plan = _build_plan(signal_date)
    text = _message(signal_date, execution_date, plan) if plan \
        else _no_action_message(signal_date, execution_date)
    status = "ok" if plan else "no_action"
    return _send_summary(event_key, text, status)
