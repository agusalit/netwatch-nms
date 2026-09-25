from apscheduler.schedulers.background import BackgroundScheduler

from app.config import PING_INTERVAL_SECONDS
from app.services.polling import poll_all_devices

scheduler = BackgroundScheduler()


def start_scheduler():
    scheduler.add_job(
        poll_all_devices,
        "interval",
        seconds=PING_INTERVAL_SECONDS,
        id="poll_all_devices",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown(wait=False)