from pathlib import Path


def test_streamlit_observatory_uses_api_and_has_drag_resize_accessibility() -> None:
    root = Path(__file__).resolve().parents[3]
    source = (root / "apps/streamlit_app.py").read_text(encoding="utf-8")
    assert "LocalAPIClient" in source
    assert "sqlite3" not in source
    assert "sort_items" in source
    assert "resize:horizontal" in source
    assert "Keyboard users" in source
    assert "Save local feedback" in source
    assert "Failure categories" in source
    assert all(
        page in source
        for page in ("Query Studio", "Run Inspector", "History", "Benchmark Lab", "System Center")
    )
