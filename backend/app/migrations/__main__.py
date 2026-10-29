"""Database migrations.

python -m app.migrations upgrade              # apply pending migrations (the app also does this on start)
python -m app.migrations new "add widgets"    # autogenerate a migration from model changes
"""

import sys

from alembic import command

from app.config import get_settings
from app.infra.db import Database, alembic_config


def main(argv: list[str]) -> None:
    db = Database(get_settings().database_url)
    if argv[:1] == ["upgrade"]:
        db.migrate()
    elif argv[:1] == ["new"] and len(argv) == 2:
        db.migrate()  # autogenerate diffs against an up-to-date schema
        with db.engine.begin() as connection:
            command.revision(alembic_config(connection), message=argv[1], autogenerate=True)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
