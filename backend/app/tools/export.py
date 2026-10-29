"""Print the tool catalog as JSON for the web app.

Usage: python -m app.tools.export > ../frontend/src/lib/tools.generated.json
"""

import json

from app.tools.base import CATEGORY_LABELS
from app.tools.registry import default_registry


def catalog() -> dict:
    return {
        "categories": [{"id": k.value, "name": v} for k, v in CATEGORY_LABELS.items()],
        "tools": [tool.describe() for tool in default_registry().all()],
    }


if __name__ == "__main__":
    print(json.dumps(catalog(), indent=1, ensure_ascii=False))
