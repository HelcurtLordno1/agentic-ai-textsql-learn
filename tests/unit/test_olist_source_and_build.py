import csv
import hashlib
import sqlite3
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest
import yaml

from agentic_text2sql.data.olist import (
    DataContractError,
    SourceManifest,
    build_olist_database,
    download_olist,
    extract_and_verify_source,
)

ROOT = Path(__file__).resolve().parents[2]

TINY_FILES = {
    "olist_customers_dataset.csv": [
        [
            "customer_id",
            "customer_unique_id",
            "customer_zip_code_prefix",
            "customer_city",
            "customer_state",
        ],
        ["c1", "u1", "12345", "city", "SP"],
    ],
    "olist_orders_dataset.csv": [
        [
            "order_id",
            "customer_id",
            "order_status",
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
        [
            "o1",
            "c1",
            "delivered",
            "2018-01-01 00:00:00",
            "2018-01-01 01:00:00",
            "2018-01-02 00:00:00",
            "2018-01-03 00:00:00",
            "2018-01-04 00:00:00",
        ],
    ],
    "olist_products_dataset.csv": [
        [
            "product_id",
            "product_category_name",
            "product_name_lenght",
            "product_description_lenght",
            "product_photos_qty",
            "product_weight_g",
            "product_length_cm",
            "product_height_cm",
            "product_width_cm",
        ],
        ["p1", "cat", "3", "4", "1", "100", "10", "5", "5"],
    ],
    "olist_sellers_dataset.csv": [
        ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"],
        ["s1", "12345", "city", "SP"],
    ],
    "olist_order_items_dataset.csv": [
        [
            "order_id",
            "order_item_id",
            "product_id",
            "seller_id",
            "shipping_limit_date",
            "price",
            "freight_value",
        ],
        ["o1", "1", "p1", "s1", "2018-01-02 00:00:00", "10.10", "0.90"],
    ],
    "olist_order_payments_dataset.csv": [
        ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"],
        ["o1", "1", "card", "1", "11.00"],
    ],
    "olist_order_reviews_dataset.csv": [
        [
            "review_id",
            "order_id",
            "review_score",
            "review_comment_title",
            "review_comment_message",
            "review_creation_date",
            "review_answer_timestamp",
        ],
        ["r1", "o1", "5", "", "ok", "2018-01-04 00:00:00", "2018-01-05 00:00:00"],
    ],
    "olist_geolocation_dataset.csv": [
        [
            "geolocation_zip_code_prefix",
            "geolocation_lat",
            "geolocation_lng",
            "geolocation_city",
            "geolocation_state",
        ],
        ["12345", "-23.0", "-46.0", "city", "SP"],
    ],
    "product_category_name_translation.csv": [
        ["product_category_name", "product_category_name_english"],
        ["cat", "category"],
    ],
}


def write_tiny_source(directory: Path) -> Path:
    directory.mkdir()
    contracts = {}
    for name, rows in TINY_FILES.items():
        path = directory / name
        with path.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerows(rows)
        contracts[name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
            "rows": len(rows) - 1,
            "headers": rows[0],
        }
    manifest = {
        "dataset_id": "olistbr/brazilian-ecommerce",
        "source_url": "https://example.test/olist",
        "license": "CC-BY-NC-SA-4.0",
        "snapshot_version": 2,
        "archive_sha256": "0" * 64,
        "archive_filename": "olist.zip",
        "redistribution": False,
        "files": contracts,
    }
    manifest_path = directory.parent / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return manifest_path


def test_download_rejects_bad_archive_hash(tmp_path: Path) -> None:
    manifest = SourceManifest.model_validate(
        {
            "dataset_id": "test",
            "source_url": "https://example.test",
            "license": "test",
            "snapshot_version": 1,
            "archive_sha256": "0" * 64,
            "archive_filename": "source.zip",
            "redistribution": False,
            "files": {},
        }
    )
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"bad"))
    )
    destination = tmp_path / "source.zip"
    with pytest.raises(DataContractError, match="SHA-256 mismatch"):
        download_olist(destination, manifest, client=client)
    assert not destination.exists()


def test_archive_rejects_extra_member(tmp_path: Path) -> None:
    archive = tmp_path / "source.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("unexpected.csv", "a\n1\n")
    manifest = SourceManifest.model_validate(
        {
            "dataset_id": "test",
            "source_url": "https://example.test",
            "license": "test",
            "snapshot_version": 1,
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "archive_filename": archive.name,
            "redistribution": False,
            "files": {},
        }
    )
    with pytest.raises(DataContractError, match="members mismatch"):
        extract_and_verify_source(archive, tmp_path / "raw", manifest)


def test_tiny_build_is_idempotent_and_failed_rebuild_preserves_output(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    manifest = write_tiny_source(raw)
    output = tmp_path / "olist.sqlite"
    kwargs = {
        "raw_dir": raw,
        "output": output,
        "manifest_path": manifest,
        "schema_path": ROOT / "datasets/olist/schema.sql",
        "indexes_path": ROOT / "datasets/olist/indexes.sql",
        "views_path": ROOT / "datasets/olist/derived_views.sql",
    }
    first = build_olist_database(**kwargs)
    second = build_olist_database(**kwargs)
    assert first.logical_sha256 == second.logical_sha256
    valid_bytes = output.read_bytes()

    item_path = raw / "olist_order_items_dataset.csv"
    rows = [row[:] for row in TINY_FILES["olist_order_items_dataset.csv"]]
    rows[1][2] = "unknown-product"
    with item_path.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows(rows)
    payload = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    payload["files"][item_path.name]["sha256"] = hashlib.sha256(item_path.read_bytes()).hexdigest()
    payload["files"][item_path.name]["bytes"] = item_path.stat().st_size
    manifest.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(sqlite3.IntegrityError):
        build_olist_database(**kwargs)
    assert output.read_bytes() == valid_bytes
    assert not output.with_suffix(".sqlite.tmp").exists()
