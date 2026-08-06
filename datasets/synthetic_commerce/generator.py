"""Build the small deterministic database used by CI and local tests."""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
from pathlib import Path
from typing import Any

import yaml

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT NOT NULL
);
CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    unit_price REAL NOT NULL CHECK (unit_price >= 0)
);
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    ordered_at TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE order_items (
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    item_number INTEGER NOT NULL,
    product_id TEXT NOT NULL REFERENCES products(product_id),
    price REAL NOT NULL,
    freight REAL NOT NULL,
    PRIMARY KEY (order_id, item_number)
);
CREATE TABLE payments (
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    sequence INTEGER NOT NULL,
    payment_type TEXT NOT NULL,
    amount REAL NOT NULL,
    PRIMARY KEY (order_id, sequence)
);
CREATE TABLE reviews (
    review_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5)
);
"""

TABLE_ORDER = ("customers", "products", "orders", "order_items", "payments", "reviews")


def load_seed(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Synthetic seed must be a mapping")
    return payload


def build_database(output: Path, seed_path: Path) -> str:
    """Build atomically and return the deterministic logical-content SHA-256."""
    seed = load_seed(seed_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        connection = sqlite3.connect(temporary)
        try:
            connection.executescript(SCHEMA)
            for table in TABLE_ORDER:
                rows = seed.get(table)
                if not isinstance(rows, list) or not rows:
                    raise ValueError(f"Synthetic seed table {table!r} must contain rows")
                placeholders = ", ".join("?" for _ in rows[0])
                connection.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise ValueError(f"Synthetic fixture has foreign-key violations: {violations}")
            connection.commit()
        finally:
            connection.close()
        temporary.replace(output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return logical_content_hash(output)


def logical_content_hash(database: Path) -> str:
    digest = hashlib.sha256()
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        for table in TABLE_ORDER:
            digest.update(table.encode())
            for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid"):
                digest.update(repr(tuple(row)).encode())
    finally:
        connection.close()
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=Path, required=True)
    args = parser.parse_args()
    digest = build_database(args.output, args.seed)
    print(f"built={args.output} logical_sha256={digest}")


if __name__ == "__main__":
    main()
