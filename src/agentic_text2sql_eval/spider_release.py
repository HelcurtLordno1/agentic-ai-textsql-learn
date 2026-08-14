"""Pinned full Spider-dev manifest and gold-separated execution evaluation."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlglot import exp, parse_one

from agentic_text2sql.adapters.sqlite_text import decode_sqlite_text
from agentic_text2sql.contracts.sql import DirectStatus
from agentic_text2sql_eval.inference_runner import SmokePrediction
from agentic_text2sql_eval.report import _percentile
from agentic_text2sql_eval.spider_adapter import case_hash, classify_complexity


class SpiderReleaseCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str = Field(pattern=r"^spider_dev_\d{4}$")
    dev_index: int = Field(ge=0)
    db_id: str
    case_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    complexity: Literal["easy", "medium", "hard", "extra"]


class SpiderReleaseManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: int = 1
    dataset: str = "spider-dev"
    selection: str = "full dev reordered by database then original row"
    dev_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tables_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    database_sha256: dict[str, str]
    case_count: int = Field(ge=1)
    database_count: int = Field(ge=1)
    cases: tuple[SpiderReleaseCase, ...]


class LoadedSpiderCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    dev_index: int
    db_id: str
    question: str
    gold_sql: str
    complexity: Literal["easy", "medium", "hard", "extra"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_release_manifest(spider_root: Path) -> SpiderReleaseManifest:
    dev_path = spider_root / "dev.json"
    tables_path = spider_root / "tables.json"
    dev: list[dict[str, Any]] = json.loads(dev_path.read_text(encoding="utf-8"))
    ordered = sorted(enumerate(dev), key=lambda item: (str(item[1]["db_id"]), item[0]))
    cases = tuple(
        SpiderReleaseCase(
            id=f"spider_dev_{index:04d}",
            dev_index=index,
            db_id=str(case["db_id"]),
            case_hash=case_hash(case),
            complexity=classify_complexity(str(case["query"])),
        )
        for index, case in ordered
    )
    db_ids = sorted({case.db_id for case in cases})
    database_hashes = {
        db_id: sha256_file(spider_root / "database" / db_id / f"{db_id}.sqlite") for db_id in db_ids
    }
    return SpiderReleaseManifest(
        dev_sha256=sha256_file(dev_path),
        tables_sha256=sha256_file(tables_path),
        database_sha256=database_hashes,
        case_count=len(cases),
        database_count=len(db_ids),
        cases=cases,
    )


def load_release_cases(
    spider_root: Path, manifest_path: Path
) -> tuple[SpiderReleaseManifest, list[LoadedSpiderCase]]:
    manifest = SpiderReleaseManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    selected_db_ids = {case.db_id for case in manifest.cases}
    if set(manifest.database_sha256) != selected_db_ids:
        raise ValueError("Spider release database hashes do not match selected databases")
    if manifest.database_count != len(selected_db_ids):
        raise ValueError("Spider release database count does not match selected databases")
    if manifest.case_count != len(manifest.cases):
        raise ValueError("Spider release case count does not match selected cases")
    if len({case.id for case in manifest.cases}) != len(manifest.cases):
        raise ValueError("Spider release manifest contains duplicate case IDs")
    if sha256_file(spider_root / "dev.json") != manifest.dev_sha256:
        raise ValueError("Spider dev checksum does not match release manifest")
    if sha256_file(spider_root / "tables.json") != manifest.tables_sha256:
        raise ValueError("Spider tables checksum does not match release manifest")
    for db_id, expected in manifest.database_sha256.items():
        database = spider_root / "database" / db_id / f"{db_id}.sqlite"
        if sha256_file(database) != expected:
            raise ValueError(f"Spider database checksum mismatch: {db_id}")
    dev: list[dict[str, Any]] = json.loads((spider_root / "dev.json").read_text(encoding="utf-8"))
    loaded: list[LoadedSpiderCase] = []
    for selected in manifest.cases:
        if selected.dev_index >= len(dev):
            raise ValueError(f"Spider release dev index is out of range: {selected.dev_index}")
        case = dev[selected.dev_index]
        if str(case["db_id"]) != selected.db_id or case_hash(case) != selected.case_hash:
            raise ValueError(f"Spider release mismatch at dev row {selected.dev_index}")
        loaded.append(
            LoadedSpiderCase(
                id=selected.id,
                dev_index=selected.dev_index,
                db_id=selected.db_id,
                question=str(case["question"]),
                gold_sql=str(case["query"]),
                complexity=selected.complexity,
            )
        )
    if len(loaded) != manifest.case_count or len({case.id for case in loaded}) != len(loaded):
        raise ValueError("Spider release manifest contains duplicate or missing cases")
    return manifest, loaded


def _execute(
    connection: sqlite3.Connection,
    sql: str,
    timeout_seconds: float,
    *,
    max_rows: int = 100_000,
) -> list[list[Any]]:
    deadline = time.monotonic() + timeout_seconds

    def progress() -> int:
        return int(time.monotonic() >= deadline)

    connection.set_progress_handler(progress, 1_000)
    try:
        rows = connection.execute(sql).fetchmany(max_rows + 1)
        if len(rows) > max_rows:
            raise sqlite3.DataError(f"evaluation row limit exceeded: {max_rows}")
        return [list(row) for row in rows]
    finally:
        connection.set_progress_handler(None, 0)


def _value_key(value: Any) -> tuple[str, Any]:
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            return ("number", str(value))
        return ("number", round(float(value), 6))
    return (type(value).__name__, value)


def _rows_key(rows: list[list[Any]], *, ordered: bool) -> list[tuple[tuple[str, Any], ...]]:
    keyed = [tuple(_value_key(value) for value in row) for row in rows]
    return keyed if ordered else sorted(keyed, key=repr)


def execution_equal(candidate: list[list[Any]], gold: list[list[Any]], *, ordered: bool) -> bool:
    if len(candidate) != len(gold):
        return False
    if not candidate and not gold:
        return True
    candidate_width = len(candidate[0]) if candidate else 0
    gold_width = len(gold[0]) if gold else 0
    if candidate_width != gold_width:
        return False
    gold_key = _rows_key(gold, ordered=ordered)
    if _rows_key(candidate, ordered=ordered) == gold_key:
        return True
    if candidate_width > 8:
        return False
    for permutation in itertools.permutations(range(candidate_width)):
        permuted = [[row[index] for index in permutation] for row in candidate]
        if _rows_key(permuted, ordered=ordered) == gold_key:
            return True
    return False


def _has_order(sql: str) -> bool:
    try:
        statement = parse_one(sql, read="sqlite")
    except Exception:
        return False
    return statement.find(exp.Order) is not None


def _failure_category(status: str, error_class: str | None, executed: bool) -> str:
    if status != DirectStatus.SUCCEEDED.value:
        return error_class or status
    return "EXECUTION_MISMATCH" if executed else "EVALUATOR_EXECUTION_ERROR"


def evaluate_spider_release(
    *,
    spider_root: Path,
    manifest: SpiderReleaseManifest,
    cases: list[LoadedSpiderCase],
    predictions: list[SmokePrediction],
    report_path: Path,
    provenance: dict[str, Any],
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Open gold only after inference and evaluate result equivalence on read-only databases."""
    by_id = {prediction.case_id: prediction for prediction in predictions}
    if len(predictions) != len(cases) or set(by_id) != {case.id for case in cases}:
        raise ValueError("Predictions must match the complete Spider release manifest")
    details: list[dict[str, Any]] = []
    connections: dict[str, sqlite3.Connection] = {}
    try:
        for case in cases:
            connection = connections.get(case.db_id)
            if connection is None:
                database = spider_root / "database" / case.db_id / f"{case.db_id}.sqlite"
                connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
                connection.text_factory = decode_sqlite_text
                connection.execute("PRAGMA query_only=ON")
                connections[case.db_id] = connection
            result = by_id[case.id].result
            generated_sql = (
                result.candidate.normalized_sql if result.candidate is not None else None
            )
            executed = False
            correct = False
            gold_rows = _execute(connection, case.gold_sql, timeout_seconds)
            if generated_sql is not None and result.status is DirectStatus.SUCCEEDED:
                try:
                    candidate_rows = _execute(connection, generated_sql, timeout_seconds)
                    executed = True
                    correct = execution_equal(
                        candidate_rows, gold_rows, ordered=_has_order(case.gold_sql)
                    )
                except sqlite3.Error:
                    pass
            details.append(
                {
                    "id": case.id,
                    "dev_index": case.dev_index,
                    "db_id": case.db_id,
                    "complexity": case.complexity,
                    "status": result.status.value,
                    "result_correct": correct,
                    "generated_sql": generated_sql,
                    "expected_result_hash": hashlib.sha256(repr(gold_rows).encode()).hexdigest(),
                    "error_class": result.error_class,
                    "failure_category": (
                        None
                        if correct
                        else _failure_category(result.status.value, result.error_class, executed)
                    ),
                    "latency_ms": result.latency_ms,
                    "correction": result.correction,
                }
            )
    finally:
        for connection in connections.values():
            connection.close()

    def slices(field: str) -> dict[str, dict[str, float | int]]:
        output: dict[str, dict[str, float | int]] = {}
        for value in sorted({str(item[field]) for item in details}):
            selected = [item for item in details if str(item[field]) == value]
            correct = sum(bool(item["result_correct"]) for item in selected)
            output[value] = {
                "count": len(selected),
                "correct": correct,
                "accuracy": correct / len(selected),
            }
        return output

    correct_count = sum(bool(item["result_correct"]) for item in details)
    latency = [float(item["latency_ms"].get("total", 0)) for item in details]
    categories = Counter(
        str(item["failure_category"]) for item in details if item["failure_category"] is not None
    )
    report: dict[str, Any] = {
        "evaluation_id": "spider-dev-1034-p6-v1",
        "benchmark_kind": "cross-domain-execution",
        "release_status": "complete",
        "case_count": len(details),
        "database_count": manifest.database_count,
        "typed_terminal_count": len(details),
        "workflow_completion_rate": 1.0,
        "result_correct_count": correct_count,
        "result_accuracy": correct_count / len(details),
        "valid_candidate_count": sum(item["generated_sql"] is not None for item in details),
        "latency_ms": {
            "p50": _percentile(latency, 0.5),
            "p95": _percentile(latency, 0.95),
        },
        "by_complexity": slices("complexity"),
        "by_database": slices("db_id"),
        "failure_categories": dict(categories.most_common()),
        "manifest": manifest.model_dump(mode="json", exclude={"cases"}),
        "provenance": provenance,
        "limitations": [
            "Execution equivalence is reported separately from Olist application fitness.",
            "Column permutations up to width eight and unordered row multisets are normalized.",
            "This local evaluator is not the official hidden Spider test-set leaderboard.",
        ],
        "details": details,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_suffix(f"{report_path.suffix}.tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(report_path)
    return report
