"""Reproducible Olist download, verification, SQLite build, and validation."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field

from agentic_text2sql.exceptions import Text2SQLError
from agentic_text2sql.settings import Settings

KAGGLE_DOWNLOAD_URL = "https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce"
LOAD_ORDER = (
    "olist_customers_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_geolocation_dataset.csv",
    "product_category_name_translation.csv",
)
CSV_TO_TABLE = {name: name.removesuffix(".csv") for name in LOAD_ORDER}


class DataContractError(Text2SQLError):
    """Raised when source or built data violates the pinned contract."""


class FileContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(gt=0)
    rows: int = Field(gt=0)
    headers: list[str]


class SourceManifest(BaseModel):
    model_config = ConfigDict(extra="allow")
    dataset_id: str
    source_url: str
    license: str
    snapshot_version: int
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_filename: str
    redistribution: bool
    files: dict[str, FileContract]


class SourceVerification(BaseModel):
    model_config = ConfigDict(frozen=True)
    archive_sha256: str
    file_sha256: dict[str, str]
    row_counts: dict[str, int]


class BuildReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    database: Path
    manifest: Path
    source_archive_sha256: str
    schema_sha256: str
    logical_sha256: str
    row_counts: dict[str, int]


class ValidationCheck(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    passed: bool
    detail: str


class OlistValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    database: Path
    checks: tuple[ValidationCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def load_source_manifest(path: Path) -> SourceManifest:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SourceManifest.model_validate(payload)


def download_olist(
    destination: Path,
    manifest: SourceManifest,
    *,
    url: str = KAGGLE_DOWNLOAD_URL,
    client: httpx.Client | None = None,
) -> Path:
    """Download to a partial file, verify it, and atomically publish the archive."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(f"{destination.suffix}.part")
    start = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={start}-"} if start else {}
    owns_client = client is None
    active_client = client or httpx.Client(follow_redirects=True, timeout=120)
    try:
        with active_client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()
            append = start > 0 and response.status_code == httpx.codes.PARTIAL_CONTENT
            mode = "ab" if append else "wb"
            with partial.open(mode) as output:
                for chunk in response.iter_bytes(1024 * 1024):
                    output.write(chunk)
    except httpx.HTTPError as exc:
        raise DataContractError(f"Olist download failed: {type(exc).__name__}") from exc
    finally:
        if owns_client:
            active_client.close()
    actual = sha256_file(partial)
    if actual != manifest.archive_sha256:
        raise DataContractError(
            f"Archive SHA-256 mismatch: expected {manifest.archive_sha256}, got {actual}"
        )
    partial.replace(destination)
    return destination


def extract_and_verify_source(
    archive: Path, raw_dir: Path, manifest: SourceManifest
) -> SourceVerification:
    archive_hash = sha256_file(archive)
    if archive_hash != manifest.archive_sha256:
        raise DataContractError(
            f"Archive SHA-256 mismatch: expected {manifest.archive_sha256}, got {archive_hash}"
        )
    raw_dir.mkdir(parents=True, exist_ok=True)
    expected_names = set(manifest.files)
    try:
        with ZipFile(archive) as bundle:
            actual_names = {item.filename for item in bundle.infolist() if not item.is_dir()}
            if actual_names != expected_names:
                raise DataContractError(
                    f"Archive members mismatch: missing={sorted(expected_names - actual_names)}, "
                    f"extra={sorted(actual_names - expected_names)}"
                )
            for item in bundle.infolist():
                if item.is_dir():
                    continue
                if Path(item.filename).name != item.filename:
                    raise DataContractError(f"Unsafe archive member: {item.filename}")
                target = raw_dir / item.filename
                temporary = target.with_suffix(f"{target.suffix}.tmp")
                with bundle.open(item) as source, temporary.open("wb") as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
                temporary.replace(target)
    except BadZipFile as exc:
        raise DataContractError("Olist archive is not a valid ZIP file") from exc
    return verify_raw_files(raw_dir, manifest, archive_hash=archive_hash)


def verify_raw_files(
    raw_dir: Path, manifest: SourceManifest, *, archive_hash: str | None = None
) -> SourceVerification:
    actual_csv_names = {path.name for path in raw_dir.glob("*.csv")}
    expected_names = set(manifest.files)
    if actual_csv_names != expected_names:
        raise DataContractError(
            f"Raw CSV set mismatch: missing={sorted(expected_names - actual_csv_names)}, "
            f"extra={sorted(actual_csv_names - expected_names)}"
        )
    hashes: dict[str, str] = {}
    counts: dict[str, int] = {}
    for filename, contract in manifest.files.items():
        path = raw_dir / filename
        actual_hash = sha256_file(path)
        if actual_hash != contract.sha256:
            raise DataContractError(f"SHA-256 mismatch for {filename}")
        if path.stat().st_size != contract.bytes:
            raise DataContractError(f"Byte-size mismatch for {filename}")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            try:
                headers = next(reader)
            except StopIteration as exc:
                raise DataContractError(f"Empty source file: {filename}") from exc
            if headers != contract.headers:
                raise DataContractError(
                    f"Header mismatch for {filename}: expected={contract.headers}, got={headers}"
                )
            row_count = sum(1 for _ in reader)
        if row_count != contract.rows:
            raise DataContractError(
                f"Row-count mismatch for {filename}: expected={contract.rows}, got={row_count}"
            )
        hashes[filename] = actual_hash
        counts[filename] = row_count
    return SourceVerification(
        archive_sha256=archive_hash or manifest.archive_sha256,
        file_sha256=hashes,
        row_counts=counts,
    )


def money_to_cents(value: str) -> int:
    try:
        cents = Decimal(value).quantize(Decimal("0.01")) * 100
    except InvalidOperation as exc:
        raise DataContractError(f"Invalid monetary value: {value!r}") from exc
    if cents != cents.to_integral_value():
        raise DataContractError(f"Monetary value has sub-cent precision: {value!r}")
    return int(cents)


def _optional_int(value: str) -> int | None:
    return int(float(value)) if value else None


def _transform_rows(filename: str, reader: Iterable[list[str]]) -> Iterator[tuple[Any, ...]]:
    for row_number, row in enumerate(reader, start=1):
        if filename == "olist_order_items_dataset.csv":
            yield (*row, money_to_cents(row[5]), money_to_cents(row[6]))
        elif filename == "olist_order_payments_dataset.csv":
            yield (*row, money_to_cents(row[4]))
        elif filename == "olist_order_reviews_dataset.csv":
            yield (row_number, *row)
        elif filename == "olist_geolocation_dataset.csv":
            yield (row_number, int(row[0]), float(row[1]), float(row[2]), row[3], row[4])
        elif filename == "olist_customers_dataset.csv":
            yield (row[0], row[1], int(row[2]), row[3], row[4])
        elif filename == "olist_sellers_dataset.csv":
            yield (row[0], int(row[1]), row[2], row[3])
        elif filename == "olist_products_dataset.csv":
            yield (row[0], row[1] or None, *(_optional_int(value) for value in row[2:]))
        elif filename == "olist_order_payments_dataset.csv":
            yield (row[0], int(row[1]), row[2], int(row[3]), row[4], money_to_cents(row[4]))
        else:
            yield tuple(value or None for value in row)


def _insert_csv(connection: sqlite3.Connection, path: Path, contract: FileContract) -> int:
    table = CSV_TO_TABLE[path.name]
    target_columns = len(contract.headers)
    if path.name == "olist_order_items_dataset.csv":
        target_columns += 2
    if path.name == "olist_order_payments_dataset.csv":
        target_columns += 1
    if path.name in {"olist_order_reviews_dataset.csv", "olist_geolocation_dataset.csv"}:
        target_columns += 1
    placeholders = ",".join("?" for _ in range(target_columns))
    count = 0
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        headers = next(reader)
        if headers != contract.headers:
            raise DataContractError(f"Header changed during build: {path.name}")
        transformed = _transform_rows(path.name, reader)
        batch: list[tuple[Any, ...]] = []
        for row in transformed:
            batch.append(row)
            if len(batch) >= 5000:
                connection.executemany(f"INSERT INTO {table} VALUES ({placeholders})", batch)
                count += len(batch)
                batch.clear()
        if batch:
            connection.executemany(f"INSERT INTO {table} VALUES ({placeholders})", batch)
            count += len(batch)
    return count


def _git_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "uncommitted"
    return result.stdout.strip()


def logical_database_hash(database: Path, tables: Sequence[str]) -> str:
    digest = hashlib.sha256()
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        for table in sorted(tables):
            digest.update(table.encode())
            columns = connection.execute(f"PRAGMA table_info('{table}')").fetchall()
            digest.update(repr(columns).encode())
            for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
                digest.update(repr(tuple(row)).encode("utf-8", errors="surrogatepass"))
    finally:
        connection.close()
    return digest.hexdigest()


def build_olist_database(
    *,
    raw_dir: Path,
    output: Path,
    manifest_path: Path,
    schema_path: Path,
    indexes_path: Path,
    views_path: Path,
    build_manifest_path: Path | None = None,
) -> BuildReport:
    manifest = load_source_manifest(manifest_path)
    verification = verify_raw_files(raw_dir, manifest)
    schema_text = schema_path.read_text(encoding="utf-8")
    indexes_text = indexes_path.read_text(encoding="utf-8")
    views_text = views_path.read_text(encoding="utf-8")
    schema_hash = hashlib.sha256((schema_text + indexes_text + views_text).encode()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    publish_temporary = output.with_suffix(f"{output.suffix}.tmp")
    publish_temporary.unlink(missing_ok=True)
    counts: dict[str, int] = {}
    destination_manifest = build_manifest_path or output.with_suffix(".build.json")
    temporary_manifest = destination_manifest.with_suffix(f"{destination_manifest.suffix}.tmp")
    temporary_manifest.unlink(missing_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="agentic-text2sql-olist-") as work_directory:
            staged = Path(work_directory) / "olist.sqlite"
            connection = sqlite3.connect(staged)
            try:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA journal_mode=MEMORY")
                connection.execute("PRAGMA synchronous=OFF")
                connection.executescript(schema_text)
                connection.execute("BEGIN IMMEDIATE")
                for filename in LOAD_ORDER:
                    count = _insert_csv(connection, raw_dir / filename, manifest.files[filename])
                    expected = manifest.files[filename].rows
                    if count != expected:
                        raise DataContractError(
                            f"Loaded {count} rows for {filename}; expected {expected}"
                        )
                    counts[CSV_TO_TABLE[filename]] = count
                connection.commit()
                connection.executescript(indexes_text)
                connection.executescript(views_text)
                metadata = {
                    "dataset_id": manifest.dataset_id,
                    "source_archive_sha256": verification.archive_sha256,
                    "schema_sha256": schema_hash,
                    "timezone": "unknown",
                    "money_storage": "raw_decimal_text_plus_integer_cents",
                }
                connection.executemany("INSERT INTO build_metadata VALUES (?, ?)", metadata.items())
                foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
                if foreign_key_errors:
                    raise DataContractError(f"Foreign-key check failed: {foreign_key_errors[:5]}")
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                if integrity != ("ok",):
                    raise DataContractError(f"SQLite integrity check failed: {integrity}")
                connection.commit()
            finally:
                connection.close()
            raw_tables = tuple(CSV_TO_TABLE.values())
            logical_hash = logical_database_hash(staged, raw_tables)
            build_payload = {
                "dataset_id": manifest.dataset_id,
                "built_at": datetime.now(UTC).isoformat(),
                "source_archive_sha256": verification.archive_sha256,
                "source_file_sha256": verification.file_sha256,
                "schema_sha256": schema_hash,
                "logical_sha256": logical_hash,
                "row_counts": counts,
                "code_commit": _git_commit(Settings().project_root),
            }
            shutil.copyfile(staged, publish_temporary)
            copied = sqlite3.connect(f"file:{publish_temporary}?mode=ro", uri=True)
            try:
                if copied.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise DataContractError("Published database copy failed integrity check")
            finally:
                copied.close()
            temporary_manifest.write_text(
                json.dumps(build_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            os.replace(publish_temporary, output)
            os.replace(temporary_manifest, destination_manifest)
    except BaseException:
        publish_temporary.unlink(missing_ok=True)
        temporary_manifest.unlink(missing_ok=True)
        raise
    return BuildReport(
        database=output,
        manifest=destination_manifest,
        source_archive_sha256=verification.archive_sha256,
        schema_sha256=schema_hash,
        logical_sha256=logical_hash,
        row_counts=counts,
    )


def _scalar(connection: sqlite3.Connection, sql: str) -> Any:
    row = connection.execute(sql).fetchone()
    return None if row is None else row[0]


def validate_olist_database(database: Path, expected_counts_path: Path) -> OlistValidationReport:
    if not database.is_file():
        raise DataContractError(f"Olist database does not exist: {database}")
    expected_payload = yaml.safe_load(expected_counts_path.read_text(encoding="utf-8"))
    expected_counts: dict[str, int] = expected_payload["tables"]
    validation_directory = tempfile.TemporaryDirectory(prefix="agentic-text2sql-validate-")
    validation_copy = Path(validation_directory.name) / "olist.sqlite"
    shutil.copyfile(database, validation_copy)
    connection = sqlite3.connect(f"file:{validation_copy}?mode=ro", uri=True)
    checks: list[ValidationCheck] = []

    def check(name: str, actual: Any, expected: Any) -> None:
        checks.append(
            ValidationCheck(
                name=name,
                passed=actual == expected,
                detail=f"actual={actual!r}, expected={expected!r}",
            )
        )

    try:
        check("integrity_check", _scalar(connection, "PRAGMA integrity_check"), "ok")
        check(
            "foreign_key_check", len(connection.execute("PRAGMA foreign_key_check").fetchall()), 0
        )
        for table, expected in expected_counts.items():
            check(
                f"row_count:{table}",
                _scalar(connection, f'SELECT COUNT(*) FROM "{table}"'),
                expected,
            )
        check(
            "products_missing_category",
            _scalar(
                connection,
                "SELECT COUNT(*) FROM olist_products_dataset WHERE product_category_name IS NULL",
            ),
            610,
        )
        check(
            "duplicate_review_id_occurrences",
            _scalar(
                connection,
                "SELECT COUNT(*) - COUNT(DISTINCT review_id) FROM olist_order_reviews_dataset",
            ),
            814,
        )
        check(
            "repeated_order_review_rows_beyond_first",
            _scalar(
                connection,
                "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM olist_order_reviews_dataset",
            ),
            551,
        )
        check(
            "orders_with_multiple_review_rows",
            _scalar(
                connection,
                "SELECT COUNT(*) FROM (SELECT order_id FROM olist_order_reviews_dataset "
                "GROUP BY order_id HAVING COUNT(*) > 1)",
            ),
            547,
        )
        check(
            "item_revenue_preserved",
            _scalar(connection, "SELECT SUM(price_cents) FROM olist_order_items_dataset"),
            _scalar(connection, "SELECT SUM(product_revenue_cents) FROM order_item_totals"),
        )
        check(
            "freight_preserved",
            _scalar(connection, "SELECT SUM(freight_value_cents) FROM olist_order_items_dataset"),
            _scalar(connection, "SELECT SUM(freight_cents) FROM order_item_totals"),
        )
        check(
            "payment_preserved",
            _scalar(
                connection, "SELECT SUM(payment_value_cents) FROM olist_order_payments_dataset"
            ),
            _scalar(connection, "SELECT SUM(paid_value_cents) FROM order_payment_totals"),
        )
        check(
            "geo_centroid_unique",
            _scalar(
                connection,
                "SELECT COUNT(*) - COUNT(DISTINCT geolocation_zip_code_prefix) "
                "FROM geo_zip_centroids",
            ),
            0,
        )
        check(
            "raw_money_matches_cents",
            _scalar(
                connection,
                "SELECT COUNT(*) FROM olist_order_items_dataset "
                "WHERE CAST(ROUND(CAST(price AS REAL) * 100) AS INTEGER) != price_cents "
                "OR CAST(ROUND(CAST(freight_value AS REAL) * 100) AS INTEGER) "
                "!= freight_value_cents",
            ),
            0,
        )
    finally:
        connection.close()
        validation_directory.cleanup()
    return OlistValidationReport(database=database, checks=tuple(checks))


def default_olist_paths(settings: Settings | None = None) -> dict[str, Path]:
    config = settings or Settings()
    root = config.project_root
    return {
        "raw_dir": config.resolved_data_dir / "raw" / "olist",
        "archive": config.resolved_data_dir / "raw" / "olist" / "olist_brazilian_ecommerce.zip",
        "database": config.resolved_data_dir / "processed" / "olist.sqlite",
        "manifest": root / "datasets" / "olist" / "source_manifest.yaml",
        "schema": root / "datasets" / "olist" / "schema.sql",
        "indexes": root / "datasets" / "olist" / "indexes.sql",
        "views": root / "datasets" / "olist" / "derived_views.sql",
        "expected_counts": root / "datasets" / "olist" / "expected_counts.yaml",
    }
