import shutil
from pathlib import Path

import pytest
import yaml

from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer4_validation.executor import ReadOnlySQLiteExecutor
from agentic_text2sql.layer4_validation.policy import SQLSafetyPolicy

ROOT = Path(__file__).resolve().parents[2]
OLIST = ROOT / "data/processed/olist.sqlite"


@pytest.mark.olist
@pytest.mark.skipif(not OLIST.is_file(), reason="canonical Olist database is not built")
def test_ten_canonical_queries_match_expected_results(tmp_path: Path) -> None:
    database = tmp_path / "olist.sqlite"
    shutil.copyfile(OLIST, database)
    catalog = SQLiteIntrospector().inspect(database, "olist")
    policy = SQLSafetyPolicy(default_limit=200)
    executor = ReadOnlySQLiteExecutor(timeout_seconds=10, max_rows=200)
    payload = yaml.safe_load(
        (ROOT / "tests/golden/olist/p1_canonical_queries.yaml").read_text(encoding="utf-8")
    )

    for case in payload["queries"]:
        decision = policy.evaluate(case["sql"], catalog)
        assert decision.allowed, (case["id"], decision.safe_message)
        assert decision.normalized_sql
        result = executor.execute(database, decision.normalized_sql)
        assert result.rows == case["expected"], case["id"]
