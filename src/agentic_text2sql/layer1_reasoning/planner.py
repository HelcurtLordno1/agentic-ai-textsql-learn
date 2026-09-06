"""Adaptive typed planner inspired by DIN-SQL."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from jinja2 import Environment, StrictUndefined

from agentic_text2sql.adapters.llm.base import StructuredLLM
from agentic_text2sql.contracts.planning import (
    ClausePlan,
    ComplexityDecision,
    ComplexityKind,
    DecomposedQuestion,
    DINSQLDraft,
    DINSQLPlan,
    JoinStep,
    LogicalPlan,
    PlanningStrategy,
    SemanticLinkPlan,
    SemanticRole,
)
from agentic_text2sql.contracts.retrieval import SchemaContext

BASELINE_PLANNER_PROMPT_VERSION = "planner_v2"
PLANNER_PROMPT_VERSION = "planner_v3_din_sql"


class PlannerAgent:
    def __init__(
        self,
        provider: StructuredLLM,
        template_path: Path,
        grounded_template_path: Path | None = None,
    ) -> None:
        self.provider = provider
        self.template_path = template_path
        self.grounded_template_path = grounded_template_path

    def plan(self, question: str, decomposition: DecomposedQuestion) -> LogicalPlan:
        template = Environment(undefined=StrictUndefined, autoescape=False).from_string(
            self.template_path.read_text(encoding="utf-8")
        )
        prompt = template.render(
            question=question,
            decomposition=decomposition.model_dump_json(indent=2),
            output_schema=json.dumps(LogicalPlan.model_json_schema(), ensure_ascii=False),
        )
        generated = self.provider.generate_structured(prompt=prompt, response_model=LogicalPlan)
        return align_plan(question, decomposition, generated)

    def plan_grounded(
        self,
        question: str,
        decomposition: DecomposedQuestion,
        semantic_links: SemanticLinkPlan,
        schema_context: SchemaContext,
    ) -> DINSQLPlan:
        """Create a bounded schema-aware clause plan without another 14B model request."""
        if (
            semantic_links.db_id != schema_context.db_id
            or semantic_links.catalog_hash != schema_context.catalog_hash
        ):
            raise ValueError("semantic links do not match schema context")
        linked_columns = {
            role: [
                f"{link.table}.{link.column}"
                for link in semantic_links.links
                if link.role is role and link.column is not None
            ]
            for role in SemanticRole
        }
        lowered = question.casefold()
        asks_count = any(
            phrase in lowered for phrase in ("how many", "có bao nhiêu", "number of", "số lượng")
        )
        asks_distinct = any(
            phrase in lowered for phrase in ("distinct", "unique", "duy nhất", "khác nhau")
        )
        required_owners = {
            link.table
            for link in semantic_links.links
            if link.role in {SemanticRole.METRIC, SemanticRole.DIMENSION, SemanticRole.FILTER}
            and (link.role is not SemanticRole.DIMENSION or not asks_count)
        }
        if semantic_links.population_owner is not None:
            required_owners.add(semantic_links.population_owner)
        if not required_owners:
            required_owners.update(semantic_links.required_tables)
        if not required_owners:
            required_owners.update(schema_context.selected_tables[:1])

        selected_join_paths: list[str] = []
        planned_tables = set(required_owners)
        if len(required_owners) > 1:
            for condition in semantic_links.join_paths:
                left, _, right = condition.partition(" = ")
                if not right:
                    continue
                selected_join_paths.append(condition)
                planned_tables.update(
                    (left.split(".", maxsplit=1)[0], right.split(".", maxsplit=1)[0])
                )
        join_steps: list[JoinStep] = []
        for condition in selected_join_paths:
            left, _, right = condition.partition(" = ")
            if not right:
                continue
            join_steps.append(
                JoinStep(
                    left_table=left.split(".", maxsplit=1)[0],
                    right_table=right.split(".", maxsplit=1)[0],
                    condition=condition,
                    purpose="connect provenance-backed semantic owners",
                )
            )
        if asks_count:
            distinct_column = next(
                (
                    column
                    for column in linked_columns[SemanticRole.DIMENSION]
                    if column.split(".", maxsplit=1)[0] in required_owners
                ),
                None,
            )
            owner = semantic_links.population_owner or sorted(required_owners)[0]
            select = [
                f"COUNT DISTINCT {distinct_column}"
                if asks_distinct and distinct_column is not None
                else f"COUNT rows of {owner}"
            ]
        else:
            selected_columns = [
                *linked_columns[SemanticRole.DIMENSION],
                *linked_columns[SemanticRole.METRIC],
            ]
            select = [
                _scalar_metric_expression(question, column)
                if not decomposition.dimension_hints
                and column in linked_columns[SemanticRole.METRIC]
                else column
                for column in selected_columns
            ]
        if not select:
            select = list(schema_context.selected_columns[:1]) or ["row count"]
        task_type: Literal["lookup", "aggregation", "ranking", "comparison", "set"] = (
            "ranking"
            if decomposition.sort_hints or decomposition.limit_hint is not None
            else "comparison"
            if decomposition.set_operation_hint
            else "aggregation"
            if decomposition.metric_hints
            else "lookup"
        )
        generated = DINSQLDraft(
            question_language=decomposition.question_language,
            task_type=task_type,
            metrics=decomposition.metric_hints,
            dimensions=[] if asks_count else decomposition.dimension_hints,
            filters=[*decomposition.filter_hints, *decomposition.time_hints],
            sort=decomposition.sort_hints,
            limit=decomposition.limit_hint,
            required_concepts=[
                *decomposition.metric_hints,
                *decomposition.entity_hints,
                *decomposition.dimension_hints,
            ],
            complexity=ComplexityDecision(
                kind=ComplexityKind.SIMPLE,
                strategy=PlanningStrategy.EASY,
                signals=("deterministic_initial",),
            ),
            clauses=ClausePlan(
                select=select,
                from_tables=sorted(planned_tables),
                joins=join_steps,
                where=[
                    f"{link.table}.{link.column} = {link.value!r}"
                    for link in semantic_links.links
                    if link.role in {SemanticRole.FILTER, SemanticRole.VALUE}
                    and link.column is not None
                    and link.value is not None
                ],
                group_by=linked_columns[SemanticRole.DIMENSION]
                if decomposition.metric_hints and not asks_count
                else [],
                order_by=decomposition.sort_hints,
                limit=decomposition.limit_hint,
                output_grain=(
                    "one scalar row"
                    if asks_count
                    else "one row per requested dimension"
                    if decomposition.dimension_hints
                    else "one scalar row"
                    if decomposition.metric_hints
                    else "requested entity rows"
                ),
            ),
        )
        aligned = align_plan(question, decomposition, generated)
        decision = classify_complexity(aligned)
        clauses = aligned.clauses.model_copy(update={"limit": aligned.limit})
        return DINSQLPlan(
            **aligned.model_dump(exclude={"complexity", "clauses"}),
            semantic_links=semantic_links,
            complexity=decision,
            clauses=clauses,
        )


def _scalar_metric_expression(question: str, column: str) -> str:
    """Make an explicit aggregate only when the scalar wording determines the operator."""
    lowered = question.casefold()
    if any(value in lowered for value in ("average", "avg", "trung bình")):
        return f"AVG {column}"
    if any(value in lowered for value in ("maximum", "max ", "lớn nhất")):
        return f"MAX {column}"
    if any(value in lowered for value in ("minimum", "min ", "nhỏ nhất")):
        return f"MIN {column}"
    if any(value in lowered for value in ("total", "sum", "tổng", "revenue", "doanh thu")):
        return f"SUM {column}"
    return column


def classify_complexity(plan: DINSQLDraft) -> ComplexityDecision:
    """Normalize the routing label from concrete clause dependencies."""
    clause_text = " ".join(
        [
            *plan.clauses.select,
            *plan.clauses.where,
            *plan.clauses.group_by,
            *plan.clauses.having,
            *plan.clauses.order_by,
        ]
    ).casefold()
    has_nested = bool(plan.clauses.subqueries or plan.clauses.set_operation) or any(
        marker in clause_text for marker in (" window ", "over(", "over (")
    )
    has_join = bool(plan.clauses.joins or len(plan.clauses.from_tables) > 1)
    has_aggregate = plan.task_type in {"aggregation", "ranking"} or bool(
        plan.clauses.group_by or plan.clauses.having
    )
    if has_nested:
        kind = ComplexityKind.NESTED_SET_WINDOW
        strategy = PlanningStrategy.NESTED
        signals = ("subquery_or_set_or_window",)
    elif has_join:
        kind = ComplexityKind.MULTI_JOIN
        strategy = PlanningStrategy.NON_NESTED
        signals = ("multiple_tables_or_join",)
    elif has_aggregate:
        kind = ComplexityKind.AGGREGATE
        strategy = PlanningStrategy.EASY
        signals = ("single_relation_aggregate",)
    else:
        kind = ComplexityKind.SIMPLE
        strategy = PlanningStrategy.EASY
        signals = ("single_relation_lookup",)
    return ComplexityDecision(kind=kind, strategy=strategy, signals=signals)


def align_plan[PlanT: LogicalPlan](
    question: str, decomposition: DecomposedQuestion, generated: PlanT
) -> PlanT:
    """Apply deterministic question constraints that the model is not allowed to weaken."""
    lowered = question.casefold()
    updates: dict[str, object] = {}
    if decomposition.limit_hint is not None:
        updates["limit"] = decomposition.limit_hint
    if decomposition.sort_hints:
        updates["sort"] = decomposition.sort_hints
    asks_ranked_rows = (
        bool(re.search(r"\bnhiều\b.{0,40}\bnhất\b", lowered))
        or any(
            phrase in lowered
            for phrase in ("most ", "top ", "nhiều nhất", "cao nhất", "xuất hiện nhiều nhất")
        )
    ) and not any(phrase in lowered for phrase in ("what is the maximum", "lớn nhất từng"))
    if asks_ranked_rows:
        updates["task_type"] = "ranking"

    asks_scalar = any(
        phrase in lowered
        for phrase in ("how many", "có bao nhiêu", "là bao nhiêu", "what is the average")
    )
    asks_derived_average = any(
        phrase in lowered
        for phrase in (
            "average number of",
            "average items per",
            "trung bình mỗi",
            "trung bình trên mỗi",
        )
    )
    explicitly_grouped = any(
        phrase in lowered for phrase in (" by ", " theo ", "per state", "mỗi ", "each ", "top ")
    )
    if (asks_scalar and not explicitly_grouped and not asks_ranked_rows) or asks_derived_average:
        updates["task_type"] = "aggregation"
        updates["dimensions"] = []
        updates["sort"] = []
        updates["limit"] = None
    asks_returning_customer = ("returning customer" in lowered or "quay lại" in lowered) and any(
        token in lowered for token in ("customer", "khách hàng")
    )
    if asks_returning_customer and asks_scalar:
        updates["task_type"] = "aggregation"
        updates["metrics"] = ["returning customer count"]
        updates["dimensions"] = []
    asks_scalar_maximum = any(
        phrase in lowered for phrase in ("what is the maximum", "lớn nhất từng")
    )
    if asks_scalar_maximum:
        updates["task_type"] = "aggregation"
        updates["dimensions"] = []
        updates["sort"] = []
        updates["limit"] = None
    return generated.model_copy(update=updates)
