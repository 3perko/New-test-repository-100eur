"""Background scheduler (separate process / container): daily inbox processing and vehicle checks.

Run: python -m app.scheduler
"""
import logging
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_config
from app.db import SessionLocal
from app.models import Company
from app.services import jobs, vehicle_check
from app.services.settings import get_param

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("scheduler")


def inbox_job():
    with SessionLocal() as db:
        log.info("Inbox run: %s", jobs.run_all(db))


def vehicle_job():
    with SessionLocal() as db:
        for c in db.query(Company).filter(Company.active.is_(True)):
            n = vehicle_check.run_api_checks(db, c.id)
            db.commit()
            log.info("Vehicle API checks for %s: %s", c.name, n)


def current_schedule() -> tuple[int, int]:
    with SessionLocal() as db:
        hhmm = str(get_param(db, "inbox_schedule_time") or "20:00")
    h, _, m = hhmm.partition(":")
    return int(h), int(m or 0)


def main():
    tz = get_config().timezone
    sched = BackgroundScheduler(timezone=tz)
    h, m = current_schedule()
    sched.add_job(inbox_job, CronTrigger(hour=h, minute=m, timezone=tz), id="inbox", replace_existing=True)
    sched.add_job(vehicle_job, CronTrigger(hour=6, minute=17, timezone=tz), id="vehicles", replace_existing=True)
    sched.start()
    log.info("Scheduler started – inbox daily at %02d:%02d (%s)", h, m, tz)
    try:
        while True:
            time.sleep(300)
            nh, nm = current_schedule()
            if (nh, nm) != (h, m):
                h, m = nh, nm
                sched.reschedule_job("inbox", trigger=CronTrigger(hour=h, minute=m, timezone=tz))
                log.info("Inbox schedule changed to %02d:%02d", h, m)
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown()


if __name__ == "__main__":
    main()
