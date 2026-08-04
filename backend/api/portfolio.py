"""组合回测 API: 8 标的统一仓位分配逻辑的净值走势与交易记录。"""
from __future__ import annotations

from fastapi import APIRouter

from config import ETFS
from store.daily_repo import get_by_code, get_trading_dates
from store.sentiment_repo import get_turnover_series, get_margin_series
from analysis.portfolio import simulate
from analysis.portfolio_signals import ALL_CODES, TRADE_START, build_trades_by_code

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

INIT_CAPITAL = 1_000_000   # 100 万初始净值
INIT_SHARES = 1_000_000    # 每份 1 元

KIND_LABEL = {
    "BUY": "买入(12.5%)",
    "TOPUP": "加仓(至25%)",
    "REDUCE": "减仓(至12.5%)",
    "SELL": "卖出",
}


def _load_trades() -> dict[str, list[dict]]:
    rows = {code: list(reversed(get_by_code(code))) for code in ALL_CODES}
    return build_trades_by_code(
        rows, get_turnover_series(), get_margin_series(),
    )


@router.get("/backtest")
def portfolio_backtest():
    trades_by_code = _load_trades()

    price_map: dict[str, dict[str, float]] = {}
    for code in ALL_CODES:
        rows = {r["date"]: r.get("close_price") for r in get_by_code(code)}
        for t in trades_by_code[code]:
            rows.setdefault(t["date"], t["price"])
        price_map[code] = rows

    dates = [d for d in get_trading_dates() if d >= TRADE_START]
    if not dates:
        dates = sorted({d for m in price_map.values() for d in m})

    result = simulate(trades_by_code, price_map, dates)

    scale = INIT_CAPITAL
    curve = [
        {"date": h["date"],
         "nav": round(h["equity"] * scale, 0),           # 总资产(元)
         "nav_per_share": round(h["equity"], 4),          # 每份净值(元)
         "position_pct": h["position_pct"]}
        for h in result["history"]
    ]
    trade_log = [
        {"date": t["date"], "signal_date": t.get("signal_date", ""),
         "code": t["code"],
         "name": ETFS.get(t["code"], {}).get("name", t["code"]),
         "kind": t["kind"], "kind_label": KIND_LABEL.get(t["kind"], t["kind"]),
         "units": t["units"], "price": t["price"],
         "amount": round(t["amount"] * t["price"] * scale, 0)}
        for t in result["trade_log"]
    ]
    open_positions = [
        {"code": p["code"], "name": ETFS.get(p["code"], {}).get("name", p["code"]),
         "units": p["units"], "buy_date": p["buy_date"]}
        for p in result["open_positions"]
    ]

    return {
        "initial_capital": INIT_CAPITAL,
        "initial_nav_per_share": 1.0,
        "total_return_pct": result["total_return_pct"],
        "max_drawdown_pct": result["max_drawdown_pct"],
        "avg_position_pct": result["avg_position_pct"],
        "final_nav": curve[-1]["nav"] if curve else INIT_CAPITAL,
        "final_nav_per_share": curve[-1]["nav_per_share"] if curve else 1.0,
        "signal_count": sum(len(v) for v in trades_by_code.values()),
        "curve": curve,
        "trades": trade_log,
        "open_positions": open_positions,
    }
