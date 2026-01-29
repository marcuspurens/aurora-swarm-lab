"""Worker loop to process queued jobs."""

from __future__ import annotations

import logging
import time
from typing import Callable, Dict

from app.queue.jobs import claim_job, mark_done, mark_failed

logger = logging.getLogger(__name__)


def run_worker(lane: str, handlers: Dict[str, Callable[[dict], None]], idle_sleep: float = 2.0) -> None:
    while True:
        job = claim_job(lane)
        if not job:
            time.sleep(idle_sleep)
            continue
        handler = handlers.get(job["job_type"])
        try:
            if handler is None:
                raise RuntimeError(f"No handler for job_type {job['job_type']}")
            handler(job)
            mark_done(job["job_id"])
        except Exception as exc:
            logger.exception("Job failed")
            mark_failed(job["job_id"], str(exc))
