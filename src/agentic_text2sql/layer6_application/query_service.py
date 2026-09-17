"""Phase 2 direct-baseline orchestration with typed terminal states."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Literal

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import (
    AdaptiveRoute,
    AdaptiveRouteDecision,
    DINSQLPlan,
    LogicalPlan,
    PlanningStrategy,
    RouteIntent,
)
from agentic_text2sql.contracts.semantics import BindingStatus
from agentic_text2sql.contracts.sql import DirectRunResult, DirectStatus
from agentic_text2sql.contracts.validation import ErrorClass, ValidationReport
from agentic_text2sql.exceptions import StructuredOutputError, Text2SQLError
from agentic_text2sql.layer1_reasoning.adaptive_routing import choose_adaptive_route
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
        policy: SQLSafetyPolicy,
        executor: ReadOnlySQLiteExecutor,
        easy_compiler: GroundedEasyCompiler | None = None,
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
        self.policy = policy
        self.executor = executor
        self.easy_compiler = easy_compiler
        self.grounding = grounding
        self.correction = correction
        self.din_correction = din_correction
        self.run_deadline_seconds = run_deadline_seconds
        self.planning_mode = planning_mode
        if planning_mode in {"hybrid", "din_sql"} and grounding is None:
            raise ValueError("hybrid/DIN-SQL planning requires an active grounded schema index")
        if planning_mode == "hybrid" and din_generation is None:
            raise ValueError("hybrid planning requires both baseline and DIN generation paths")

    def run(self, question: str, database: Path, catalog: CatalogSnapshot) -> DirectRunResult:
        return self._run(
            question,
            database,
            catalog,
            baseline_plan_override=None,
            semantic_intervention_only=False,
        )

    def run_from_baseline_plan(
        self,
        question: str,
        database: Path,
        catalog: CatalogSnapshot,
        baseline_plan: LogicalPlan,
    ) -> DirectRunResult:
        """Run the specialist intervention from the incumbent's frozen P6 control plan."""
        if self.planning_mode != "hybrid":
            raise ValueError("baseline-plan reuse is available only in hybrid mode")
        return self._run(
            question,
            database,
            catalog,
            baseline_plan_override=baseline_plan,
            semantic_intervention_only=True,
        )

    def _run(
        self,
        question: str,
        database: Path,
        catalog: CatalogSnapshot,
        *,
        baseline_plan_override: LogicalPlan | None,
        semantic_intervention_only: bool,
    ) -> DirectRunResult:
        run_id = str(uuid.uuid4())
        din_sql = self.planning_mode == "din_sql"
        hybrid = self.planning_mode == "hybrid"
        versions = {
            "planner": (
                BASELINE_PLANNER_PROMPT_VERSION
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
        adaptive_route: AdaptiveRouteDecision | None = None
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
        plan: LogicalPlan
        baseline_plan: LogicalPlan | None = None

        def fall_back_to_baseline(signal: str) -> None:
            """Discard specialist state and restore the single frozen P6 path."""
            nonlocal adaptive_route, plan, schema_context, semantic_links
            if baseline_plan is None or adaptive_route is None:
                raise RuntimeError("specialist fallback requires a preserved baseline plan")
            plan = baseline_plan
            schema_context = None
            semantic_links = None
            adaptive_route = AdaptiveRouteDecision(
                route=AdaptiveRoute.BASELINE_PRESERVE,
                signals=tuple((*adaptive_route.signals, signal)[-8:]),
            )
            versions["planner"] = BASELINE_PLANNER_PROMPT_VERSION
            versions["adaptive_route"] = adaptive_route.route.value

        if hybrid:
            planning_started = time.monotonic()
            if baseline_plan_override is not None:
                plan = baseline_plan_override
                versions["control_plan_source"] = "incumbent_p6"
            else:
                try:
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
                        safe_message=str(exc),
                        latency_ms=timings,
                    )
            timings["planning"] = (time.monotonic() - planning_started) * 1000
            baseline_plan = plan
            adaptive_route = choose_adaptive_route(question, decomposition, plan)
            if semantic_intervention_only:
                adaptive_route = AdaptiveRouteDecision(
                    route=AdaptiveRoute.DIN_SQL_ENHANCE,
                    signals=tuple(
                        dict.fromkeys((*adaptive_route.signals, "PROVEN_SEMANTIC_INTERVENTION"))
                    ),
                )
            versions["adaptive_route"] = adaptive_route.route.value

        if self.grounding is not None and (
            din_sql
            or (
                hybrid
                and adaptive_route is not None
                and adaptive_route.route is AdaptiveRoute.DIN_SQL_ENHANCE
            )
        ):
            grounding_started = time.monotonic()
            try:
                schema_context, semantic_links = self.grounding.prepare_for_planning(
                    question, decomposition
                )
            except (ValueError, Text2SQLError) as exc:
                if hybrid and baseline_plan is not None:
                    timings["din_grounding"] = (time.monotonic() - grounding_started) * 1000
                    fall_back_to_baseline("DIN_GROUNDING_FAILED_BASELINE_FALLBACK")
                else:
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
            else:
                timings["grounding"] = (time.monotonic() - grounding_started) * 1000

        if not hybrid:
            planning_started = time.monotonic()
            try:
                if din_sql and schema_context is not None and semantic_links is not None:
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
                    schema_context=(
                        schema_context.model_dump(mode="json") if schema_context else None
                    ),
                    safe_message=str(exc),
                    latency_ms=timings,
                )
            timings["planning"] = (time.monotonic() - planning_started) * 1000

        if hybrid:
            if not isinstance(plan, LogicalPlan):
                raise TypeError("adaptive routing requires a typed control plan")
            if adaptive_route is None:
                raise RuntimeError("hybrid control planning did not produce an adaptive route")
            if adaptive_route.route is AdaptiveRoute.DIN_SQL_ENHANCE:
                baseline_plan = plan
                if self.grounding is None or schema_context is None or semantic_links is None:
                    raise RuntimeError("adaptive DIN-SQL requires grounding")
                proven_binding = bool(
                    semantic_links.binding is not None
                    and semantic_links.binding.status is BindingStatus.PROVEN
                )
                versions["planner"] = (
                    f"adaptive({BASELINE_PLANNER_PROMPT_VERSION},typed_semantic_plan_v1)"
                    if proven_binding
                    else f"adaptive({BASELINE_PLANNER_PROMPT_VERSION},{PLANNER_PROMPT_VERSION})"
                )
                din_planning_started = time.monotonic()
                try:
                    plan = self.planner.plan_grounded(
                        question,
                        decomposition,
                        semantic_links,
                        schema_context,
                        use_model=not proven_binding,
                    )
                except (StructuredOutputError, Text2SQLError, ValueError):
                    timings["din_planning"] = (time.monotonic() - din_planning_started) * 1000
                    # The P6 plan was already produced before specialist routing. A failed DIN
                    # planning call therefore has one safe, bounded backtrack: discard specialist
                    # context and replay the frozen baseline grounding/generation path. No retry
                    # is made against the failed planner and no confidence guess is required.
                    fall_back_to_baseline("DIN_PLANNING_FAILED_BASELINE_FALLBACK")
                timings["din_planning"] = (time.monotonic() - din_planning_started) * 1000

        adaptive_route_payload = (
            adaptive_route.model_dump(mode="json") if adaptive_route is not None else None
        )

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
                    adaptive_route=adaptive_route_payload,
                    plan=plan.model_dump(mode="json"),
                    safe_message=str(exc),
                    latency_ms=timings,
                )
            timings["grounding"] = (time.monotonic() - grounding_started) * 1000

        plan_validation = None
        if schema_context is not None and isinstance(plan, DINSQLPlan):
            plan_validation = validate_plan(plan, catalog, schema_context)
            if not plan_validation.accepted:
                if (
                    hybrid
                    and baseline_plan is not None
                    and adaptive_route is not None
                    and adaptive_route.route is AdaptiveRoute.DIN_SQL_ENHANCE
                ):
                    fall_back_to_baseline("DIN_PLAN_REJECTED_BASELINE_FALLBACK")
                    adaptive_route_payload = adaptive_route.model_dump(mode="json")
                    if self.grounding is None:  # Constructor invariant; narrows the typed boundary.
                        raise RuntimeError("hybrid fallback requires grounding")
                    fallback_grounding_started = time.monotonic()
                    try:
                        schema_context = self.grounding.ground(question, plan)
                    except (ValueError, Text2SQLError) as exc:
                        timings["fallback_grounding"] = (
                            time.monotonic() - fallback_grounding_started
                        ) * 1000
                        finish_timings()
                        return DirectRunResult(
                            run_id=run_id,
                            question=question,
                            status=DirectStatus.GROUNDING_ERROR,
                            route_reason=route.reason,
                            prompt_versions=versions,
                            adaptive_route=adaptive_route_payload,
                            plan=plan.model_dump(mode="json"),
                            safe_message=str(exc),
                            latency_ms=timings,
                        )
                    timings["fallback_grounding"] = (
                        time.monotonic() - fallback_grounding_started
                    ) * 1000
                    plan_validation = None
                else:
                    finish_timings()
                    return DirectRunResult(
                        run_id=run_id,
                        question=question,
                        status=DirectStatus.GROUNDING_ERROR,
                        route_reason=route.reason,
                        prompt_versions=versions,
                        adaptive_route=adaptive_route_payload,
                        plan=plan.model_dump(mode="json"),
                        plan_validation=plan_validation.model_dump(mode="json"),
                        schema_context=schema_context.model_dump(mode="json"),
                        safe_message=plan_validation.safe_message,
                        latency_ms=timings,
                    )
        plan_validation_payload = (
            plan_validation.model_dump(mode="json") if plan_validation is not None else None
        )
        has_generation_advisory = bool(
            plan_validation
            and any(
                signal != "UNPROVEN_SEMANTIC_BINDING" for signal in plan_validation.advisory_signals
            )
        )

        compiled_candidate = (
            self.easy_compiler.compile(plan, catalog)
            if (
                isinstance(plan, DINSQLPlan)
                and adaptive_route is not None
                and adaptive_route.route is AdaptiveRoute.DIN_SQL_ENHANCE
                and self.easy_compiler is not None
            )
            else None
        )
        use_din_generation = bool(
            isinstance(plan, DINSQLPlan)
            and (
                self.planning_mode == "din_sql"
                or (
                    self.planning_mode == "hybrid"
                    and adaptive_route is not None
                    and adaptive_route.route is AdaptiveRoute.DIN_SQL_ENHANCE
                    and plan.complexity.strategy is not PlanningStrategy.EASY
                    and not has_generation_advisory
                )
            )
        )
        active_generation = (
            self.din_generation
            if use_din_generation and self.din_generation is not None
            else self.generation
        )
        use_semantic_path = use_din_generation or compiled_candidate is not None
        # A deterministic proof compiler is the terminal semantic implementation of its typed
        # binding. Sending that SQL through a model corrector can silently replace a proven AVG,
        # predicate, or grain with a plausible but different query. It still passes the SQL safety
        # policy and bounded read-only execution below; only model rewriting is disabled.
        active_correction = (
            None
            if compiled_candidate is not None
            else self.din_correction
            if use_semantic_path and self.din_correction is not None
            else self.correction
        )
        generation_plan: LogicalPlan = plan
        if isinstance(plan, DINSQLPlan) and not use_semantic_path:
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
        versions["generator"] = (
            compiled_candidate.prompt_version
            if compiled_candidate is not None
            else active_generation.prompt_version
        )
        if active_correction is not None:
            versions["corrector"] = active_correction.corrector.prompt_version

        generation_started = time.monotonic()
        try:
            candidate = compiled_candidate or active_generation.run(
                question, generation_plan, catalog, schema_context
            )
        except SQLParseError as exc:
            timings["generation"] = (time.monotonic() - generation_started) * 1000
            finish_timings()
            return DirectRunResult(
                run_id=run_id,
                question=question,
                status=DirectStatus.INVALID_SQL,
                route_reason=route.reason,
                prompt_versions=versions,
                adaptive_route=adaptive_route_payload,
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
                adaptive_route=adaptive_route_payload,
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
                    adaptive_route=adaptive_route_payload,
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
                    adaptive_route=adaptive_route_payload,
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
                adaptive_route=adaptive_route_payload,
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
                adaptive_route=adaptive_route_payload,
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
                adaptive_route=adaptive_route_payload,
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
            adaptive_route=adaptive_route_payload,
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
