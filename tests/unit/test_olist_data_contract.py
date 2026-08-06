from agentic_text2sql.data.olist import _transform_rows, money_to_cents


def test_money_uses_exact_decimal_cents() -> None:
    assert money_to_cents("10.10") == 1010
    assert money_to_cents("0.01") == 1


def test_order_item_transform_matches_nine_schema_columns() -> None:
    source = [["o", "1", "p", "s", "2018-01-01 00:00:00", "10.10", "0.01"]]
    transformed = list(_transform_rows("olist_order_items_dataset.csv", source))
    assert len(transformed[0]) == 9
    assert transformed[0][-2:] == (1010, 1)


def test_payment_transform_matches_six_schema_columns() -> None:
    source = [["o", "1", "credit_card", "2", "10.10"]]
    transformed = list(_transform_rows("olist_order_payments_dataset.csv", source))
    assert len(transformed[0]) == 6
    assert transformed[0][-1] == 1010
