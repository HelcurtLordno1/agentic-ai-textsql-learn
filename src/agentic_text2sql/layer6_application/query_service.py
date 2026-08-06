"""Phase 2 direct-baseline orchestration with typed terminal states."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import RouteIntent
from agentic_text2sql.contracts.sql import DirectRunResult, DirectStatus
from agentic_text2sql.exceptions import StructuredOutputError, Text2SQLError
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer
from agentic_text2sql.layer1_reasoning.planner import PLANNER_PROMPT_VERSION, PlannerAgent
from agentic_text2sql.layer1_reasoning.router import QueryRouter
from agentic_text2sql.layer3_generation.prompt_builder import GENERATOR_PROMPT_VERSION
from agentic_text2sql.layer3_generation.service import GenerationService
from agentic_text2sql.layer4_validation.error_normalizer import normalize_error
from agentic_text2sql.layer4_validation.executor import ReadOnlySQLiteExecutor
from agentic_text2sql.layer4_validation.parser import SQLParseError
from agentic_text2sql.layer4_validation.policy import SQLSafetyPolicy


class DirectBaselineService:
    """Bounded Router→Planner→Generator→Policy→Executor vertical slice."""

    def __init__(
        self,
        *,
        router: QueryRouter,
        decomposer: Decomposer,
        planner: PlannerAgent,
        generation: GenerationService,
        policy: SQLSafetyPolicy,
        executor: ReadOnlySQLiteExecutor,
    ) -> None:
        self.router = router
        self.decomposer = decomposer
        self.planner = planner
        self.generation = generation
        self.policy = policy
        self.executor = executor

    def run(self, question: str, database: Path, catalog: CatalogSnapshot) -> DirectRunResult:
        run_id = str(uuid.uuid4())
        versions = {
            "planner": PLANNER_PROMPT_VERSION,
            "generator": GENERATOR_PROMPT_VERSION,
        }
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
        planning_started = time.monotonic()
        try:
            plan = self.planner.plan(question, decomposition)
        except (StructuredOutputError, Text2SQLError) as exc:
            timings["planning"] = (time.monotonic() - planning_started) * 1000
            finish_timings()
            return DirectRunResult(
                run_id=run_id,
                question=question,
                status=DirectStatus.MODEL_ERROR,
                route_reason=route.reason,
                prompt_versions=versions,
                safe_message=str(exc),
                latency_ms=timings,
            )
        timings["planning"] = (time.monotonic() - planning_started) * 1000

        generation_started = time.monotonic()
        try:
            candidate = self.generation.run(question, plan, catalog)
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
                safe_message=str(exc),
                latency_ms=timings,
            )
        timings["generation"] = (time.monotonic() - generation_started) * 1000

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
            candidate=candidate,
            result_columns=result.columns,
            result_rows=result.rows,
            latency_ms=timings,
        )
