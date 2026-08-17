from datetime import datetime
from typing import Callable

from apscheduler.events import EVENT_JOB_MISSED, JobExecutionEvent
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import (
    CALENDAR_SYNC_DOW, CALENDAR_SYNC_HOUR, CALENDAR_SYNC_MIN,
    FEISHU_NOTIFY_HOUR, FEISHU_NOTIFY_MIN,
    FEISHU_PERPETUAL_HOUR, FEISHU_PERPETUAL_MIN,
    FEISHU_PLAN_PREFETCH_HOUR, FEISHU_PLAN_PREFETCH_MIN,
    FEISHU_RESONANCE_HOUR, FEISHU_RESONANCE_MIN, REALTIME_INTERVAL_SEC,
    SCHEDULER_MISFIRE_GRACE_SEC, SENTIMENT_FETCH_HOUR, SENTIMENT_FETCH_MIN,
)
from scheduler.perpetual_notify import task_notify_perpetual_timing
from scheduler.portfolio_notify import (
    task_notify_next_day_plan, task_prefetch_plan_data,
)
from scheduler.resonance_notify import task_notify_resonance_snapshot
from scheduler.tasks import (
    task_cleanup, task_daily_analysis, task_fetch_breadth, task_fetch_sentiment,
    task_fetch_shares, task_intraday_update, task_preload_kline,
    task_realtime_poll, task_sync_calendar,
)
from scheduler.time_guard import is_trading_time, trading_day_guard
from store.calendar_repo import get_calendar_count, reload_cache
from store.database import init_db
from store.sentiment_repo import get_margin_count, get_turnover_count

scheduler = AsyncIOScheduler(
    executors={"default": ThreadPoolExecutor(4)},
    job_defaults={
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": SCHEDULER_MISFIRE_GRACE_SEC,
    },
)


def _on_job_missed(event: JobExecutionEvent) -> None:
    print(
        f"[SCHEDULER] missed job {event.job_id} "
        f"(scheduled {event.scheduled_run_time})"
    )


def _bootstrap() -> None:
    init_db()
    reload_cache()
    if get_calendar_count() == 0:
        task_sync_calendar()
    task_preload_kline()
    task_fetch_shares()
    if is_trading_time(datetime.now()):
        print("[SCHEDULER] trading hours detected, fetching today's data...")
        try:
            task_realtime_poll()
            task_intraday_update()
        except Exception as exc:
            print(f"[SCHEDULER] initial fetch failed (non-critical): {exc}")
    if get_turnover_count() == 0 or get_margin_count() == 0:
        task_fetch_sentiment(backfill=True)


def _add_trading_cron(
    fn: Callable[[], object], job_id: str, hour: int, minute: int,
) -> None:
    scheduler.add_job(
        trading_day_guard(fn),
        CronTrigger(hour=hour, minute=minute, day_of_week="mon-fri"),
        id=job_id,
        replace_existing=True,
    )


def _register_jobs() -> None:
    scheduler.add_job(
        task_realtime_poll,
        IntervalTrigger(seconds=REALTIME_INTERVAL_SEC),
        id="realtime_poll",
        replace_existing=True,
    )
    scheduler.add_job(
        trading_day_guard(task_intraday_update),
        IntervalTrigger(minutes=15),
        id="intraday_update",
        replace_existing=True,
    )
    _add_trading_cron(task_preload_kline, "preload_kline", 9, 0)
    _add_trading_cron(task_notify_resonance_snapshot, "notify_resonance_snapshot",
                      FEISHU_RESONANCE_HOUR, FEISHU_RESONANCE_MIN)
    _add_trading_cron(task_daily_analysis, "daily_analysis", 15, 30)
    _add_trading_cron(task_fetch_sentiment, "fetch_sentiment",
                      SENTIMENT_FETCH_HOUR, SENTIMENT_FETCH_MIN)
    _add_trading_cron(task_fetch_breadth, "fetch_breadth", 16, 30)
    _add_trading_cron(task_fetch_shares, "fetch_shares", 19, 30)
    _add_trading_cron(task_prefetch_plan_data, "prefetch_plan_data",
                      FEISHU_PLAN_PREFETCH_HOUR, FEISHU_PLAN_PREFETCH_MIN)
    _add_trading_cron(task_notify_next_day_plan, "notify_next_day_plan",
                      FEISHU_NOTIFY_HOUR, FEISHU_NOTIFY_MIN)
    _add_trading_cron(task_notify_perpetual_timing, "notify_perpetual_timing",
                      FEISHU_PERPETUAL_HOUR, FEISHU_PERPETUAL_MIN)
    scheduler.add_job(
        task_cleanup, CronTrigger(hour=2, minute=0),
        id="cleanup", replace_existing=True,
    )
    scheduler.add_job(
        task_sync_calendar,
        CronTrigger(
            day_of_week=CALENDAR_SYNC_DOW,
            hour=CALENDAR_SYNC_HOUR,
            minute=CALENDAR_SYNC_MIN,
        ),
        id="sync_calendar",
        replace_existing=True,
    )


def start_scheduler() -> None:
    _bootstrap()
    _register_jobs()
    scheduler.add_listener(_on_job_missed, EVENT_JOB_MISSED)
    scheduler.start()
    print("[SCHEDULER] started")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("[SCHEDULER] stopped")
