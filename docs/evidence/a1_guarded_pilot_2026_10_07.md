# Qwen3-14B guarded pilot — 2026-10-07

Gate A1 vẫn IN_PROGRESS. Không có full benchmark/accuracy/novelty kết luận mới.

## Authorization và cấu hình thực tế

Người dùng cho phép chạy hai batch kiểm tra, rồi full Spider200+Olist60 nếu an toàn,
sau khi Windows Administrator báo `nvidia-smi -i 0 -lgc 300,800` thành công.
Người dùng yêu cầu giữ Qwen3-14B, tìm cách cân bằng CPU/GPU/RAM; không cho phép nới thresholds.

Nguồn trước pilot: `make check` pass (Ruff/format272, mypy119, 245 tests,
1 Ollama test deselected). Windows Job Object model-free smoke đóng owned child thành công;
owned native backend/proxy API ready, ps empty và cleanup pass. Không tải model mới.

Actual session: `a1-qwen-both-20261007`; A1 `obligation-cpu`;
Qwen3:14b-q4_K_M digest
`bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`;
Windows Ollama0.30.10, owned backend gateway:11436, loopback proxy:11435.
Profile tại thời điểm pilot:24 GPU layers, 8CPU threads, num_batch64, ctx4096,
KVq8, flash attention, keep_alive0, maxloaded1, parallel1, suitebatch1/cooldown60.
RAM min14GiB, swap/pagefile max0.25GiB, VRAM max6144MiB, GPU tempmax65C,
powermax65W, clockmax800MHz. Cả host Windows và WSL được kiểm tra liên tục.

## Quan sát và stop

Pilot Spider đầu tiên **không hoàn tất**. Cả native guardian và guarded wrapper phát hiện
VRAM6223MiB >=6144MiB; không chuyển sang pilot Olist hoặc full. Prefix cuối:
Spider0/200, Olist0/60. Source/backend identity và journals được giữ; chưa có completed prediction.

Native journal:68 observations trước stop; observed extrema:

| Metric | Quan sát |
|---|---:|
| Windows available RAM minimum |16.5451GiB|
| Windows swap/pagefile maximum |0GiB|
| GPU memory maximum |6223MiB|
| GPU temperature maximum |53C|
| GPU power max(average,instant) |30.13W|
| GPU graphics clock maximum |795MHz|
| GPU utilization maximum |98%|

Wrapper độc lập ghi54 samples ở0.5giây, VRAMmax6223MiB, RAMmin16.5608GiB.
Native Job Object đóng server/runners; wrapper dừng child/cooldown. HTTP unload của wrapper
bị RemoteProtocolError vì native guardian đã đóng backend; đó không có nghĩa model còn chạy.
Cleanup/state code cũ đã ghi thêm generic cleanup failure; journal/latch gốc được bảo toàn.
Kiểm tra độc lập sau đó xác nhận không còn owned native Ollama/PowerShell monitor/guardian,
proxy hay wrapper/inference jobs; Windows service cũ PID8168 tồn tại nhưng API ps=[];
tmux pane_dead=1. Idle sau cleanup: RAM21.1929GiB, swap0, GPU711MiB/49C/22.08W/300MHz.
Root state được đồng bộ PIDs=null với reason VRAM và ghi nhận audit, vẫn RESOURCE_STOP.

Ignored local evidence nằm ở `data/artifacts/experiments/a1-qwen-both-20261007/`
và `evals/reports/a1-qwen-both-20261007-spider.resource-stop*`.
Không xóa stop latch, không chạy lại model, không dùng tên mới để retry cấu hình24 lớp.
Không có shutdown trong lần chạy được quan sát; không suy ra bảo đảm chống shutdown tuyệt đối.

## Source remediation (chưa có model pilot)

Giữ Qwen14B và mọi thresholds, giảm bounded offload24→20 để chừa thêm VRAM;
RAM đã có khoảng trống lúc24 lớp, nhưng khả năng phù hợp20 lớp vẫn cần pilot thực tế.
Native guardian xuất cleanup_complete; harness chỉ chấp nhận native exit1 như một resource stop
đã cleanup nếu có bằng chứng này. Còn latch vẫn chặn mọi resume; unit test kiểm tra cả hai điều.
Root state xóa PID khi process đã chết, reason chứa observed breach; SUCCESS dùng số cases thực.
Proxy xử lý Ctrl+C cleanup không in traceback như workload failure.

Cấu hình mới cần sự đồng ý chạy một pilot mới sau resource breach theo AGENTS;
không tự restart. Commands chuẩn bị và recovery protocol ở
[run_both_benchmarks_2026_10_07.md](../run_both_benchmarks_2026_10_07.md).
Latency comparison phải chạy control cùng profile/backend; peak của pilot không phải accuracy.

Final source verification sau remediation20 lớp: `make check` pass, Ruff và format273 files,
mypy119 source files, 246 tests pass/1 Ollama test deselected (77.33s).
PowerShell parser kiểm tra cả4 scripts pass. Chưa chạy local-model inference lần nữa;
câu hỏi xin phép pilot20 lớp đã gửi, chưa coi thời gian chờ hoặc lựa chọn preselected là phép chạy.
