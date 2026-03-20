"""무한매수법 자동화 서비스 - FastAPI 앱"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from scheduler import setup_scheduler
from routers import dashboard, settings, trades, auth, market

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    setup_scheduler()
    logging.info("무한매수법 서비스 시작")
    yield
    # Shutdown
    logging.info("무한매수법 서비스 종료")


app = FastAPI(
    title="무한매수법 자동화",
    description="라오어 무한매수법 자동 매수/매도 서비스",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:5177", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(settings.router)
app.include_router(trades.router)
app.include_router(market.router)
