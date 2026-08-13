from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.sql import CandidateRecord, SqlCandidate
from agentic_text2sql.contracts.validation import ErrorClass, ValidationReport
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer3_generation.normalizer import CandidateNormalizer
from agentic_text2sql.layer4_validation.executor import ReadOnlySQLiteExecutor
from agentic_text2sql.layer4_validation.policy import SQLSafetyPolicy
from agentic_text2sql.layer4_validation.service import ValidationService
from agentic_text2sql.layer5_correction.corrector import CorrectorAgent
from agentic_text2sql.layer5_correction.service import CorrectionService


class FakeProvider:
    def __init__(self, candidates: list[SqlCandidate]) -> None:
        self.candidates = candidates
        self.prompts: list[str] = []

    def generate_structured[StructuredModel: BaseModel](
        self,
        *,
        prompt: str,
        response_model: type[StructuredModel],
        model: str | None = None,
    ) -> StructuredModel:
        del model
        self.prompts.append(prompt)
        return response_model.model_validate(self.candidates.pop(0).model_dump())


def make_database(tmp_path: Path) -> Path:
    database = tmp_path / "correction.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE reviews(review_score INTEGER)")
    connection.executemany("INSERT INTO reviews VALUES (?)", [(5,), (3,)])
    connection.commit()
    connection.close()
    return database


def make_service(tmp_path: Path, provider: FakeProvider, **budgets: Any) -> CorrectionService:
    template = tmp_path / "corrector.j2"
    template.write_text(
        "{{ question }} {{ logical_plan }} {{ failed_sql }} {{ correction_plan }} "
        "{{ previous_attempts }} {{ schema_context }} {{ business_glossary }} {{ output_schema }}",
        encoding="utf-8",
    )
    glossary = tmp_path / "glossary.md"
    glossary.write_text("Average means AVG(review_score).", encoding="utf-8")
    validation = ValidationService(SQLSafetyPolicy(), ReadOnlySQLiteExecutor())
    corrector = CorrectorAgent(
        provider,
        CandidateNormalizer(),
        template,
        glossary,
        "local-test-model",
    )
    return CorrectionService(corrector=corrector, validation=validation, **budgets)


def initial_candidate(sql: str, catalog_hash: str) -> CandidateRecord:
    return CandidateNormalizer().normalize(
        SqlCandidate(sql=sql, confidence=0.5),
        model_name="test",
        prompt_version="test_v1",
        catalog_hash=catalog_hash,
    )


def average_plan() -> LogicalPlan:
    return LogicalPlan(
        question_language="en",
        task_type="aggregation",
        metrics=["average review score"],
    )


def test_correction_recovers_and_revalidates_without_gold(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    catalog = SQLiteIntrospector().inspect(database, "test")
    provider = FakeProvider(
        [SqlCandidate(sql="SELECT AVG(review_score) FROM reviews", confidence=0.9)]
    )
    service = make_service(tmp_path, provider)
    failed = initial_candidate("SELECT review_score FROM reviews", catalog.catalog_hash)
    initial_report, _ = service.validation.run(
        database,
        failed.normalized_sql,
        catalog,
        question="What is the average review score?",
        plan=average_plan(),
    )

    outcome, candidate, report, result = service.run(
        question="What is the average review score?",
        plan=average_plan(),
        catalog=catalog,
        database=database,
        failed_candidate=failed,
        initial_report=initial_report,
    )

    assert outcome.recovered and outcome.repairs == outcome.llm_calls == 1
    assert report.accepted and result is not None and result.rows == [[4.0]]
    assert "AVG(review_score)" in candidate.normalized_sql
    assert "gold_sql" not in provider.prompts[0].casefold()
    assert "gold_rows" not in provider.prompts[0].casefold()


def test_valid_candidate_is_never_repaired(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    catalog = SQLiteIntrospector().inspect(database, "test")
    provider = FakeProvider([])
    service = make_service(tmp_path, provider)
    candidate = initial_candidate("SELECT AVG(review_score) FROM reviews", catalog.catalog_hash)
    report, _ = service.validation.run(
        database,
        candidate.normalized_sql,
        catalog,
        question="What is the average review score?",
        plan=average_plan(),
    )
    outcome, _, _, _ = service.run(
        question="What is the average review score?",
        plan=average_plan(),
        catalog=catalog,
        database=database,
        failed_candidate=candidate,
        initial_report=report,
    )
    assert not outcome.attempted
    assert provider.prompts == []


def test_policy_violation_is_never_repaired(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    catalog = SQLiteIntrospector().inspect(database, "test")
    provider = FakeProvider([])
    service = make_service(tmp_path, provider)
    candidate = initial_candidate("SELECT review_score FROM reviews", catalog.catalog_hash)
    report = ValidationReport(
        accepted=False,
        error_class=ErrorClass.POLICY_VIOLATION,
        safe_message="Write blocked",
    )
    outcome, _, _, _ = service.run(
        question="Delete reviews",
        plan=average_plan(),
        catalog=catalog,
        database=database,
        failed_candidate=candidate,
        initial_report=report,
    )
    assert not outcome.attempted
    assert provider.prompts == []


def test_loop_stops_on_repeated_sql(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    catalog = SQLiteIntrospector().inspect(database, "test")
    failed = initial_candidate("SELECT review_score FROM reviews", catalog.catalog_hash)
    provider = FakeProvider([failed.candidate])
    service = make_service(tmp_path, provider, max_repairs=2, max_llm_calls=2)
    report = ValidationReport(
        accepted=False,
        error_class=ErrorClass.SEMANTIC_MISMATCH,
        safe_message="Average missing",
        signals=["AVERAGE_AGGREGATE_MISSING"],
        repair_eligible=True,
    )
    outcome, _, _, _ = service.run(
        question="What is the average review score?",
        plan=average_plan(),
        catalog=catalog,
        database=database,
        failed_candidate=failed,
        initial_report=report,
    )
    assert outcome.stop_reason.value == "REPEATED_SQL"
    assert outcome.repairs == outcome.llm_calls == 1


def test_expired_deadline_prevents_model_call(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    catalog = SQLiteIntrospector().inspect(database, "test")
    provider = FakeProvider([])
    service = make_service(tmp_path, provider)
    failed = initial_candidate("SELECT review_score FROM reviews", catalog.catalog_hash)
    report = ValidationReport(
        accepted=False,
        error_class=ErrorClass.SEMANTIC_MISMATCH,
        signals=["AVERAGE_AGGREGATE_MISSING"],
        repair_eligible=True,
    )
    outcome, _, _, _ = service.run(
        question="What is the average review score?",
        plan=average_plan(),
        catalog=catalog,
        database=database,
        failed_candidate=failed,
        initial_report=report,
        deadline=time.monotonic() - 1,
    )
    assert outcome.stop_reason.value == "DEADLINE"
    assert provider.prompts == []


def test_correction_keeps_database_immutable(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    catalog = SQLiteIntrospector().inspect(database, "test")
    provider = FakeProvider(
        [SqlCandidate(sql="SELECT AVG(review_score) FROM reviews", confidence=0.9)]
    )
    service = make_service(tmp_path, provider)
    failed = initial_candidate("SELECT review_score FROM reviews", catalog.catalog_hash)
    report = ValidationReport(
        accepted=False,
        error_class=ErrorClass.SEMANTIC_MISMATCH,
        signals=["AVERAGE_AGGREGATE_MISSING"],
        repair_eligible=True,
    )
    service.run(
        question="What is the average review score?",
        plan=average_plan(),
        catalog=catalog,
        database=database,
        failed_candidate=failed,
        initial_report=report,
    )
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
