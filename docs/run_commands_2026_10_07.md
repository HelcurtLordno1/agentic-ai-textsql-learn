# Commands sau sửa lỗi dependency/type — 2026-10-07

Đã khôi phục UI/API packages và pass Ruff, format check, mypy 118 source files.
Agent chưa chạy pytest, dataset, model, benchmark hoặc tmux session. Các lệnh sau dành cho
người dùng chạy. [Evidence](evidence/a1_static_fix_2026_10_07.md); gate vẫn `IN_PROGRESS`.

## 1. WSL: chuẩn bị và kiểm tra tĩnh

```bash
cd '/mnt/d/desktop_informations/vnpt ai/agentic_text_to_sql'
make sync
make format
make check-static
```

`make sync` tương đương `uv sync --frozen --extra ui --group dev`. Extra `ui` chứa
FastAPI/Uvicorn cần cho type checking các API modules. Các Make targets chọn extra này
explicitly. `check-static` chỉ Ruff/format check/mypy; không pytest, SQL, dataset hay model.

Nếu muốn chạy **test suite đầy đủ không có marker Ollama**, chạy riêng:

```bash
make check
```

Lệnh này có pytest, gồm tests dùng SQLite synthetic và có thể đọc Olist local nếu DB tồn tại.
Nó không phải chỉ static check. Không sửa/format source sau khi experiment đã tạo checkpoint;
worker pin source hash và từ chối append nếu identity đổi.

## 2. Windows: Administrator hard clock cap

Mở PowerShell/CMD **Run as Administrator**, xác định GPU 0 đúng GPU dùng inference:

```powershell
nvidia-smi -L
nvidia-smi -i 0 -q -d CLOCK,POWER,SUPPORTED_CLOCKS
nvidia-smi -i 0 -lgc 300,800
nvidia-smi -i 0 -q -d CLOCK,POWER
nvidia-smi -i 0 --query-gpu=timestamp,clocks.current.graphics,temperature.gpu,power.draw,memory.used,utilization.gpu --format=csv -l 1
```

`Not Supported` hoặc lỗi permission không phải cap thành công. Giữ cửa sổ monitor khi pilot;
clock cap phải xác minh trên workload và không thay watchdog. Không nới thresholds: RAM≥14 GiB,
swap<0.25 GiB, VRAM<6 GiB, GPU<68°C, power<70W. Model offload một layer, batch một, cooldown 60s.
[NVIDIA docs](https://docs.nvidia.com/deploy/nvidia-smi/).

Ollama Windows cần có `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1`,
`OLLAMA_KEEP_ALIVE=0`; `.env` dùng đúng `OLLAMA_BASE_URL`, không đặt marker nội bộ
`TEXT2SQL_GUARDED_RUN=true`. Dữ liệu/index và model đã cài phải đúng cấu hình/digest đang pin.
Các commands này không download model hoặc tạo dataset.

Trước pilot/recovery, kiểm tra không có stale jobs và idle RAM/swap/GPU an toàn; worker guard
lấy sample trước và trong workload. Workload Olist Qwen3-14B đã chạm 78W vẫn cần hard cap và
pilot độc lập theo AGENTS; không bỏ latch bằng tên experiment mới hoặc wrapper mới.

## 3. Spider 200: pilot rồi resume hết suite

Tên/paths mới tránh trộn với source trước bản sửa. Chỉ tạo **một** experiment một lần.

```bash
uv run --frozen --extra ui --group dev python scripts/tmux_experiment.py run \
  --name a1-spider-20261007 --suite spider --variant obligation-cpu \
  --profile acceptance-safe --manifest evals/configs/spider-laptop-200.json \
  --predictions evals/predictions/a1-obligation-cpu-spider-200-20261007.jsonl \
  --report evals/reports/a1-obligation-cpu-spider-200-20261007.json \
  --allow-dirty-source --max-batches 1

tmux attach -t a1-spider-20261007
```

Chờ pilot `PAUSED` sau checkpoint/unload/cooldown; review resource peaks, cap và output trước
khi chạy phần còn lại. Detach **Ctrl+b rồi d**. Sau đó:

```bash
uv run --frozen --extra ui --group dev python scripts/tmux_experiment.py status --name a1-spider-20261007
uv run --frozen --extra ui --group dev python scripts/tmux_experiment.py resume --name a1-spider-20261007
tmux attach -t a1-spider-20261007
```

Resume không có max-batches chạy toàn bộ **case còn lại đến đủ 200**. Nếu session đang chạy,
resume chỉ báo attach, không thêm job. Nếu đã đủ và report hợp lệ, sẽ hiện:

```text
SUCCESS FINISH ALL: 200/200; report=...
```

Completion nghĩa checkpoint/report đủ manifest, không nghĩa accuracy 100% hoặc gate VERIFIED.
Logs tại `data/artifacts/experiments/a1-spider-20261007/run.log`.

## 4. Pause, attach và recovery

```bash
# Pause sau case hiện tại và cooldown, không kill giữa inference.
uv run --frozen --extra ui --group dev python scripts/tmux_experiment.py pause --name a1-spider-20261007
uv run --frozen --extra ui --group dev python scripts/tmux_experiment.py status --name a1-spider-20261007

# Chờ PAUSED, rồi tiếp tục:
uv run --frozen --extra ui --group dev python scripts/tmux_experiment.py resume --name a1-spider-20261007
tmux attach -t a1-spider-20261007
```

Detach/đóng client giữ tmux chạy; Ctrl+C trong pane gửi graceful pause. Đừng dùng kill-session
hoặc kill -9 để pause có kế hoạch. Sau mất điện/reboot/kill bất ngờ, kiểm tra stale jobs absent,
idle resources/cap safe rồi chạy tối đa một case recovery:

```bash
uv run --frozen --extra ui --group dev python scripts/tmux_experiment.py resume \
  --name a1-spider-20261007 --recovery-pilot
tmux attach -t a1-spider-20261007
```

Sau recovery pilot an toàn/PAUSED, dùng resume bình thường ở trên. Resource latch không bị
recovery flag xóa hoặc bypass. Source/config/.env/model/template/manifest/DB/index đổi thì
không append vào checkpoint cũ. Không xóa plan/predictions/latch để ép cùng experiment chạy lại.

## 5. Olist 60: chạy tuần tự sau Spider

```bash
uv run --frozen --extra ui --group dev python scripts/tmux_experiment.py run \
  --name a1-olist-20261007 --suite olist --variant obligation-cpu \
  --profile acceptance-safe --cases evals/configs/olist-acceptance-60.jsonl \
  --predictions evals/predictions/a1-obligation-cpu-olist-60-20261007.jsonl \
  --report evals/reports/a1-obligation-cpu-olist-60-20261007.json \
  --max-batches 1

tmux attach -t a1-olist-20261007
```

Sau pilot `PAUSED` và review resources:

```bash
uv run --frozen --extra ui --group dev python scripts/tmux_experiment.py resume --name a1-olist-20261007
tmux attach -t a1-olist-20261007
```

Pause/status/recovery giống Spider, thay `--name a1-olist-20261007`. Không chạy hai workloads
đồng thời. Report thành công cuối sẽ ghi `SUCCESS FINISH ALL: 60/60`.
