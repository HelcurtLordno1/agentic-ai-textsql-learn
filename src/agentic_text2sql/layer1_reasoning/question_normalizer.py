"""Lossless bilingual normalization before question reliability analysis."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from agentic_text2sql.contracts.planning import NormalizedQuestion

_VIETNAMESE_MARKERS = frozenset(
    {"bao", "ban", "cao", "co", "doanh", "don", "giao", "hang", "khach", "nhieu", "theo"}
)
_ENGLISH_MARKERS = frozenset(
    {"average", "by", "count", "customer", "how", "many", "order", "revenue", "show", "what"}
)
_TYPO_ALIASES = {
    "catagory": "category",
    "custumer": "customer",
    "oder": "order",
    "revanue": "revenue",
}
_PHRASE_ALIASES = {
    "bang khach hang": "customer state",
    "da duoc giao": "order status delivered",
    "da huy": "order status canceled",
    "danh muc": "category",
    "doanh thu san pham": "product revenue",
    "don hang": "order",
    "khach hang": "customer",
    "nguoi ban": "seller",
    "phi van chuyen": "freight",
    "san pham ban": "sold item",
    "so don": "order count",
    "trang thai": "status",
    "tung thang": "monthly",
}


class QuestionNormalizer:
    def normalize(self, question: str) -> NormalizedQuestion:
        raw = question
        normalized = " ".join(unicodedata.normalize("NFKC", raw).split())
        if not normalized:
            # The public API rejects this; the runtime still needs a typed fail-closed path.
            normalized = "?"
        folded = _strip_diacritics(normalized.casefold())
        tokens = re.findall(r"[a-z0-9_]+", folded)
        aliases: list[str] = []
        corrected = []
        for token in tokens:
            replacement = _TYPO_ALIASES.get(token, token)
            if replacement != token:
                aliases.append(f"{token}->{replacement}")
            corrected.append(replacement)
        search_text = " ".join(corrected)
        for phrase, replacement in _PHRASE_ALIASES.items():
            if phrase in search_text:
                aliases.append(f"{phrase}->{replacement}")
                search_text = search_text.replace(phrase, replacement)
        return NormalizedQuestion(
            raw_text=raw if raw else "?",
            normalized_text=normalized,
            search_text=search_text or normalized.casefold(),
            question_language=_language(normalized),
            aliases_applied=tuple(dict.fromkeys(aliases)),
        )


def _strip_diacritics(value: str) -> str:
    value = value.replace("đ", "d")
    return "".join(
        character
        for character in unicodedata.normalize("NFD", value)
        if unicodedata.category(character) != "Mn"
    )


def _language(value: str) -> Literal["vi", "en", "other"]:
    folded = _strip_diacritics(value.casefold())
    tokens = set(re.findall(r"[a-z]+", folded))
    vi_score = len(tokens & _VIETNAMESE_MARKERS)
    en_score = len(tokens & _ENGLISH_MARKERS)
    if vi_score > en_score:
        return "vi"
    if en_score:
        return "en"
    return "other"
