import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUERY_EVAL_PATH = PROJECT_ROOT / "data" / "evals" / "query_eval.json"

STEP3_COMMAND = ["steps/03-query-rewrite-and-sparse-query/run_step_03_query_rewrite_and_sparse_query.py", "--all-queries"]
STEP4_COMMAND = ["steps/04-semantic-retrieval/run_step_04_semantic_retrieval.py"]
FINAL_STEP_COMMANDS = [
    ["steps/05-sparse-keyword-retrieval/run_step_05_sparse_keyword_retrieval.py"],
    ["steps/06-rerank/run_step_06_rerank.py"],
    ["steps/07-extract-quotes/run_step_07_extract_quotes.py", "--all-queries"],
    ["steps/08-answer/run_step_08_answer.py", "--all-queries"],
    ["steps/09-eval/run_step_09_eval.py"],
]


def load_query_ids() -> list[str]:
    rows = json.loads(QUERY_EVAL_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError("query_eval.json must contain a JSON array of query rows.")
    return [str(row.get("id", "")).strip() for row in rows if isinstance(row, dict) and str(row.get("id", "")).strip()]


def run_command(command: list[str]) -> None:
    print(f"\n==> Running: python {' '.join(command)}")
    subprocess.run([sys.executable, *command], cwd=PROJECT_ROOT, check=True)


def main() -> int:
    run_command(STEP3_COMMAND)

    for query_id in load_query_ids():
        run_command([*STEP4_COMMAND, "--query-id", query_id])

    for command in FINAL_STEP_COMMANDS:
        run_command(command)

    print("\nQuery processing, answering, and eval completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
