from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import ETFS
from store.live_portfolio_repo import (
    confirm_live_plan, get_live_config, get_live_plans, get_live_positions,
    initialize_live_portfolio, skip_live_plan,
)

router = APIRouter(prefix="/api/live-portfolio", tags=["live-portfolio"])


class InitializeRequest(BaseModel):
    inception_date: str


def _validate_date(value: str) -> None:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日期格式必须为 YYYY-MM-DD") from exc
    if parsed.date() > datetime.now().date():
        raise HTTPException(status_code=400, detail="起始日不能晚于今天")


def _decorate_position(row: dict) -> dict:
    info = ETFS.get(row["code"], {})
    return {
        **row,
        "name": info.get("name", row["code"]),
        "position_pct": int(row["units"]) * 12.5,
    }


def _decorate_plan(row: dict) -> dict:
    info = ETFS.get(row["code"], {})
    return {
        **row,
        "name": info.get("name", row["code"]),
        "target_position_pct": int(row["target_units"]) * 12.5,
    }


@router.get("")
def live_portfolio_state():
    positions = [_decorate_position(row) for row in get_live_positions()]
    pending = [_decorate_plan(row) for row in get_live_plans("pending")]
    history = [_decorate_plan(row) for row in get_live_plans(limit=100)
               if row["status"] != "pending"]
    total_units = sum(int(row["units"]) for row in positions)
    return {
        "config": get_live_config(),
        "positions": positions,
        "total_position_pct": total_units * 12.5,
        "pending_plans": pending,
        "history": history,
    }


@router.post("/initialize")
def initialize_live(request: InitializeRequest):
    _validate_date(request.inception_date)
    existing = get_live_config()
    if existing and existing["inception_date"] != request.inception_date:
        raise HTTPException(status_code=409, detail="实盘账本已经初始化，不能覆盖")
    return initialize_live_portfolio(request.inception_date)


@router.post("/plans/{plan_id}/confirm")
def confirm_plan(plan_id: int):
    pending = next(
        (row for row in get_live_plans("pending") if row["id"] == plan_id),
        None,
    )
    if pending and pending["execution_date"] > datetime.now().strftime("%Y-%m-%d"):
        raise HTTPException(status_code=400, detail="计划执行日未到，不能提前确认")
    try:
        return _decorate_plan(confirm_live_plan(plan_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/plans/{plan_id}/skip")
def skip_plan(plan_id: int):
    try:
        return _decorate_plan(skip_live_plan(plan_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
