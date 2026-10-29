"""Replay saved model outputs through control/candidate; no Ollama/network calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from agentic_text2sql.adapters.sqlite_text import decode_sqlite_text
from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.retrieval import SchemaContext
from agentic_text2sql.contracts.sql import DirectStatus, SqlCandidate
from agentic_text2sql.layer2_grounding.service import GroundingService
from agentic_text2sql.layer6_application.a1_service import A1QueryService
from agentic_text2sql.settings import Settings
from agentic_text2sql_eval.olist_acceptance import _rows_equal, load_olist_acceptance
from agentic_text2sql_eval.runtime_checkpoint import atomic_json, file_sha256
from agentic_text2sql_eval.spider_release import (
    _execute,
    _has_order,
    execution_equal,
    load_release_cases,
)

ROOT = Path(__file__).resolve().parents[1]
Response = TypeVar("Response", bound=BaseModel)


class SavedProvider:
    def __init__(self, evaluations: list[dict[str, Any]]) -> None:
        self.outputs = [
            SqlCandidate(sql=evaluation["raw_sql"], confidence=0)
            for evaluation in evaluations
            if evaluation.get("origin", "model") == "model"
        ]

    def generate_structured(
        self, *, prompt: str, response_model: type[Response], model: str | None = None
    ) -> Response:
        del prompt, model
        if not self.outputs:
            raise ValueError("Replay cannot invent a new model response")
        return response_model.model_validate(self.outputs.pop(0).model_dump())


class SavedGrounding(GroundingService):
    def __init__(self, context: SchemaContext) -> None:
        self.context = context
        self.token_budget = 1200

    def ground(self, question: str, plan: LogicalPlan) -> SchemaContext:
        del question, plan
        return self.context.model_copy(deep=True)


def audit(baseline: str, output: Path) -> dict[str, Any]:
    lock = json.loads((ROOT / "data/artifacts/v5-upgrade-20261024/baseline-lock.json").read_text())
    for relative, digest in lock["hashes"].items():
        if file_sha256(ROOT / relative) != digest:
            raise ValueError(f"Historical evidence changed: {relative}")
    _, spider_cases = load_release_cases(
        ROOT / "data/raw/spider/spider_data", ROOT / "evals/configs/spider-laptop-200.json"
    )
    olist_cases = load_olist_acceptance(ROOT / "evals/configs/olist-acceptance-60.jsonl")
    catalogs: dict[str, CatalogSnapshot] = {}
    summary: dict[str, Any] = {"baseline": baseline, "model_inference_requests": 0}
    with tempfile.TemporaryDirectory(prefix="v5-contract-replay-") as temporary:
        native_olist = Path(temporary) / "olist.sqlite"
        original_olist = ROOT / "data/processed/olist.sqlite"
        shutil.copyfile(original_olist, native_olist)
        if file_sha256(native_olist) != file_sha256(original_olist):
            raise ValueError("Offline database copy differs")
        for suite, cases in (("spider", spider_cases), ("olist", olist_cases)):
            labels = {
                item["id"]: item
                for item in json.loads(
                    (ROOT / f"evals/reports/{baseline}-{suite}.json").read_text()
                )["details"]
            }
            rows = {
                item["case_id"]: item["result"]
                for line in (ROOT / f"evals/predictions/{baseline}-{suite}.jsonl")
                .read_text()
                .splitlines()
                if (item := json.loads(line))
            }
            if set(labels) != set(rows) or set(rows) != {case.id for case in cases}:
                raise ValueError("Replay must cover the complete frozen suite")
            details = []
            for case in cases:
                old = rows[case.id]
                context = (
                    SchemaContext.model_validate(old["schema_context"])
                    if old["schema_context"]
                    else None
                )
                db_id = context.db_id if context else getattr(case, "db_id", "olist")
                if db_id not in catalogs:
                    index = ROOT / "data/indexes/p3_1_semantic" / db_id
                    version = json.loads((index / "active.json").read_text())["version_id"]
                    catalogs[db_id] = CatalogSnapshot.model_validate_json(
                        (index / "versions" / version / "catalog.json").read_text()
                    )
                database = (
                    native_olist
                    if suite == "olist"
                    else ROOT / f"data/raw/spider/spider_data/database/{db_id}/{db_id}.sqlite"
                )
                connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
                connection.text_factory = decode_sqlite_text
                connection.execute("PRAGMA query_only=ON")
                try:
                    gold = _execute(connection, case.gold_sql, 10)
                    if (
                        hashlib.sha256(repr(gold).encode()).hexdigest()
                        != labels[case.id]["expected_result_hash"]
                    ):
                        raise ValueError(f"Frozen expected result differs: {case.id}")
                    record: dict[str, Any] = {
                        "id": case.id,
                        "prior_correct": labels[case.id]["result_correct"],
                    }
                    for variant, enabled in (("control", False), ("candidate", True)):
                        settings = Settings(
                            _env_file=None,
                            TEXT2SQL_PIPELINE_MODE="a1",
                            TEXT2SQL_CRITIC_MODE="repair",
                            TEXT2SQL_COMPUTE_POLICY="obligation",
                            TEXT2SQL_DETERMINISTIC_REPAIR=True,
                            TEXT2SQL_RECOVER_EMPTY_RELATIONS=True,
                            TEXT2SQL_RESOLVE_DERIVED_COLUMNS=True,
                            TEXT2SQL_BOUNDED_OUTPUT_CONTRACTS=enabled,
                            TEXT2SQL_OWNER_REPAIR_FEEDBACK=enabled,
                            TEXT2SQL_OLLAMA_NUM_GPU=0,
                            TEXT2SQL_RUN_DEADLINE_SECONDS=900,
                            TEXT2SQL_REQUEST_TIMEOUT_SECONDS=300,
                        )
                        provider = SavedProvider(old["assessment"].get("evaluations", []))
                        service = A1QueryService(
                            provider,
                            settings,
                            grounding=SavedGrounding(context) if context else None,
                            correction_enabled=True,
                        )
                        result = service.run(old["question"], database, catalogs[db_id])
                        assessment = result.assessment or {}
                        correct = False
                        full_count = None
                        if result.status is DirectStatus.SUCCEEDED:
                            if suite == "spider":
                                actual = _execute(connection, assessment["executed_sql"], 10)
                                full_count = len(actual)
                                correct = execution_equal(
                                    actual, gold, ordered=_has_order(case.gold_sql)
                                )
                            else:
                                correct = _rows_equal(
                                    result.result_rows,
                                    gold,
                                    order_matters=case.result_order_matters,
                                    tolerance=case.tolerance,
                                )
                        if variant == "control" and correct != record["prior_correct"]:
                            raise ValueError(f"Control does not reproduce saved label: {case.id}")
                        draft = assessment.get("prompts", {}).get("draft")
                        old_draft = old["assessment"].get("prompts", {}).get("draft")
                        if bool(draft) != bool(old_draft) or (
                            draft and draft["sha256"] != old_draft["sha256"]
                        ):
                            raise ValueError(f"Draft prompt changed: {case.id}")
                        record[variant] = {
                            "correct": correct,
                            "status": result.status.value,
                            "sql": result.candidate.normalized_sql if result.candidate else None,
                            "repair_admitted": assessment.get("repair_admitted", False),
                            "contract": assessment.get("repair_contract"),
                            "full_rows": full_count,
                        }
                    details.append(record)
                finally:
                    connection.close()
            gains = [
                d["id"] for d in details if d["candidate"]["correct"] and not d["prior_correct"]
            ]
            losses = [
                d["id"] for d in details if not d["candidate"]["correct"] and d["prior_correct"]
            ]
            summary[suite] = {
                "n": len(details),
                "baseline_correct": sum(d["prior_correct"] for d in details),
                "candidate_correct": sum(d["candidate"]["correct"] for d in details),
                "gains": gains,
                "losses": losses,
                "changed_sql": [
                    d["id"] for d in details if d["control"]["sql"] != d["candidate"]["sql"]
                ],
                "draft_prompts_preserved": sum(
                    bool(row["assessment"].get("prompts", {}).get("draft")) for row in rows.values()
                ),
                "cases_with_unchanged_draft_state": len(rows),
                "details": details,
            }
            print(
                json.dumps(
                    {
                        suite: {
                            key: value for key, value in summary[suite].items() if key != "details"
                        }
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    for relative, digest in lock["hashes"].items():
        if file_sha256(ROOT / relative) != digest:
            raise ValueError(f"Historical evidence changed during replay: {relative}")
    summary["historical_hashes_preserved"] = len(lock["hashes"])
    summary["claim"] = "Saved-model-output replay, not fresh LLM benchmark accuracy"
    atomic_json(output, summary)
    if any(summary[suite]["losses"] for suite in ("spider", "olist")):
        raise ValueError("Prior-correct loss blocks the next gate; inspect saved replay")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="v4-cpu600-stream-20261016")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/artifacts/v5-upgrade-20261024/replay.json"
    )
    args = parser.parse_args()
    audit(args.baseline, args.output)


if __name__ == "__main__":
    main()
