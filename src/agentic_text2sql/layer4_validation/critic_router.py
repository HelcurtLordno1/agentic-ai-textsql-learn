"""Gold-independent routing with a fixed, deterministic shadow audit sample."""

from __future__ import annotations

import hashlib

from sqlglot import exp

from agentic_text2sql.contracts.assessment import CandidateEvaluation, RoutingDecision
from agentic_text2sql.layer4_validation.parser import parse_one


def route_critic(
    question: str,
    evaluation: CandidateEvaluation,
    *,
    enabled: bool,
    shadow_sample_rate: float = 0,
    seed: int = 42,
    compute_policy: str = "legacy",
    production_repair: bool = False,
    contract_eligible: bool = False,
) -> RoutingDecision:
    if not enabled or not evaluation.validation.accepted:
        return RoutingDecision(call_critic=False)
    reasons: list[str] = []
    if evaluation.checks.contradictions:
        reasons.append("deterministic_contradiction")
    if any(f.code == "SIBLING_JOIN_GRAIN_UNKNOWN" for f in evaluation.checks.findings):
        reasons.append("join_grain")
    sql = evaluation.candidate.normalized_sql if evaluation.candidate else evaluation.raw_sql
    statement = parse_one(sql)
    if any(statement.find(kind) is not None for kind in (exp.Subquery, exp.CTE, exp.Window)):
        reasons.append("complex_scope")
    if isinstance(statement, exp.SetOperation):
        reasons.append("set_operation")
    if statement.find(exp.Where) is not None:
        reasons.append("predicate_binding")
    if evaluation.result is not None and not evaluation.result.rows:
        reasons.append("empty_result_unknown")
    if evaluation.result is not None and evaluation.result.truncated:
        reasons.append("preview_truncated")
    digest = hashlib.sha256(f"{seed}\0{question}".encode()).digest()
    sampled = int.from_bytes(digest[:8], "big") / 2**64 < shadow_sample_rate
    if sampled:
        reasons.append("fixed_shadow_sample")
    if compute_policy == "obligation" and production_repair:
        # Actionable edits already have CPU feedback; reserve compute for repair.
        # Unsupported risks stay unknown. A separate shadow sample estimates blind spots.
        if contract_eligible:
            return RoutingDecision(call_critic=False, reasons=("compute_reserved_for_contract",))
        return RoutingDecision(
            call_critic=sampled,
            reasons=tuple([*reasons, "no_admissible_semantic_edit"]),
            shadow_sample=sampled,
        )
    return RoutingDecision(call_critic=bool(reasons), reasons=tuple(reasons), shadow_sample=sampled)
