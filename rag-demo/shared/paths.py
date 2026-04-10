from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
INPUTS_DIR = DATA_DIR / "inputs"
OUTPUTS_DIR = DATA_DIR / "outputs"

UNSTRUCTURED_DIR = INPUTS_DIR / "unstructured_data"
GOLD_QUESTIONS_PATH = INPUTS_DIR / "gold_questions" / "gold_questions.jsonl"
QUERY_EVAL_PATH = DATA_DIR / "evals" / "query_eval.json"

STEP1_DIR = OUTPUTS_DIR / "01-extract-metadata"
STEP2_DIR = OUTPUTS_DIR / "02-build-vector-store"
STEP3_DIR = OUTPUTS_DIR / "03-query-rewrite-and-sparse-query"
STEP4_DIR = OUTPUTS_DIR / "04-semantic-retrieval"
STEP5_DIR = OUTPUTS_DIR / "05-sparse-keyword-retrieval"
STEP6_DIR = OUTPUTS_DIR / "06-rerank"
STEP7_DIR = OUTPUTS_DIR / "07-extract-quotes"
STEP8_DIR = OUTPUTS_DIR / "08-answer"
STEP9_DIR = OUTPUTS_DIR / "09-eval"

EXTRACTIONS_PATH = STEP1_DIR / "extractions.jsonl"
VECTOR_STORE_MANIFEST_PATH = STEP2_DIR / "vector_store_manifest.json"
