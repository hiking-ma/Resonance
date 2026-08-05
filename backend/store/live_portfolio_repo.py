import sqlite3
from typing import Optional

from store.database import get_connection

MAX_PORTFOLIO_UNITS = 8
VALID_TRANSITIONS = {
    "BUY": (0, 1),
    "TOPUP": (1, 2),
    "REDUCE": (2, 1),
    "SELL": (1, 0),
}


def get_live_config() -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT inception_date, initialized_at FROM live_portfolio_config WHERE id=1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def initialize_live_portfolio(inception_date: str) -> dict:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO live_portfolio_config(id, inception_date) VALUES(1, ?)",
            (inception_date,),
        )
        conn.commit()
    finally:
        conn.close()
    return get_live_config() or {"inception_date": inception_date}


def get_live_positions() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT code, units, opened_date, last_action_date, updated_at "
            "FROM live_positions ORDER BY code"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_live_plans(status: Optional[str] = None, limit: int = 100) -> list[dict]:
    conn = get_connection()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM live_trade_plans WHERE status=? "
                "ORDER BY execution_date, id LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM live_trade_plans ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def create_live_plans(plans: list[dict]) -> list[dict]:
    if not plans:
        return []
    conn = get_connection()
    try:
        conn.executemany("""
            INSERT OR IGNORE INTO live_trade_plans
                (signal_date, execution_date, code, kind, target_units, reason)
            VALUES (:signal_date, :execution_date, :code, :kind, :target_units, :reason)
        """, plans)
        conn.commit()
        signal_date = plans[0]["signal_date"]
        execution_date = plans[0]["execution_date"]
        rows = conn.execute(
            "SELECT * FROM live_trade_plans "
            "WHERE signal_date=? AND execution_date=? AND status='pending' "
            "ORDER BY CASE kind WHEN 'SELL' THEN 1 WHEN 'REDUCE' THEN 2 "
            "WHEN 'BUY' THEN 3 ELSE 4 END, id",
            (signal_date, execution_date),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _current_units(conn: sqlite3.Connection, code: str) -> int:
    row = conn.execute(
        "SELECT units FROM live_positions WHERE code=?", (code,),
    ).fetchone()
    return int(row["units"]) if row else 0


def _validate_transition(kind: str, current: int, target: int) -> None:
    expected = VALID_TRANSITIONS.get(kind)
    if expected is None:
        raise ValueError(f"未知计划类型: {kind}")
    if kind == "SELL":
        if current not in (1, 2) or target != 0:
            raise ValueError(f"当前仓位 {current} 单位，无法执行 {kind}")
    elif (current, target) != expected:
        raise ValueError(f"当前仓位 {current} 单位，无法执行 {kind}→{target}")


def _validate_capacity(conn: sqlite3.Connection, code: str, target: int) -> None:
    total = conn.execute(
        "SELECT COALESCE(SUM(units), 0) AS total FROM live_positions"
    ).fetchone()["total"]
    current = _current_units(conn, code)
    if int(total) - current + target > MAX_PORTFOLIO_UNITS:
        raise ValueError("确认后总仓位将超过 100%")


def confirm_live_plan(plan_id: int) -> dict:
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM live_trade_plans WHERE id=?", (plan_id,),
        ).fetchone()
        if not row:
            raise ValueError("计划不存在")
        plan = dict(row)
        if plan["status"] != "pending":
            raise ValueError("计划已处理")
        current = _current_units(conn, plan["code"])
        target = int(plan["target_units"])
        _validate_transition(plan["kind"], current, target)
        _validate_capacity(conn, plan["code"], target)
        if target == 0:
            conn.execute("DELETE FROM live_positions WHERE code=?", (plan["code"],))
        else:
            opened = plan["execution_date"]
            existing = conn.execute(
                "SELECT opened_date FROM live_positions WHERE code=?", (plan["code"],)
            ).fetchone()
            if existing:
                opened = existing["opened_date"]
            conn.execute("""
                INSERT INTO live_positions
                    (code, units, opened_date, last_action_date, updated_at)
                VALUES (?, ?, ?, ?, datetime('now','localtime'))
                ON CONFLICT(code) DO UPDATE SET
                    units=excluded.units,
                    last_action_date=excluded.last_action_date,
                    updated_at=excluded.updated_at
            """, (plan["code"], target, opened, plan["execution_date"]))
        conn.execute(
            "UPDATE live_trade_plans SET status='confirmed', "
            "resolved_at=datetime('now','localtime') WHERE id=?",
            (plan_id,),
        )
        conn.commit()
        return {**plan, "status": "confirmed"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def skip_live_plan(plan_id: int) -> dict:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE live_trade_plans SET status='skipped', "
            "resolved_at=datetime('now','localtime') "
            "WHERE id=? AND status='pending'",
            (plan_id,),
        )
        if cursor.rowcount == 0:
            raise ValueError("计划不存在或已处理")
        conn.commit()
        row = conn.execute(
            "SELECT * FROM live_trade_plans WHERE id=?", (plan_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()
