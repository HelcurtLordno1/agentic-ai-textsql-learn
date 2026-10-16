# A1 monitor recovery — 2026-10-07

Scope: hoàn thiện monitor/cleanup và tiếp tục workload đã được user cho phép.
Research gate vẫn IN_PROGRESS; chưa đủ final reports để kết luận accuracy hoặc hoàn tất260cases.

## Incident và remediation

Run cũ `a1-fullgpu450-20261007`: Spider18/200, Olist1/60, Python stop
`monitor failure: ValueError`. Exception message đã bị cắt nên nguồn sensor failure
không thể xác định chắc chắn. KeyboardInterrupt là guard gửi SIGINT trong khi import.
Native guardian sau đó ghi `Harness heartbeat stale`, cleanup_complete=true.
Root có blocking wait200s trong failure cleanup; child vẫn cooldown60s nhưng heartbeat
không được cập nhật, vượt10s native lease. Regression nay mô phỏng đủ60s và stuck worker.
Native incident peak19.7406GiBRAMavailable/0.035156GiBpagefile/9725MiBVRAM/59C/
65.19W/450MHz không ghi nhận hardware breach.

6 file source sửa: Windows memory API helper, Windows memory streamer, native guardian,
Python Windows monitor, Python resource guard, tmux sequence cleanup.
CIM pagefile mỗi vòng đổi sang EnumPageFilesW; cộng số pages đang dùng, nhân system page size.
Native API live cross-check38027264bytes so với CIM36MiB (CIM làm tròn MiB).
Giữ sensor freshness1s, sampling0.5s, native loop deadline1s; streamer sensor budget500ms.
Exception message/stale age/EOF/bounded4096charstderr được giữ để chẩn đoán tiếp.
Failure cleanup duy trì heartbeat mỗi0.2s trong bounded200s wait, vẫn kill nếu worker stuck.
Không thêm retries, không bỏ guard, không nới resource limits.

## Reproducible checks

- `make check`: Ruff pass; format278files; mypy119sourcefiles;
  255tests passed,1Ollama deselected,77.86s.
- `uv run --frozen --extra ui --group dev python -m pytest tests/unit/test_windows_monitor.py tests/unit/test_resource_watchdog.py tests/unit/test_sequence_safety.py -q`:
  20passed. Gồm stale/malformed/EOF/stdErr, detailed failure latch, heartbeat cooldown/stuck.
- PowerShell AST parser: cả5scripts pass.
- Idle Windows+WSL/GPU continuous180.072s/360samples/0.5s, reason=null:
  RAMmin20.3177GiB, pagefilemax0.037006GiB, VRAMmax855MiB,temp52C,power21.32W,clock300MHz.
- Stale model jobs absent; existing Windows Ollama `/api/ps` models=[];
  owned backend11436 và loopbackproxy11435 free trước start.

## Checkpoint provenance

Baseline source trước edit khớp cả2runtime checkpoints:
`df4c096bb221dd7b54a5b7a0271b144d8faf9519c86e29c6b0f7b7c051a98c38`.
Source mới:
`409532b35155ef8567251f94db268c8532a6b6d1140a1a5bc066a7fde409f449`.

One-time audit clone tạo sequence `a1-monitorfix450-20261007`, giữ byte-identical
predictions prefixes18/1 và backend snapshots. Chỉ6file guard/monitor/cleanup đổi;
mọi runtime identity field ngoài source_sha256 phải bằng run cũ, bao gồm settings,
resource profile, manifest, DBs, indexes, selection. Prompts/model/evaluator không thay đổi.
Olist giữ evaluation_id gốc để bảo toàn inference identity.
Spider provenance thêm monitor_migration và cập nhật source hash có audit.
Mọi original artifacts/latches/runtime identity nguyên vẹn; không auto override.

Ignored reproducibility/audit artifacts:
`data/artifacts/monitor-remediation-20261007/{before.json,idle.json,clone_checkpoints.py}`;
`data/artifacts/experiments/a1-monitorfix450-20261007/monitor-migration.json`.

## Guarded recovery pilots

Bounded41GPUlayers,300–450MHzhardclockcap,180scasedeadline,batch1,unload,cooldown60s;
Qwen3:14b-q4_K_M/Ollama0.30.10/variantobligation-cpu giữ nguyên.

| Benchmark | New pilot | Terminal status | RAM min GiB | VRAM max MiB | Temp max C | Power max W | Clock max MHz | Samples |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Spider | spider_regression_0139 | SUCCEEDED |19.9638|9834|58|61.09|450|64|
| Olist | olist_acc_002 | SUCCEEDED |19.8406|9834|58|62.90|450|65|

Cả2 resource journals reason=null,cleanup_error=null,resource_stop=false,
Windows RAM có evidence, pagefilemax0.036907GiB, interval0.5s.
Checkpoint sau pilots19/200 và2/60; pilot launch dùngmax-batches2 để chờ cooldown/cleanup
và kiểm tra rồi mới resume full. SUCCEEDED là executable status, chưa phải gold accuracy.

Commands và kế hoạch:
[monitor_recovery_plan_2026_10_07.md](../monitor_recovery_plan_2026_10_07.md).

## Full resume

Hai pilots đều root mark PILOT VERIFIED; phase PAUSED tại19/200+2/60,
worker/server/proxy PID null sau unload/cooldown và clean native shutdown.
Đã gọi `python -m scripts.tmux_benchmarks resume --name a1-monitorfix450-20261007`
khôngmax-batches; root chuyển RUNNING/Spider19/200, cả2pilot_passed=true,reason=null.
Root tự quản lý batch1, tuần tự chạy Spider còn lại rồi Olist còn lại. Workload được để
chạy trong tmux; chưa có completion/accuracy claim khi bàn giao.

## Backend metadata ordering fix

Batch đầu sau full resume dừng trước generation với `Checkpoint backend/model/template
changed across databases`. Guard journal resource_stop=false; không có hardware breach.
Model/template/options không đổi; `/api/show.parameters` khác thứ tự các dòng key/value.
Đã enumerate permutations6lines và tái tạo chính xác frozen rawhash
`8cc0007dceee22ee948234837dc27549bed43f827fc0b60372eecd91e7ddb32c`;
raw response hiện tại hash `d6b2700710ae824c6690a7b47383ea3836790cb59d52dc3018ad7b5530faf124`.
Old/current chỉ khác thứ tựkeys. Template hash vẫn
`ae370d884f108d16e7cc8fd5259ebc5773a0afa6e078b11f4ed7e39a27e0dfc4`.

Provider nay hash canonical key/value JSON: sortkeys, sortstopstrings, giữ value,
duplicate count và repeatedscalarorder. Không thay actual options hoặc requests.
Metadata thật thay đổi vẫn bị chặn. Backend failure ghi changed field names.
Regression test parameter reorder/spacing/stop order ổn định, đổitemperature làm hash đổi,
repeatedscalarorder/duplicates được bảo toàn, malformed metadata failclosed.
Final `make check`: Ruff/format279files pass; mypy119sourcefiles pass;
257tests passed/1Ollama deselected/76.97s.

Read-only startup preflight cả20SpiderDB vàOlist pass: catalog/index loading và shared
backend fingerprint đều khớp; HTTP guard chặn mọi path ngoài metadata, inference_requests=0.
Artifact `data/artifacts/monitor-remediation-20261007/all-database-preflight.json`.

Migrationmetadata có audit tại
`data/artifacts/experiments/a1-monitorfix450-20261007/metadata-migration.json`;
originalprefix19/2,sidecars,suite states,workloaderror vàrunlog giữ trong
`metadata-migration-originals/`. Primary run trước remediation nguyên vẹn.
Only2sourcefiles tiếp theo đổi (`ollama_provider.py`, `runtime_checkpoint.py`),
runtime settings/profile/DB/index/manifest/selection không đổi; canonical parametershash
`5bf5c6aa4c80431040e0d70526a554fb75ecda60d07a4043880551dc2cc9b56f`.
Final source hash:
`daec311d64316272e64a1ebb6eba1e9c2d824a7916cfbb21f43ca13572169c24`.
Two pilots reset để kiểm tra sau normalization, rồi mới resume full.

Post-normalization pilots đều SUCCEEDED và root PILOT VERIFIED sau clean unload/cooldown60s:

| Benchmark | Case / checkpoint | RAM min GiB | VRAM max MiB | Temp max C | Power max W | Clock max MHz | Samples |
|---|---|---:|---:|---:|---:|---:|---:|
| Spider | spider_regression_0145 /20/200 |19.8119|9834|58|60.37|450|63|
| Olist | olist_acc_003 /3/60 |19.7965|9834|57|58.83|450|63|

Resource_stop=false,reason=null,cleanup_error=null,WindowsRAM có evidence,
pagefilemax0.036907GiB,interval0.5s. PAUSED20/200+3/60 với mọiPIDnull sau server cleanup.
Đã resume lần cuối không tổngmax-batches; originalprefix18/1 được đối chiếu JSON unchanged.

Đã quan sát batch sau server restart: `spider_regression_0175: SUCCEEDED`,
checkpoint21/200; Olist3/60. Không còn false metadata stop ở lần restart này;
suite COOLING sau checkpoint/unload, root RUNNING và pane sống để tiếp tục tự động.
Full sequence không có tổngmax-batches, chưa hoàn tất260cases lúc bàn giao.
