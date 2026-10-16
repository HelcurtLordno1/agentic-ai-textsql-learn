# Monitor remediation và chạy nốt Spider/Olist

Latest continuation: `a1-startupfix450-20261007`, từ checkpointSpider173/200+Olist3/60.
Run `a1-monitorfix450-20261007` bị startup timeout; giữ latch/evidence nguyên vẹn.
Helper cache + startup readiness15s, freshness1s và hardware limits giữ nguyên.
Evidence: [startup recovery](evidence/a1_monitor_startup_recovery_2026_10_07.md).

Scope: sửa infrastructure monitor/cleanup, giữ A1 model, pipeline, prompts, evaluator,
token/request budgets và profile `qwen14b-16gb-clock-capped` ở 300–450 MHz.
Không bảo đảm hardware/sensor không bao giờ lỗi; safety failure vẫn stop và giữ checkpoint.

## Chẩn đoán

Session `a1-fullgpu450-20261007` dừng ở Spider 18/200, Olist 1/60.
Python chỉ lưu `monitor failure: ValueError`, nên không thể xác định chắc chắn sensor nào lỗi
từ log cũ. `KeyboardInterrupt` ở import là hậu quả guard gửi SIGINT.
Native stop sau đó ghi `Harness heartbeat stale`, cleanup_complete=true.
Code root chờ wrapper kết thúc tối đa 200s mà không cập nhật heartbeat, trong khi wrapper
còn cooldown 60s; guardian hết hạn sau 10s. Đây là lỗi cleanup tái lập được.
Peak native: RAM available 19.7406 GiB, pagefile 0.035156 GiB, VRAM 9725 MiB,
59 C, 65.19 W, clock 450 MHz; evidence không ghi nhận hardware threshold breach.

## Các bước và tiêu chí

1. Giữ nguyên artifacts/latches của run cũ. Chụp source hashes trước edit và xác nhận chúng
   khớp frozen runtime của cả hai checkpoint.
2. Thay truy vấn pagefile CIM trong mỗi vòng bằng native `EnumPageFilesW`, cộng TotalInUse
   nhân system page size. Giữ RAM native, sampling 0.5s, freshness 1s và fail closed.
   API contract: [Microsoft EnumPageFilesW](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-enumpagefilesw),
   [pagefile fields](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-enum_page_file_information).
3. Lưu exception message, stdout EOF, bounded stderr để lần stop sau có nguyên nhân cụ thể.
   Heartbeat vẫn được cập nhật mỗi 0.2s trong lúc chờ worker cleanup/cooldown; deadline
   cleanup vẫn 200s và kill escalation giữ nguyên.
4. Chạy regression cho stale/invalid/closed sensor, failure details, heartbeat qua 60s cooldown
   và worker stuck. `make check` bắt buộc; PowerShell parse và native API/CIM cross-check.
5. Kiểm tra không có stale workload, models trống và theo dõi idle Windows/WSL/GPU trong 180s.
6. Tạo sequence mới `a1-monitorfix450-20261007`, sao chép nguyên byte prefix 18/1.
   Migration audit chỉ cho phép 6 file monitor/guard/cleanup thay đổi; source hash được cập nhật
   minh bạch ở artifacts mới. Runtime settings, resource profile, manifest, databases, indexes,
   backend/model/template đều phải khớp. Không sửa latch/identity của run cũ.
   Batch đầu sau resume phát hiện thêm fingerprint `/api/show` hash theo thứ tự map;
   xác nhận hash cũ khớp permutation chính xác của cùng các dòng parameters. Chuẩn hóa
   metadata theo tên tham số (và thứ tự stop strings), giữ nguyên giá trị và inference.
   Migration metadata riêng lưu originals của prefix19/2 và sidecars; chỉ2file fingerprint/
   diagnostics đổi, audit kiểm tra runtime chỉ đổi source hash. Reset pilots rồi thử lại.
   Preflight startup/catalog/index/backend cho cả20SpiderDB vàOlist, chặn mọi inference request.
7. Chạy đúng một guarded pilot mới cho Spider và Olist, batch=1, unload và cooldown60.
   Chỉ sau hai pilot sạch, mới resume full không `max-batches`: Spider rồi Olist.
8. Chỉ coi workload hoàn tất khi in `SUCCESS FINISH ALL: Spider 200/200 + Olist 60/60`,
   reports đủ IDs và server cleanup xong. Research gate vẫn IN_PROGRESS.

## Monitor / điều khiển

```bash
cd '/mnt/d/Desktop_informations/VNPT AI/Agentic_text_to_sql'
tmux attach -t a1-startupfix450-20261007
```

Ctrl+b rồi d để detach, giữ workload chạy. Status:

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks status --name a1-startupfix450-20261007
```

Pause sạch, chờ PAUSED và worker/server/proxy PID null:

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks pause --name a1-startupfix450-20261007
```

Resume pause sạch hoặc dead pane không có resource latch:

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume --name a1-startupfix450-20261007
tmux attach -t a1-startupfix450-20261007
```

Sau reboot: Administrator áp lại `nvidia-smi -i 0 -lgc 300,450`; kiểm tra stale jobs và
idle an toàn rồi dùng `resume --name a1-startupfix450-20261007 --recovery-pilot`.
Chờ pilot sạch/PAUSED rồi resume bình thường. RESOURCE_STOP cần đọc evidence và remediation;
resume không xóa/override latch, không tự retry sensor hoặc thermal/power/VRAM breach.
Không thay source/config/model/index/data khi workload đang chạy.
