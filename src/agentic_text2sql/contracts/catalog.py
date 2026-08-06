"""Schema catalog contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ColumnInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    data_type: str
    nullable: bool = True
    primary_key_position: int = 0


class ForeignKeyInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    from_columns: tuple[str, ...]
    target_table: str
    target_columns: tuple[str, ...]


class IndexInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    unique: bool
    columns: tuple[str, ...]


class TableInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    kind: str = "table"
    columns: tuple[ColumnInfo, ...]
    foreign_keys: tuple[ForeignKeyInfo, ...] = ()
    indexes: tuple[IndexInfo, ...] = ()


class CatalogSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    db_id: str
    dialect: str = "sqlite"
    tables: tuple[TableInfo, ...]
    catalog_hash: str = Field(min_length=8)
