"""Evidence-scoped semantic assessments; execution success is not semantic proof."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentic_text2sql.contracts.sql import CandidateRecord
from agentic_text2sql.contracts.validation import PolicyDecision, ResultPreview, ValidationReport


class CheckOutcome(StrEnum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTION = "CONTRADICTION"
    UNKNOWN = "UNKNOWN"


class SemanticEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: str
    kind: Literal["question", "catalog", "domain"]
    text: str = Field(max_length=12000)


class ClauseFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    code: str = Field(max_length=80)
    clause: Literal[
        "SELECT", "FROM", "JOIN", "WHERE", "GROUP BY", "HAVING", "ORDER BY", "LIMIT", "QUERY"
    ]
    outcome: CheckOutcome
    message: str = Field(max_length=600)
    evidence_ids: tuple[str, ...] = ()
    question_span: str | None = Field(default=None, max_length=200)
    source: Literal["deterministic", "model"] = "deterministic"


class ClauseAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    findings: tuple[ClauseFinding, ...] = ()
    semantic_status: Literal["UNVERIFIED", "CONTRADICTION"] = "UNVERIFIED"

    @property
    def contradictions(self) -> frozenset[str]:
        return frozenset(
            item.code
            for item in self.findings
            if item.source == "deterministic" and item.outcome is CheckOutcome.CONTRADICTION
        )


class ModelCritique(BaseModel):
    model_config = ConfigDict(extra="forbid")
    findings: list[ClauseFinding] = Field(default_factory=list, max_length=8)
    summary: str = Field(default="", max_length=600)


class CandidateEvaluation(BaseModel):
    """A snapshot for selection and offline diagnostics, including invalid drafts."""

    model_config = ConfigDict(extra="forbid")
    raw_sql: str
    candidate: CandidateRecord | None = None
    policy: PolicyDecision
    validation: ValidationReport
    checks: ClauseAssessment
    result: ResultPreview | None = None
    origin: Literal["model", "deterministic"] = "model"


class RepairContract(BaseModel):
    """A scoped edit license, never a proof of full semantic equivalence."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    version: str = "rank-edit-contract-v1"
    eligible: bool
    reason: str
    evidence_ids: tuple[str, ...] = ()
    question_spans: tuple[str, ...] = ()
    target_codes: tuple[str, ...] = ()
    allowed_fields: tuple[Literal["order", "limit"], ...] = ()
    metric: str | None = None
    planned_sql: str | None = None


class RoutingDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    call_critic: bool
    reasons: tuple[str, ...] = ()
    shadow_sample: bool = False


class PromptRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    estimated_tokens: int = Field(ge=0)
    output_token_cap: int = Field(ge=1)
    rendered_prompt: str | None = Field(default=None, max_length=12000)


class A1Trace(BaseModel):
    """Typed runtime trace; intentionally contains no evaluation IDs or gold labels."""

    model_config = ConfigDict(extra="forbid")
    pipeline: Literal["a1"] = "a1"
    trace_version: str = "a1-trace-v3"
    critic_mode: Literal["off", "shadow", "repair"]
    generation_format: Literal["json", "sql_text"]
    feedback_mode: Literal["grounded", "generic"] = "grounded"
    compute_policy: Literal["legacy", "obligation"] = "legacy"
    repairability_routing: bool = True
    semantic_status: Literal["UNVERIFIED", "CONTRADICTION"] = "UNVERIFIED"
    max_requests: int = Field(ge=1, le=3)
    actual_generation_requests: int = Field(default=0, ge=0, le=3)
    attempts: list[str] = Field(default_factory=list)
    evidence: tuple[SemanticEvidence, ...] = ()
    prompts: dict[str, PromptRecord] = Field(default_factory=dict)
    candidates: list[CandidateRecord] = Field(default_factory=list)
    evaluations: list[CandidateEvaluation] = Field(default_factory=list)
    draft_checks: ClauseAssessment | None = None
    draft_validation: ValidationReport | None = None
    repair_checks: ClauseAssessment | None = None
    repair_validation: ValidationReport | None = None
    model_findings: tuple[ClauseFinding, ...] = ()
    discarded_model_findings: int = Field(default=0, ge=0)
    critic_routed: bool = False
    routing: RoutingDecision | None = None
    repair_attempted: bool = False
    repair_contract: RepairContract | None = None
    repair_source: Literal["model", "deterministic"] | None = None
    repair_admitted: bool = False
    repair_reason: str | None = None
    repair_skipped_reason: str | None = None
    selection_reason: str = "draft"
    stage_errors: dict[str, str] = Field(default_factory=dict)
    executed_sql: str | None = None
    result_truncated: bool = False
    selected_candidate_index: int | None = None
    grounding_metadata: dict[str, Any] = Field(default_factory=dict)
