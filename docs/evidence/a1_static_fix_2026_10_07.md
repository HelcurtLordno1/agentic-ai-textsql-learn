# A1 static dependency/type fix — 2026-10-07

Người dùng gửi log `make check` dừng ở mypy với 22 lỗi. `uv sync --frozen --group dev`
bỏ 32 packages UI/API; cả `mypy src` và API tests cần extra `ui`. Một lỗi độc lập là
`Expression.selects`: property này không có trên base AST type.

Đã thêm guard `isinstance(statement, exp.Select)` trước projection alias binding; các AST root
khác không nhận metric proof. Không dùng type ignore hoặc tắt strict mypy. Make sync/check
targets chọn `--frozen --extra ui --group dev`; thêm `format`, `check-static`; pytest runner
dùng `python -m pytest`. CI sử dụng cùng Make targets. Không đổi pyproject/uv.lock hoặc thêm SDK.

Đã chạy thực tế trong WSL workspace:

```text
make sync
Installed 32 packages (including FastAPI/Uvicorn/Streamlit)

make check-static
ruff check: All checks passed!
ruff format --check: 266 files already formatted
mypy src: Success: no issues found in 118 source files
```

Đã gọi `--help` cho `tmux_experiment.py`, `run_guarded_spider.py`,
`run_guarded_acceptance.py`: cả ba exit code 0. Chỉ parse help; không tạo tmux session,
không đọc/chạy dataset hay instantiate inference runtime. `make -n check` chỉ in commands,
không chạy pytest. Không gọi `make check`, pytest, SQLite evaluation, model, benchmark,
GPU monitor hoặc thay clock/power. Không có prediction mới và không sửa/xóa checkpoint.

Source fingerprints tại lúc kiểm tra:

| File | SHA-256 |
|---|---|
| `rank_binding.py` | `bf516fcaf8bc6f76ed519f4276d568c05a78da1665b5aaf12e79eec7744c20ca` |
| `Makefile` | `0cb749a1d71ae1dbf8c550bc9cc4457ee6cb1e68085edeaa151cd69738b9884a` |
| `.github/workflows/ci.yml` | `f923af7dadfe2b00c4d77236c56e746a8f0afedbfb869d939b4d69982e495e7c` |

Static error log đã được xử lý; full test suite, tmux lifecycle, hardware pilot và research
evidence vẫn chưa verified. Gate A1 giữ `IN_PROGRESS` trong canonical ledger.
Commands bàn giao: [run_commands_2026_10_07.md](../run_commands_2026_10_07.md).
