import sqlite3
from pathlib import Path

import pytest
import yaml

from datasets.synthetic_commerce.generator import build_database, logical_content_hash


def seed_path() -> Path:
    return Path(__file__).resolve().parents[2] / "datasets/synthetic_commerce/seed.yaml"


def test_synthetic_fixture_is_deterministic_and_integral(tmp_path: Path) -> None:
    first = tmp_path / "first.sqlite"
    second = tmp_path / "second.sqlite"
    first_hash = build_database(first, seed_path())
    second_hash = build_database(second, seed_path())

    assert first_hash == second_hash == logical_content_hash(first)
    connection = sqlite3.connect(first)
    try:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone() == (4,)
        assert connection.execute(
            "SELECT COUNT(*) FROM payments WHERE order_id = 'o001'"
        ).fetchone() == (2,)
    finally:
        connection.close()


def test_failed_build_does_not_replace_existing_database(tmp_path: Path) -> None:
    output = tmp_path / "fixture.sqlite"
    original_hash = build_database(output, seed_path())
    bad_seed = tmp_path / "bad.yaml"
    payload = yaml.safe_load(seed_path().read_text(encoding="utf-8"))
    payload["customers"] = []
    bad_seed.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="customers"):
        build_database(output, bad_seed)

    assert logical_content_hash(output) == original_hash
    assert not output.with_suffix(".sqlite.tmp").exists()
