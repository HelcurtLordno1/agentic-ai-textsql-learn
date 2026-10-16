# A1 construction — 2026-10-03

Base: P6 `0972e47`; development branch: `research_local_sql_a1_20261003`.
Canonical status: `IN_PROGRESS`, chưa `VERIFIED` hoặc promote champion.

[Assessment và kế hoạch](../research_plan/local_sql_a1_2026_10_03.md) ghi rõ
problem/mechanism/conditions của paper, adaptation và điều kiện bác bỏ.

Đã viết source cho question-first generation, evidence PK/FK/uniqueness,
CPU clause checks, critic shadow, một targeted repair với admission giữ nguyên
phần SQL ngoài mục tiêu sửa, shared request budget gồm retries, SQL text adapter,
factory dùng chung và resource/checkpoint guard. P6 vẫn mặc định.

Offline inventory đã đọc artifacts lịch sử; không có prediction hoặc benchmark mới.
Actual prompts và reviewed root-cause taxonomy vẫn thiếu. Specialist/template pilot,
hardware pilot, detector calibration và fresh-schema evaluation chưa thực hiện.

## Giới hạn thực thi do người dùng chốt

Người dùng yêu cầu **chỉ viết code, không chạy test/dataset** và hủy kiểm tra đang chạy.
Trước yêu cầu dừng, agent đã chạy kiểm tra model-free, gồm test SQLite synthetic
và một số integration test đọc database local. Đây là vượt phạm vi mong muốn;
không gọi các lần chạy đó là benchmark mới. Không gọi Ollama hoặc chạy local LLM.

Đã yêu cầu dừng kiểm tra; tại thời điểm kiểm tra tiến trình không còn job test/check
hoạt động trong workspace. Không tiếp tục test, dataset, pilot hoặc benchmark.
Source cuối cùng chưa được tuyên bố verified. Việc kiểm chứng tiếp theo chỉ thực hiện
khi người dùng cho phép chạy lại.

## Source bàn giao sau yêu cầu “code xong hết”

Đã khép kín source cho A1 trace v2, operational repair một lượt và semantic repair giữ AST,
critic risk routing/shadow sampling, grounded/generic feedback, database/index/backend identity,
template digest, guard workload lease/cooldown/cleanup/resource journal và UI assessment.
Thêm offline diagnostics cho detector, chi phí, first-pass/final/pool oracle dùng labels review riêng;
không có labels thì không tuyên bố accuracy. Viết thêm test source, không thực thi chúng.

**Source construction đã bàn giao; gate vẫn `IN_PROGRESS`, chưa `VERIFIED`.**
Không có `make check`, test, dataset, model hoặc benchmark được chạy sau yêu cầu hủy kiểm tra.
[Hướng dẫn chạy cuối cho người dùng](../a1_run_after_coding.md) ghi lệnh kiểm tra, pilot và giới hạn.

## Bổ sung theo yêu cầu novelty và tmux

Source có independent lexical ranking binding, contract trước repair, optional CPU AST edit,
repairability routing và risk-routing control cùng contract để tách tác động routing khỏi
admission/edit synthesis. Trace v3 ghi candidate origin/contract và request counts.
Đã sửa duplicate/derived order alias ambiguity, added wrong-metric checks và ambiguous-direction
scope. Không có evidence cho general population/grain repair; UNKNOWN vẫn được giữ.

Eval có saved draft/candidate-pool scoring, CPU-vs-model origins và paired draft→selected
gain/loss. Olist không còn gán A1 selected repair vào first-pass. Spider evaluator v2 chỉ lấy
outer order; lịch sử cần cùng evaluator trước paired comparisons. Setup latency tách khỏi
service total; hash/copy/checkpoint/cooldown còn chi phí được wrapper wall time phản ánh.

Tmux manager freeze typed settings/.env hash, wrapper args và artifact paths; không lưu process
environment toàn bộ. Python interpreter path/version được pin; worker spawn trực tiếp để
tránh launcher overhead. Durable suite state phân biệt PAUSED/COMPLETE/FAILED/RESOURCE_STOP,
lưu cooldown deadline và worker process group. Checkpoint ghi file tạm duy nhất, flush/fsync trước
atomic replace. Pause Ctrl+C/file request chờ worker checkpoint/unload/cooldown; resume không
tạo job trùng; final report đủ manifest mới hiện SUCCESS. Olist full checkpoint có đường tạo
report không tạo RuntimeBundle. Generic child failure tách khỏi resource breach nhưng vẫn
cleanup/cooldown; cleanup/monitor/resource failure giữ stop latch và không auto-retry.

**Chỉ review đọc source và viết code/docs/tests; không chạy checks, formatter, tmux, model,
dataset hoặc thay settings GPU.** Không có bằng chứng thực thi cho các bổ sung này, không mark
gate complete. [Novelty assessment](../research_plan/novelty_and_repairability_2026_10_03.md)
và [operator commands](../a1_run_after_coding.md) mô tả research question và bước người dùng chạy cuối.
