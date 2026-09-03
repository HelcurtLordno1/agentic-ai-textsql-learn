"""Run the gold-isolated PRACTIQ-inspired classification and clarification benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

from agentic_text2sql.adapters.llm.ollama_provider import OllamaProvider
from agentic_text2sql.contracts.planning import (
    AnswerabilityOutcome,
    ClarificationContext,
)
from agentic_text2sql.hardware import sample_resources
from agentic_text2sql.layer1_reasoning.question_analyst import (
    QUESTION_ANALYST_PROMPT_VERSION,
    QuestionAnalyst,
)
from agentic_text2sql.layer1_reasoning.question_normalizer import QuestionNormalizer
from agentic_text2sql.layer1_reasoning.question_reliability import QuestionReliabilityService
from agentic_text2sql.layer1_reasoning.router import QueryRouter
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.settings import Settings
from agentic_text2sql_eval.question_reliability import (
    ReliabilityJudgment,
    ReliabilityLabel,
    evaluate_reliability,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * quantile)))
    return ordered[position]


def checkpoint(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    temporary.replace(path)


def source_snapshot(root: Path, challenge: Path) -> dict[str, str]:
    files = (
        challenge,
        root / "configs/prompts/question_analyst_v1.j2",
        root / "datasets/olist/business_glossary.yaml",
        root / "src/agentic_text2sql/contracts/planning.py",
        root / "src/agentic_text2sql/layer1_reasoning/question_analyst.py",
        root / "src/agentic_text2sql/layer1_reasoning/question_normalizer.py",
        root / "src/agentic_text2sql/layer1_reasoning/question_reliability.py",
    )
    return {str(path.relative_to(root)): sha256(path) for path in files}


def expand_cases(path: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases: list[dict[str, str]] = []
    for family in payload["families"]:
        for index, question in enumerate(family["questions"], start=1):
            case = {
                "case_id": f"{family['id']}_{index:02d}",
                "family_id": str(family["id"]),
                "question": str(question),
                "expected": str(family["expected"]),
            }
            if family.get("clarification"):
                case["clarification"] = str(family["clarification"])
            cases.append(case)
    counts = {label: sum(case["expected"] == label for case in cases) for label in ReliabilityLabel}
    if len(cases) != 100 or counts != {
        ReliabilityLabel.ANSWER: 40,
        ReliabilityLabel.CLARIFY: 30,
        ReliabilityLabel.CANNOT_ANSWER: 30,
    }:
        raise ValueError(f"challenge distribution is invalid: n={len(cases)}, counts={counts}")
    return payload, cases


def mapped_outcome(outcome: AnswerabilityOutcome) -> ReliabilityLabel:
    if outcome is AnswerabilityOutcome.ANSWER:
        return ReliabilityLabel.ANSWER
    if outcome is AnswerabilityOutcome.CLARIFY:
        return ReliabilityLabel.CLARIFY
    return ReliabilityLabel.CANNOT_ANSWER


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--challenge", type=Path, default=Path("evals/configs/practiq-r1-challenge-families.yaml")
    )
    parser.add_argument(
        "--predictions", type=Path, default=Path("evals/predictions/practiq-r1-100-v5.jsonl")
    )
    parser.add_argument("--report", type=Path, default=Path("evals/reports/practiq-r1-100-v5.json"))
    parser.add_argument("--max-new-cases", type=int)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    settings = Settings()
    root = settings.project_root
    challenge = (root / args.challenge).resolve()
    predictions_path = (root / args.predictions).resolve()
    report_path = (root / args.report).resolve()
    provenance_path = predictions_path.with_suffix(".provenance.json")
    challenge_meta, cases = expand_cases(challenge)
    snapshot = source_snapshot(root, challenge)
    database = settings.resolved_data_dir / "processed/olist.sqlite"
    catalog = SQLiteIntrospector().inspect(database, "olist")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, timeout=5
    ).strip()
    records: list[dict[str, Any]] = []
    if not args.no_resume and predictions_path.is_file():
        records = [
            json.loads(line)
            for line in predictions_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if [record["case_id"] for record in records] != [
        case["case_id"] for case in cases[: len(records)]
    ]:
        raise SystemExit("prediction checkpoint is not a challenge prefix")

    with OllamaProvider(settings) as provider:
        models = provider.list_models()
        digest = next(
            str(model["digest"]) for model in models if model.get("name") == settings.ollama_model
        )
        provenance = {
            "evaluation_id": challenge_meta["evaluation_id"],
            "git_commit": commit,
            "tracked_worktree_clean": not bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain", "--untracked-files=no"],
                    cwd=root,
                    text=True,
                    timeout=5,
                ).strip()
            ),
            "source_snapshot": snapshot,
            "challenge_sha256": sha256(challenge),
            "database_sha256": sha256(database),
            "catalog_hash": catalog.catalog_hash,
            "model": settings.ollama_model,
            "model_digest": digest,
            "seed": settings.ollama_seed,
            "prompt_version": QUESTION_ANALYST_PROMPT_VERSION,
            "baseline": "legacy rule router mapped to three classes",
            "treatment": "rule-first plus one local schema-constrained analyst call",
            "oracle_evidence_used_by_runtime": False,
        }
        if provenance_path.is_file() and not args.no_resume:
            previous = json.loads(provenance_path.read_text(encoding="utf-8"))
            for key in ("source_snapshot", "model_digest", "catalog_hash", "challenge_sha256"):
                if previous.get(key) != provenance[key]:
                    raise SystemExit(f"resume provenance mismatch: {key}")
        provenance_path.parent.mkdir(parents=True, exist_ok=True)
        provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
        analyst = QuestionAnalyst(
            provider,
            root / "configs/prompts/question_analyst_v1.j2",
            root / "datasets/olist/business_glossary.yaml",
        )
        service = QuestionReliabilityService(QuestionNormalizer(), QueryRouter(), analyst)
        remaining = cases[len(records) :]
        if args.max_new_cases is not None:
            remaining = remaining[: args.max_new_cases]
        resource_start = sample_resources().__dict__
        for case in remaining:
            before = provider.telemetry.milliseconds()
            started = time.monotonic()
            normalized, decision = service.evaluate(case["question"], catalog)
            initial_ms = (time.monotonic() - started) * 1000
            resolved: bool | None = None
            follow_up_outcome: str | None = None
            if (
                case["expected"] == ReliabilityLabel.CLARIFY.value
                and decision.outcome is AnswerabilityOutcome.CLARIFY
            ):
                context = ClarificationContext(
                    parent_run_id=case["case_id"],
                    original_question=case["question"],
                    assistant_question=decision.clarification_question or "Clarify the request",
                    options=decision.clarification_options,
                    user_response=case["clarification"],
                )
                _, follow_up = service.evaluate(case["clarification"], catalog, context)
                follow_up_outcome = follow_up.outcome.value
                resolved = follow_up.outcome is AnswerabilityOutcome.ANSWER
            after = provider.telemetry.milliseconds()
            records.append(
                {
                    "case_id": case["case_id"],
                    "family_id": case["family_id"],
                    "question": case["question"],
                    "expected": case["expected"],
                    "baseline_predicted": (
                        "CLARIFY"
                        if QueryRouter().route(case["question"]).intent.value == "CLARIFY"
                        else "ANSWER"
                    ),
                    "treatment_predicted": mapped_outcome(decision.outcome).value,
                    "reason_code": decision.reason_code.value,
                    "source": decision.source,
                    "clarification_resolved": resolved,
                    "follow_up_outcome": follow_up_outcome,
                    "normalized": normalized.model_dump(mode="json"),
                    "initial_latency_ms": initial_ms,
                    "telemetry_delta": {key: after[key] - before.get(key, 0.0) for key in after},
                }
            )
            checkpoint(predictions_path, records)
            print(
                f"{len(records)}/100 {case['case_id']} expected={case['expected']} "
                f"predicted={decision.outcome.value}",
                flush=True,
            )
        resource_end = sample_resources().__dict__

    if len(records) != len(cases):
        print(json.dumps({"status": "checkpointed", "completed": len(records), "total": 100}))
        return
    treatment = evaluate_reliability(
        [
            ReliabilityJudgment(
                case_id=record["case_id"],
                expected=ReliabilityLabel(record["expected"]),
                predicted=ReliabilityLabel(record["treatment_predicted"]),
                clarification_resolved=record["clarification_resolved"],
            )
            for record in records
        ]
    )
    baseline = evaluate_reliability(
        [
            ReliabilityJudgment(
                case_id=record["case_id"],
                expected=ReliabilityLabel(record["expected"]),
                predicted=ReliabilityLabel(record["baseline_predicted"]),
            )
            for record in records
        ]
    )
    latencies = [float(record["initial_latency_ms"]) for record in records]
    prompt_tokens = sum(record["telemetry_delta"]["llm_prompt_tokens"] for record in records)
    output_tokens = sum(record["telemetry_delta"]["llm_output_tokens"] for record in records)
    report = {
        "provenance": provenance,
        "case_count": len(records),
        "distribution": {
            label.value: sum(record["expected"] == label.value for record in records)
            for label in ReliabilityLabel
        },
        "baseline": baseline.model_dump(mode="json"),
        "treatment": treatment.model_dump(mode="json"),
        "paired_delta": {
            "macro_f1": treatment.macro_f1 - baseline.macro_f1,
            "ambiguity_recall": treatment.ambiguity_recall - baseline.ambiguity_recall,
            "answerable_false_refusal": (
                treatment.answerable_false_refusal - baseline.answerable_false_refusal
            ),
        },
        "latency_ms": {
            "mean": statistics.fmean(latencies),
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
        },
        "token_usage": {"prompt": prompt_tokens, "output": output_tokens},
        "reason_code_counts": {
            code: sum(record["reason_code"] == code for record in records)
            for code in sorted({record["reason_code"] for record in records})
        },
        "resource_start": resource_start,
        "resource_end": resource_end,
        "prediction_sha256": sha256(predictions_path),
        "limitations": [
            "Project-authored paired-family pilot; not the PRACTIQ dataset or leaderboard.",
            "Labels have one reviewer; independent second review remains required for promotion.",
            "Schema/FK metadata only; database-value absence is outside this R1 treatment.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
