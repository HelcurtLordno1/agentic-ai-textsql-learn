"""Phase 2 direct-baseline orchestration with typed terminal states."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Literal

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import (
    DINSQLPlan,
    LogicalPlan,
    PlanningStrategy,
    RouteIntent,
)
from agentic_text2sql.contracts.sql import DirectRunResult, DirectStatus
from agentic_text2sql.contracts.validation import ErrorClass, ValidationReport
from agentic_text2sql.exceptions import StructuredOutputError, Text2SQLError
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer
from agentic_text2sql.layer1_reasoning.plan_validator import validate_plan
from agentic_text2sql.layer1_reasoning.planner import (
    BASELINE_PLANNER_PROMPT_VERSION,
    PLANNER_PROMPT_VERSION,
    PlannerAgent,
)
from agentic_text2sql.layer1_reasoning.router import QueryRouter
from agentic_text2sql.layer2_grounding.service import GroundingService
from agentic_text2sql.layer3_generation.easy_compiler import GroundedEasyCompiler
from agentic_text2sql.layer3_generation.service import GenerationService
from agentic_text2sql.layer4_validation.error_normalizer import normalize_error
from agentic_text2sql.layer4_validation.executor import ReadOnlySQLiteExecutor
from agentic_text2sql.layer4_validation.parser import SQLParseError
from agentic_text2sql.layer4_validation.policy import SQLSafetyPolicy
from agentic_text2sql.layer5_correction.service import CorrectionService


class DirectBaselineService:
    """Bounded Router→Planner→Generator→Policy→Executor vertical slice."""

    def __init__(
        self,
        *,
        router: QueryRouter,
        decomposer: Decomposer,
        planner: PlannerAgent,
        generation: GenerationService,
        din_generation: GenerationService | None = None,
        easy_compiler: GroundedEasyCompiler | None = None,
        policy: SQLSafetyPolicy,
        executor: ReadOnlySQLiteExecutor,
        grounding: GroundingService | None = None,
        correction: CorrectionService | None = None,
        din_correction: CorrectionService | None = None,
        run_deadline_seconds: float = 60.0,
        planning_mode: Literal["baseline", "hybrid", "din_sql"] = "baseline",
    ) -> None:
        self.router = router
        self.decomposer = decomposer
        self.planner = planner
        self.generation = generation
        self.din_generation = din_generation
        self.easy_compiler = easy_compiler
        self.policy = policy
        self.executor = executor
        self.grounding = grounding
        self.correction = correction
        self.din_correction = din_correction
        self.run_deadline_seconds = run_deadline_seconds
        self.planning_mode = planning_mode
        if planning_mode in {"hybrid", "din_sql"} and grounding is None:
            raise ValueError("hybrid/DIN-SQL planning requires an active grounded schema index")
        if planning_mode == "hybrid" and din_generation is None:
            raise ValueError("hybrid planning requires both baseline and DIN generation paths")
        if planning_mode == "hybrid" and easy_compiler is None:
            raise ValueError("hybrid planning requires the grounded EASY compiler")

    def run(self, question: str, database: Path, catalog: CatalogSnapshot) -> DirectRunResult:
        run_id = str(uuid.uuid4())
        din_sql = self.planning_mode == "din_sql"
        hybrid = self.planning_mode == "hybrid"
        versions = {
            "planner": (
                "hybrid_deterministic_v1"
                if hybrid
                else PLANNER_PROMPT_VERSION
                if din_sql
                else BASELINE_PLANNER_PROMPT_VERSION
            ),
            "generator": self.generation.prompt_version,
        }
        if self.correction is not None:
            versions["corrector"] = self.correction.corrector.prompt_version
        timings: dict[str, float] = {}
        started = time.monotonic()

        def finish_timings() -> None:
            timings["total"] = (time.monotonic() - started) * 1000

        route = self.router.route(question)
        timings["route"] = (time.monotonic() - started) * 1000
        if route.intent is not RouteIntent.QUERY:
            status = {
                RouteIntent.CLARIFY: DirectStatus.CLARIFY,
                RouteIntent.UNSUPPORTED: DirectStatus.UNSUPPORTED,
                RouteIntent.WRITE_REQUEST: DirectStatus.WRITE_BLOCKED,
            }[route.intent]
            finish_timings()
            return DirectRunResult(
                run_id=run_id,
                question=question,
                status=status,
                route_reason=route.reason,
                prompt_versions=versions,
                safe_message=route.reason,
                latency_ms=timings,
            )

        decomposition = self.decomposer.decompose(question)
        schema_context = None
        semantic_links = None
        if self.grounding is not None and self.planning_mode in {"hybrid", "din_sql"}:
            grounding_started = time.monotonic()
            try:
                schema_context, semantic_links = self.grounding.prepare_for_planning(
                    question, decomposition
                )
            except (ValueError, Text2SQLError) as exc:
                timings["grounding"] = (time.monotonic() - grounding_started) * 1000
                finish_timings()
                return DirectRunResult(
                    run_id=run_id,
                    question=question,
                    status=DirectStatus.GROUNDING_ERROR,
                    route_reason=route.reason,
                    prompt_versions=versions,
                    safe_message=str(exc),
                    latency_ms=timings,
                )
            timings["grounding"] = (time.monotonic() - grounding_started) * 1000

        planning_started = time.monotonic()
        plan: LogicalPlan
        try:
            if (
                self.planning_mode in {"hybrid", "din_sql"}
                and schema_context is not None
                and semantic_links is not None
            ):
                plan = self.planner.plan_grounded(
                    question, decomposition, semantic_links, schema_context
                )
            else:
                plan = self.planner.plan(question, decomposition)
        except (StructuredOutputError, Text2SQLError, ValueError) as exc:
            timings["planning"] = (time.monotonic() - planning_started) * 1000
            finish_timings()
            return DirectRunResult(
                run_id=run_id,
                question=question,
                status=DirectStatus.MODEL_ERROR,
                route_reason=route.reason,
                prompt_versions=versions,
                schema_context=(schema_context.model_dump(mode="json") if schema_context else None),
                safe_message=str(exc),
                latency_ms=timings,
            )
        timings["planning"] = (time.monotonic() - planning_started) * 1000

        if self.grounding is not None and schema_context is None:
            grounding_started = time.monotonic()
            try:
                schema_context = self.grounding.ground(question, plan)
            except (ValueError, Text2SQLError) as exc:
                timings["grounding"] = (time.monotonic() - grounding_started) * 1000
                finish_timings()
                return DirectRunResult(
                    run_id=run_id,
                    question=question,
                    status=DirectStatus.GROUNDING_ERROR,
                    route_reason=route.reason,
                    prompt_versions=versions,
                    plan=plan.model_dump(mode="json"),
                    safe_message=str(exc),
                    latency_ms=timings,
                )
            timings["grounding"] = (time.monotonic() - grounding_started) * 1000

        plan_validation = None
        if schema_context is not None and isinstance(plan, DINSQLPlan):
            plan_validation = validate_plan(plan, catalog, schema_context)
            if not plan_validation.accepted:
                finish_timings()
                return DirectRunResult(
                    run_id=run_id,
                    question=question,
                    status=DirectStatus.GROUNDING_ERROR,
                    route_reason=route.reason,
                    prompt_versions=versions,
                    plan=plan.model_dump(mode="json"),
                    plan_validation=plan_validation.model_dump(mode="json"),
                    schema_context=schema_context.model_dump(mode="json"),
                    safe_message=plan_validation.safe_message,
                    latency_ms=timings,
                )
        plan_validation_payload = (
            plan_validation.model_dump(mode="json") if plan_validation is not None else None
        )

        use_din_generation = bool(
            isinstance(plan, DINSQLPlan)
            and (
                self.planning_mode == "din_sql"
                or (
                    self.planning_mode == "hybrid"
                    and plan.complexity.strategy is not PlanningStrategy.EASY
                    and not (plan_validation and plan_validation.advisory_signals)
                )
            )
        )
        active_generation = (
            self.din_generation
            if use_din_generation and self.din_generation is not None
            else self.generation
        )
        active_correction = (
            self.din_correction
            if use_din_generation and self.din_correction is not None
            else self.correction
        )
        generation_plan: LogicalPlan = plan
        if isinstance(plan, DINSQLPlan) and not use_din_generation:
            generation_plan = LogicalPlan.model_validate(
                plan.model_dump(
                    include={
                        "question_language",
                        "task_type",
                        "metrics",
                        "dimensions",
                        "filters",
                        "sort",
                        "limit",
                        "required_concepts",
                        "ambiguities",
                        "assumptions",
                    }
                )
            )
        versions["generator"] = active_generation.prompt_version
        if active_correction is not None:
            versions["corrector"] = active_correction.corrector.prompt_version

        generation_started = time.monotonic()
        try:
            candidate = (
                self.easy_compiler.compile(plan, catalog)
                if hybrid
                and isinstance(plan, DINSQLPlan)
                and plan.complexity.strategy is PlanningStrategy.EASY
                and not (plan_validation and plan_validation.advisory_signals)
                and self.easy_compiler is not None
                else None
            )
            if candidate is None:
                candidate = active_generation.run(
                    question, generation_plan, catalog, schema_context
                )
            else:
                versions["generator"] = candidate.prompt_version
        except SQLParseError as exc:
            timings["generation"] = (time.monotonic() - generation_started) * 1000
            finish_timings()
            return DirectRunResult(
                run_id=run_id,
                question=question,
                status=DirectStatus.INVALID_SQL,
                route_reason=route.reason,
                prompt_versions=versions,
                plan=plan.model_dump(mode="json"),
                plan_validation=plan_validation_payload,
                schema_context=(schema_context.model_dump(mode="json") if schema_context else None),
                safe_message=str(exc),
                latency_ms=timings,
            )
        except (StructuredOutputError, Text2SQLError) as exc:
            timings["generation"] = (time.monotonic() - generation_started) * 1000
            finish_timings()
            return DirectRunResult(
                run_id=run_id,
                question=question,
                status=DirectStatus.MODEL_ERROR,
                route_reason=route.reason,
                prompt_versions=versions,
                plan=plan.model_dump(mode="json"),
                plan_validation=plan_validation_payload,
                schema_context=(schema_context.model_dump(mode="json") if schema_context else None),
                safe_message=str(exc),
                latency_ms=timings,
            )
        timings["generation"] = (time.monotonic() - generation_started) * 1000

        if active_correction is not None:
            validation_started = time.monotonic()
            initial_report, initial_result = active_correction.validation.run(
                database,
                candidate.normalized_sql,
                catalog,
                question=question,
                plan=generation_plan,
            )
            timings["validation"] = (time.monotonic() - validation_started) * 1000
            if initial_report.accepted and initial_result is not None:
                finish_timings()
                return DirectRunResult(
                    run_id=run_id,
                    question=question,
                    status=DirectStatus.SUCCEEDED,
                    route_reason=route.reason,
                    prompt_versions=versions,
                    plan=plan.model_dump(mode="json"),
                    plan_validation=plan_validation_payload,
                    schema_context=(
                        schema_context.model_dump(mode="json") if schema_context else None
                    ),
                    candidate=candidate,
                    result_columns=initial_result.columns,
                    result_rows=initial_result.rows,
                    latency_ms=timings,
                )
            correction_started = time.monotonic()
            outcome, final_candidate, final_report, final_result = active_correction.run(
                question=question,
                plan=generation_plan,
                catalog=catalog,
                database=database,
                failed_candidate=candidate,
                initial_report=initial_report,
                schema_context=schema_context,
                deadline=started + self.run_deadline_seconds,
            )
            timings["correction"] = (time.monotonic() - correction_started) * 1000
            finish_timings()
            if outcome.recovered and final_result is not None:
                return DirectRunResult(
                    run_id=run_id,
                    question=question,
                    status=DirectStatus.SUCCEEDED,
                    route_reason=route.reason,
                    prompt_versions=versions,
                    plan=plan.model_dump(mode="json"),
                    plan_validation=plan_validation_payload,
                    schema_context=(
                        schema_context.model_dump(mode="json") if schema_context else None
                    ),
                    candidate=final_candidate,
                    result_columns=final_result.columns,
                    result_rows=final_result.rows,
                    latency_ms=timings,
                    correction=outcome.model_dump(mode="json"),
                )
            return DirectRunResult(
                run_id=run_id,
                question=question,
                status=_status_for_report(final_report),
                route_reason=route.reason,
                prompt_versions=versions,
                plan=plan.model_dump(mode="json"),
                plan_validation=plan_validation_payload,
                schema_context=(schema_context.model_dump(mode="json") if schema_context else None),
                candidate=final_candidate,
                result_columns=final_result.columns if final_result else [],
                result_rows=final_result.rows if final_result else [],
                error_class=(final_report.error_class.value if final_report.error_class else None),
                safe_message=final_report.safe_message,
                latency_ms=timings,
                correction=outcome.model_dump(mode="json"),
            )

        policy_started = time.monotonic()
        decision = self.policy.evaluate(candidate.normalized_sql, catalog)
        timings["policy"] = (time.monotonic() - policy_started) * 1000
        if not decision.allowed or decision.normalized_sql is None:
            finish_timings()
            return DirectRunResult(
                run_id=run_id,
                question=question,
                status=DirectStatus.POLICY_BLOCKED,
                route_reason=route.reason,
                prompt_versions=versions,
                plan=plan.model_dump(mode="json"),
                plan_validation=plan_validation_payload,
                schema_context=(schema_context.model_dump(mode="json") if schema_context else None),
                candidate=candidate,
                error_class=decision.error_class.value if decision.error_class else None,
                safe_message=decision.safe_message,
                latency_ms=timings,
            )

        execution_started = time.monotonic()
        try:
            result = self.executor.execute(database, decision.normalized_sql)
        except Exception as exc:  # Stable typed boundary around SQLite adapter failures.
            report = normalize_error(exc)
            timings["execution"] = (time.monotonic() - execution_started) * 1000
            finish_timings()
            return DirectRunResult(
                run_id=run_id,
                question=question,
                status=DirectStatus.EXECUTION_ERROR,
                route_reason=route.reason,
                prompt_versions=versions,
                plan=plan.model_dump(mode="json"),
                plan_validation=plan_validation_payload,
                schema_context=(schema_context.model_dump(mode="json") if schema_context else None),
                candidate=candidate,
                error_class=report.error_class.value if report.error_class else None,
                safe_message=report.safe_message,
                latency_ms=timings,
            )
        timings["execution"] = (time.monotonic() - execution_started) * 1000
        finish_timings()
        return DirectRunResult(
            run_id=run_id,
            question=question,
            status=DirectStatus.SUCCEEDED,
            route_reason=route.reason,
            prompt_versions=versions,
            plan=plan.model_dump(mode="json"),
            plan_validation=plan_validation_payload,
            schema_context=(schema_context.model_dump(mode="json") if schema_context else None),
            candidate=candidate,
            result_columns=result.columns,
            result_rows=result.rows,
            latency_ms=timings,
        )


def _status_for_report(report: ValidationReport) -> DirectStatus:
    if report.error_class is ErrorClass.POLICY_VIOLATION:
        return DirectStatus.POLICY_BLOCKED
    if report.error_class in {ErrorClass.RESULT_SHAPE_MISMATCH, ErrorClass.SEMANTIC_MISMATCH}:
        return DirectStatus.VALIDATION_FAILED
    return DirectStatus.EXECUTION_ERROR
