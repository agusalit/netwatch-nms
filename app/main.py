import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.models.database import init_db
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.polling import poll_all_devices
from app.routes import devices


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    await asyncio.to_thread(poll_all_devices)
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="NMS", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(devices.router)


@app.get("/health")
def health():
    return {"status": "ok"}