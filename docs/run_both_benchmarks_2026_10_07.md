# Lịch sử: profile20 lớp chưa được pilot

**Lệnh hiện hành sau consent mới:** [full Qwen14B trên GPU16GiB](run_full_qwen14b_2026_10_07.md).
Các phần dưới giữ lịch sử remediation20 lớp, không phải run đang được triển khai.

Người dùng cho phép chạy ngày 07/10/2026, sau khi Administrator đã khóa xung
`nvidia-smi -i 0 -lgc 300,800`. Giữ Qwen3:14b-q4_K_M hiện có, không download model.
Lần pilot thực tế `a1-qwen-both-20261007` dùng 24 GPU layers đã dừng vì VRAM
6223 MiB >= 6144 MiB, trước khi có prediction. Peak Windows RAM khả dụng min16.545 GiB,
swap0, GPU53°C, power30.13 W, clock795 MHz. Cả hai guard đã dừng; native server/runner,
wrapper và proxy không còn, service Windows cũ idle. Không chạy pilot Olist hoặc full.
Latch và provenance cũ được giữ nguyên; **không resume session cũ**.

Source mới giảm offload xuống20 lớp để tạo thêm khoảng trống VRAM, vẫn giữ thresholds.
**Các lệnh dưới đây được chuẩn bị cho một pilot mới cần người dùng cho phép sau breach;
chưa chạy và chưa được xác nhận bằng model. Không đổi tên để retry cấu hình24 lớp.**
Phiên dự kiến: `a1-qwen20-both-20261007`, variant `obligation-cpu` (A1).

## Profile và giới hạn

`clock-capped-safe`: GPU offload **20 lớp**, 8 generation CPU threads,
context 4096, prefill `num_batch=64`, một request/model, KV q8_0,
flash attention, keep_alive=0, một case mỗi batch, unload và cooldown 60 giây.
20 lớp là giới hạn cấu hình cho pilot, không phải khẳng định trước rằng model sẽ vừa RAM.

Guard dừng ở RAM khả dụng <14 GiB (lấy min Windows/WSL), swap/pagefile ≥0.25 GiB,
VRAM ≥6144 MiB, nhiệt ≥65°C, power ≥65 W, xung >800 MHz hoặc monitor lỗi.
Power là max giá trị instantaneous và average. Không tự retry hay xóa resource stop latch.
Cấu hình này không dùng exception Olist 78 W trước đây.

Harness sở hữu riêng Windows Ollama ở WSL gateway:11436, qua proxy loopback:11435.
Gateway được xác định lại mỗi lần khởi động; URL và cấu hình checkpoint giữ nguyên.
Không đóng Ollama app/service cũ ở 11434, nhưng từ chối chạy nếu service đó đang giữ model.
Native server và descendants nằm trong Windows Job Object có KILL_ON_JOB_CLOSE;
guard Windows kiểm tra RAM/pagefile/GPU mỗi 0.5 giây và heartbeat harness.
Mất heartbeat >10 giây dừng owned server/runners và ghi latch. Guard wrapper riêng
cũng kiểm tra liên tục mỗi 0.5 giây trong workload. Không có khả năng bảo đảm tuyệt đối
trước lỗi driver, mất điện hoặc hệ điều hành; cơ chế này ưu tiên dừng bảo toàn checkpoint.

## Khởi tạo (chỉ dùng khi chưa có experiment)

```bash
cd '/mnt/d/desktop_informations/vnpt ai/agentic_text_to_sql'
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks run \
  --name a1-qwen20-both-20261007 \
  --models-dir /mnt/c/Users/ADMIN/.ollama/models --profile clock-capped-safe --max-batches 2
```

Hai batch đầu gồm một case Spider và một case Olist. Chỉ pilot có kết quả executable,
clock cap và resource journal hợp lệ mới được đánh dấu passed. Thành công executable
không chứng minh accuracy của toàn benchmark hoặc novelty của method.
Sau khi cả hai pilot sạch và phase PAUSED, chạy phần còn lại bằng một lệnh:

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume \
  --name a1-qwen20-both-20261007
```

Spider còn lại chạy trước, rồi Olist còn lại; mỗi case ghi checkpoint bền vững,
unload, cooldown. Chỉ khi cả hai báo cáo đủ IDs và cleanup thành công mới in:
`SUCCESS FINISH ALL: Spider 200/200 + Olist 60/60`.

## Monitor / detach

```bash
tmux attach -t a1-qwen20-both-20261007
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks status \
  --name a1-qwen20-both-20261007
```

Trong tmux: Ctrl+b, rồi d để detach; process vẫn chạy khi đóng terminal.
Log đầy đủ: `data/artifacts/experiments/a1-qwen20-both-20261007/run.log`.
Journal native: `server.samples.jsonl` trong cùng thư mục.
Checkpoint/report riêng từng benchmark dưới `evals/predictions/` và `evals/reports/`.

## Dừng trước khi tắt máy

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks pause \
  --name a1-qwen20-both-20261007
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks status \
  --name a1-qwen20-both-20261007
```

Chờ phase `PAUSED`, `worker_pid`, `server_pid`, `proxy_pid` đều null rồi tắt máy.
Pause chờ case đang chạy ghi checkpoint, unload và cooldown, không cắt giữa request.
Tắt đột ngột vẫn giữ các case đã fsync; case chưa ghi xong chưa được tính hoàn thành.

## Sau khởi động lại / shutdown bất ngờ

PowerShell **Administrator**, áp lại hard clock cap (không giả định cap còn sau reboot):

```powershell
nvidia-smi -i 0 -lgc 300,800
nvidia-smi -i 0 --query-gpu=clocks.current.graphics,temperature.gpu,memory.used,power.draw.instant,power.draw.average --format=csv
```

Trong WSL, harness kiểm tra stale jobs/idle resources; chạy đúng một case recovery trước:

```bash
cd '/mnt/d/desktop_informations/vnpt ai/agentic_text_to_sql'
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume \
  --name a1-qwen20-both-20261007 --recovery-pilot
tmux attach -t a1-qwen20-both-20261007
```

Sau recovery pilot sạch và PAUSED, resume cả hai benchmark đến cuối:

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume \
  --name a1-qwen20-both-20261007
tmux attach -t a1-qwen20-both-20261007
```

Nếu `RESOURCE_STOP`: không resume, không đổi tên experiment để vượt latch. Đọc reason/peak,
khắc phục điều kiện bên ngoài trước và đánh giá lại pilot; không tự nới thresholds.
Không sửa source/config/.env/model/index/dataset trong khi experiment đang chạy.
Backend, model digest, template, source và config được pin để từ chối trộn thí nghiệm.
Latency của profile này phải so với control chạy cùng profile; không suy ra speedup từ
số liệu cũ dùng backend/offload khác. Gate nghiên cứu vẫn IN_PROGRESS.
