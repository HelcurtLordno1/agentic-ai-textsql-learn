"""Narrow question-bound output edits; unsupported language always abstains."""

from __future__ import annotations

import re

from sqlglot import exp

from agentic_text2sql.contracts.assessment import RepairContract
from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.layer4_validation.parser import parse_one

VERSION = "question-output-contract-v1"
PROJECTION_CODE = "REQUESTED_OUTPUT_PROJECTION"
RANK_CODE = "REQUESTED_GROUP_COUNT_RANKING"
SCALAR_CODE = "REQUESTED_SCALAR_AGGREGATE"


def words(value: str) -> set[str]:
    tokens = re.findall(r"[^\W_]+", value.casefold())
    return {
        token[:-3] + "y"
        if token.endswith("ies") and len(token) > 4
        else token[:-1]
        if token.endswith("s") and not token.endswith("ss") and len(token) > 3
        else token
        for token in tokens
    }


def _simple(sql: str) -> exp.Select | None:
    tree = parse_one(sql)
    if not isinstance(tree, exp.Select) or any(
        tree.find(kind) is not None for kind in (exp.Subquery, exp.CTE, exp.Window)
    ):
        return None
    if any(item.is_star for item in tree.selects):
        return None
    if tree.args.get("distinct") or tree.args.get("offset"):
        return None
    return tree


def _requested_head(question: str) -> str | None:
    # Take an explicit final instruction over a preceding explanatory question.
    instructions = list(
        re.finditer(r"\b(?:list|return|show|give)\s+(?:me\s+)?(?:the\s+)?([^.!?]+)", question, re.I)
    )
    if instructions:
        head = instructions[-1].group(1)
    else:
        match = re.match(r"\s*what\s+(?:is|are)\s+(?:the\s+)?([^.!?]+)", question, re.I)
        if match is None:
            return None
        head = match.group(1)
    parts = re.split(
        r"\b(?:of|that|who|with|from|for|which|having|ordered|sorted)\b",
        head,
        maxsplit=1,
        flags=re.I,
    )
    head = parts[0]
    if len(parts) > 1 and re.search(r"\band\b|,|\balong with\b", parts[1], re.I):
        return None
    if len(parts) > 1 and re.search(r"\bwith\b", parts[1], re.I):
        if not re.search(
            r"\bwith\s+(?:the\s+)?(?:most|least|highest|lowest|greatest|smallest|largest)\b",
            parts[1],
            re.I,
        ):
            return None
    if re.search(r"\bwith\b", question, re.I) and not re.search(
        r"\bwith\s+(?:the\s+)?(?:most|least|highest|lowest|greatest|smallest|largest)\b",
        question,
        re.I,
    ):
        return None
    if not head.strip() or re.search(
        r"\b(?:count|number|many|much|average|mean|sum|total|minimum|maximum|both|all)\b",
        head,
        re.I,
    ):
        return None
    return head.strip()


def _projection(question: str, tree: exp.Select, catalog: CatalogSnapshot) -> exp.Select | None:
    head = _requested_head(question)
    if head is None or len(tree.selects) < 2:
        return None
    # Do not change scalar-aggregate cardinality or nested lexical scopes.
    if tree.find(exp.AggFunc) is not None and tree.args.get("group") is None:
        return None
    requested = words(head) - {"the", "a", "an", "only", "distinct", "different", "and", "s"}
    aliases = {source.alias_or_name: source.name for source in tree.find_all(exp.Table)}
    tables = {table.name: table for table in catalog.tables}
    bindings: dict[tuple[str, str], set[str]] = {}
    for owner in aliases.values():
        table = tables.get(owner)
        if table is None:
            return None
        for column in table.columns:
            terms = words(column.name)
            if terms and terms.issubset(requested):
                bindings[(owner, column.name)] = terms
    # Every requested term must be a bound column or an explicitly named source.
    entity_terms = set().union(*(words(name) for name in aliases.values()))
    covered = set().union(*bindings.values()) if bindings else set()
    if not covered or requested - covered - entity_terms:
        return None
    # Ambiguous name owners cannot be selected from the draft's guesses.
    for terms in bindings.values():
        if sum(other == terms for other in bindings.values()) != 1:
            return None
    keep: list[exp.Expression] = []
    dropped: list[exp.Expression] = []
    matched: set[tuple[str, str]] = set()
    for item in tree.selects:
        value = item.this if isinstance(item, exp.Alias) else item
        binding = None
        if isinstance(value, exp.Column):
            owners = (
                [aliases[value.table]]
                if value.table in aliases
                else [owner for owner, name in bindings if name == value.name]
                if not value.table
                else []
            )
            if len(owners) == 1:
                binding = (owners[0], value.name)
        if binding in bindings:
            keep.append(item.copy())
            matched.add(binding)
        else:
            dropped.append(item)
    if not dropped or matched != set(bindings) or len(keep) != len(bindings):
        return None
    # Ordinal references would change meaning after dropping/reordering outputs.
    for key in ("order", "group"):
        clause = tree.args.get(key)
        if clause is not None and any(
            isinstance(node, exp.Literal) and node.is_int for node in clause.walk()
        ):
            return None
    repaired = tree.copy()
    # Preserve ORDER BY/HAVING aliases of removed metrics by expanding expressions.
    for item in dropped:
        if not isinstance(item, exp.Alias):
            continue
        if sum(output.alias == item.alias for output in tree.selects) != 1:
            return None
        if any(column.name == item.alias for table in tables.values() for column in table.columns):
            return None
        for key in ("order", "having", "group"):
            clause = repaired.args.get(key)
            if clause is not None:
                repaired.set(
                    key,
                    clause.transform(
                        lambda node, output=item: (
                            output.this.copy()
                            if isinstance(node, exp.Column)
                            and not node.table
                            and node.name == output.alias
                            else node
                        )
                    ),
                )
    repaired.set("expressions", keep)
    return repaired


def _group_count_rank(
    question: str, tree: exp.Select, catalog: CatalogSnapshot
) -> exp.Select | None:
    """Add count ranking only for an explicit singular request with a tie policy."""
    if any(tree.find(kind) is not None for kind in (exp.Join, exp.Subquery, exp.CTE, exp.Window)):
        return None
    if any(tree.args.get(key) is not None for key in ("distinct", "offset", "having")):
        return None
    if re.search(r"\b(?:not|without|except|all ties|không|trừ|đồng hạng)\b", question, re.I):
        return None
    rank = re.search(r"\b(nhiều|ít)\s+(.+?)\s+nhất\b", question, re.I)
    tie = re.search(r"\bh[oò]a\s+thì\s+(.+?)\s+(tăng|giảm)\s+dần\b", question, re.I)
    if rank is None or tie is None:
        return None
    # A singular 'which' request + tie-break licenses one winner, not all ties.
    if not re.search(r"\bnào\b", question, re.I):
        return None
    if re.search(r"\d|\b(?:all|mọi|tất cả)\b", question, re.I):
        return None
    group = tree.args.get("group")
    sources = list(tree.find_all(exp.Table))
    if not isinstance(group, exp.Group) or len(group.expressions) != 1 or len(sources) != 1:
        return None
    table = next((table for table in catalog.tables if table.name == sources[0].name), None)
    if table is None or table.kind != "table":
        return None
    primary = [column.name for column in table.columns if column.primary_key_position]
    if len(primary) != 1:
        return None
    # Generic bilingual entity words; no database/table names or benchmark IDs.
    entities = {
        "đơn": "order",
        "đơn hàng": "order",
        "sản phẩm": "product",
        "khách hàng": "customer",
        "nhân viên": "employee",
        "sinh viên": "student",
        "vé": "ticket",
        "review": "review",
    }
    noun = rank.group(2).casefold()
    entity = next((value for term, value in entities.items() if noun.startswith(term)), None)
    if entity is None or entity not in words(table.name):
        return None
    aggregates = list(tree.find_all(exp.AggFunc))
    if not aggregates or any(not isinstance(node, exp.Count) for node in aggregates):
        return None
    count = aggregates[0]
    if any(node != count for node in aggregates) or not (
        isinstance(count.this, exp.Star)
        or (
            isinstance(count.this, exp.Column)
            and count.this.name == primary[0]
            and any(c.name == primary[0] and not c.nullable for c in table.columns)
        )
    ):
        return None
    key = group.expressions[0]
    if isinstance(key, exp.Column) and not key.table:
        projected = [item for item in tree.selects if item.alias_or_name == key.name]
        if len(projected) != 1:
            return None
        key = projected[0].this if isinstance(projected[0], exp.Alias) else projected[0]
    tie_terms = words(tie.group(1))
    if isinstance(key, exp.Column):
        if not words(key.name).issubset(tie_terms):
            return None
    elif isinstance(key, exp.TimeToStr):
        # SQLite STRFTIME('%Y-%m', timestamp) is a month grouping, not a row index.
        if (
            not isinstance(key.args.get("format"), exp.Literal)
            or key.args["format"].this != "%Y-%m"
        ):
            return None
        if not tie_terms.intersection({"month", "tháng"}):
            return None
    else:
        return None
    if any(
        isinstance(item, exp.Column) and item.name not in {column.name for column in table.columns}
        for item in key.find_all(exp.Column)
    ):
        return None
    return (
        tree.copy()
        .order_by(
            exp.Ordered(
                this=count.copy(), desc=rank.group(1).casefold() == "nhiều", nulls_first=False
            ),
            exp.Ordered(this=key.copy(), desc=tie.group(2).casefold() == "giảm", nulls_first=True),
            append=False,
        )
        .limit(1)
    )


def _scalar_average(question: str, tree: exp.Select, catalog: CatalogSnapshot) -> exp.Select | None:
    """Compile an explicit unfiltered scalar AVG over one uniquely named raw metric."""
    match = re.fullmatch(
        r"\s*what\s+is\s+(?:the\s+)?(?:average|mean)\s+([\w ]+?)\s+"
        r"rounded\s+to\s+([0-8])\s+decimals?\s*[?.]?\s*",
        question,
        re.I,
    )
    if match is None or tree.find(exp.AggFunc) is not None or tree.find(exp.Join) is not None:
        return None
    if any(
        tree.args.get(key) is not None for key in ("where", "group", "having", "order", "limit")
    ):
        return None
    metric_words = words(match.group(1))
    owners = [
        (table.name, column.name)
        for table in catalog.tables
        if table.kind == "table"
        for column in table.columns
        if words(column.name) == metric_words
        and column.data_type.upper() in {"INT", "INTEGER", "REAL", "FLOAT", "DOUBLE", "NUMERIC"}
    ]
    if len(owners) != 1:
        return None
    owner, column = owners[0]
    value = exp.Round(
        this=exp.Avg(this=exp.column(column, table=owner, quoted=True)),
        decimals=exp.Literal.number(match.group(2)),
    )
    return exp.select(value).from_(exp.to_table(owner, quoted=True))


def compile_output_contract(question: str, sql: str, catalog: CatalogSnapshot) -> RepairContract:
    unknown = RepairContract(version=VERSION, eligible=False, reason="No unambiguous output edit")
    tree = parse_one(sql)
    if not isinstance(tree, exp.Select):
        return unknown
    simple = _simple(sql)
    if simple is None:
        return unknown
    repaired = _projection(question, simple, catalog)
    code = PROJECTION_CODE
    if repaired is None:
        repaired = _group_count_rank(question, simple, catalog)
        code = RANK_CODE
    if repaired is None:
        repaired = _scalar_average(question, simple, catalog)
        code = SCALAR_CODE
    if repaired is None or repaired == tree:
        return unknown
    return RepairContract(
        version=VERSION,
        eligible=True,
        reason="Question-bound output edit with independently bound fields and bounded scope",
        evidence_ids=("question", "catalog:" + catalog.catalog_hash),
        question_spans=(question[:200],),
        target_codes=(code,),
        allowed_fields=("select",)
        if code == PROJECTION_CODE
        else ("select", "from")
        if code == SCALAR_CODE
        else ("order", "limit"),
        planned_sql=repaired.sql(dialect="sqlite"),
    )
