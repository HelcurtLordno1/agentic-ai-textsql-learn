import json
from pathlib import Path

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.sql import DirectRunResult, DirectStatus
from agentic_text2sql_eval.inference_runner import SmokeCase, run_inference


class GoldBlindService:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def run(self, question: str, database: Path, catalog: CatalogSnapshot) -> DirectRunResult:
        del database, catalog
        self.questions.append(question)
        return DirectRunResult(
            run_id="test-run",
            question=question,
            status=DirectStatus.SUCCEEDED,
            route_reason="test",
            prompt_versions={"planner": "v1", "generator": "v1"},
            result_columns=["value"],
            result_rows=[[1]],
        )


def test_inference_receives_only_question_and_prediction_contains_no_gold(tmp_path: Path) -> None:
    case = SmokeCase(
        id="secret-case",
        language="en",
        question="Return one",
        expected_status=DirectStatus.SUCCEEDED,
        gold_sql="SELECT 987654321 AS secret_gold",
    )
    service = GoldBlindService()
    path = tmp_path / "predictions.jsonl"
    run_inference(
        cases=[case],
        service=service,  # type: ignore[arg-type]
        database=tmp_path / "unused.sqlite",
        catalog=CatalogSnapshot(db_id="test", tables=(), catalog_hash="a" * 64),
        prediction_path=path,
    )
    serialized = path.read_text(encoding="utf-8")
    assert service.questions == ["Return one"]
    assert "987654321" not in serialized
    assert "gold_sql" not in serialized
    assert json.loads(serialized)["case_id"] == "secret-case"
