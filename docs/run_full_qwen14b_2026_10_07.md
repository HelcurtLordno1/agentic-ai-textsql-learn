# Full Spider 200 + Olist 60 trên GPU 16 GiB / RAM 32 GiB

Người dùng đã cho phép điều chỉnh hardware limits và chạy experiment mới sau stop VRAM6GiB.
Session mới: `a1-fullgpu450-20261007`; source variant `obligation-cpu`, Qwen3:14b-q4_K_M hiện có.
Lần full offload ở cap800MHz đã dừng do power peak81.2W; RAM/VRAM vừa (19.79GiB/9705MiB).
Driver không hỗ trợ power-limit; Administrator đã áp dụng hard clock cap300–450MHz.
Giữ nguyên model/prompt/critic/evaluator/token budgets; deadline180s cho xung thấp hơn.
Không tiếp tục session24-layers/800MHz cũ và không xóa latch/evidence cũ. Không cần xin phép lại
cho cấu hình và pilot/full đã được người dùng cho phép trong lượt này.

Profile `qwen14b-16gb-clock-capped`: bounded `num_gpu=41` (model40 transformer blocks + output),
CPUthreads8, case deadline180s, ctx4096, num_batch64, flash attention, q8 KV, keep_alive0, maxloaded1/parallel1.
Đưa weights sang GPU để giảm phần CPU inference và cân RAM; không dùng generation và embedding
đồng thời. GPU có16384MiB được xác nhận; watchdog VRAM14336MiB giữ2GiB cho hệ thống,
RAM available>=8GiB (min Windows/WSL), swap/pagefile<0.25GiB, GPUtemperature<68C,
power<70W (max instantaneous/average), graphicsclock<=450MHz. Ngưỡng và nguồn profile được pin;
Windows guardian đọc cùng limits JSON như Python guard. Batch1, unload, cooldown60s.
Sensor failure hoặc actual safety breach vẫn dừng workload/checkpoint, không vòng lặp retry.

## Chạy mới — một lệnh tự xử lý cả hai benchmark

Đây là lệnh tái tạo; nếu session/plan đã tồn tại, dùng resume thay vì chạy lại run.

```bash
cd '/mnt/d/Desktop_informations/VNPT AI/Agentic_text_to_sql'
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks run \
  --name a1-fullgpu450-20261007 --profile qwen14b-16gb-clock-capped \
  --models-dir /mnt/c/Users/ADMIN/.ollama/models
```

Harness chạy một pilot Spider và một pilot Olist trước; sau khi resource journal/clock cap,
checkpoint và executable result đều hợp lệ, tự chạy phần Spider còn lại rồi Olist còn lại.
Không đặt max-batches nên không cần người dùng bấm chạy benchmark thứ hai.
Chỉ in `SUCCESS FINISH ALL: Spider 200/200 + Olist 60/60` khi hai reports đủ IDs và cleanup xong.
Đây là hoàn thành workload/evaluation; không có nghĩa accuracy100% hoặc method verified.

## Monitor

```bash
tmux attach -t a1-fullgpu450-20261007
```

Ctrl+b rồi d: detach, terminal đóng vẫn chạy; việc tắt máy kết thúc process và cần resume.

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks status \
  --name a1-fullgpu450-20261007
```

Log: `data/artifacts/experiments/a1-fullgpu450-20261007/run.log`.
Native journal: `server.samples.jsonl` cùng thư mục. Root state đếm prefix/checkpoint bền vững.
Full reports/predictions tách `a1-fullgpu450-20261007-spider` và `a1-fullgpu450-20261007-olist`.
Không thay source/config/.env/models/index/dataset trong lúc experiment chạy hoặc giữa resume.

## Pause trước khi tắt máy

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks pause \
  --name a1-fullgpu450-20261007
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks status \
  --name a1-fullgpu450-20261007
```

Chờ PAUSED và worker_pid/server_pid/proxy_pid đều null: case hiện tại đã được checkpoint,
model unload, cooldown và owned native server/proxy đã đóng. Case chưa checkpoint khi tắt đột ngột
sẽ được chạy lại; case đã fsync được giữ và không tạo duplicate ID.

## Resume bình thường (cùng boot, pause sạch)

```bash
cd '/mnt/d/Desktop_informations/VNPT AI/Agentic_text_to_sql'
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume \
  --name a1-fullgpu450-20261007
tmux attach -t a1-fullgpu450-20261007
```

Nếu session còn chạy, resume báo active và không tạo worker/model thứ hai.

## Sau reboot hoặc shutdown bất ngờ

PowerShell Administrator: áp lại cap; không giả định cap giữ nguyên sau reboot.

```powershell
nvidia-smi -i 0 -lgc 300,450
nvidia-smi -i 0 --query-gpu=memory.used,temperature.gpu,power.draw.instant,power.draw.average,clocks.current.graphics --format=csv
```

Trong WSL, chạy recovery một case; harness kiểm tra stale jobs và idle resources.

```bash
cd '/mnt/d/Desktop_informations/VNPT AI/Agentic_text_to_sql'
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume \
  --name a1-fullgpu450-20261007 --recovery-pilot
tmux attach -t a1-fullgpu450-20261007
```

Sau recovery sạch, phase PAUSED, resume một lệnh để chạy nốt cả hai:

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume \
  --name a1-fullgpu450-20261007
tmux attach -t a1-fullgpu450-20261007
```

Nếu RESOURCE_STOP/sensor failure: giữ evidence, đọc reason/peak trước khi đánh giá remediation;
không tắt monitor hoặc lặp lại thermal/power breach. Profile này dùng consent mới về VRAM/RAM,
không dùng exception Olist78W cũ. Latency cần control cùng profile để so sánh nghiên cứu.
