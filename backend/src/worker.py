import time,logging
from pathlib import Path
from src.config.database import Session
from src.models.entities import ForecastRun
from src.services import queue
from src.services.runner import process

with Session() as recovery:
    for pending in recovery.query(ForecastRun).filter(ForecastRun.state.in_(['queued','running'])).all():
        pending.state='queued';queue.enqueue(pending.id)
    recovery.commit()

while True:
    Path('/tmp/heartbeat').touch()
    try:
        run_id=queue.take()
        if run_id is not None:process(run_id)
    except Exception:
        logging.exception('worker');time.sleep(2)
