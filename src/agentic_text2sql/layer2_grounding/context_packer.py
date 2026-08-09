"""Greedy stable context packing with a hard estimated-token budget."""

from agentic_text2sql.contracts.retrieval import RankedDocument


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def pack_candidates(
    candidates: list[RankedDocument], token_budget: int
) -> tuple[tuple[RankedDocument, ...], int]:
    if token_budget < 1:
        raise ValueError("token_budget must be positive")
    packed: list[RankedDocument] = []
    used = 0
    for candidate in candidates:
        cost = estimate_tokens(candidate.document.retrieval_text())
        if used + cost <= token_budget:
            packed.append(candidate)
            used += cost
    return tuple(packed), used
