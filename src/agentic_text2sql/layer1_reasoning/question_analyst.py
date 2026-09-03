"""PRACTIQ-inspired schema-aware answerability analysis using one local LLM call."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined

from agentic_text2sql.adapters.llm.base import StructuredLLM
from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import (
    AMBIGUOUS_CATEGORIES,
    UNANSWERABLE_CATEGORIES,
    AnswerabilityDecision,
    AnswerabilityOutcome,
    ClarificationContext,
    Interpretation,
    NormalizedQuestion,
    QuestionAnalysisPrediction,
    QuestionCategory,
)

QUESTION_ANALYST_PROMPT_VERSION = "question_analyst_v1"


class QuestionAnalyst:
    def __init__(
        self,
        provider: StructuredLLM,
        template_path: Path,
        glossary_path: Path | None = None,
    ) -> None:
        self.provider = provider
        self.template_path = template_path
        self.glossary_path = glossary_path

    def analyze(
        self,
        question: NormalizedQuestion,
        catalog: CatalogSnapshot,
        clarification: ClarificationContext | None = None,
    ) -> AnswerabilityDecision:
        template = Environment(undefined=StrictUndefined, autoescape=False).from_string(
            self.template_path.read_text(encoding="utf-8")
        )
        prompt = template.render(
            question=question.model_dump_json(indent=2),
            clarification=(clarification.model_dump_json(indent=2) if clarification else "null"),
            catalog=json.dumps(_bounded_catalog(catalog), ensure_ascii=False, indent=2),
            business_glossary=json.dumps(
                _bounded_glossary(self.glossary_path, catalog.db_id),
                ensure_ascii=False,
                indent=2,
            ),
            output_schema=json.dumps(
                QuestionAnalysisPrediction.model_json_schema(), ensure_ascii=False
            ),
        )
        prediction = self.provider.generate_structured(
            prompt=prompt, response_model=QuestionAnalysisPrediction
        )
        return decision_from_prediction(prediction)


def decision_from_prediction(prediction: QuestionAnalysisPrediction) -> AnswerabilityDecision:
    interpretations: tuple[Interpretation, ...]
    if prediction.category is QuestionCategory.ANSWERABLE:
        outcome = AnswerabilityOutcome.ANSWER
        interpretations = (prediction.interpretations[0],)
    elif prediction.category in AMBIGUOUS_CATEGORIES:
        outcome = AnswerabilityOutcome.CLARIFY
        interpretations = prediction.interpretations
    elif prediction.category in UNANSWERABLE_CATEGORIES:
        outcome = AnswerabilityOutcome.CANNOT_ANSWER
        interpretations = prediction.interpretations
    else:
        raise ValueError(f"Unsupported local-LLM category: {prediction.category}")
    return AnswerabilityDecision(
        outcome=outcome,
        reason_code=prediction.category,
        rationale=prediction.rationale,
        interpretations=interpretations,
        clarification_question=prediction.clarification_question,
        clarification_options=prediction.clarification_options,
        missing_evidence=prediction.missing_evidence,
        source="local_llm",
    )


def _bounded_glossary(path: Path | None, db_id: str, budget_chars: int = 5000) -> object:
    """Load bounded domain rules; fail closed to an empty mapping on invalid config."""
    if path is None or not path.is_file():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(payload, dict) or payload.get("dataset_id") != db_id:
        return {}
    encoded = json.dumps(payload, ensure_ascii=False)
    if len(encoded) <= budget_chars:
        return payload
    concepts = payload.get("concepts")
    if not isinstance(concepts, dict):
        return {}
    bounded: dict[str, object] = {
        "dataset_id": db_id,
        "unsupported_concepts": payload.get("unsupported_concepts", []),
        "concepts": {},
        "truncated": True,
    }
    for key, value in concepts.items():
        candidate = dict(bounded)
        candidate["concepts"] = {**bounded["concepts"], key: value}  # type: ignore[dict-item]
        if len(json.dumps(candidate, ensure_ascii=False)) > budget_chars:
            break
        bounded = candidate
    return bounded


def _bounded_catalog(catalog: CatalogSnapshot, budget_chars: int = 8000) -> dict[str, object]:
    """Expose schema/FK metadata only; never rows, gold SQL, or benchmark labels."""
    tables: list[dict[str, object]] = []
    used = len(catalog.db_id) + len(catalog.dialect) + 100
    truncated = False
    for table in catalog.tables[:60]:
        entry: dict[str, object] = {
            "name": table.name,
            "kind": table.kind,
            "columns": [],
            "foreign_keys": [],
        }
        base_cost = len(table.name) + len(table.kind) + 60
        if used + base_cost > budget_chars:
            truncated = True
            break
        used += base_cost
        columns: list[str] = []
        for column in table.columns:
            cost = len(column.name) + 4
            if used + cost > budget_chars:
                truncated = True
                break
            columns.append(column.name)
            used += cost
        entry["columns"] = columns
        foreign_keys: list[dict[str, object]] = []
        for foreign_key in table.foreign_keys:
            payload: dict[str, object] = {
                "from": list(foreign_key.from_columns),
                "to_table": foreign_key.target_table,
                "to": list(foreign_key.target_columns),
            }
            cost = len(json.dumps(payload, ensure_ascii=False))
            if used + cost > budget_chars:
                truncated = True
                break
            foreign_keys.append(payload)
            used += cost
        entry["foreign_keys"] = foreign_keys
        tables.append(entry)
        if truncated:
            break
    if len(tables) < len(catalog.tables):
        truncated = True
    return {
        "db_id": catalog.db_id,
        "dialect": catalog.dialect,
        "tables": tables,
        "truncated": truncated,
    }
