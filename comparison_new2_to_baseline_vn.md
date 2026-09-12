# So sánh kiến trúc Paper II / DIN-SQL với baseline Olist đã đóng băng

**Trạng thái thí nghiệm:** revision đầu đã dừng theo accuracy gate; revision adaptive mới chưa có
kết quả accuracy vì guarded pilot không vượt qua planner timeout

**Ngày:** 2026-09-11 (Asia/Bangkok)

**Quyết định:** **GIỮ baseline P6 làm champion.** Loại revision `f70d191`; revision adaptive
`e8fab80` đã qua construction gate nhưng benchmark còn `INCONCLUSIVE`, nên chưa promote và chưa chạy
Spider.

## 0. Cập nhật revision adaptive baseline-first

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

Giữ baseline P6 `57/60` làm champion. Không chạy Spider và không resume checkpoint
`olist-paper2-semantic-f70d191-v1`. Hướng adaptive complex planning cùng grain/lineage invariants đã
được construct tại `e8fab80`, nhưng guarded pilot chưa tạo được một SQL để đo accuracy. Do đó revision
mới vẫn là candidate `IN_PROGRESS`, không phải winner hay failure. Bước hợp lệ tiếp theo là đánh giá
đúng frozen revision trên môi trường chạy đủ nhanh và an toàn bằng evaluation ID sạch; không sửa code
từ terminal timeout này và không resume `olist-paper2-adaptive-e8fab80-v1`.

## 15. Kiểm tra repository sau benchmark

Sau redesign, `make check` hoàn tất mà không gọi Ollama: Ruff lint pass, 232 file pass format check,
strict mypy pass 111 source file, và pytest non-Ollama pass **235 test** với một test Ollama deselect.
Cảnh báo duy nhất là Starlette/httpx deprecation đã tồn tại. Sau adaptive pilot, không có
benchmark/model process còn chạy và hard clock đã được reset trước khi bàn giao.
