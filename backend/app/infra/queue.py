"""JobQueue adapters: Redis/RQ for real deployments, inline for tests and single-process dev."""

from collections.abc import Callable


class RQJobQueue:
    def __init__(self, redis_url: str, queue_name: str = "folio", job_timeout: int = 1800):
        from redis import Redis
        from rq import Queue

        self._queue = Queue(queue_name, connection=Redis.from_url(redis_url), default_timeout=job_timeout)

    def enqueue(self, job_id: str) -> None:
        self._queue.enqueue("app.worker.run_job", job_id, job_id=job_id, result_ttl=0, failure_ttl=3600)


class InlineJobQueue:
    """Runs the job immediately in-process. The runner is injected to avoid an import cycle."""

    def __init__(self) -> None:
        self.runner: Callable[[str], None] | None = None

    def enqueue(self, job_id: str) -> None:
        if self.runner is None:
            raise RuntimeError("InlineJobQueue has no runner attached")
        self.runner(job_id)
