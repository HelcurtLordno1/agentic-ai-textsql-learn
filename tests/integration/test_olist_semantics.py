import shutil
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OLIST = ROOT / "data/processed/olist.sqlite"


@pytest.fixture
def olist_connection(tmp_path: Path):
    if not OLIST.is_file():
        pytest.skip("canonical Olist database is not built")
    database = tmp_path / "olist.sqlite"
    shutil.copyfile(OLIST, database)
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    yield connection
    connection.close()


@pytest.mark.olist
def test_item_payment_preaggregation_prevents_fanout(olist_connection) -> None:
    raw_total = olist_connection.execute(
        "SELECT SUM(price_cents) FROM olist_order_items_dataset"
    ).fetchone()[0]
    safe_total = olist_connection.execute(
        "SELECT SUM(product_revenue_cents) FROM order_item_totals"
    ).fetchone()[0]
    naive_total = olist_connection.execute(
        "SELECT SUM(i.price_cents) FROM olist_order_items_dataset i "
        "JOIN olist_order_payments_dataset p ON p.order_id = i.order_id"
    ).fetchone()[0]
    assert raw_total == safe_total == 1359164370
    assert naive_total > raw_total


@pytest.mark.olist
def test_customer_identity_and_geolocation_grain(olist_connection) -> None:
    repeat_people = olist_connection.execute(
        "SELECT COUNT(*) FROM customer_order_facts WHERE order_count > 1"
    ).fetchone()[0]
    duplicate_centroids = olist_connection.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT geolocation_zip_code_prefix) FROM geo_zip_centroids"
    ).fetchone()[0]
    assert repeat_people == 2997
    assert duplicate_centroids == 0
