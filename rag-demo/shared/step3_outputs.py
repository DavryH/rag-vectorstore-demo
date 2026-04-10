import json
from pathlib import Path
from typing import Any

from shared.paths import STEP3_DIR

QUERY_PLANS_FILENAME = "query-plans.json"


def find_query_plan(query_id: str) -> dict[str, Any]:
    query_plans_path = STEP3_DIR / QUERY_PLANS_FILENAME
    if not query_plans_path.exists():
        raise FileNotFoundError(f"Step 03 output not found: {query_plans_path}")

    query_plans = json.loads(query_plans_path.read_text(encoding="utf-8"))
    if not isinstance(query_plans, list):
        raise RuntimeError("Step 03 query-plans.json must be a JSON array.")

    for query_plan in query_plans:
        if isinstance(query_plan, dict) and query_plan.get("query_id") == query_id:
            return query_plan

    raise ValueError(f"Query id not found in Step 03 query plans: {query_id}")
