from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app.models.database import init_db
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.polling import poll_all_devices


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    poll_all_devices()  # one immediate sweep so the dashboard isn't empty on first load
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="NMS", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/health")
def health():
    return {"status": "ok"}
