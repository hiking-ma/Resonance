"""组合策略信号汇总；纯函数，不读取数据库。"""
import math
from typing import Callable

from analysis.resonance import turnover_value
from analysis.sentiment import enrich_turnover, percentile_series
from analysis.strategy_div import DIV_CODE, run_div_strategy
from analysis.strategy_kc import KC_CODE, run_kc_strategy
from analysis.strategy_kc50 import KC50_CODE, run_kc50_strategy
from analysis.strategy_sc50 import SC50_CODE, run_sc50_strategy
from analysis.strategy_sh50 import SH50_CODE, run_sh50_strategy
from analysis.strategy_zz import ZZ_CODE, run_zz_strategy
from analysis.strategy_zz500 import ZZ500_CODE, run_zz500_strategy
from config import SENTIMENT_ZONE_MIN_PTS, SENTIMENT_ZONE_WINDOW

TRADE_START = "2024-10-08"
ALL_CODES = [
    "510300", "510050", "510500", "512100",
    "515080", "588000", "589680", "159780",
]
RUNNERS: dict[str, Callable[[list[dict]], dict]] = {
    SH50_CODE: run_sh50_strategy,
    ZZ500_CODE: run_zz500_strategy,
    KC_CODE: run_kc_strategy,
    KC50_CODE: run_kc50_strategy,
    SC50_CODE: run_sc50_strategy,
    ZZ_CODE: run_zz_strategy,
    DIV_CODE: run_div_strategy,
}


def _percentile(rows: list[dict], values: list[float | None]) -> dict[str, float]:
    result = percentile_series(
        [row.get("date") for row in rows],
        values,
        SENTIMENT_ZONE_WINDOW,
        SENTIMENT_ZONE_MIN_PTS,
    )
    return {date: item.get("percentile") for date, item in result.items()}


def _is_buy(row: dict, turn_p: float | None) -> bool:
    position = row.get("price_position")
    direction = row.get("trade_direction")
    share = row.get("share_prob")
    composite = row.get("composite_prob")
    return (
        position is not None and direction == "ACCUMULATE"
        and (
            (position <= 40 and share is not None and share >= 65)
            or (position <= 40 and turn_p is not None and turn_p <= 10)
            or (position <= 10 and composite is not None and composite > 60)
        )
    )


def _generic_v1_trades(
    rows: list[dict], turn_pct: dict[str, float], margin_pct: dict[str, float],
) -> list[dict]:
    trades: list[dict] = []
    position, hold_days, sell_threshold, dist_count = 0.0, 0, 1, 0
    for index, row in enumerate(rows):
        date = row["date"]
        if date not in turn_pct and date not in margin_pct:
            continue
        close = row.get("close_price")
        if close is None:
            continue
        action = "BUY" if position == 0 and date >= TRADE_START \
            and _is_buy(row, turn_pct.get(date)) else None
        if position == 1:
            hold_days += 1
            if (row.get("trade_direction") == "DISTRIBUTE"
                    and (row.get("price_position") or 0) >= 80
                    and (margin_pct.get(date) or 0) >= 90):
                dist_count += 1
            if hold_days >= 10 and row.get("trade_direction") == "DISTRIBUTE" \
                    and dist_count >= sell_threshold:
                action = "SELL"
        if action == "BUY":
            position, hold_days, dist_count = 1.0, 0, 0
            previous = [rows[i].get("volume") or 0
                        for i in range(max(0, index - 20), index)]
            average = sum(previous) / len(previous) if previous else 1
            ratio = (row.get("volume") or 0) / average if average > 0 else 1.0
            turn_value = turn_pct.get(date)
            sell_threshold = 1 if turn_value is not None and turn_value <= 10 \
                else max(2, math.ceil(2 + ratio * 0.55))
            trades.append({"date": date, "action": action, "price": close})
        elif action == "SELL":
            position = 0.0
            trades.append({"date": date, "action": action, "price": close})
    return trades


def build_trades_by_code(
    rows_by_code: dict[str, list[dict]],
    turnover_rows: list[dict],
    margin_rows: list[dict],
) -> dict[str, list[dict]]:
    turnover = enrich_turnover(turnover_rows)
    turn_pct = _percentile(turnover, [turnover_value(row) for row in turnover])
    margin_pct = _percentile(
        margin_rows, [row.get("fin_balance_yi") for row in margin_rows],
    )
    output: dict[str, list[dict]] = {}
    for code in ALL_CODES:
        rows = [dict(row) for row in rows_by_code.get(code, [])]
        runner = RUNNERS.get(code)
        if runner is None:
            trades = _generic_v1_trades(rows, turn_pct, margin_pct)
        else:
            if runner in (run_div_strategy, run_zz_strategy):
                for row in rows:
                    row["_tp"] = turn_pct.get(row["date"])
            trades = runner(rows)["trades"]
        output[code] = [trade for trade in trades if trade["date"] >= TRADE_START]
    return output
