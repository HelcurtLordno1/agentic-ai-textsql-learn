"""Bounded question-reliability gate that is authoritative before SQL generation."""

from __future__ import annotations

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import (
    AnswerabilityDecision,
    AnswerabilityOutcome,
    ClarificationContext,
    ClarificationOption,
    Interpretation,
    NormalizedQuestion,
    QuestionCategory,
    RouteIntent,
)
from agentic_text2sql.exceptions import StructuredOutputError, Text2SQLError
from agentic_text2sql.layer1_reasoning.question_analyst import QuestionAnalyst
from agentic_text2sql.layer1_reasoning.question_normalizer import QuestionNormalizer
from agentic_text2sql.layer1_reasoning.router import QueryRouter


class QuestionReliabilityService:
    def __init__(
        self,
        normalizer: QuestionNormalizer,
        router: QueryRouter,
        analyst: QuestionAnalyst,
    ) -> None:
        self.normalizer = normalizer
        self.router = router
        self.analyst = analyst

    def evaluate(
        self,
        question: str,
        catalog: CatalogSnapshot,
        clarification: ClarificationContext | None = None,
    ) -> tuple[NormalizedQuestion, AnswerabilityDecision]:
        normalized = self.normalizer.normalize(question)
        deterministic = self._rule_first(normalized, catalog, clarification)
        if deterministic is not None:
            return normalized, deterministic
        try:
            decision = self.analyst.analyze(normalized, catalog, clarification)
            return normalized, _collapse_physical_only_ambiguity(decision)
        except (StructuredOutputError, Text2SQLError, ValueError):
            return normalized, _uncertain_decision(normalized.question_language)

    def _rule_first(
        self,
        question: NormalizedQuestion,
        catalog: CatalogSnapshot,
        clarification: ClarificationContext | None,
    ) -> AnswerabilityDecision | None:
        text_to_route = clarification.user_response if clarification else question.normalized_text
        route = self.router.route(text_to_route)
        if route.intent is RouteIntent.WRITE_REQUEST:
            return AnswerabilityDecision(
                outcome=AnswerabilityOutcome.SAFE_REJECT,
                reason_code=QuestionCategory.WRITE_REQUEST,
                rationale=route.reason,
                source="rule",
            )
        if route.intent is RouteIntent.UNSUPPORTED:
            return AnswerabilityDecision(
                outcome=AnswerabilityOutcome.SAFE_REJECT,
                reason_code=QuestionCategory.UNSUPPORTED_REQUEST,
                rationale=route.reason,
                source="rule",
            )
        if route.intent is RouteIntent.CLARIFY:
            asks_returns = _asks_returns(text_to_route)
            if catalog.db_id.casefold() == "olist" and asks_returns:
                return AnswerabilityDecision(
                    outcome=AnswerabilityOutcome.CANNOT_ANSWER,
                    reason_code=QuestionCategory.NONEXISTENT_SELECT_COLUMN,
                    rationale=(
                        "Olist contains order statuses but no return or refund fact; canceled "
                        "orders must not be treated as returns."
                    ),
                    missing_evidence=("return or refund event",),
                    source="rule",
                )
            if not asks_returns:
                vi = question.question_language == "vi"
                return AnswerabilityDecision(
                    outcome=AnswerabilityOutcome.CLARIFY,
                    reason_code=QuestionCategory.MISSING_INTENT,
                    rationale=route.reason,
                    clarification_question=(
                        "Bạn muốn đo chỉ số nào và cho nhóm đối tượng nào?"
                        if vi
                        else "Which metric and business population do you want?"
                    ),
                    clarification_options=(
                        ClarificationOption(
                            option_id="o1",
                            label=(
                                "Nêu chỉ số và đối tượng" if vi else "Specify metric and population"
                            ),
                        ),
                        ClarificationOption(
                            option_id="o2",
                            label=(
                                "Viết lại câu hỏi đầy đủ" if vi else "Restate the full question"
                            ),
                        ),
                    ),
                    source="rule",
                )
        status_decision = _explicit_olist_status_decision(question, catalog)
        if status_decision is not None:
            return status_decision
        return None


def _collapse_physical_only_ambiguity(decision: AnswerabilityDecision) -> AnswerabilityDecision:
    """Do not ask users to choose between physically equivalent schema implementations."""
    if (
        decision.outcome is not AnswerabilityOutcome.CLARIFY
        or decision.reason_code is not QuestionCategory.AMBIGUOUS_SELECT_COLUMN
        or len(decision.interpretations) < 2
    ):
        return decision
    semantic_shapes = {
        (
            item.metric.casefold() if item.metric else None,
            tuple(value.casefold() for value in item.dimensions),
            tuple(value.casefold() for value in item.filters),
            item.grain.casefold() if item.grain else None,
        )
        for item in decision.interpretations
    }
    if len(semantic_shapes) != 1:
        return decision
    accepted = decision.interpretations[0].model_copy(update={"assumptions": ()})
    return decision.model_copy(
        update={
            "outcome": AnswerabilityOutcome.ANSWER,
            "reason_code": QuestionCategory.ANSWERABLE,
            "rationale": (
                "The interpretations differ only by physical schema implementation; "
                "the accepted business meaning is unchanged."
            ),
            "interpretations": (accepted,),
            "clarification_question": None,
            "clarification_options": (),
        }
    )


def _asks_returns(value: str) -> bool:
    folded = value.casefold()
    return any(
        phrase in folded
        for phrase in (
            "return rate",
            "returns",
            "returned",
            "refund",
            "trả hàng",
            "hoàn hàng",
            "hoàn tiền",
            "tỷ lệ trả",
        )
    )


def _explicit_olist_status_decision(
    question: NormalizedQuestion, catalog: CatalogSnapshot
) -> AnswerabilityDecision | None:
    if catalog.db_id.casefold() != "olist":
        return None
    text = f"{question.normalized_text.casefold()} {question.search_text}"
    if not any(token in text for token in ("order", "orders", "đơn hàng")):
        return None
    aliases = {
        "delivered": (
            "order status delivered",
            "delivered status",
            "status delivered",
            "delivered",
        ),
        "canceled": (
            "order status canceled",
            "canceled",
            "cancelled",
            "đã hủy",
            "da huy",
        ),
        "unavailable": ("order status unavailable", "unavailable status"),
    }
    status = next(
        (
            canonical
            for canonical, values in aliases.items()
            if any(value in text for value in values)
        ),
        None,
    )
    if status == "delivered" and any(
        marker in text for marker in ("late", "timestamp", "non-null", "not null", "is not null")
    ):
        return None
    if status is None:
        return None
    return AnswerabilityDecision(
        outcome=AnswerabilityOutcome.ANSWER,
        reason_code=QuestionCategory.ANSWERABLE,
        rationale=f"The request explicitly names the canonical Olist order status '{status}'.",
        interpretations=(
            Interpretation(
                interpretation_id="i1",
                metric="order count",
                filters=(f"order status {status}",),
                grain="order",
                business_label=f"Order count with {status} status",
            ),
        ),
        source="rule",
    )


def _uncertain_decision(language: str) -> AnswerabilityDecision:
    vi = language == "vi"
    return AnswerabilityDecision(
        outcome=AnswerabilityOutcome.CLARIFY,
        reason_code=QuestionCategory.ANALYSIS_UNCERTAIN,
        rationale="The local question analyst could not produce a valid bounded decision.",
        clarification_question=(
            "Bạn có thể xác nhận chỉ số, phạm vi và khoảng thời gian cần phân tích không?"
            if vi
            else "Can you confirm the metric, population, and time range to analyze?"
        ),
        clarification_options=(
            ClarificationOption(
                option_id="o1", label=("Bổ sung phạm vi" if vi else "Add business scope")
            ),
            ClarificationOption(
                option_id="o2", label=("Viết lại yêu cầu" if vi else "Restate the request")
            ),
        ),
        source="fail_closed",
    )
