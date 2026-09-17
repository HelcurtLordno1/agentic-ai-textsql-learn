"""Bounded champion--challenger orchestration for research-safe hybrid promotion."""

from __future__ import annotations

import signal
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from pydantic import ValidationError

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import AdaptiveRoute, LogicalPlan
from agentic_text2sql.contracts.semantics import BindingStatus, SemanticBinding, SemanticCatalog
from agentic_text2sql.contracts.sql import (
    CandidateArbitration,
    CandidateSelection,
    DirectRunResult,
    DirectStatus,
)
from agentic_text2sql.layer1_reasoning.adaptive_routing import choose_adaptive_route
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer
from agentic_text2sql.layer2_grounding.semantic_catalog import resolve_semantic_binding
from agentic_text2sql.layer3_generation.easy_compiler import (
    GROUNDED_EASY_COMPILER_MODEL,
    GROUNDED_EASY_COMPILER_VERSION,
)
from agentic_text2sql.layer4_validation.binding_validator import validate_sql_against_binding


class QueryRuntime(Protocol):
    def run(self, question: str, database: Path, catalog: CatalogSnapshot) -> DirectRunResult: ...


@runtime_checkable
class BaselinePlanAwareRuntime(Protocol):
    def run_from_baseline_plan(
        self,
        question: str,
        database: Path,
        catalog: CatalogSnapshot,
        baseline_plan: LogicalPlan,
    ) -> DirectRunResult: ...


def _fingerprint(result: DirectRunResult) -> str | None:
    return result.candidate.fingerprint if result.candidate is not None else None


def _proven_binding(result: DirectRunResult) -> SemanticBinding | None:
    if result.plan is None or "semantic_links" not in result.plan:
        return None
    links = result.plan.get("semantic_links")
    if not isinstance(links, dict):
        return None
    payload = links.get("binding")
    if not isinstance(payload, dict):
        return None
    try:
        binding = SemanticBinding.model_validate(payload)
    except ValidationError:
        return None
    return binding if binding.status is BindingStatus.PROVEN else None


def incumbent_control_plan(result: DirectRunResult) -> LogicalPlan | None:
    """Recover only a typed baseline plan; malformed/absent state fails closed."""
    if result.plan is None or "complexity" in result.plan:
        return None
    try:
        return LogicalPlan.model_validate(result.plan)
    except ValidationError:
        return None


def admits_adaptive_intervention(
    question: str,
    incumbent: DirectRunResult,
    catalog: CatalogSnapshot,
) -> bool:
    """Admit DIN only from the same schema-agnostic structural policy used by hybrid runtime."""
    del catalog
    plan = incumbent_control_plan(incumbent)
    if plan is None:
        return False
    decomposition = Decomposer().decompose(question)
    return (
        choose_adaptive_route(question, decomposition, plan).route is AdaptiveRoute.DIN_SQL_ENHANCE
    )


def admits_proven_semantic_intervention(
    question: str,
    incumbent: DirectRunResult,
    catalog: CatalogSnapshot,
    *,
    semantic_catalog: SemanticCatalog,
) -> bool:
    """Admit only interventions capable of producing a catalog-proven typed proof."""
    if incumbent_control_plan(incumbent) is None:
        return False
    decomposition = Decomposer().decompose(question)
    binding = resolve_semantic_binding(question, decomposition, catalog, semantic_catalog)
    return binding.status is BindingStatus.PROVEN


class ChallengerDeadlineExceeded(TimeoutError):
    """The optional challenger exhausted its enforceable wall-clock budget."""


class ChallengerDeadlineUnavailable(RuntimeError):
    """The execution context cannot safely interrupt a blocking challenger call."""


@contextmanager
def challenger_wall_clock_deadline(seconds: float) -> Iterator[None]:
    """Interrupt blocking local HTTP before the outer guarded batch deadline."""
    if seconds <= 0:
        raise ChallengerDeadlineExceeded
    if threading.current_thread() is not threading.main_thread() or not hasattr(
        signal, "setitimer"
    ):
        raise ChallengerDeadlineUnavailable
    prior_delay, prior_interval = signal.getitimer(signal.ITIMER_REAL)
    if prior_delay > 0 or prior_interval > 0:
        raise ChallengerDeadlineUnavailable
    prior_handler = signal.getsignal(signal.SIGALRM)

    def expire(_signum: int, _frame: object) -> None:
        raise ChallengerDeadlineExceeded

    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prior_handler)


class CandidateArbitrator:
    """Apply a deterministic commit rule without benchmark labels or model confidence."""

    def __init__(self, certified_proof_kinds: frozenset[str] = frozenset()) -> None:
        self.certified_proof_kinds = certified_proof_kinds

    @staticmethod
    def proof_kind(binding: SemanticBinding) -> str:
        if binding.frequency_ranking is not None:
            return "frequency_ranking"
        if binding.aggregate is not None:
            return f"aggregate:{binding.aggregate.operator.value.casefold()}"
        raise ValueError("proven binding has no typed proof")

    def decide(
        self,
        incumbent: DirectRunResult,
        challenger: DirectRunResult,
        *,
        mode: Literal["shadow", "enforce"],
        elapsed_ms: float,
    ) -> CandidateArbitration:
        binding = _proven_binding(challenger)
        rule_ids = binding.rule_ids if binding is not None else ()
        proof_kind = self.proof_kind(binding) if binding is not None else None
        incumbent_contradictions = (
            validate_sql_against_binding(incumbent.candidate.normalized_sql, binding)
            if binding is not None and incumbent.candidate is not None
            else ()
        )
        challenger_contradictions = (
            validate_sql_against_binding(challenger.candidate.normalized_sql, binding)
            if binding is not None and challenger.candidate is not None
            else ()
        )
        deterministic_proof_candidate = bool(
            challenger.candidate is not None
            and challenger.candidate.model_name == GROUNDED_EASY_COMPILER_MODEL
            and challenger.candidate.prompt_version == GROUNDED_EASY_COMPILER_VERSION
        )

        def decision(
            selection: CandidateSelection,
            reason: str,
            *,
            proof_accepted: bool = False,
        ) -> CandidateArbitration:
            return CandidateArbitration(
                mode=mode,
                selection=selection,
                reason=reason,
                incumbent_status=incumbent.status,
                challenger_status=challenger.status,
                incumbent_fingerprint=_fingerprint(incumbent),
                challenger_fingerprint=_fingerprint(challenger),
                incumbent_candidate=incumbent.candidate,
                incumbent_result_columns=incumbent.result_columns,
                incumbent_result_rows=incumbent.result_rows,
                challenger_candidate=challenger.candidate,
                challenger_result_columns=challenger.result_columns,
                challenger_result_rows=challenger.result_rows,
                challenger_rule_ids=rule_ids,
                challenger_proof_kind=proof_kind,
                challenger_proof_accepted=proof_accepted,
                incumbent_contradictions=incumbent_contradictions,
                challenger_contradictions=challenger_contradictions,
                elapsed_ms=elapsed_ms,
            )

        if challenger.status is not DirectStatus.SUCCEEDED:
            return decision(CandidateSelection.KEEP_INCUMBENT, "CHALLENGER_NOT_SUCCESSFUL")
        if binding is None or challenger.plan_validation is None:
            return decision(
                CandidateSelection.KEEP_INCUMBENT,
                "CHALLENGER_LACKS_PROVEN_PLAN",
            )
        if not bool(challenger.plan_validation.get("accepted")):
            return decision(CandidateSelection.KEEP_INCUMBENT, "CHALLENGER_PLAN_NOT_ACCEPTED")
        if not deterministic_proof_candidate:
            return decision(
                CandidateSelection.KEEP_INCUMBENT,
                "CHALLENGER_NOT_DETERMINISTIC_PROOF_COMPILER",
            )
        if challenger_contradictions:
            return decision(
                CandidateSelection.KEEP_INCUMBENT,
                "CHALLENGER_SQL_CONTRADICTS_PROOF",
            )
        if mode == "shadow":
            return decision(
                CandidateSelection.KEEP_INCUMBENT,
                "SHADOW_MODE_NEVER_CHANGES_OUTPUT",
                proof_accepted=True,
            )
        proof_kind = self.proof_kind(binding)
        if proof_kind not in self.certified_proof_kinds:
            return decision(
                CandidateSelection.KEEP_INCUMBENT,
                f"UNCERTIFIED_PROOF_KIND:{proof_kind}",
                proof_accepted=True,
            )
        if incumbent.status is DirectStatus.SUCCEEDED and not incumbent_contradictions:
            return decision(
                CandidateSelection.KEEP_INCUMBENT,
                "INCUMBENT_ALREADY_ACCEPTED",
                proof_accepted=True,
            )
        reason = (
            f"CERTIFIED_CHALLENGER_REPAIRS_CONTRADICTION:{proof_kind}"
            if incumbent_contradictions
            else f"CERTIFIED_CHALLENGER_RECOVERS_TERMINAL:{proof_kind}"
        )
        return decision(CandidateSelection.PROMOTE_CHALLENGER, reason, proof_accepted=True)


class ChampionChallengerService:
    """Run two bounded paths sequentially and preserve P6 output in shadow mode."""

    def __init__(
        self,
        *,
        incumbent: QueryRuntime,
        challenger: QueryRuntime,
        mode: Literal["shadow", "enforce"],
        total_deadline_seconds: float,
        minimum_challenger_seconds: float,
        arbitrator: CandidateArbitrator,
        admission: Callable[[str, DirectRunResult, CatalogSnapshot], bool] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if minimum_challenger_seconds >= total_deadline_seconds:
            raise ValueError("challenger reserve must be smaller than the total deadline")
        self.incumbent = incumbent
        self.challenger = challenger
        self.mode = mode
        self.total_deadline_seconds = total_deadline_seconds
        self.minimum_challenger_seconds = minimum_challenger_seconds
        self.arbitrator = arbitrator
        self.admission = admission
        self.monotonic = monotonic

    def run(self, question: str, database: Path, catalog: CatalogSnapshot) -> DirectRunResult:
        started = self.monotonic()
        incumbent = self.incumbent.run(question, database, catalog)
        elapsed = self.monotonic() - started
        remaining = self.total_deadline_seconds - elapsed
        admission_reason = (
            "NO_PROVEN_SEMANTIC_INTERVENTION"
            if self.admission is not None and not self.admission(question, incumbent, catalog)
            else None
        )

        def skip(reason: str, elapsed_seconds: float) -> DirectRunResult:
            arbitration = CandidateArbitration(
                mode=self.mode,
                selection=CandidateSelection.SKIP_CHALLENGER,
                reason=reason,
                incumbent_status=incumbent.status,
                incumbent_fingerprint=_fingerprint(incumbent),
                incumbent_candidate=incumbent.candidate,
                incumbent_result_columns=incumbent.result_columns,
                incumbent_result_rows=incumbent.result_rows,
                elapsed_ms=elapsed_seconds * 1000,
            )
            return incumbent.model_copy(update={"arbitration": arbitration})

        if admission_reason is not None or remaining < self.minimum_challenger_seconds:
            return skip(
                admission_reason or "INSUFFICIENT_CHALLENGER_DEADLINE_RESERVE",
                elapsed,
            )

        baseline_plan = incumbent_control_plan(incumbent)
        try:
            with challenger_wall_clock_deadline(remaining):
                challenger = (
                    self.challenger.run_from_baseline_plan(
                        question, database, catalog, baseline_plan
                    )
                    if baseline_plan is not None
                    and isinstance(self.challenger, BaselinePlanAwareRuntime)
                    else self.challenger.run(question, database, catalog)
                )
        except ChallengerDeadlineUnavailable:
            return skip("CHALLENGER_DEADLINE_UNENFORCEABLE", self.monotonic() - started)
        except ChallengerDeadlineExceeded:
            return skip("CHALLENGER_DEADLINE_EXHAUSTED", self.monotonic() - started)
        except Exception as exc:
            return skip(f"CHALLENGER_EXCEPTION:{type(exc).__name__}", self.monotonic() - started)
        elapsed_ms = (self.monotonic() - started) * 1000
        arbitration = self.arbitrator.decide(
            incumbent,
            challenger,
            mode=self.mode,
            elapsed_ms=elapsed_ms,
        )
        selected = (
            challenger
            if arbitration.selection is CandidateSelection.PROMOTE_CHALLENGER
            else incumbent
        )
        combined_timings = {
            **selected.latency_ms,
            "champion_challenger_total": elapsed_ms,
            "incumbent_total": incumbent.latency_ms.get("total", 0),
            "challenger_total": challenger.latency_ms.get("total", 0),
        }
        return selected.model_copy(
            update={"latency_ms": combined_timings, "arbitration": arbitration}
        )
