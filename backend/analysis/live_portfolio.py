"""基于已确认实际仓位生成保守型次日操作计划。纯函数，无 I/O。"""

MAX_UNITS = 8


def extract_day_signals(
    trades_by_code: dict[str, list[dict]], signal_date: str,
) -> list[dict]:
    signals = []
    for code, trades in trades_by_code.items():
        for trade in trades:
            if trade["date"] == signal_date:
                signals.append({
                    "code": code,
                    "action": trade["action"],
                    "reason": trade.get("reason") or f"策略{trade['action']}信号",
                })
    return signals


def _action(
    signal_date: str, execution_date: str, code: str,
    kind: str, target_units: int, reason: str,
) -> dict:
    return {
        "signal_date": signal_date,
        "execution_date": execution_date,
        "code": code,
        "kind": kind,
        "target_units": target_units,
        "reason": reason,
    }


def _sell_actions(
    signals: list[dict], units: dict[str, int],
    signal_date: str, execution_date: str,
) -> list[dict]:
    actions = []
    for signal in signals:
        code = signal["code"]
        if signal["action"] != "SELL" or units.get(code, 0) == 0:
            continue
        actions.append(_action(
            signal_date, execution_date, code, "SELL", 0, signal["reason"],
        ))
        units.pop(code, None)
    return actions


def _buy_actions(
    signals: list[dict], units: dict[str, int],
    signal_date: str, execution_date: str,
) -> list[dict]:
    fresh = [
        signal for signal in signals
        if signal["action"] == "BUY" and units.get(signal["code"], 0) == 0
    ]
    if not fresh:
        return []
    actions = []
    for code in sorted(units):
        if units[code] == 2:
            units[code] = 1
            actions.append(_action(
                signal_date, execution_date, code, "REDUCE", 1,
                "为新的买入信号释放组合资金",
            ))
    for signal in fresh:
        if sum(units.values()) >= MAX_UNITS:
            break
        code = signal["code"]
        units[code] = 1
        actions.append(_action(
            signal_date, execution_date, code, "BUY", 1, signal["reason"],
        ))
    return actions


def _topup_actions(
    positions: list[dict], units: dict[str, int],
    signal_date: str, execution_date: str,
) -> list[dict]:
    if sum(units.values()) >= MAX_UNITS:
        return []
    candidates = sorted(
        (
            row for row in positions
            if units.get(row["code"]) == 1
            and row["last_action_date"] < execution_date
        ),
        key=lambda row: row["opened_date"],
        reverse=True,
    )
    actions = []
    for row in candidates:
        if sum(units.values()) >= MAX_UNITS:
            break
        code = row["code"]
        units[code] = 2
        actions.append(_action(
            signal_date, execution_date, code, "TOPUP", 2,
            "持仓满一个交易日且组合仍有余钱",
        ))
    return actions


def build_live_plan(
    signals: list[dict], positions: list[dict],
    signal_date: str, execution_date: str,
) -> list[dict]:
    units = {row["code"]: int(row["units"]) for row in positions}
    actions = _sell_actions(signals, units, signal_date, execution_date)
    buys = _buy_actions(signals, units, signal_date, execution_date)
    actions.extend(buys)
    if not buys:
        actions.extend(_topup_actions(
            positions, units, signal_date, execution_date,
        ))
    return actions
