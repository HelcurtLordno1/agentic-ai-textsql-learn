"""Replay saved V4 contexts/policy without an LLM; never regenerate predictions."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from agentic_text2sql.adapters.sqlite_text import decode_sqlite_text
from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.retrieval import SchemaContext
from agentic_text2sql.contracts.validation import PolicyDecision
from agentic_text2sql.layer3_generation.a1_prompt import (
    build_a1_prompt,
    build_evidence,
    complete_empty_relation_context,
    enforce_prompt_budget,
)
from agentic_text2sql.layer4_validation.policy import SQLSafetyPolicy
from agentic_text2sql_eval.runtime_checkpoint import atomic_json, file_sha256
from agentic_text2sql_eval.spider_release import (
    _execute,
    _has_order,
    execution_equal,
    load_release_cases,
)

ROOT = Path(__file__).resolve().parents[1]


def audit(baseline: str, output: Path) -> dict[str, Any]:
    catalogs: dict[str, CatalogSnapshot] = {}
    counts: Counter[str] = Counter()
    details: list[dict[str, Any]] = []
    recovered: list[dict[str, Any]] = []
    newly_allowed: list[dict[str, Any]] = []
    preserved_large_results: list[dict[str, Any]] = []
    seen_new: set[tuple[str, str | None]] = set()
    spider_gold: dict[str, str] = {}
    inputs = [
        ROOT / f"evals/{kind}/{baseline}-{suite}.{suffix}"
        for kind, suffix in (("reports", "json"), ("predictions", "jsonl"))
        for suite in ("spider", "olist")
    ]
    # Stop artifacts are read-only evidence too, including all previous failed profiles.
    inputs.extend(sorted((ROOT / "evals/reports").glob("*.resource-stop.json")))
    inputs.extend(sorted((ROOT / "data/artifacts/experiments").glob("*/server.resource-stop.json")))
    hashes = {str(p.relative_to(ROOT)): file_sha256(p) for p in inputs}

    def catalog(db_id: str) -> CatalogSnapshot:
        if db_id not in catalogs:
            index = ROOT / "data/indexes/p3_1_semantic" / db_id
            version = json.loads((index / "active.json").read_text())["version_id"]
            catalogs[db_id] = CatalogSnapshot.model_validate_json(
                (index / "versions" / version / "catalog.json").read_text()
            )
        return catalogs[db_id]

    for suite in ("spider", "olist"):
        predictions = ROOT / f"evals/predictions/{baseline}-{suite}.jsonl"
        report = json.loads((ROOT / f"evals/reports/{baseline}-{suite}.json").read_text())
        labels = {d["id"]: d for d in report["details"]}
        for line in predictions.read_text().splitlines():
            row = json.loads(line)
            case_id, result = row["case_id"], row["result"]
            counts["cases"] += 1
            counts["prior_correct"] += bool(labels[case_id]["result_correct"])
            if not result["schema_context"]:
                counts["no_context"] += 1
                continue
            ctx = SchemaContext.model_validate(result["schema_context"])
            cat = catalog(ctx.db_id)
            domain = (
                (ROOT / "datasets/olist/business_glossary.yaml").read_text()
                if cat.db_id == "olist"
                else ""
            )
            original = None
            try:
                original = build_a1_prompt(build_evidence(result["question"], cat, ctx, domain))
            except ValueError as exc:
                if str(exc) != "Selected relation has no grounded columns":
                    raise
            fixed = complete_empty_relation_context(cat, ctx)
            prompt = build_a1_prompt(build_evidence(result["question"], cat, fixed, domain))
            record = {
                "suite": suite,
                "id": case_id,
                "estimated_prompt_tokens": enforce_prompt_budget(prompt, 2800),
                "estimated_schema_tokens": fixed.estimated_tokens,
            }
            if original is not None:
                expected = result["assessment"]["prompts"]["draft"]["sha256"]
                if (
                    fixed is not ctx
                    or prompt != original
                    or hashlib.sha256(prompt.encode()).hexdigest() != expected
                ):
                    raise ValueError(f"Previously working prompt changed: {case_id}")
                counts["byte_identical_prompts"] += 1
            else:
                counts["recovered_prompts"] += 1
                recovered.append(record)
            details.append(record)

            for evaluation in result["assessment"].get("evaluations", []):
                candidate = evaluation.get("candidate")
                sql = candidate["normalized_sql"] if candidate else evaluation["raw_sql"]
                before = SQLSafetyPolicy().evaluate(sql, cat)
                after = SQLSafetyPolicy(resolve_derived_columns=True).evaluate(sql, cat)
                if before != PolicyDecision.model_validate(evaluation["policy"]):
                    raise ValueError(f"Control policy no longer matches V4 artifact: {case_id}")
                counts["policy_evaluations"] += 1
                if before.allowed:
                    if before != after:
                        raise ValueError(f"Previously accepted SQL/policy mutated: {case_id}")
                    counts["unchanged_allowed_policy"] += 1
                if not before.allowed and after.allowed:
                    counts["newly_allowed_evaluations"] += 1
                    key = (case_id, after.normalized_sql)
                    if key in seen_new:
                        continue
                    seen_new.add(key)
                    newly_allowed.append(
                        {"id": case_id, "suite": suite, "sql": after.normalized_sql}
                    )
                # Full-result check where preview was truncated, plus every newly allowed SQL.
                if (not before.allowed and after.allowed) or (
                    labels[case_id]["result_correct"]
                    and result["assessment"].get("result_truncated")
                ):
                    db = (
                        ROOT / "data/processed/olist.sqlite"
                        if suite == "olist"
                        else ROOT
                        / f"data/raw/spider/spider_data/database/{cat.db_id}/{cat.db_id}.sqlite"
                    )
                    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as connection:
                        connection.text_factory = decode_sqlite_text
                        connection.execute("PRAGMA query_only=ON")
                        rows = _execute(connection, after.normalized_sql or sql, 10)
                        expected_hash = labels[case_id]["expected_result_hash"]
                        same = hashlib.sha256(repr(rows).encode()).hexdigest() == expected_hash
                        if before.allowed:
                            if rows != _execute(connection, before.normalized_sql or sql, 10):
                                raise ValueError(f"Full result changed: {case_id}")
                            preserved_large_results.append({"id": case_id, "rows": len(rows)})
                        else:
                            if suite == "spider":
                                if not spider_gold:
                                    _, cases = load_release_cases(
                                        ROOT / "data/raw/spider/spider_data",
                                        ROOT / "evals/configs/spider-laptop-200.json",
                                    )
                                    spider_gold = {case.id: case.gold_sql for case in cases}
                                gold_sql = spider_gold[case_id]
                                gold = _execute(connection, gold_sql, 10)
                                if hashlib.sha256(repr(gold).encode()).hexdigest() != expected_hash:
                                    raise ValueError("Frozen gold result changed")
                                same = execution_equal(rows, gold, ordered=_has_order(gold_sql))
                            newly_allowed[-1].update(rows=len(rows), local_result_equivalent=same)
    for relative, digest in hashes.items():
        if file_sha256(ROOT / relative) != digest:
            raise ValueError(f"Input evidence changed: {relative}")
    summary = {
        "baseline": baseline,
        "counts": dict(counts),
        "maximum_prompt_tokens": max(d["estimated_prompt_tokens"] for d in details),
        "recovered": recovered,
        "newly_allowed": newly_allowed,
        "preserved_large_results": preserved_large_results,
        "input_hashes": hashes,
        "model_requests": 0,
        "claim": "Mechanical replay only; no new end-to-end model accuracy measured",
    }
    atomic_json(output, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="a1-startupfix450-20261007")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data/artifacts/v4-reliability-20261016/offline-replay.json",
    )
    args = parser.parse_args()
    summary = audit(args.baseline, args.output)
    print(
        json.dumps(
            {k: summary[k] for k in ("counts", "maximum_prompt_tokens", "model_requests")}, indent=2
        )
    )
    print(f"Evidence: {args.output}")


if __name__ == "__main__":
    main()
