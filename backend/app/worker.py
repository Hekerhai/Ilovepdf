"""RQ worker entry points. Run with: rq worker folio --url $REDIS_URL (see docker-compose.yml)."""

import logging

from app.container import get_container

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def run_job(job_id: str) -> None:
    get_container().jobs.run(job_id)
