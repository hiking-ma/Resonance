from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scheduler.setup import start_scheduler, stop_scheduler
from api.signals import router as signals_router
from api.etf import router as etf_router
from api.realtime import router as realtime_router
from api.stats import router as stats_router
from api.sentiment import router as sentiment_router
from api.calendar import router as calendar_router
from api.resonance import router as resonance_router
from api.data import router as data_router
from api.portfolio import router as portfolio_router
from api.live_portfolio import router as live_portfolio_router

ROUTERS = (
    signals_router, etf_router, realtime_router, stats_router, sentiment_router,
    calendar_router, resonance_router, data_router, portfolio_router,
    live_portfolio_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="ETF 国家队监控系统",
              description="三因子 ETF 国家队资金监测 — 盘中实时信号",
              version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in ROUTERS:
    app.include_router(router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
