# So sánh kiến trúc Paper II / DIN-SQL với baseline Olist đã đóng băng

## Revision G — global semantic proof-first (REJECTED, đã phục hồi Revision E)

Revision E đã nâng prefix sạch lên 28/31 nhưng không thể vượt champion 57/60. Revision F sửa ba
failure class tổng quát: raw payment-record frequency, freight-per-order aggregate và
`customer_unique_id` source-grain lineage. Pilot Revision F không kết luận accuracy vì planner v2
timeout hai lần ở case đầu, dù guard không breach (đỉnh 2.125 MiB VRAM, 56 C, 45,18 W, swap 0).

Revision G đã thử resolver trước retrieval/model và deterministic compiler trên mọi binding
`PROVEN`, nhưng clean run chỉ đạt **7/10**. Hai case `005`, `007` kết thúc `MODEL_ERROR`; case
`010` sinh weighted-average SQL nhưng validator/corrector không hoàn tất. 8/10 case bị route vào
proof path, cho thấy catalog coverage đã bị dùng như ontology hoàn chỉnh. Candidate được lưu
để điều tra tại `c4851eb` nhưng bị reject. Revision E 28/31 đã được phục hồi tại
`80e94ec`; gate phục hồi pass 260 test non-Ollama. Không giữ exact payment/freight aliases,
product-category special checks hay global zero-model route. P6 57/60 vẫn là champion.

Nguồn thiết kế: [SQLens, NeurIPS 2025](https://proceedings.neurips.cc/paper_files/paper/2025/hash/c57812dee8acade8c5e385260b2cde28-Abstract-Conference.html),
[Multi-grained Error Identification, COLING 2025](https://aclanthology.org/2025.coling-main.289/),
[DAC, Findings EMNLP 2025](https://aclanthology.org/2025.findings-emnlp.22/), và
[DART-SQL, Findings ACL 2024](https://aclanthology.org/2024.findings-acl.120/).

## Revision C — semantic proof và hierarchical backtracking (2026-09-13)

Revision C xử lý failure class, không hard-code gold SQL. Phân tích prefix revision B cho thấy bốn
SQL đều executable nhưng sai entity/value, identity/grain hoặc distribution shape. Thiết kế mới:

1. proof gate question--entity--skeleton bắt explicit order status, explicit
   `customer_unique_id`, returning-customer scalar grain, full distribution và tie-break;
2. semantic validation dùng SQL nguyên bản, còn safety policy vẫn execute bản normalized có
   `LIMIT 200`, tránh nhầm safety limit thành model intent;
3. correction target đúng clause và được backtrack tối đa hai bước, nhưng dừng ngay khi SQL/error
   lặp;
4. owner/join failure chỉ mở rộng schema khi catalog <=12 bảng và context <=1.600 token;
5. returning-customer + more-than-one-order được route sang DIN vì đây là group-filter aggregate
   dependency, thay vì giả định là scalar EASY.

Cách này phù hợp với evidence mới: SQLens dùng database+LLM signal theo clause và báo tăng execution
accuracy của hệ có sẵn tới 20%; multi-grained identification tách system/skeleton/value error; DAC
so entity+skeleton trước correction và báo tăng trung bình 1,4 điểm trên Spider/BIRD/KaggleDBQA.
DART-SQL cũng cho thấy database content + execution-guided refinement cải thiện trung bình 12,41%
cho DAIL-SQL và 5,38% cho C3. Các con số paper chỉ là external prior, không phải claim cho project.

Diagnostic source-locked trên bốn regression revision B, dưới guarded profile, cho revision C bước
đầu đạt 2/4: `003` và `007` đều sai first pass nhưng correction cứu đúng; `011` chứng minh hai bước
shape -> owner vẫn không đủ khi baseline route giữ skeleton sai; `014` phát hiện bug safety-limit và
đã có deterministic regression test. V3 schema expansion vẫn không cứu `011` (0/1, 149,59 giây),
nên route được sửa ở reasoning thay vì tăng retry tiếp. Đây là diagnostic reused-development set,
không phải benchmark/promotion score; cần evaluation ID sạch trên Olist gate mới.

Nguồn chính: [SQLens, NeurIPS 2025](https://proceedings.neurips.cc/paper_files/paper/2025/hash/c57812dee8acade8c5e385260b2cde28-Abstract-Conference.html),
[Multi-grained Error Identification, COLING 2025](https://aclanthology.org/2025.coling-main.289/),
[DAC, Findings EMNLP 2025](https://aclanthology.org/2025.findings-emnlp.22/), và
[DART-SQL, Findings ACL 2024](https://aclanthology.org/2024.findings-acl.120/).

## Cập nhật revision B — baseline-equivalent selective DIN

### Kết luận

Revision B sửa đúng confound của A4500: `BASELINE_PRESERVE` không còn dùng deterministic control
planner và không còn gọi `prepare_for_planning()`/BM25 thay cho đường P6. Nó chạy planner v2, hybrid
`ground()`, generator v4 và corrector v3 theo cùng thứ tự với baseline; chỉ plan có dependency phức
tạp rõ ràng mới gọi thêm grounded DIN planner/generator. Đây là điều kiện cần để paired transition
có thể quy cho DIN thay vì cho một baseline bị thay thế.

Code và dependency tests đã hoàn tất; `make check` pass **240 test**, 1 Ollama test deselect. Sau khi
Administrator hard-cap GPU ở 300--600 MHz, pilot một case pass và đúng checkpoint được tiếp tục.
Accuracy kill dừng source-locked run tại **10/14 (71,43%)**: bốn lỗi đã làm cận trên toàn suite chỉ
còn `10 + 46 = 56/60`, thấp hơn gate 57/60. Baseline P6 đúng **13/14 (92,86%)** trên cùng prefix;
paired delta là -3 case / -21,43 điểm phần trăm. Vì vậy revision B không được promote và Spider vẫn
bị khóa.

Đây không phải resource failure. Peak monitor liên tục của guarded server là VRAM 1.719 MiB, 57 C,
72,26 W, utilization 98%, graphics clock 600 MHz, RAM khả dụng tối thiểu 22,31 GiB và swap 0. Sau
run không còn Ollama/benchmark process. Hard clock vẫn cần được reset từ Administrator PowerShell
bằng `nvidia-smi -i 0 -rgc`.

### Cơ sở nghiên cứu và thiết kế

DIN-SQL cho thấy decomposition có lợi khi tách schema linking, difficulty classification,
difficulty-specific generation và self-correction, nhưng kết quả paper không chứng minh rằng mọi
query nên đi qua decomposition.^1 DEA-SQL củng cố cách nhìn workflow theo độ khó và lọc thông tin để
giảm attention diffusion.^2 RoSL đặc biệt phù hợp với Qwen local nhỏ hơn: decomposition ở schema
linking được báo cáo tăng schema recall và execution accuracy trên BIRD, nên nên đặt nó trong nhánh
specialist thay vì thay retrieval của control.^3

Hai bổ sung tiếp theo nên được làm theo gate riêng, không nhồi vào revision B:

1. **Semantic proof graph / SQLens-inspired validation.** So khớp question-plan-SQL theo từng
   clause, owner, population, grain và modifier; chỉ correction khi có signal từ database/AST.
   SQLens báo fine-grained database+LLM signals tốt hơn self-evaluation và có thể cải thiện hệ
   Text-to-SQL có sẵn, nhưng project chỉ chuyển giao interface deterministic/typed, không nhập
   model hay data của paper.^4
2. **Join-hop-aware DIN.** Tính hop depth từ FK graph sau retrieval; chỉ decomposition sâu khi
   đường join dài hoặc có anti-join/subquery dependency. SchemaScope 2026 cho thấy accuracy giảm
   mạnh theo join-hop và decomposition theo subquery là một remedy, nhưng evidence dùng frontier
   models/benchmark khác nên chỉ là prior cho Spider, chưa phải claim Olist.^5

Không mở best-of-N lúc này. Tailored prompting cho thấy schema-link granularity và clause order có
ảnh hưởng, nhưng multi-solution + selector sẽ tăng inference/latency và không giải quyết confound
control trước.^6

### Kiến trúc revision B

```text
question
  -> P6 router + decomposer + planner v2
  -> conservative complexity route
       BASELINE_PRESERVE
         -> P6 hybrid ground -> generator v4 -> validator -> corrector v3
       DIN_SQL_ENHANCE
         -> decomposed semantic linking -> DIN typed clause plan
         -> plan consistency -> DIN generator -> shared validator/corrector
```

### Gate tiếp theo

- Revision B đã hoàn thành phép đo và bị reject; không resume checkpoint và không sửa theo ID lỗi.
- Giữ P6 làm champion. Bước nghiên cứu kế tiếp phải đo control variance nhiều seed/run trên một
  development partition tách biệt, rồi mới thử proof-graph validator hoặc join-hop-aware DIN như
  một intervention độc lập.
- Chỉ mở evaluation Olist-60 mới sau construction gate, `make check`, pilot mới và evaluation ID
  sạch. Promotion tối thiểu 57/60; research target 58/60. Không chạy Spider trước non-regression.

### Bằng chứng revision B

| Trường | Giá trị |
|---|---|
| Evaluation ID | `olist-paper2-revb-baseline-equivalent-v1-prefix-14` |
| Candidate prefix | 10/14 (71,43%) |
| Baseline P6 cùng prefix | 13/14 (92,86%) |
| Upper bound candidate | 56/60 |
| Candidate EN / VI | 6/7 / 4/7 |
| Candidate easy / medium | 7/9 / 3/5 |
| Workflow / valid candidate | 14/14 / 14/14 |
| P50 / P95 | 54,26 s / 213,16 s |
| Correction | thử 1, cứu 0 |
| Prediction SHA-256 | `cd9ec9b3a595f9229b8f1fb45fbaf27d0625c88da596e6e6f122e636102ed29f` |
| Progress SHA-256 | `c1dc4364c7be8e72033e5fdb6ebca9a2c6d4523eb4e0124dced374dbd9c28243` |

Ba paired regression là `olist_acc_003`, `007`, `011`; `olist_acc_014` sai ở cả candidate và P6.
Case DIN-enhanced duy nhất trong prefix, `olist_acc_013`, đúng với clause/schema/plan-to-SQL metrics
đều 1,0. Quan sát này vẫn quá ít để ước lượng DIN effect; kết quả chủ yếu cho thấy một LLM baseline
run không mặc nhiên tái lập champion lịch sử dù call graph đã tương đương. Raw artifacts ở local,
gitignored theo policy:

- `evals/predictions/olist-paper2-revb-baseline-equivalent-v1.jsonl`;
- `evals/reports/olist-paper2-revb-baseline-equivalent-v1.progress.json`.

### Nguồn của cập nhật revision B

1. Pourreza & Rafiei. [DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with Self-Correction](https://proceedings.neurips.cc/paper_files/paper/2023/hash/72223cc66f63ca1aa59edaec1b3670e6-Abstract-Conference.html). NeurIPS 2023.
2. Xie et al. [Decomposition for Enhancing Attention: Improving LLM-based Text-to-SQL through Workflow Paradigm](https://aclanthology.org/2024.findings-acl.641/). Findings of ACL 2024.
3. Pradeep et al. [Divide, Link, and Conquer: Recall-oriented Schema Linking for NL-to-SQL via Question Decomposition](https://aclanthology.org/2025.emnlp-industry.122/). EMNLP Industry 2025.
4. Gong et al. [SQLens: An End-to-End Framework for Error Detection and Correction in Text-to-SQL](https://proceedings.neurips.cc/paper_files/paper/2025/hash/c57812dee8acade8c5e385260b2cde28-Abstract-Conference.html). NeurIPS 2025.
5. Bukkapatnam & Malik. [SchemaScope: How Join-Hop Depth Breaks Text-to-SQL in Large Language Models, and a Decomposition-Based Remedy](https://aclanthology.org/2026.surgellm-1.17/). SURGeLLM 2026.
6. Tan et al. [Enhancing Text-to-SQL Capabilities of Large Language Models through Tailored Promptings](https://aclanthology.org/2024.lrec-main.539/). LREC-COLING 2024.

---

**Trạng thái thí nghiệm:** revision A4500 tối ưu đã dừng đúng accuracy gate tại checkpoint 20;
candidate không đạt điều kiện non-regression

**Ngày:** 2026-09-12 (Asia/Bangkok)

**Quyết định:** **GIỮ baseline P6 làm champion.** Loại revision `f70d191` và candidate A4500
`c40b75c`; không promote Paper II và không chạy Spider. Runtime mặc định vẫn là P6
(`TEXT2SQL_PLANNING_MODE=baseline`); DIN-SQL chỉ còn là research opt-in.

## 0. Kết quả revision A4500 source-locked

### Phán quyết

Revision kiến trúc `924a1d3` và harness `c40b75c` đã giải quyết được vấn đề vận hành: một case hoàn
thành trong khoảng 15,72 giây ở pilot ext4 thay vì 113,17 giây khi đọc model từ NTFS; run không có
OOM, swap, thermal/power stop hoặc shutdown. Tuy nhiên candidate **không giữ được accuracy**.

Evaluation ID sạch `olist-paper2-a4500-c40b75c-v1` được pilot một case rồi tiếp tục đúng cùng
checkpoint. Tại case 20, evaluator offline đo `16/20`; do còn 40 case, cận trên toàn suite là:

```text
16 đúng + 40 chưa chạy = tối đa 56/60 < 57/60
```

Guarded wrapper vì vậy phát `ACCURACY_STOP` và không mở case 21–60. Đây không phải score full-suite
`56/60`; kết quả có thể bảo vệ là prefix **16/20 (80,00%)** và upper bound **<=56/60**. Baseline P6
đạt **19/20 (95,00%)** trên đúng prefix này, nên paired delta là **-3 case / -15 điểm phần trăm**.

### Candidate thực sự đã chạy gì

```text
DecomposedQuestion
  -> deterministic control plan (không gọi LLM)
  -> adaptive route trước generation
       BASELINE_PRESERVE: 19/20
       DIN_SQL_ENHANCE:     1/20
  -> một BM25 grounding pass
  -> Qwen generator; optional bounded correction
```

Nhánh EASY dùng một model call thay vì planner + generator; nhánh complex dùng hai. Qwen được giữ
resident trong một case, wrapper unload sau từng checkpoint và cooldown 60 giây. Query retrieval
trên profile laptop dùng BM25 để BGE không thay Qwen trong one-model slot. Tổng cộng prefix dùng 27
LLM calls, 26.146 prompt tokens, 1.651 output tokens; P50 là 25,68 giây và P95 50,86 giây.

### Paired attribution, không sửa theo case

| Nhóm paired trên 20 case | Số case |
|---|---:|
| Cả hai đúng | 16 |
| Candidate sửa được baseline sai | 0 |
| Candidate làm hỏng baseline đúng | 3 |
| Cả hai sai | 1 |

Ba hồi quy mới là `olist_acc_016`, `018`, `020`; cả ba đều mang provenance
`BASELINE_PRESERVE`, không đi qua DIN planner. Case duy nhất kích hoạt `DIN_SQL_ENHANCE`,
`olist_acc_013`, trả đúng và có clause/table/column/join recall cùng plan-to-SQL agreement bằng
1,0. Case `014` sai ở cả baseline lẫn candidate vì tie-break direction, nên không tạo paired gain
hay regression.

Điều này chỉ ra lỗi thiết kế ở **intervention isolation**, không phải một danh sách ba câu cần
hard-code: route được gọi là “baseline preserve” nhưng đã thay P6 planner LLM bằng deterministic
control skeleton **và** đổi retrieval backend từ hybrid BGE sang BM25. Vì hai thay đổi cùng lúc,
không thể quy ba hồi quy cho riêng planner hay retrieval; SQL sai ở `016`, `018`, `020` phù hợp với
việc mất planning/schema evidence của baseline. Benchmark bác bỏ toàn bộ candidate tích hợp này,
nhưng chỉ có một quan sát thật sự về DIN complex path; không đủ cơ sở để tuyên bố phương pháp
DIN-SQL nói chung phản tác dụng.

### Bằng chứng tái lập

| Trường | Giá trị |
|---|---|
| Source revision | `c40b75cdc8a96c0064ccbf95c1c09cf75a924a0b` (parent kiến trúc `924a1d336201ef7eae5471130da40f32d7bbd906`) |
| Evaluation ID | `olist-paper2-a4500-c40b75c-v1-prefix-20` |
| Candidate prefix | 16/20 (80,00%) |
| Paired baseline prefix | 19/20 (95,00%) |
| Upper bound candidate | <=56/60 |
| Candidate EN / VI | 6/10 / 10/10 |
| Candidate easy / medium | 10/12 / 6/8 |
| First pass | 13/20 |
| Correction | thử 6, cứu 4 |
| Prediction SHA-256 | `b223e0d779826878376eab672d50f05feb8671fa9c2e478620861de37b734384` |
| Progress SHA-256 | `42b0012f3ac2b694f998cf4d82fdd010c4b011018d87d3c3dbcdc895b0bcac4c` |
| Baseline report SHA-256 | `26fbb521ac3d693258429e6a22ba6847602ac3c0874dec4182618ad81264064e` |

Raw prediction/report ở local theo policy và không commit:

- `evals/predictions/olist-paper2-a4500-c40b75c-v1.jsonl`;
- `evals/reports/olist-paper2-a4500-c40b75c-v1.progress.json`.

### An toàn phần cứng và trạng thái sau run

Run dùng profile `olist-paper2-a4500-safe`: batch một, sampling 0,5 giây ở cả guarded server lẫn
wrapper, `TEXT2SQL_OLLAMA_NUM_GPU=6`, một model resident, 512 output tokens, request timeout 240
giây, hard clock Administrator 300–600 MHz, stop ở VRAM 4.096 MiB / 65°C / 70 W / 650 MHz, RAM
khả dụng tối thiểu 14 GiB và swap dưới 0,25 GiB. Exact Qwen manifest và năm blob được SHA-256 verify
rồi stage trên ext4; generation và embedding không chạy đồng thời.

Không guard nào bị breach; nếu một sample vi phạm thì server/wrapper đã dừng với exit 75 thay vì
đi tới accuracy stop 76. Peak đã quan sát và giữ lại đến checkpoint 13 là RAM dùng 2,148 GiB, swap
0, VRAM 2.692 MiB, 58°C và 59,69 W; terminal stdout sau checkpoint 20 không được lưu thành artifact,
nên không trình bày các số này như peak chính xác của toàn prefix. Ràng buộc có thể khẳng định cho
toàn run là mọi sample đều nằm nghiêm dưới các stop nói trên.

Sau accuracy stop, Ollama/model đã unload và hard clock được reset bằng Administrator. Mẫu idle xác
minh: RAM khả dụng 22 GiB, swap 0, VRAM 575 MiB, GPU 46°C, 17,50 W và graphics clock 210 MHz; không
còn process model hoặc benchmark.

### Quyết định phát triển

Không resume checkpoint, không chạy Spider và không sửa ba case rồi rerun. Bước Paper II tiếp theo,
nếu được mở thành revision nghiên cứu mới, phải là factorial ablation trên development set riêng:

1. chứng minh `BASELINE_PRESERVE` giữ nguyên P6 planner, retrieval/context và model-call contract;
2. tách deterministic routing/retrieval intervention khỏi DIN intervention; BM25 hoặc planner
   skeleton không được gọi là baseline-preserving;
3. nếu cần BGE trên laptop, chạy embedding tuần tự rồi unload trước Qwen và calibrate bằng pilot mới,
   hoặc dùng một retriever không-model đã được đánh giá độc lập;
4. đo đủ population của complex route trước khi kết luận về DIN;
5. chỉ mở lại Olist-60 với commit/evaluation ID sạch sau construction gate và `make check`.

Candidate hiện tại bị **REJECTED FOR PROMOTION**. R2 vẫn `IN_PROGRESS`, không `VERIFIED`.

## 0A. Lịch sử revision adaptive baseline-first

Sau kết quả `8/12` của revision đầu, project chỉ thực hiện một redesign ở cấp kiến trúc, không sửa
theo benchmark ID. Revision sạch `e8fab80582113263fa75e1f625fc7b9729fbe65f` thay đổi intervention
boundary như sau:

```text
frozen P6 planner
  -> AdaptiveRouteDecision
       mặc định BASELINE_PRESERVE
         -> nguyên P6 grounding -> generator -> corrector
       chỉ cấu trúc dependency phức tạp mới DIN_SQL_ENHANCE
         -> semantic evidence -> schema-bounded DIN planner
         -> typed plan validation -> DIN generator/corrector
```

DIN chỉ được kích hoạt bởi các family tổng quát: set/comparison, nested/anti-join, aggregate
dependency, hoặc grouped aggregate/ranking có nhiều semantic role. Coverage của catalog không được
dùng để tự kích hoạt DIN. EASY không còn đi qua deterministic semantic compiler trong hybrid
runtime. Đồng thời, aggregate contract mang source grain, weight column và rounding; validator tiêu
thụ proven lineage thay vì chỉ dò tên cột trong SQL.

Construction gate của revision này đã pass `make check`: Ruff, format, strict mypy trên 111 source
file và **235 pytest pass**, một Ollama test deselect. Test mới chứng minh route distribution,
baseline path/call preservation, complex three-stage hand-off, schema-bounded DIN prompt,
weighted-average grain và lineage compatibility.

### Guarded pilot của revision adaptive

Evaluation ID mới là `olist-paper2-adaptive-e8fab80-v1`; không resume hoặc trộn artifact của
`f70d191`. Pilot dùng đúng profile `olist-paper1-ultrasafe`, hard clock 300–600 MHz, một GPU layer,
batch một case, sampling 0,5 giây, unload/cooldown và checkpoint.

Case đầu `olist_acc_001` dừng ở P6 planner với `Ollama request failed: ReadTimeout` sau khoảng 600
giây, trước grounding, adaptive routing và SQL generation. Guarded wrapper dùng đúng một retry hạ
tầng; retry cũng timeout ở cùng stage. Vì không có SQL/prediction về mặt nội dung, full Olist được
dừng và Spider không chạy. Con số cơ học `result_correct_count=0` trong progress report **không phải
accuracy 0/1 có thể dùng để đánh giá kiến trúc**; pilot này là infrastructure-inconclusive.

Artifact local, không commit theo policy:

- prediction terminal: `evals/predictions/olist-paper2-adaptive-e8fab80-v1.jsonl`;
- progress report: `evals/reports/olist-paper2-adaptive-e8fab80-v1.progress.json`;
- SHA-256 prediction: `264a1771a2ae3fa6afb3e717dc796ad3557f462d62ab0ad1349d9cb03cb7e751`;
- SHA-256 progress: `32c4f6ba17f2f807ec566708ceca4c607349694ce2b84e13f2da89e16fc287c5`.

Peak quan sát của pilot adaptive là RAM hệ thống dùng 1,843 GiB, swap 0, VRAM 1.682 MiB, 56°C,
45,07 W và 600 MHz. Không có OOM, resource breach, throttle do guard hay shutdown. Sau khi dừng,
không còn process model/benchmark; idle sample là RAM khả dụng 22 GiB, swap 0, VRAM 688 MiB, 50°C,
20,95 W và clock 210 MHz sau reset.

Kết quả này không bác bỏ redesign về accuracy. Nó cho thấy frozen baseline-first path gọi P6 planner
không hoàn tất trong deadline 600 giây dưới profile một GPU layer bắt buộc. Đánh giá tiếp cần giữ
nguyên commit/evaluation protocol và chuyển sang server đủ mạnh hoặc một profile laptop mới được
calibrate, phê duyệt và pilot riêng; không được tăng timeout/clock rồi tự resume artifact này.

## 1. Kết luận điều hành

Baseline P6 đã đóng băng đạt **57/60 (95,00%)** trên Olist-60. Benchmark Paper II được chạy từ
revision sạch `f70d191` và dừng tại checkpoint 12 sau khi có bốn kết quả sai. Prefix được evaluator
offline chấm **8/12 (66,67%)**; ngay cả nếu toàn bộ 48 case chưa chạy đều đúng, điểm cuối cao nhất
chỉ còn:

```text
8 case đã đúng + 48 case chưa chạy = tối đa 56/60 (93,33%)
```

Cận trên này thấp hơn champion `57/60`, nên chạy tiếp không thể thỏa điều kiện non-regression. Trên
cùng 12 case đầu, baseline đạt **12/12 (100%)**: biến thể mới tạo bốn hồi quy và không sửa thêm case
nào trong prefix.

Đây không phải điểm full-suite `56/60`. Con số có thể bảo vệ là prefix thực đo `8/12` và cận trên
toàn suite `<=56/60`. Holdout chưa được mở tới, Spider không chạy, và không có tuyên bố tăng accuracy.

Kết luận kỹ thuật quan trọng hơn từng failure: typed clause plan đạt **100% clause exact/F1** trên
prefix nhưng execution accuracy chỉ **66,67%**. Kiến trúc hiện kiểm tốt sự hiện diện của clause,
nhưng chưa chứng minh đúng population, grain và semantic owner; correction cũng không cứu được hai
case đã thử. Vì vậy, revision hiện tại không đủ điều kiện promotion.

## 2. Các hệ thống được so sánh

Cả hai hệ thống dùng cùng manifest `olist-acceptance-60.jsonl` đã review và cùng Olist SQLite của
project. Gold chỉ được evaluator offline mở sau khi prediction đã checkpoint; runtime không import
`agentic_text2sql_eval` hoặc benchmark gold.

### Baseline P6 đã đóng băng

```text
Câu hỏi
  -> router/decomposer
  -> logical planner
  -> hybrid schema retrieval + bounded context
  -> SQL candidate
  -> AST/read-only/semantic/result-shape validation
  -> bounded correction
  -> typed terminal result
```

Revision hệ thống baseline là `1509faa`; commit evidence trực tiếp kế tiếp là `0972e47`, nơi ghi
Olist `57/60` và Spider `130/200`. Baseline lịch sử dùng sáu GPU layer, nên latency không phải phép
A/B phần cứng với run Paper II siêu an toàn một GPU layer.

### Biến thể Paper II / DIN-SQL

```text
DecomposedQuestion
  + SemanticCatalog versioned và kiểm với CatalogSnapshot
  -> SemanticBinding(PROVEN | INCOMPLETE | AMBIGUOUS)
       AggregateSpec, PredicateSpec, owners/columns/rule IDs
  -> required-evidence SchemaContext
  -> SemanticLinkPlan
  -> ComplexityDecision(EASY | NON_NESTED | NESTED)
  -> typed ClausePlan
       SELECT/FROM/JOIN/WHERE/GROUP/HAVING/ORDER/LIMIT/subquery/set
       + output grain
  -> PlanConsistencyValidator
  -> PROVEN scalar: deterministic SQLGlot compiler
     unsupported EASY: baseline generator fallback
     validated complex: DIN generator
  -> normal validation + clause-specific bounded correction
```

Implementation chuyển giao interface phân rã của DIN-SQL, không sao chép prompt GPT-4 dài hoặc
chain-of-thought tự do. Semantic catalog không chứa case ID, gold SQL hay expected rows. Compiler
chỉ nhận typed aggregate/predicate và fail closed khi bằng chứng không đầy đủ.

## 3. Bằng chứng có thể tái lập

| Bằng chứng | Baseline P6 | Paper II hiện tại |
|---|---:|---:|
| Revision | `1509faa` | `f70d1912220902326d821557ab3ab5d6a616f39b` |
| Evaluation ID | `olist-acceptance-60-p6-v1` | `olist-paper2-semantic-f70d191-v1-prefix-12` |
| Case đã đánh giá | 60 | Prefix 12, sau đó dừng |
| Result đúng | 57/60 (95,00%) | 8/12 (66,67%) |
| Cùng prefix 12 case | 12/12 (100%) | 8/12 (66,67%) |
| Thay đổi theo cặp | — | **-4 case / -33,33 điểm %** |
| First-pass đúng | 51/60 (85,00%) | 8/12 (66,67%) |
| Correction thử/cứu | 6/6 | 2/0 |
| Valid candidate | không dùng làm gate | 11/12 (91,67%) |
| P50 | 61,92 giây | 30,15 giây |
| P95 | 91,62 giây | 630,76 giây |
| Tiếng Việt | 29/30 (96,67%) | 4/6 (66,67%) |
| Tiếng Anh | 28/30 (93,33%) | 4/6 (66,67%) |
| Easy | 34/37 (91,89%) | 7/8 (87,50%) |
| Medium | 21/21 (100%) | 1/4 (25,00%) |
| Clause exact / macro F1 | chưa đo | 12/12 / 1,000 |
| Table / column recall macro | chưa đo | 0,6667 / 0,5556 |
| Plan -> SQL clause agreement | chưa đo | 1,000 |
| Cận trên toàn suite | đã đo 57/60 | **<=56/60 (93,33%)** |

P50 thấp của Paper II chủ yếu do bảy case đi qua deterministic compiler; P95 bị chi phối bởi timeout
600 giây. Không được suy ra Paper II nhanh hơn baseline nói chung vì cấu hình GPU và tỷ lệ fast path
khác nhau.

Artifact local, không commit theo policy repository:

- prediction: `evals/predictions/olist-paper2-semantic-f70d191-v1.jsonl`;
- prefix report: `evals/reports/olist-paper2-semantic-f70d191-v1.progress.json`;
- SHA-256 prediction: `f17fbe387c474ab250240ae46e7ab9b2301b595282c059a3a348083df12c7752`;
- SHA-256 prefix report: `6968c180968b86f59e1ad2379ab45fd916d23ee64077ab22878ead027ddcf200`;
- baseline report SHA-256: `26fbb521ac3d693258429e6a22ba6847602ac3c0874dec4182618ad81264064e`;
- baseline prediction SHA-256: `f7ee0fd35ca0bf3ea680d326119dcbb6b425d1effb3922ca997446e810c91fe9`.

## 4. Bốn failure chính xác

### `olist_acc_005` — semantic binding không hoàn tất, fallback model timeout

- Câu hỏi: `Tổng doanh thu sản phẩm tính theo cents là bao nhiêu?`
- Kỳ vọng: tổng `price_cents`, baseline trả `1359164370`.
- Paper II nhận ra `order_item_totals.product_revenue_cents`, nhưng binding là `INCOMPLETE` với
  `NON_SCALAR_SHAPE` và `COUNT_METRIC_CONFLICT`.
- Hệ thống chuyển sang generator fallback, hết thời gian sau khoảng 600 giây và trả `MODEL_ERROR`.
- Guarded runner cho phép đúng một retry hạ tầng; retry cũng timeout, không có prediction đúng để
  thay checkpoint.

Đây là lỗi boundary giữa semantic matcher và fallback: intent `SUM` đúng tồn tại trong catalog,
nhưng parser tạo conflict nên deterministic path không được dùng. Fallback quá đắt dưới profile an
toàn một GPU layer và không bảo đảm terminal SQL.

### `olist_acc_010` — đúng clause shape nhưng sai grain

- Câu hỏi: `What is the average review score rounded to 6 decimals?`
- Kỳ vọng: `4.086421`, tính trên các review row.
- SQL mới:

```sql
SELECT AVG(average_review_score) FROM order_review_summary
```

- Kết quả: `4.0867934152875325`; trạng thái `SUCCEEDED` nhưng evaluator chấm sai.

`order_review_summary` có grain một dòng mỗi order. Lấy trung bình của trung bình theo order làm mỗi
order có trọng số bằng nhau, khác với trung bình trên mọi review row; SQL cũng không áp dụng yêu cầu
làm tròn sáu chữ số. Catalog gắn `metric.review_score` với owner dẫn xuất không giữ được weighting
semantics. Plan/SQL agreement 100% không phát hiện được lỗi owner/grain này.

### `olist_acc_011` — SQL đúng ý nhưng validator từ chối semantic view

- Câu hỏi: `Có bao nhiêu khách hàng quay lại với hơn một đơn hàng?`
- SQL được compiler tạo:

```sql
SELECT COUNT(*) FROM customer_order_facts WHERE order_count > 1
```

- View `customer_order_facts` đã có grain `customer_unique_id`; SQL này biểu diễn đúng phép đếm.
- Validator yêu cầu chuỗi `customer_unique_id` xuất hiện trực tiếp trong SQL, báo
  `SEMANTIC_MISMATCH`; correction gọi model nhưng kết thúc `MODEL_ERROR` sau khoảng 600 giây.

Typed lineage đã chứng minh grain nhưng semantic validator cũ không tiêu thụ lineage đó. Đây là
false positive do contract giữa planner/compiler/validator không thống nhất, không phải thiếu clause.

### `olist_acc_012` — semantic catalog bỏ sót quan hệ timestamp, correction lặp lỗi

- Câu hỏi: `How many orders were delivered late based on actual versus estimated delivery timestamp?`
- Kỳ vọng: `7827`, baseline dùng `order_delivery_facts.is_late_delivered = 1`.
- Binding ban đầu chỉ giữ `COUNT orders` và `order_status='delivered'`; không giữ phép so sánh actual
  với estimated timestamp.
- Corrector tạo:

```sql
SELECT COUNT(*)
FROM olist_orders_dataset
WHERE order_delivered_customer_date > order_estimated_delivery_date
  AND order_status = 'delivered'
```

- Kết quả thực thi là `7826`; validator đúng khi phát tín hiệu
  `DELIVERY_POPULATION_NARROWED_BY_STATUS`, nhưng correction lặp lại lỗi và dừng.

Một row có actual timestamp trễ nhưng không thuộc status filter bị loại. Lỗi gốc nằm trước generator:
semantic binding không biểu diễn predicate so sánh hai cột hoặc rule derived late-delivery, nên typed
plan đã mất điều kiện cốt lõi.

## 5. Chuyển đổi theo cặp so với baseline

Baseline đúng cả `olist_acc_001` đến `olist_acc_012`. Paper II giữ đúng tám case
`001–004`, `006–009` và làm sai `005`, `010`, `011`, `012`.

```text
case baseline sai được sửa trong prefix: 0
case baseline đúng bị hồi quy:          4
thay đổi ròng:                         -4
```

Ba trong bốn lỗi nằm ở medium hoặc semantic aggregate; easy cũng hồi quy một case do timeout. Đây
không phải bằng chứng DIN-SQL nói chung làm giảm accuracy. Nó chứng minh revision tích hợp hiện tại
không giữ được champion trên Olist dưới cấu hình vận hành được phép.

## 6. Kết quả planning và điều nó thực sự đo

Offline planning metrics báo clause exact `12/12`, macro clause F1 `1,000` và plan-to-SQL clause
agreement `1,000`. Tuy nhiên table recall chỉ `0,6667`, column recall `0,5556`, và result accuracy
`0,6667`.

Sự tách rời này có nguyên nhân:

- clause metric chỉ biết câu hỏi cần `SELECT/FROM/WHERE`, không chứng minh đúng relation/grain;
- plan-to-SQL agreement chỉ chứng minh generator làm theo plan, không chứng minh plan đúng;
- semantic view có thể đúng cột nhưng sai weighting population;
- validator vẫn dùng lexical rule ngoài typed lineage;
- một plan không có SQL vì timeout vẫn có thể đúng clause presence.

Do đó, metric planning hiện là kiểm tra cấu trúc nội bộ, không phải surrogate đủ mạnh cho execution
accuracy. Gate tiếp theo phải đo population owner, grain transformation, predicate completeness và
semantic-view lineage, thay vì tối ưu clause F1 vốn đã bão hòa.

## 7. Hồ sơ an toàn phần cứng

Không benchmark local-LLM nào được chạy trực tiếp. Run dùng guarded Ollama server và guarded Olist
wrapper với profile `olist-paper1-ultrasafe` đã được phê duyệt:

- `TEXT2SQL_OLLAMA_NUM_GPU=1`, CPU tối đa 6 core;
- batch một case, checkpoint atomic, một model resident;
- sample RAM/swap/VRAM/nhiệt/công suất/utilization/clock mỗi 0,5 giây;
- unload model sau mỗi case, cooldown 60 giây;
- VRAM stop 4.096 MiB, nhiệt stop 65°C, power stop 78 W, clock watchdog 650 MHz;
- Qwen3-14B `q4_K_M`, context 4.096, q8 KV; embedding và generation không chạy đồng thời;
- NVIDIA Administrator hard clock lock `300–600 MHz`, xác minh bằng peak 600 MHz dưới tải.

Trước pilot: RAM khả dụng 22,60 GiB, swap 0, VRAM 564 MiB, 51°C, 21,05 W. Pilot case đầu đúng
`1/1` và nằm xa mọi ngưỡng. Peak tích lũy quan sát trong run:

| Tài nguyên | Peak quan sát | Stop |
|---|---:|---:|
| RAM hệ thống dùng | 2,277 GiB | guard yêu cầu hệ thống còn >=14 GiB |
| Swap dùng | 0 GiB | 0,25 GiB |
| VRAM | 1.557 MiB | 4.096 MiB |
| GPU temperature | 56°C | 65°C |
| GPU power | 45,01 W | 78 W |
| Graphics clock | 600 MHz | 650 MHz |

Không có OOM, thermal/power breach, throttle do chạm guard hay shutdown. Sau accuracy stop, runner và
Ollama được dừng, model đã unload, RAM khả dụng trở lại 22 GiB, swap 0, VRAM 564 MiB, GPU 49–50°C và
khoảng 20,7 W. Lệnh Administrator `nvidia-smi -rgc` thành công; clock idle trở lại 210 MHz.

## 8. Logic dừng và vì sao Spider không chạy

1. Case 1 là pilot guarded và đúng; cùng checkpoint được tiếp tục, không ghép artifact khác.
2. Evaluator chấm offline sau từng durable prediction.
3. Tại checkpoint 12, điểm thực là `8/12`.
4. Cận trên là `8 + (60 - 12) = 56`, thấp hơn ngưỡng `57`.
5. Wrapper phát `ACCURACY_STOP` và dừng với checkpoint được bảo toàn.
6. Theo protocol, Spider chỉ chạy nếu Olist giữ champion; điều kiện đó không đạt.

Chạy nốt 48 case không thể thay đổi quyết định non-regression và sẽ vừa tốn compute vừa mở thêm
holdout sau khi giả thuyết đã bị bác. Spider “tính sau” ở đây có nghĩa là chỉ chạy từ một revision
mới đã vượt gate Olist bằng evaluation ID mới, không resume artifact này.

## 9. Phán quyết nhân quả

```text
typed decomposition và compiler giảm LLM call trên scalar dễ
  + clause plan giữ hình dạng truy vấn nhất quán
  - semantic binding chưa đóng kín population/grain/predicate
  - validator cũ không tiêu thụ typed lineage
  - fallback/correction không khả dụng ổn định dưới runtime siêu an toàn
  = cấu trúc nội bộ nhất quán nhưng kết quả giảm 4/12 so với baseline
```

DIN-SQL vẫn có giá trị cho bài toán complex query, đặc biệt trên Spider medium/hard. Nhưng đưa semantic
compiler mới vào fast path Olist đã thay hành vi của các câu baseline vốn đúng. Revision này thất bại
ở non-regression trước khi có cơ hội chứng minh gain trên Spider.

Không nên sửa lần lượt bốn case vừa thấy rồi rerun cùng holdout như bằng chứng. Điều đó lặp lại kiểu
overfit case-directed đã bị loại trước khi construct `f70d191`. Evidence này chỉ được dùng để xác định
failure family và thiết kế invariant ở một development set riêng.

## 10. Định hướng kiến trúc nên làm tiếp

Nếu tiếp tục Paper II, cần một revision mới theo các contract tổng quát sau:

1. **Semantic operator completeness:** binding chỉ `PROVEN` khi mọi metric, modifier, rounding và
   predicate quan hệ cột-cột đều có typed representation; token `tổng` không được gây conflict với
   metric `SUM` đã xác định.
2. **Grain algebra:** mỗi table/view khai báo input grain, output grain, weighting key và aggregate
   composability. `AVG(AVG(x))` phải fail closed trừ khi có weight/count chứng minh tương đương.
3. **Lineage-aware validation:** validator đọc `SemanticBinding` và catalog lineage thay vì tìm tên
   cột trong SQL text; view đã chứng minh identity không bị lexical rule từ chối.
4. **Predicate coverage:** plan validator so required semantic predicates với clause predicates,
   gồm column-vs-column và derived flags; mất “actual versus estimated” phải bị chặn trước generation.
5. **Bounded fallback contract:** fallback phải có stage deadline tương thích hardware; timeout không
   được chiếm 600 giây rồi mới terminal. Không tăng clock/power để che lỗi budget.
6. **Distributional tests:** sinh paraphrase/metamorphic fixtures theo operator × grain × language ×
   owner × predicate family, không branch theo benchmark ID hay expected result.
7. **Fresh evaluation:** chỉ sau khi invariant suite và `make check` pass mới chạy Olist-60 bằng
   artifact/evaluation ID mới. Không nối hoặc ghi đè prefix hiện tại.

Một lựa chọn ít rủi ro hơn là không đặt semantic compiler trên Olist fast path: giữ nguyên P6 cho
EASY/AGGREGATE đã tự tin, chỉ bật DIN decomposition cho `NON_NESTED/NESTED` hoặc classifier uncertainty
cao. Điều này sát với lợi ích gốc của paper và giảm bề mặt hồi quy trên champion 95%.

## 11. Các mối đe dọa đối với tính hợp lệ

- **Suite dừng sớm:** chỉ 12 case được đo; `56/60` là cận trên, không phải full accuracy.
- **Không tới holdout:** mọi kết luận chỉ thuộc prefix dev đã mở.
- **Phần cứng khác baseline:** một GPU layer và cap 300–600 MHz so với sáu layer lịch sử; so sánh
  latency không cô lập overhead kiến trúc.
- **Timeout bị tính sai:** theo gate terminal, timeout là failure hợp lệ; chưa biết cùng query có thể
  thành công trên server mạnh hơn hay không.
- **Model variance:** model/seed được khóa nhưng local inference không được tuyên bố bit-identical.
- **Metric proxy yếu:** clause exact cao không đo semantic owner/grain.
- **Mẫu nhỏ:** không suy rộng kết quả này thành phán quyết về DIN-SQL trên Spider hoặc model khác.

## 12. Ranh giới tuyên bố

- Đã chứng minh: revision `f70d191` không thể đạt baseline Olist `57/60` trong run source-locked này.
- Đã đo: Paper II prefix `8/12`; paired baseline prefix `12/12`.
- Đã chứng minh vận hành: benchmark không gây OOM, swap, thermal/power breach hay shutdown.
- Chưa đo: case 13–60, Olist holdout Paper II, Spider Paper II, hay full latency distribution.
- Không tuyên bố: DIN-SQL nói chung làm giảm text-to-SQL accuracy.
- Gate: R2 vẫn `IN_PROGRESS`, revision hiện tại **REJECTED FOR PROMOTION**, không `VERIFIED`.

## 13. Nguồn nghiên cứu

- Pourreza & Rafiei, [DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with
  Self-Correction](https://proceedings.neurips.cc/paper_files/paper/2023/hash/72223cc66f63ca1aa59edaec1b3670e6-Abstract-Conference.html),
  NeurIPS 2023.
- Thiết kế chuyển giao và gate nội bộ: `docs/research_plan/paper_to_research_implement.md`, mục Paper
  II; `docs/research_plan/r2_semantic_construction.md`.

## 14. Quyết định cuối cùng

Giữ baseline P6 `57/60` làm champion. Không chạy Spider và không resume bất kỳ checkpoint Paper II
nào. Candidate A4500 `c40b75c` đã có accuracy evidence hợp lệ và bị reject: prefix `16/20`, paired
baseline `19/20`, upper bound `<=56/60`. Kết quả chỉ có một complex DIN case nên không bác bỏ DIN-SQL
nói chung; nó bác bỏ phép tích hợp hiện tại vì “baseline preserve” đã bị confound bởi BM25 retrieval.
R2 giữ `IN_PROGRESS`, research opt-in và không `VERIFIED`.

## 15. Kiểm tra repository sau benchmark

Trước source-locked run, `make check` hoàn tất mà không gọi Ollama: Ruff lint/format pass, strict
mypy pass 111 source file, và pytest non-Ollama pass **240 test** với một test Ollama deselect. Cảnh
báo duy nhất là Starlette/httpx deprecation đã tồn tại. Sau accuracy stop, không có benchmark/model
process còn chạy và hard clock đã được reset trước khi bàn giao. Một `make check` cuối được chạy sau
khi cập nhật evidence; kết quả cuối nằm trong phần bàn giao của commit evidence.
