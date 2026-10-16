"""Extract one final SQL artifact; never extract a query from hidden reasoning."""

import re

from agentic_text2sql.contracts.sql import SqlCandidate
from agentic_text2sql.exceptions import StructuredOutputError


def sql_text_candidate(content: str) -> SqlCandidate:
    if "<think>" in content:
        if "</think>" not in content:
            raise StructuredOutputError("SQL text response has incomplete reasoning tags")
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    fences = re.findall(r"```(?:sql)?\s*\n?(.*?)```", content, flags=re.I | re.S)
    if len(fences) > 1:
        raise StructuredOutputError("SQL text response has multiple candidate blocks")
    sql = fences[0].strip() if fences else content.strip()
    if not sql:
        raise StructuredOutputError("SQL text response is empty")
    return SqlCandidate(sql=sql, confidence=0, assumptions=["Semantic correctness is unverified"])
