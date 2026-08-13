"""Bounded correction orchestration; every candidate re-enters the full Layer 4 gate."""

from __future__ import annotations

import time
from pathlib import Path

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.correction import (
    AttemptSummary,
    CorrectionOutcome,
    StopReason,
)
from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.retrieval import SchemaContext
from agentic_text2sql.contracts.sql import CandidateRecord
from agentic_text2sql.contracts.validation import ResultPreview, ValidationReport
from agentic_text2sql.exceptions import StructuredOutputError, Text2SQLError
from agentic_text2sql.layer4_validation.parser import SQLParseError
from agentic_text2sql.layer4_validation.service import ValidationService
from agentic_text2sql.layer5_correction.correction_planner import build_correction_plan
from agentic_text2sql.layer5_correction.corrector import CorrectorAgent
from agentic_text2sql.layer5_correction.loop_controller import LoopController, error_fingerprint


class CorrectionService:
    def __init__(
        self,
        *,
        corrector: CorrectorAgent,
        validation: ValidationService,
        max_repairs: int = 1,
        max_llm_calls: int = 1,
        min_remaining_seconds: float = 1.0,
    ) -> None:
        self.corrector = corrector
        self.validation = validation
        self.max_repairs = max_repairs
        self.max_llm_calls = max_llm_calls
        self.min_remaining_seconds = min_remaining_seconds

    def run(
        self,
        *,
        question: str,
        plan: LogicalPlan,
        catalog: CatalogSnapshot,
        database: Path,
        failed_candidate: CandidateRecord,
        initial_report: ValidationReport,
        schema_context: SchemaContext | None = None,
        deadline: float | None = None,
    ) -> tuple[CorrectionOutcome, CandidateRecord, ValidationReport, ResultPreview | None]:
        plan_for_repair = build_correction_plan(initial_report)
        if not plan_for_repair.should_retry:
            return (
                CorrectionOutcome(
                    attempted=False,
                    recovered=False,
                    stop_reason=StopReason.NOT_ELIGIBLE,
                    repairs=0,
                    llm_calls=0,
                    trigger_error_class=initial_report.error_class,
                ),
                failed_candidate,
                initial_report,
                None,
            )

        controller = LoopController(
            max_repairs=self.max_repairs,
            max_llm_calls=self.max_llm_calls,
            deadline=deadline,
            min_remaining_seconds=self.min_remaining_seconds,
        )
        attempts: list[AttemptSummary] = []
        seen_sql = {failed_candidate.fingerprint}
        seen_errors = {error_fingerprint(initial_report)}
        current = failed_candidate
        current_report = initial_report
        result: ResultPreview | None = None
        repairs = 0
        llm_calls = 0

        while True:
            stop = controller.before_repair(repairs=repairs, llm_calls=llm_calls)
            if stop is not None:
                return (
                    CorrectionOutcome(
                        attempted=llm_calls > 0,
                        recovered=False,
                        stop_reason=stop,
                        repairs=repairs,
                        llm_calls=llm_calls,
                        trigger_error_class=initial_report.error_class,
                        attempts=attempts,
                    ),
                    current,
                    current_report,
                    result,
                )
            correction_plan = build_correction_plan(current_report)
            if not correction_plan.should_retry:
                return (
                    CorrectionOutcome(
                        attempted=llm_calls > 0,
                        recovered=False,
                        stop_reason=StopReason.NOT_ELIGIBLE,
                        repairs=repairs,
                        llm_calls=llm_calls,
                        trigger_error_class=initial_report.error_class,
                        attempts=attempts,
                    ),
                    current,
                    current_report,
                    result,
                )
            started = time.monotonic()
            llm_calls += 1
            try:
                corrected = self.corrector.correct(
                    question=question,
                    plan=plan,
                    catalog=catalog,
                    failed_candidate=current,
                    correction_plan=correction_plan,
                    schema_context=schema_context,
                    previous_attempts=attempts,
                )
            except (SQLParseError, StructuredOutputError, Text2SQLError, ValueError):
                return (
                    CorrectionOutcome(
                        attempted=True,
                        recovered=False,
                        stop_reason=StopReason.MODEL_ERROR,
                        repairs=repairs,
                        llm_calls=llm_calls,
                        trigger_error_class=initial_report.error_class,
                        attempts=attempts,
                    ),
                    current,
                    current_report,
                    result,
                )
            repairs += 1
            if corrected.fingerprint in seen_sql:
                return (
                    CorrectionOutcome(
                        attempted=True,
                        recovered=False,
                        stop_reason=StopReason.REPEATED_SQL,
                        repairs=repairs,
                        llm_calls=llm_calls,
                        trigger_error_class=initial_report.error_class,
                        attempts=attempts,
                    ),
                    corrected,
                    current_report,
                    result,
                )
            seen_sql.add(corrected.fingerprint)
            report, result = self.validation.run(
                database,
                corrected.normalized_sql,
                catalog,
                question=question,
                plan=plan,
            )
            attempts.append(
                AttemptSummary(
                    attempt=repairs,
                    sql_fingerprint=corrected.fingerprint,
                    validation=report,
                    elapsed_ms=(time.monotonic() - started) * 1000,
                )
            )
            current = corrected
            current_report = report
            if report.accepted:
                return (
                    CorrectionOutcome(
                        attempted=True,
                        recovered=True,
                        stop_reason=StopReason.VALID,
                        repairs=repairs,
                        llm_calls=llm_calls,
                        trigger_error_class=initial_report.error_class,
                        attempts=attempts,
                    ),
                    current,
                    report,
                    result,
                )
            fingerprint = error_fingerprint(report)
            if fingerprint in seen_errors:
                return (
                    CorrectionOutcome(
                        attempted=True,
                        recovered=False,
                        stop_reason=StopReason.REPEATED_ERROR,
                        repairs=repairs,
                        llm_calls=llm_calls,
                        trigger_error_class=initial_report.error_class,
                        attempts=attempts,
                    ),
                    current,
                    report,
                    result,
                )
            seen_errors.add(fingerprint)
