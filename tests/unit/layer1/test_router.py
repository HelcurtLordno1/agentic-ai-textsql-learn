import pytest

from agentic_text2sql.contracts.planning import RouteIntent
from agentic_text2sql.layer1_reasoning.router import QueryRouter

CASES = [
    ("How many orders were delivered?", RouteIntent.QUERY),
    ("Tổng doanh thu sản phẩm là bao nhiêu?", RouteIntent.QUERY),
    ("Top 5 categories by revenue", RouteIntent.QUERY),
    ("Số khách hàng quay lại", RouteIntent.QUERY),
    ("Average review score", RouteIntent.QUERY),
    ("Orders in 2017", RouteIntent.QUERY),
    ("Freight by state", RouteIntent.QUERY),
    ("Which seller has most items?", RouteIntent.QUERY),
    ("Payment type counts", RouteIntent.QUERY),
    ("Late delivery rate", RouteIntent.QUERY),
    ("DELETE FROM orders", RouteIntent.WRITE_REQUEST),
    ("Drop table customers", RouteIntent.WRITE_REQUEST),
    ("Update every customer record", RouteIntent.WRITE_REQUEST),
    ("Insert a new order", RouteIntent.WRITE_REQUEST),
    ("Alter table products", RouteIntent.WRITE_REQUEST),
    ("Xóa dữ liệu đơn hàng", RouteIntent.WRITE_REQUEST),
    ("Thêm bản ghi vào bảng orders", RouteIntent.WRITE_REQUEST),
    ("Cập nhật dữ liệu khách hàng", RouteIntent.WRITE_REQUEST),
    ("Hello", RouteIntent.UNSUPPORTED),
    ("Xin chào", RouteIntent.UNSUPPORTED),
    ("Thanks", RouteIntent.UNSUPPORTED),
    ("Cảm ơn", RouteIntent.UNSUPPORTED),
    ("What is the return rate?", RouteIntent.CLARIFY),
    ("How many refunds occurred?", RouteIntent.CLARIFY),
    ("Tỷ lệ trả hàng", RouteIntent.CLARIFY),
    ("Có bao nhiêu đơn hoàn tiền?", RouteIntent.CLARIFY),
    ("", RouteIntent.CLARIFY),
    ("?", RouteIntent.CLARIFY),
    ("Compare paid value and revenue", RouteIntent.QUERY),
    ("Danh mục có review thấp nhất", RouteIntent.QUERY),
    ("Return the payment type and count", RouteIntent.QUERY),
]


@pytest.mark.parametrize(("question", "expected"), CASES)
def test_router_bilingual_fixtures(question: str, expected: RouteIntent) -> None:
    assert QueryRouter().route(question).intent is expected


def test_all_explicit_write_fixtures_are_recognized() -> None:
    writes = [case for case in CASES if case[1] is RouteIntent.WRITE_REQUEST]
    assert writes
    assert all(
        QueryRouter().route(question).intent is RouteIntent.WRITE_REQUEST for question, _ in writes
    )
