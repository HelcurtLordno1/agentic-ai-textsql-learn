"""Pinned Spider mini-set selection and integrity validation."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlglot import exp, parse_one


class SpiderMiniCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    dev_index: int = Field(ge=0)
    db_id: str
    case_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    complexity: Literal["easy", "medium", "hard", "extra"]


class SpiderMiniManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: int = 1
    dataset: str = "spider-dev"
    dev_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection: str
    case_count: int = 100
    cases: tuple[SpiderMiniCase, ...]


def case_hash(case: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"db_id": case["db_id"], "question": case["question"], "query": case["query"]},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def classify_complexity(sql: str) -> Literal["easy", "medium", "hard", "extra"]:
    expression = parse_one(sql, read="sqlite")
    table_count = sum(1 for _ in expression.find_all(exp.Table))
    select_count = sum(1 for _ in expression.find_all(exp.Select))
    join_count = sum(1 for _ in expression.find_all(exp.Join))
    set_count = sum(1 for _ in expression.find_all(exp.SetOperation))
    group_count = sum(1 for _ in expression.find_all(exp.Group))
    having_count = sum(1 for _ in expression.find_all(exp.Having))
    score = max(0, table_count - 1) + 2 * max(0, select_count - 1)
    score += join_count + 2 * set_count + group_count + having_count
    if score <= 1:
        return "easy"
    if score <= 3:
        return "medium"
    if score <= 5:
        return "hard"
    return "extra"


def create_manifest(
    dev_path: Path, *, excluded_indices: frozenset[int] = frozenset()
) -> SpiderMiniManifest:
    raw = dev_path.read_bytes()
    dev: list[dict[str, Any]] = json.loads(raw)
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, case in enumerate(dev):
        if index not in excluded_indices:
            grouped[str(case["db_id"])].append((index, case))
    quotas = {db_id: min(5, len(cases)) for db_id, cases in grouped.items()}
    deficit = 100 - sum(quotas.values())
    while deficit:
        candidates = [db_id for db_id, cases in grouped.items() if quotas[db_id] < len(cases)]
        if not candidates:
            raise ValueError("Spider dev does not contain 100 unique cases")
        chosen = max(candidates, key=lambda db_id: (len(grouped[db_id]) / quotas[db_id], db_id))
        quotas[chosen] += 1
        deficit -= 1
    selected: list[SpiderMiniCase] = []
    for db_id in sorted(grouped):
        ranked = sorted(
            grouped[db_id],
            key=lambda item: (
                ("easy", "medium", "hard", "extra").index(
                    classify_complexity(str(item[1]["query"]))
                ),
                case_hash(item[1]),
            ),
        )
        quota = quotas[db_id]
        positions = [math.floor((rank + 0.5) * len(ranked) / quota) for rank in range(quota)]
        for position in positions:
            dev_index, case = ranked[position]
            selected.append(
                SpiderMiniCase(
                    dev_index=dev_index,
                    db_id=db_id,
                    case_hash=case_hash(case),
                    complexity=classify_complexity(str(case["query"])),
                )
            )
    if len(selected) != 100 or len({case.dev_index for case in selected}) != 100:
        raise ValueError("mini manifest must contain exactly 100 unique dev rows")
    return SpiderMiniManifest(
        dev_sha256=hashlib.sha256(raw).hexdigest(),
        selection=(
            "domain-balanced deterministic AST-complexity quantiles"
            + (f" excluding {len(excluded_indices)} pinned rows" if excluded_indices else "")
        ),
        cases=tuple(selected),
    )


def load_manifest_cases(dev_path: Path, manifest_path: Path) -> list[dict[str, Any]]:
    raw = dev_path.read_bytes()
    manifest = SpiderMiniManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if hashlib.sha256(raw).hexdigest() != manifest.dev_sha256:
        raise ValueError("Spider dev checksum does not match mini manifest")
    dev: list[dict[str, Any]] = json.loads(raw)
    cases = []
    for selected in manifest.cases:
        case = dev[selected.dev_index]
        if str(case["db_id"]) != selected.db_id or case_hash(case) != selected.case_hash:
            raise ValueError(f"Spider mini case mismatch at dev row {selected.dev_index}")
        cases.append(case)
    if len(cases) != manifest.case_count or len({case_hash(case) for case in cases}) != len(cases):
        raise ValueError("Spider mini manifest contains duplicate or missing cases")
    return cases
