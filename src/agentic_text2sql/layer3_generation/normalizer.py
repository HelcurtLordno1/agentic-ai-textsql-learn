"""Syntax-only candidate cleanup and fingerprinting; never repairs semantics."""

from __future__ import annotations

import hashlib
import re

from sqlglot import exp

from agentic_text2sql.contracts.sql import CandidateRecord, SqlCandidate
from agentic_text2sql.layer4_validation.parser import SQLParseError, parse_one

FENCE = re.compile(r"^\s*```(?:sql)?\s*(.*?)\s*```\s*$", re.IGNORECASE | re.DOTALL)


class CandidateNormalizer:
    def normalize(
        self,
        candidate: SqlCandidate,
        *,
        model_name: str,
        prompt_version: str,
        catalog_hash: str,
        prompt_estimated_tokens: int = 0,
    ) -> CandidateRecord:
        sql = candidate.sql.strip()
        match = FENCE.fullmatch(sql)
        if match:
            sql = match.group(1).strip()
        sql = sql.rstrip().removesuffix(";").rstrip()
        statement = parse_one(sql)
        if not isinstance(statement, exp.Query):
            raise SQLParseError("Candidate must be a read query")
        normalized = statement.sql(dialect="sqlite")
        fingerprint = hashlib.sha256(normalized.encode()).hexdigest()
        clean_candidate = candidate.model_copy(update={"sql": normalized})
        return CandidateRecord(
            candidate=clean_candidate,
            normalized_sql=normalized,
            fingerprint=fingerprint,
            model_name=model_name,
            prompt_version=prompt_version,
            catalog_hash=catalog_hash,
            prompt_estimated_tokens=prompt_estimated_tokens,
        )
