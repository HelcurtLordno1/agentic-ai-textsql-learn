"""Deterministic weighted reciprocal-rank fusion."""


def reciprocal_rank_fusion(
    rankings: dict[str, list[tuple[int, float]]],
    weights: dict[str, float] | None = None,
    constant: int = 60,
) -> list[tuple[int, float, tuple[str, ...]]]:
    if constant < 1:
        raise ValueError("constant must be positive")
    weights = weights or {}
    scores: dict[int, float] = {}
    sources: dict[int, set[str]] = {}
    for source, ranking in rankings.items():
        for rank, (document_index, _) in enumerate(ranking, start=1):
            scores[document_index] = scores.get(document_index, 0.0) + weights.get(source, 1.0) / (
                constant + rank
            )
            sources.setdefault(document_index, set()).add(source)
    return sorted(
        ((index, score, tuple(sorted(sources[index]))) for index, score in scores.items()),
        key=lambda item: (-item[1], item[0]),
    )
