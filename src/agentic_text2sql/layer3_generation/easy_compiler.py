"""Catalog-checked compilation for the provable scalar subset of grounded plans."""

from __future__ import annotations

import re

from sqlglot import exp

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import DINSQLPlan, PlanningStrategy
from agentic_text2sql.contracts.sql import CandidateRecord, SqlCandidate
from agentic_text2sql.layer3_generation.normalizer import CandidateNormalizer

GROUNDED_EASY_COMPILER_VERSION = "generator_v6_grounded_easy"
GROUNDED_EASY_COMPILER_MODEL = "deterministic-grounded-compiler"

_COUNT_ROWS = re.compile(r"^COUNT rows of ([A-Za-z_][A-Za-z0-9_]*)$")
_COLUMN_AGGREGATE = re.compile(
    r"^(COUNT DISTINCT|SUM|AVG|MIN|MAX) "
    r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)$"
)
_STRING_EQUALITY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*) = '([^']*)'$")


class GroundedEasyCompiler:
    """Compile only a small SQL subset whose identifiers can be proven from the catalog.

    Returning ``None`` is an intentional hand-off to model generation. The compiler never guesses
    an identifier, join, aggregation, or predicate that is absent from the validated clause plan.
    """

    def __init__(self, normalizer: CandidateNormalizer) -> None:
        self.normalizer = normalizer
        self.prompt_version = GROUNDED_EASY_COMPILER_VERSION

    def compile(self, plan: DINSQLPlan, catalog: CatalogSnapshot) -> CandidateRecord | None:
        clauses = plan.clauses
        if (
            plan.complexity.strategy is not PlanningStrategy.EASY
            or clauses.output_grain.casefold() != "one scalar row"
            or len(clauses.select) != 1
            or len(clauses.from_tables) != 1
            or clauses.joins
            or clauses.group_by
            or clauses.having
            or clauses.order_by
            or clauses.limit is not None
            or clauses.subqueries
            or clauses.set_operation is not None
        ):
            return None

        table_name = clauses.from_tables[0]
        table = next((item for item in catalog.tables if item.name == table_name), None)
        if table is None:
            return None
        catalog_columns = {column.name for column in table.columns}

        used_columns: list[str] = []
        select_text = clauses.select[0]
        count_rows = _COUNT_ROWS.fullmatch(select_text)
        aggregate = _COLUMN_AGGREGATE.fullmatch(select_text)
        if count_rows is not None:
            if count_rows.group(1) != table_name:
                return None
            selection: exp.Expression = exp.Count(this=exp.Star())
        elif aggregate is not None:
            operation, owner, column = aggregate.groups()
            if owner != table_name or column not in catalog_columns:
                return None
            used_columns.append(column)
            operand = exp.column(column)
            if operation == "COUNT DISTINCT":
                selection = exp.Count(this=exp.Distinct(expressions=[operand]))
            elif operation == "SUM":
                selection = exp.Sum(this=operand)
            elif operation == "AVG":
                selection = exp.Avg(this=operand)
            elif operation == "MIN":
                selection = exp.Min(this=operand)
            else:
                selection = exp.Max(this=operand)
        else:
            return None

        query = exp.select(selection).from_(table_name)
        predicates: list[exp.Expression] = []
        for predicate_text in clauses.where:
            equality = _STRING_EQUALITY.fullmatch(predicate_text)
            if equality is None:
                return None
            owner, column, value = equality.groups()
            if owner != table_name or column not in catalog_columns:
                return None
            used_columns.append(column)
            predicates.append(exp.column(column).eq(exp.Literal.string(value)))
        if predicates:
            condition = predicates[0]
            for predicate in predicates[1:]:
                condition = exp.and_(condition, predicate)
            query = query.where(condition)

        candidate = SqlCandidate(
            sql=query.sql(dialect="sqlite"),
            used_tables=[table_name],
            used_columns=list(dict.fromkeys(used_columns)),
            assumptions=[],
            confidence=1.0,
        )
        return self.normalizer.normalize(
            candidate,
            model_name=GROUNDED_EASY_COMPILER_MODEL,
            prompt_version=self.prompt_version,
            catalog_hash=catalog.catalog_hash,
        )
