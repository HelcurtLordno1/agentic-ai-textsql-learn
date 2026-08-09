"""Build stable retrieval documents from an introspected catalog."""

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.retrieval import CatalogDocument


def build_documents(
    catalog: CatalogSnapshot, aliases: dict[str, str] | None = None
) -> tuple[CatalogDocument, ...]:
    aliases = aliases or {}
    documents: list[CatalogDocument] = []
    for table in catalog.tables:
        table_neighbors = tuple(sorted({fk.target_table for fk in table.foreign_keys}))
        documents.append(
            CatalogDocument(
                document_id=f"{catalog.db_id}.{table.name}",
                db_id=catalog.db_id,
                kind="table",
                table=table.name,
                description=aliases.get(table.name, f"table {table.name}"),
                neighbors=table_neighbors,
                catalog_hash=catalog.catalog_hash,
            )
        )
        pk_names = {column.name for column in table.columns if column.primary_key_position}
        for column in table.columns:
            key = f"{table.name}.{column.name}"
            neighbors = []
            for fk in table.foreign_keys:
                for source, target in zip(fk.from_columns, fk.target_columns, strict=True):
                    if source == column.name:
                        neighbors.append(f"{fk.target_table}.{target}")
            key_note = " primary key" if column.name in pk_names else ""
            documents.append(
                CatalogDocument(
                    document_id=f"{catalog.db_id}.{key}",
                    db_id=catalog.db_id,
                    kind="column",
                    table=table.name,
                    column=column.name,
                    data_type=column.data_type,
                    description=aliases.get(key, f"column {column.name} in {table.name}{key_note}"),
                    neighbors=tuple(sorted(neighbors)),
                    catalog_hash=catalog.catalog_hash,
                )
            )
        for number, fk in enumerate(table.foreign_keys):
            pairs = tuple(
                f"{table.name}.{source}={fk.target_table}.{target}"
                for source, target in zip(fk.from_columns, fk.target_columns, strict=True)
            )
            documents.append(
                CatalogDocument(
                    document_id=f"{catalog.db_id}.{table.name}.fk{number}",
                    db_id=catalog.db_id,
                    kind="relationship",
                    table=table.name,
                    description="foreign key " + " ".join(pairs),
                    neighbors=pairs,
                    catalog_hash=catalog.catalog_hash,
                )
            )
    return tuple(sorted(documents, key=lambda item: item.document_id))
