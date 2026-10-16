# A1: bàn giao source và trình tự chạy cuối

Source được viết trên `research_local_sql_a1_20261003`, xuất phát từ P6 `0972e47`.
Theo yêu cầu của bạn, agent không chạy test, `make check`, dataset, model hoặc benchmark
sau khi bạn hủy phần kiểm tra. Các lệnh dưới đây dành cho bạn chạy sau; chúng chưa được chạy.
Gate trong [ledger](../realistic_project_creation_codex.md) còn `IN_PROGRESS`, chưa `VERIFIED`.

**Cập nhật 2026-10-07:** đã sửa lỗi type binding và môi trường thiếu UI/API extra; `make sync`
và `make check-static` đã pass, cùng ba CLI `--help`. Không chạy pytest/dataset/model/benchmark
hoặc tmux session. Phần hướng dẫn 03/10 dưới đây là lịch sử construction; dùng
[commands đã cập nhật](run_commands_2026_10_07.md) cho lần chạy sau bản sửa.

## Phần đã code

- A1 nhận question và evidence từ catalog/retrieval, sinh một draft; không gọi planner LLM.
- Evidence có PK/FK, cột nối và metadata unique index. Metadata index hiện thiếu thông tin
  partial/expression, nên không dùng nó làm bằng chứng chắc chắn về entity grain.
- Checker theo clause kết luận `SUPPORTED`, `CONTRADICTION` hoặc `UNKNOWN`. Execution thành
  công không chứng minh đúng nghĩa. Fan-out, output binding và population còn cần review.
- Critic có routing theo rủi ro và mẫu shadow cố định theo question/seed. Chỉ nhận findings
  có evidence IDs và question span hợp lệ; mọi finding LLM vẫn là nhận định tham khảo.
- Repair phải bật cả mode `repair` và correction. SQL đã chạy được chỉ được sửa ORDER/LIMIT
  khi giảm contradiction, giữ metric/order keys và các phần AST khác. Không tự thêm order key
  khi thiếu bằng chứng metric binding. SQL lỗi cú pháp/cột/hàm có một lượt sửa riêng; write,
  timeout và lỗi runtime chưa xác định không vào lượt sửa này.
- Tối đa ba HTTP generation attempts cho cả request, gồm JSON retries; deadline/context/output
  cap dùng chung. Native SQL text adapter dùng installed template; chưa cài model specialist.
- Trace lưu rendered prompt theo stage, SHA và estimated/output token caps để review input
  thực tế. Đây là artifacts local có thể chứa schema/question; không commit hoặc publish trace.
- Factory dùng chung cho CLI/API/eval; UI hiển thị assessment và trạng thái meaning unverified.
- Guard kiểm tra RAM/swap/VRAM/nhiệt/power/utilization liên tục, giới hạn offload, unload,
  checkpoint từng case, cooldown 60 giây, giữ stop latch và không tự retry. Workload lease
  dùng chung giữa các workspace của cùng WSL user; Ollama phải chạy một model/parallelism một.
- Checkpoint pin source/config/manifest/database/index/profile; backend sidecar pin model digest,
  template và Ollama version. Thay identity thì phải dùng checkpoint mới.
- Báo cáo offline đọc saved traces và labels review riêng, không khởi tạo runtime/execute SQL.
  Không có labels thì semantic accuracy giữ `null`; execution không biến thành nhãn đúng.
- Đã viết test source cho các trường hợp bình thường và failure/negative cases; chưa chạy bản cuối.

**Bổ sung hiện hành:** [novelty assessment](research_plan/novelty_and_repairability_2026_10_03.md)
chốt research question và ablations. `obligation` controller có độc lập lexical metric binding,
edit contract ORDER/LIMIT, CPU repair opt-in và trace v3. Điều kiện “không thêm order key” ở trên
mô tả legacy mode; obligation mode chỉ thêm khi contract bind được metric từ question/catalog.
Report mới có draft/pool scoring riêng; Spider evaluator v2 xét outer ORDER, nên không so trực
tiếp với score lịch sử khi chưa chấm lại cùng evaluator. Tmux manager mới được hướng dẫn ở §6–9.

## 1. Kiểm tra source khi bạn muốn bắt đầu

```bash
make sync
make format
make check-static
```

Chỉ khi bạn muốn chạy cả pytest, chạy thêm:

```bash
make check
```

`make check` gồm Ruff, format check, mypy và tests không có marker Ollama. Một số integration
tests có thể đọc database local. Nếu có lỗi, sửa source và kiểm tra lại trước model pilot.
Không xem trạng thái bàn giao source là bằng chứng các checks này đã pass.

`make sync` dùng `uv sync --frozen --extra ui --group dev`: `mypy src` kiểm cả API/UI nên cần
FastAPI/Uvicorn. Core vẫn có thể cài không có UI, nhưng môi trường kiểm tra toàn repository phải
chọn extra này. `make check-static` chỉ lint/format-check/mypy; không chạy pytest, SQLite, dataset
hoặc model. Các Make targets dùng cùng extra và frozen lockfile, không dựa vào packages còn sót
từ một lần cài trước. Không chạy lại `uv sync --frozen --group dev` để kiểm tra toàn source vì
lệnh đó bỏ UI extra. [Cơ chế sync của uv](https://docs.astral.sh/uv/concepts/projects/sync/).

## 2. Chuẩn bị model và guard

Giữ mặc định P6 để làm control. Đọc [assessment paper](research_plan/local_sql_a1_2026_10_03.md)
trước khi chọn variant. Model nhỏ hơn không được tự coi là tốt hơn; cỡ/quantization và native
template cần được pin, review và pilot riêng. Không có weight download/convert trong lần code này.

Nếu Ollama nằm trong WSL, có thể dùng terminal riêng:

```bash
uv run python scripts/serve_ollama_guarded.py --profile cpu-fallback --sample-seconds 0.5
```

Nếu Ollama chạy trên Windows, cấu hình `OLLAMA_BASE_URL` đúng host và bảo đảm server có
`OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_KEEP_ALIVE=0`.
Wrapper đọc cả Settings/.env cho URL. `cpu-fallback` đặt generation offload bằng 0;
`acceptance-safe` đặt bằng 1, cùng thresholds RAM ≥14 GiB, swap <0.25 GiB, VRAM <6 GiB,
nhiệt <68 C, power <70 W. Không tự tăng các giới hạn.

Sau shutdown, kiểm tra không có stale jobs và idle sample an toàn trước pilot. Workload
Qwen3-14B Olist từng chạm stop 78 W vẫn bị điều kiện hard cap OS/NVIDIA Administrator trong
AGENTS chặn; không dùng wrapper mới để bỏ qua điều kiện đó hoặc resume workload này.
`TEXT2SQL_GUARDED_RUN` là marker nội bộ của wrapper, không tự đặt trong `.env`.

## 3. Pilot một case, chưa chạy full

Ví dụ A1 JSON với model đang được pin trong cấu hình:

```bash
TEXT2SQL_PIPELINE_MODE=a1 TEXT2SQL_CRITIC_MODE=off \
  uv run python scripts/run_guarded_spider.py \
  --profile cpu-fallback --batch-size 1 --cooldown-seconds 60 --max-batches 1 \
  --manifest evals/configs/spider-laptop-200.json \
  --predictions evals/predictions/a1-off-code-pilot.jsonl \
  --report evals/reports/a1-off-code-pilot.json \
  --no-correction --allow-dirty-source
```

`--allow-dirty-source` cho phép pilot source chưa commit và vẫn pin source hash; release mode
mặc định yêu cầu tracked tree sạch/known commit. Dùng paths mới cho mỗi cấu hình. Pilot chỉ
ghi một case của manifest, nên report toàn suite chưa tồn tại cho đến khi hoàn tất manifest.
Không suy ra accuracy từ pilot. Với specialist đã cài, thêm `TEXT2SQL_OLLAMA_MODEL`,
`TEXT2SQL_GENERATION_MODEL_DIGEST=<64 hex>` và `TEXT2SQL_GENERATION_FORMAT=sql_text`.
Chưa chứng nhận adapter này tái lập Arctic/OmniSQL; review installed template trước pilot.
Nếu output cap 2048, input cap phải ≤1792; tổng input/output/reserve không vượt 4096.

Kiểm tra `*.runtime.json`, `*.backend.json`, `*.provenance.json`, saved assessment và
`*.resource-stop.samples.jsonl`. Journal ghi summary mỗi batch, gồm peak và số samples.
Có monitor failure/breach/cleanup error thì dừng, giữ checkpoint/stop record và xử lý nguyên nhân;
không xóa latch để tự retry. Giữ đầy đủ artifacts local, không commit chúng.

## 4. Các variant sau khi pilot phù hợp

| Variant | Pipeline | Critic | Correction | Ý nghĩa |
|---|---|---|---|---|
| Control mới | p6 | off | cùng protocol đã chốt | So sánh dưới guard hiện hành |
| A1 draft | a1 | off | no | Đo tác động bỏ planner LLM |
| A1 shadow | a1 | shadow | no | Đo detector; giữ nguyên draft |
| A1 repair | a1 | repair | yes | Đo gain/loss do bounded repair |

Shadow sample thêm `TEXT2SQL_CRITIC_SHADOW_SAMPLE_RATE=0.1`; `0` vẫn cho phép risk routing.
So sánh feedback grounded/generic bằng `TEXT2SQL_REPAIR_FEEDBACK_MODE`, cùng request budget,
seed/model/manifest. Đổi mode/feedback/budget thì dùng prediction/report paths mới.
Chỉ sau pilot và review resource/format mới cân nhắc tự chạy suite; không chạy full ngay.

## 5. Báo cáo offline từ predictions đã lưu

```bash
uv run python scripts/report_a1_diagnostics.py \
  --predictions evals/predictions/a1-off-code-pilot.jsonl \
  --output data/artifacts/a1-off-diagnostics.json
```

Thêm `--reviewed-labels <path.jsonl>` khi có review độc lập. Một record theo schema:

```json
{"case_id":"example-case-id","review_status":"REVIEWED","reviewer":"independent-review","semantic_error":true,"contradictory_codes":["EXPLICIT_RANK_DIRECTION"],"candidate_correct":[false,true],"final_correct":true}
```

`semantic_error` và contradictory codes mô tả **draft đầu**, không phải repair cuối.
`candidate_correct` khớp thứ tự/tổng số `assessment.evaluations`, gồm cả candidate invalid;
`null` nghĩa chưa chấm. Chỉ báo pool oracle trên các pool đã được chấm đầy đủ. Labels/gold
chỉ được script eval offline đọc, không truyền vào runtime. Paired gains/losses và fresh-schema
evidence vẫn phải thu thập theo research plan trước khi đổi champion.

## 6. NVIDIA Administrator: giới hạn graphics clock 300–800 MHz

Chạy trong **PowerShell/CMD Windows với Run as Administrator**, trước local-model pilot.
Đây là commands bàn giao; agent không chạy hay thay clock/power trên máy.

```powershell
nvidia-smi -L
nvidia-smi -i 0 -q -d CLOCK,POWER,SUPPORTED_CLOCKS
nvidia-smi -i 0 -lgc 300,800
nvidia-smi -i 0 -q -d CLOCK,POWER
nvidia-smi -i 0 --query-gpu=timestamp,clocks.current.graphics,temperature.gpu,power.draw,memory.used,utilization.gpu --format=csv -l 1
```

Kiểm tra GPU index 0 đúng GPU muốn dùng. NVIDIA định nghĩa `-lgc` là min/max desired graphics
clocks, phần cứng chọn giá trị hỗ trợ gần nhất và yêu cầu quyền admin/root; không coi return lỗi
`Not Supported` là đã cap thành công. Clock có thể xuống dưới 300 khi idle. CLI thành công chưa
đủ chứng minh workload an toàn: giữ cửa sổ monitor, xác minh trên pilot và đọc resource journal.
Không tự nới stop thresholds hoặc dùng 800 MHz thay cho power cap.
[Tài liệu NVIDIA chính thức](https://docs.nvidia.com/deploy/nvidia-smi/#-lgc---lock-gpu-clocksmin_gpu_clockmax_gpu_clock).

Host cap áp dụng lại sau reboot nếu cần. Nếu workload Olist Qwen3-14B đã chạm 78 W trước đây,
chỉ cân nhắc resume sau hard cap được xác minh bằng **pilot độc lập một case** theo AGENTS;
wrapper mới không có quyền xóa stop latch hoặc vượt điều kiện đó. Profile `acceptance-safe`
trong các lệnh sau vẫn dùng stop 70 W/68 C/6 GiB, không tái sử dụng exception 78 W.

## 7. Run trong tmux: pilot rồi full cùng checkpoint

Commands dưới đây chạy trong **WSL bash**, tại repository. Cần có `tmux`, `uv`, Python đúng
lockfile, model đã cài đúng digest trong configs và dữ liệu/index local đã chuẩn bị.
Ollama host giữ parallel=1, max loaded models=1, keep alive=0 như §2. Không chạy hai experiments
cùng lúc; lease chỉ bảo vệ guarded jobs của cùng WSL user, không thay việc dừng jobs bên ngoài.
Trước pilot, kiểm tra stale jobs và idle RAM/swap/GPU bằng `pgrep -af 'run_guarded|run_benchmark|run_olist|ollama'`,
`free -h`, `nvidia-smi`, `ollama ps` trên host phù hợp. Watchdog sẽ lấy idle sample trước khi sinh.

```bash
cd '/mnt/d/desktop_informations/vnpt ai/agentic_text_to_sql'

# Một case: chờ PAUSED sau checkpoint, unload và cooldown 60 giây.
uv run python scripts/tmux_experiment.py run \
  --name a1-spider --suite spider --variant obligation-cpu \
  --profile acceptance-safe --manifest evals/configs/spider-laptop-200.json \
  --predictions evals/predictions/a1-obligation-cpu-spider-200.jsonl \
  --report evals/reports/a1-obligation-cpu-spider-200.json \
  --allow-dirty-source --max-batches 1

tmux attach -t a1-spider
```

Trong tmux, **Ctrl+b rồi d** detach. Đóng terminal/client sau detach không dừng workload.
Khi pilot đã PAUSED và đã review journal/cap/output phù hợp, lệnh sau chạy phần còn lại của
**toàn bộ 200 case**. Không sửa source, `.env`, model/template, DB/index, manifest hoặc config
giữa pilot và resume; khác identity thì script từ chối trộn kết quả.

```bash
uv run python scripts/tmux_experiment.py status --name a1-spider
uv run python scripts/tmux_experiment.py resume --name a1-spider
tmux attach -t a1-spider
```

Resume khi session còn chạy chỉ báo attach, không tạo một job trùng. `--max-batches 1` chỉ giới
hạn lần pilot, không bị đóng băng thành giới hạn full run. Model/config lấy lại từ frozen plan
trong `data/artifacts/experiments/a1-spider/plan.json`; process env riêng không copy secrets.
Source hash thực tế được pin trong checkpoint của worker. `--allow-dirty-source` vẫn pin hash,
không cho phép sửa source trong experiment; nó chỉ bỏ yêu cầu tracked worktree sạch lúc bắt đầu.
Manager pin interpreter path/version và dùng Python đang được `uv run` chọn để spawn wrappers/
workers trực tiếp; không lệ thuộc PATH cũ của tmux server hoặc gọi `uv` lặp lại cho từng case.

Olist 60 case chạy **sau khi Spider kết thúc/đã pause sạch**, với pilot và paths riêng:

```bash
uv run python scripts/tmux_experiment.py run \
  --name a1-olist --suite olist --variant obligation-cpu \
  --profile acceptance-safe --cases evals/configs/olist-acceptance-60.jsonl \
  --predictions evals/predictions/a1-obligation-cpu-olist-60.jsonl \
  --report evals/reports/a1-obligation-cpu-olist-60.json --max-batches 1

tmux attach -t a1-olist
# Sau PAUSED và review pilot an toàn:
uv run python scripts/tmux_experiment.py resume --name a1-olist
tmux attach -t a1-olist
```

Đây là commands full cho manifests hiện có, không phải lệnh chạy đồng thời hai suites. Nếu cần
Spider full-dev 1034, tạo experiment name/paths mới, thay manifest bằng
`evals/configs/spider-release-1034.json`, vẫn pilot một case trước. Tập lớn hơn không tự trở thành
fresh holdout; protocol novelty ở assessment phải được freeze trước khi xem kết quả.

## 8. Pause, resume, attach và completion

```bash
# Từ terminal khác: pause sau case hiện tại; giữ checkpoint và cooldown.
uv run python scripts/tmux_experiment.py pause --name a1-spider
uv run python scripts/tmux_experiment.py status --name a1-spider

# Chờ status PAUSED, rồi tiếp tục ở case chưa checkpoint.
uv run python scripts/tmux_experiment.py resume --name a1-spider

# Cả hai cách attach đều có thể dùng:
uv run python scripts/tmux_experiment.py attach --name a1-spider
tmux attach -t a1-spider
```

Ctrl+C trong managed pane cũng gửi pause, không kill worker đang inference; chờ worker hoàn tất
case, unload và cooldown. Pause giữa một request có thể phải chờ request deadline. Đừng dùng
`tmux kill-session`, kill -9 hoặc tắt WSL để pause có kế hoạch. Session dùng `remain-on-exit`
để giữ output sau khi wrapper thoát; resume dùng `respawn-pane` khi pane đã chết.
[Cơ chế tmux chính thức](https://man.openbsd.org/tmux#remain-on-exit).

Cuối suite sẽ hiện, ví dụ:

```text
SUCCESS FINISH ALL: 200/200; report=.../a1-obligation-cpu-spider-200.json
```

Chỉ hiện khi checkpoint là prefix đủ, không trùng case, final report đủ đúng manifest và
cooldown xong. `COMPLETE` nghĩa hoàn thành experiment/report, không nghĩa mọi SQL đều đúng
hoặc research gate VERIFIED. `PAUSED` có exit code 0 cũng chưa phải COMPLETE.
Log append trong `data/artifacts/experiments/<name>/run.log`; suite state cạnh report;
resource journals/identity sidecars cạnh report/predictions. Không commit artifacts này.

Nếu mất điện/reboot/SIGKILL: checkpoint đã ghi được giữ, case đang tính có thể cần làm lại.
Kiểm tra stale jobs absent, idle safe, hard cap còn active trước khi chạy:

```bash
uv run python scripts/tmux_experiment.py resume --name a1-spider --recovery-pilot
tmux attach -t a1-spider
# Chỉ sau khi recovery pilot PAUSED, đã review resources:
uv run python scripts/tmux_experiment.py resume --name a1-spider
```

Recovery flag chỉ chạy tối đa một case còn lại; **không override resource latch**. Monitor failure,
thermal/RAM/swap/VRAM/power breach hoặc cleanup failure vẫn fail closed, lưu observed peak và
không auto-retry. Đừng xóa latch để ép resume. Nếu checkpoint đủ nhưng final report còn thiếu,
worker có thể dựng lại report sau inference mà không sinh thêm SQL; Olist cũng không tạo runtime
LLM cho đường finalization đó. Không có cam kết “resume luôn không lỗi” khi data/source đổi hoặc
máy chưa an toàn; các trường hợp này bị từ chối có chủ ý để bảo vệ experiment và laptop.

## 9. Các lượt đối chứng cho research

Giữ cùng `.env`/model/seed/resource settings. Các giá trị khác biệt cần thử bằng variants và
paths mới; chạy tuần tự, mỗi lượt đều pilot rồi resume. Ví dụ controller LLM đối chứng với CPU:

```bash
uv run python scripts/tmux_experiment.py run \
  --name a1-spider-llm --suite spider --variant obligation-llm \
  --profile acceptance-safe --manifest evals/configs/spider-laptop-200.json \
  --predictions evals/predictions/a1-obligation-llm-spider-200.jsonl \
  --report evals/reports/a1-obligation-llm-spider-200.json \
  --allow-dirty-source --max-batches 1

# Review pilot trước khi tiếp tục.
uv run python scripts/tmux_experiment.py resume --name a1-spider-llm
tmux attach -t a1-spider-llm
```

Các variant còn lại: `p6`, `a1-off`, `a1-shadow`, `a1-legacy-repair`; đổi cả name/predictions/report.
`obligation-risk` và `obligation-risk-cpu` dùng cùng contract/admission với các treatments nhưng
giữ critic risk routing: đối chứng này cần để tách tác động của routing khỏi CPU synthesis.
Shadow sample set `TEXT2SQL_CRITIC_SHADOW_SAMPLE_RATE=0.1` trước khi tạo plan. Cấu hình được freeze
ở thời điểm tạo, không tự nhận env mới lúc resume. Reports có `a1_candidate_quality` gồm
first-pass/pool coverage, gain/loss và repair origins; semantic localization/FPR vẫn cần review
độc lập qua script §5. Latency service, runtime setup và wall time có cooldown phải báo riêng.
