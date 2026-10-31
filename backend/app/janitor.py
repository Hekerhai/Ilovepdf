"""Deletes expired files on a loop. Run as its own process: python -m app.janitor"""

import logging
import time

from app.container import get_container

log = logging.getLogger("janitor")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    container = get_container()
    interval = container.settings.janitor_interval_seconds
    log.info("Janitor started: deleting files older than %sh every %ss", container.settings.file_ttl_hours, interval)
    while True:
        try:
            container.privacy.purge_expired()
            container.esign.purge()
        except Exception:
            log.exception("Janitor pass failed")
        time.sleep(interval)


if __name__ == "__main__":
    main()
