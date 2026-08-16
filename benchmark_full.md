# Gate P6 benchmark dossier — Local Laptop Release

Ngày tổng hợp: 2026-08-16
Revision benchmark: `1509faa786534f36d33df34d4d5c4a9ed5fc1c54`
Gate completion commit: `0972e4715f2aa8a64652c3b27d10c80f178bc162`
Trạng thái: `GATE_P6_VERIFIED`

> Ghi chú hậu P6 (2026-08-16): các score dưới đây chỉ có hiệu lực cho revision benchmark
> `1509faa...`, generator v4 và corrector v3. Working tree sau benchmark đã harden schema-linking,
> prompt và runtime/UI để sửa các lỗi join/scope/scalar thực tế. Không được coi 95%/65% là accuracy
> đã đo của generator v6/corrector v5; muốn công bố score mới phải chạy lại manifest khóa độc lập. Kết quả cũ
> vẫn là historical release evidence hợp lệ, không bị sửa ngược.

## 1. Phạm vi và nguyên tắc

Đây là kết quả chạy thật trên laptop local, hoàn toàn miễn phí, với Qwen3-14B Q4_K_M qua Ollama,
BGE-M3 hybrid retrieval, seed 42, bounded correction và 6 GPU layers. Hai benchmark phục vụ hai
mục tiêu khác nhau và tuyệt đối không được lấy trung bình thành một accuracy duy nhất:

- **Olist-60** đo application fitness trên domain thương mại điện tử đã được thiết kế semantic
  contracts và acceptance set song ngữ.
- **Spider-200 laptop-stratified** đo cross-domain generalization trên 20 database, gồm
  regression-100 và disjoint holdout-100.

Full Spider-dev 1.034 case là P6.1 optional cho hardware mạnh hơn. Project chưa chạy và không tuyên
bố score full-1.034. Evaluator đã được self-test bằng exact-gold 1.034/1.034, nhưng đây là kiểm thử
evaluator chứ không phải accuracy của model.

## 2. Kết quả Spider-200

| Metric | Kết quả |
|---|---:|
| Database | 20 |
| Typed workflow completion | 200/200 (100%) |
| Valid candidate | 199/200 (99,50%) |
| Execution accuracy | 130/200 (65,00%) |
| Regression | 63/100 (63,00%) |
| Disjoint holdout | 67/100 (67,00%) |
| Easy | 83/107 (77,57%) |
| Medium | 27/53 (50,94%) |
| Hard | 16/29 (55,17%) |
| Extra-hard | 4/11 (36,36%) |
| P50 latency | 58,51 giây |
| P95 latency | 85,29 giây |

Failure taxonomy giữ nguyên toàn bộ 70 case sai trong mẫu số:

- `EXECUTION_MISMATCH`: 68;
- `UNKNOWN_RUNTIME_ERROR`: 1;
- `WRITE_BLOCKED`: 1 (safety layer chặn đúng thay vì nới policy để tăng điểm).

Nhận xét: 65% là kết quả cross-domain có giá trị đối với local 14B quantized, đặc biệt vì holdout
67% không sụp so với regression 63%. Tuy nhiên đây chưa phải mức cạnh tranh với các hệ thống
frontier/paper dùng model lớn, multi-candidate search, verifier mạnh hoặc compute server. Nút thắt
chính là semantic execution mismatch, nhất là medium/extra-hard, không phải độ ổn định workflow.

## 3. Kết quả Olist-60

| Metric | Kết quả |
|---|---:|
| Typed workflow completion | 60/60 (100%) |
| Valid candidate | 60/60 (100%) |
| Result accuracy | 57/60 (95,00%) |
| First-pass correct | 51/60 (85,00%) |
| Dev | 28/30 (93,33%) |
| Regression | 14/15 (93,33%) |
| Holdout | 15/15 (100%) |
| English | 28/30 (93,33%) |
| Tiếng Việt | 29/30 (96,67%) |
| Correction recovery | 6/6 (100%) |
| P50 latency | 61,92 giây |
| P95 latency | 91,62 giây |

Nhận xét: application fitness đã đạt mức rất tốt cho demo/portfolio local. Holdout 100%, tiếng Việt
96,67% và correction 6/6 là điểm mạnh. Ba case sai vẫn được giữ trong mẫu số. Giới hạn đáng kể còn
lại là tốc độ: P95 vượt target interactive 60 giây.

## 4. Hardware và độ ổn định

Môi trường chính: Intel Core i7-12800H, NVIDIA RTX A4500 Laptop 16 GiB, khoảng 24 GiB system RAM,
WSL2/Linux. Runtime dùng partial GPU offload 6 layers, context 4.096, parallelism 1, batch có
checkpoint và cooldown.

- Olist peak: 91,75 W, 61°C, 2.725 MiB VRAM, khoảng 3,82 GiB RAM dùng thêm, swap 0.
- Các Spider segment an toàn: 60–61°C, khoảng 2,7 GiB VRAM, ít nhất 18,86 GiB RAM khả dụng,
  swap 0.
- Supervisor hai lần bắt power-sensor spike và tắt Ollama tại durable checkpoint. Không mất
  prediction, không đổi commit/seed/model digest/config khi resume và laptop không sập.
- Sau benchmark GPU trở về idle khoảng 20 W và 607 MiB VRAM.

Điều này chứng minh fail-closed resource governance hoạt động. Hai guard stop vẫn bị trừ điểm ổn
định vì benchmark chưa chạy liền mạch một mạch, dù đó là controlled stop chứ không phải crash.

## 5. Điểm hardware-aware: 90/100

Thang điểm dưới đây đánh giá **chất lượng release trên đúng laptop hiện tại**, không phải điểm Spider
leaderboard. Accuracy vẫn chiếm 45/100; hardware chỉ ảnh hưởng target hợp lý và phần latency/stability.

| Thành phần | Công thức/chứng cứ | Điểm |
|---|---|---:|
| Olist application accuracy | `15 × 0,95` | 14,25/15 |
| Spider cross-domain accuracy | target local 70%; `20 × min(0,65 / 0,70, 1)` | 18,57/20 |
| Generalization quality | holdout không giảm; có complexity/DB slices, nhưng extra-hard thấp | 7,50/10 |
| Workflow, safety, correction | completion 100%, valid 259/260, correction 6/6, safety fail-closed | 14,95/15 |
| Reproducibility và evaluation integrity | pinned manifest/hash/digest/seed, gold separation, resume provenance, CI | 15,00/15 |
| Laptop resource stability | nhiệt/RAM/swap tốt; trừ 2 điểm vì hai controlled guard stops | 8,00/10 |
| Latency | `10 × mean(60/85,29; 60/91,62)` | 6,79/10 |
| UI/API và khả năng demo | API/UI local, sanitized report, trace và Benchmark Lab | 5,00/5 |
| **Tổng** | `14,25 + 18,57 + 7,50 + 14,95 + 15 + 8 + 6,79 + 5` | **90,06 ≈ 90/100** |

### Cách hiểu điểm

- **90/100 theo chuẩn local-laptop engineering/portfolio**: kiến trúc, reproducibility, safety và
  Olist application quality rất mạnh; benchmark đủ nghiêm túc và trung thực để trình diễn.
- **Không phải 90/100 theo chuẩn research SOTA**: Spider 65% và extra-hard 36,36% còn khoảng cách
  lớn; full-1.034 và hidden-test leaderboard chưa chạy.
- Nếu chấm thuần accuracy paper/server, bỏ lợi thế engineering và hardware constraints, project chỉ
  nên ở khoảng **72–78/100**, tùy baseline/model được dùng để so sánh.

## 6. Muốn tăng từ 90 lên 95

Ưu tiên khoa học nhất, không làm laptop quá tải:

1. giảm `EXECUTION_MISMATCH` bằng error clustering theo aggregate/join/nested-query thay vì tăng
   model hoặc tăng GPU layers;
2. thêm deterministic semantic verifier và candidate reranking nhỏ cho medium/extra-hard;
3. cache planner/schema evidence và giảm token output để đưa P95 gần 60 giây;
4. chạy một fresh external subset sau khi khóa mọi tuning;
5. chỉ chạy full Spider-1.034 trên workstation/server phù hợp hoặc theo nhiều phiên cooled resume.

## 7. Kết luận

Benchmark hiện tại **đủ để đóng Gate P6 và chứng minh một project local chất lượng cao**. Điểm mạnh
nhất là Olist 95%, holdout Spider không collapse, workflow 100%, gold separation, safety và khả năng
resume có provenance. Điểm yếu chính là Spider semantic accuracy ở query phức tạp và P95 latency.
Đánh giá hợp lý nhất trên laptop hiện tại là **90/100**, với giới hạn được công khai thay vì che giấu.
