import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import SESSION_SECRET_KEY
from app.logging_config import configure_logging
from app.models.database import init_db
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.polling import poll_all_devices
from app.startup_checks import run_startup_checks
from app.routes import devices, auth, scan

configure_logging()
logger = logging.getLogger("nms.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_startup_checks()
    init_db()
    # Run in a worker thread, not directly on the event loop — poll_all_devices()
    # calls asyncio.run() internally (for the SNMP checks), which fails if called
    # from a thread that already has a running event loop, as this async function's
    # thread does. APScheduler's later polls don't hit this since they already run
    # in their own worker thread.
    await asyncio.to_thread(poll_all_devices)
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="NMS", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

_session_secret = SESSION_SECRET_KEY
if not _session_secret:
    _session_secret = secrets.token_hex(32)
    logger.warning(
        "SESSION_SECRET_KEY is not set in .env — using a random ephemeral "
        "key for this process. Every restart will log everyone out. Set "
        "SESSION_SECRET_KEY in .env for persistent sessions."
    )
app.add_middleware(SessionMiddleware, secret_key=_session_secret)

app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(scan.router)


@app.get("/health")
def health():
    return {"status": "ok"}