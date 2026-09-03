# Từ paper tới kiến trúc triển khai: luận đề nghiên cứu cho Agentic Text-to-SQL local

**Trạng thái:** research blueprint, chưa triển khai các experiment bên dưới<br>
**Ngày khóa số liệu:** 2026-08-27<br>
**Phạm vi:** tăng semantic accuracy và độ hữu ích với câu hỏi thực tế, dưới giới hạn laptop local<br>
**Câu hỏi nghiên cứu trung tâm:** *Làm thế nào một hệ Agentic Text-to-SQL dùng model local 14B có thể
giảm câu trả lời “SQL chạy được nhưng sai nghĩa”, đồng thời biết hỏi lại hoặc từ chối đúng khi câu hỏi
mơ hồ/không thể trả lời, mà không làm latency và tài nguyên vượt ngưỡng laptop?*

---

## Tóm tắt luận đề

Project đã giải quyết tốt phần engineering: workflow có trạng thái rõ, SQL read-only, schema retrieval,
bounded correction, benchmark có gold firewall, UI/API và resource governor. Tuy nhiên, bằng chứng trước
nghiên cứu cho thấy bottleneck đã dịch chuyển khỏi “hệ thống có chạy hay không” sang “hệ thống có hiểu đúng
ý nghĩa hay không”. Trên Spider-200, 199/200 case có valid candidate nhưng chỉ 130/200 trả về đúng kết quả;
68/70 failure là `EXECUTION_MISMATCH`. Đây là dấu hiệu rất rõ: thêm parser hoặc rule syntax không đủ để tạo
bước nhảy accuracy.

Luận đề này không sao chép nguyên một framework paper. Nó chọn năm cơ chế bổ sung cho nhau:

1. **PRACTIQ:** quyết định `ANSWER / CLARIFY / CANNOT_ANSWER` trước khi sinh SQL;
2. **DIN-SQL:** phân rã semantic problem thành schema linking, complexity và clause plan;
3. **CHESS:** đưa database values/metadata vào grounding bằng context tối thiểu nhưng đủ;
4. **CHASE-SQL:** chỉ với case khó, tạo các candidate khác nhau về logic rồi chọn bằng evidence;
5. **APEL:** để non-coder sửa hệ thống bằng cách chọn output/assumption, không phải đọc SQL.

[Semantic Evaluation with Distilled Test Suites](https://aclanthology.org/2020.emnlp-main.29/) là lớp
đánh giá xuyên suốt. Nó nhắc rằng một database instance hoặc exact SQL không đủ phân biệt mọi chương trình
tương đương/sai nghĩa. Vì vậy score cuối cùng phải kết hợp execution accuracy, test-suite/mutation evidence,
challenge set và review các paired regressions.

---

## 1. Evidence trước khi chỉnh sửa hoặc nâng cấp

Các số dưới đây là **baseline lịch sử đã khóa**, không phải score của code sẽ được xây sau tài liệu này.
Không lấy trung bình Spider và Olist vì hai benchmark đo hai mục tiêu khác nhau.

### 1.1 Benchmark output hiện có

| Chỉ số | Kết quả trước nghiên cứu | Ý nghĩa chẩn đoán |
|---|---:|---|
| Spider-200 execution accuracy | **130/200 = 65,00%** | Cross-domain generalization còn khoảng trống lớn |
| Spider valid candidate | **199/200 = 99,50%** | Syntax/workflow không phải bottleneck chính |
| Spider holdout / regression | **67% / 63%** | Chưa thấy holdout collapse ở aggregate |
| Spider easy | **83/107 = 77,57%** | Luồng đơn giản tương đối ổn |
| Spider medium | **27/53 = 50,94%** | Reasoning cấu trúc suy giảm rõ |
| Spider hard | **16/29 = 55,17%** | Sample nhỏ nhưng vẫn còn nhiều semantic failure |
| Spider extra-hard | **4/11 = 36,36%** | Cần decomposition/candidate diversity có điều kiện |
| Spider failure | **68/70 execution mismatch** | SQL chạy được nhưng kết quả sai nghĩa |
| Schema table recall@20 | **100,00%** | Không nên chỉ tiếp tục tăng top-k retrieval |
| Qualified column recall@20 | **99,65%** | Column retrieval gần bão hòa ở metric hiện tại |
| Join-edge recall | **86,36%** | Join path/evidence vẫn là khoảng trống cụ thể |
| Olist-60 result accuracy | **57/60 = 95,00%** | Semantic contract theo domain đem lại hiệu quả cao |
| Olist first-pass | **51/60 = 85,00%** | Correction còn đóng góp 6 case |
| Olist holdout | **15/15 = 100%** | Dùng làm non-regression guardrail, không xem là SOTA claim |
| Olist VI / EN | **29/30 / 28/30** | Song ngữ không phải bottleneck aggregate hiện tại |
| Spider P50 / P95 | **58,51 s / 85,29 s** | Không thể áp dụng multi-agent vô điều kiện |
| Olist P50 / P95 | **61,92 s / 91,62 s** | Chưa đạt target interactive 60 giây ở tail |

Nguồn số liệu: [`benchmark_full.md`](../../benchmark_full.md),
[`docs/evidence/p6_gate.md`](../evidence/p6_gate.md) và
[`docs/error_analysis.md`](../error_analysis.md). Revision benchmark là
`1509faa786534f36d33df34d4d5c4a9ed5fc1c54`, dùng Qwen3-14B Q4_K_M, seed 42 và 6 GPU layers.
Không được gán 65%/95% cho một revision khác nếu chưa rerun manifest khóa.

### 1.2 Output free-form cho thấy vấn đề thực tế

Case `e4e905f4...` hỏi số khách hàng quay lại theo `customer_unique_id`. Candidate đầu tiên dùng cột
ở sai owner, kết thúc `UNKNOWN_COLUMN` sau **71,92 giây**; correction còn sai scalar shape; một semantic
validator sau đó lại tạo false positive. Sau hardening, run `170c567e...` trả được:

```sql
SELECT COUNT(*)
FROM customer_order_facts
WHERE order_count > 1
```

Kết quả là **2.997**, latency **71,08 giây**. Run này chứng minh một case đã được sửa, không chứng minh
accuracy cho mọi câu free-form. Confidence 95% của model là self-report, **không phải xác suất đúng**.
Case được ghi tại [`docs/evidence/p6_3_query_recovery.md`](../evidence/p6_3_query_recovery.md).

### 1.3 Điều có thể và không thể suy ra

- Có thể suy ra pipeline hiện đã đủ ổn định để nghiên cứu semantic quality.
- Có thể suy ra semantic mismatch và query complexity quan trọng hơn lỗi syntax tổng quát.
- Không thể suy ra 68 mismatch đều do cùng một nguyên nhân khi chưa có AST/result-level labels.
- Không thể so trực tiếp 65% Spider-200 với score paper trên full hidden Spider/BIRD: khác data slice,
  model, prompt, compute và evaluator.
- Không thể tăng “độ tin cậy” bằng self-confidence; cần calibration split và observable evidence.

---

## 2. Chẩn đoán ưu tiên

| Ưu tiên | Chẩn đoán từ project | Paper/cơ chế trả lời | Quyết định nghiên cứu |
|---:|---|---|---|
| **P0** | Score mới chưa được khóa trên generator/corrector hiện tại; 68 mismatch chưa có root-cause label | Test-suite evaluation + failure analysis | Freeze baseline và gắn nhãn failure trước khi đổi kiến trúc |
| **P1** | User có thể hỏi mơ hồ, typo hoặc ngoài dữ liệu; hiện router chưa biểu diễn nhiều interpretation | PRACTIQ | Xây Question Reliability Contract trước SQL |
| **P1** | Medium 50,94%, extra-hard 36,36%; planner hiện one-shot | DIN-SQL | Clause plan và complexity router, không chain-of-thought dài vô điều kiện |
| **P1** | Schema recall cao nhưng join-edge 86,36%; lỗi owner/value/grain vẫn xuất hiện | CHESS | Semantic catalog + bounded value/entity retrieval |
| **P2** | Một candidate đúng/sai tạo variance lớn; correction chỉ phản ứng sau validation | CHASE-SQL | Logic-diverse best-of-3 chỉ cho case khó, có selector |
| **P2** | Feedback non-coder chưa tạo được label semantic chất lượng | APEL | Output/assumption comparison và reviewed data flywheel |
| **Guardrail** | P95 85–92 giây và laptop từng có power stop | Kiến trúc adaptive của project | Mọi module mới phải có budget, cache, checkpoint và kill rule |

Thứ tự trên chủ ý đặt **đo lường và question contract trước multi-agent**. Nếu không, hệ thống có thể tốn
ba lần inference để tạo ba SQL cho một câu vốn không đủ dữ liệu hoặc cần user làm rõ.

---

## 3. Paper I — PRACTIQ: trước khi trả lời, phải biết câu hỏi thuộc loại nào

**Nguồn:** Dong et al., *PRACTIQ: A Practical Conversational Text-to-SQL Dataset with Ambiguous and
Unanswerable Queries*, NAACL 2025. [ACL Anthology](https://aclanthology.org/2025.naacl-long.13/).

### 3.1 Motive và kiến trúc của paper

Benchmark Text-to-SQL truyền thống phần lớn giả định câu hỏi có một intent rõ và database chứa đủ dữ liệu.
PRACTIQ thay giả định đó bằng bài toán gần sản phẩm hơn: câu hỏi có thể answerable, ambiguous hoặc
unanswerable. Paper xây **2.800 hội thoại**, định nghĩa bốn loại ambiguity và bốn loại unanswerability.
Một sample hoàn chỉnh có bốn lượt: user hỏi, assistant hỏi làm rõ, user xác nhận, assistant sinh SQL kèm
giải thích execution result.

Pipeline baseline của paper có hai nhiệm vụ tách biệt:

```text
question + schema
      ↓
category classification
      ↓
answer directly | ask clarification | explain unanswerable
      ↓
clarified SQL + result explanation
```

Điểm quan trọng không nằm ở prompt hội thoại, mà ở **decision boundary trước SQL generation**. Kết quả paper
cho thấy đây vẫn là bài toán khó: Claude 3.5 Sonnet đạt trung bình **72,15%** execution accuracy ở bảng so
sánh chính; Llama-3.1 70B đạt **68,55%**; Llama-3.1 8B chỉ **52,50%**. Paper cũng báo phần lớn model dưới
60% ở nhận diện ambiguity/unanswerability chi tiết. Các con số này thuộc PRACTIQ và model của paper, không
phải target trực tiếp cho Qwen local.

### 3.2 Weakness của project mà paper giải quyết

Router hiện có thể phân biệt query/clarify/unsupported/write, nhưng chưa có typed representation cho:

- nhiều interpretation hợp lý của cùng câu;
- assumption quyết định metric, filter, time grain hoặc population;
- lý do database không thể trả lời;
- clarification options bằng ngôn ngữ nghiệp vụ;
- false-refusal và clarification-success metrics.

Incident free-form cho thấy hệ thống cố sinh SQL ngay cả khi lexical/semantic ownership chưa chắc chắn. Với
user bình thường, “không có output” là lỗi; nhưng “bịa một SQL chạy được” còn nguy hiểm hơn. PRACTIQ cho phép
định nghĩa output có ích mà không giả vờ biết câu trả lời.

### 3.3 Phần kiến trúc sẽ lấy và cách chuyển giao

Không import dataset/paper code vào runtime. Ta chuyển giao **question category contract**:

```text
RawQuestion
  → NormalizedQuestion (typo, không dấu, VI/EN aliases; giữ raw text)
  → InterpretationSet[1..3] (metric, dimensions, filters, grain, assumptions)
  → AnswerabilityDecision
      ANSWER | CLARIFY | CANNOT_ANSWER | SAFE_REJECT
  → SQL pipeline chỉ khi đủ evidence
```

Vị trí triển khai dự kiến:

- typed contracts mới cạnh `contracts/planning.py`;
- classifier/interpretation stage trong `layer1_reasoning/` trước planner;
- state transition mới trong `workflow/graph.py` và `workflow/state.py`;
- presenter/UI hiển thị clarification/missing evidence trong `layer6_application/`;
- feedback reason codes lưu local, không tự coi là gold.

### 3.4 Experiment và tiêu chí chấp nhận

Tạo challenge set DB-disjoint gồm answerable paraphrase, ambiguity, unanswerable, typo/không dấu và VI/EN
mix. Mỗi family giữ cùng canonical intent để đo consistency.

- ambiguity/unanswerability macro-F1;
- ambiguity recall ≥ **85%**;
- answerable false-refusal ≤ **3%**;
- clarification success ≥ **80%** trên scripted follow-up;
- confident-wrong giảm ≥ **30%**;
- Spider clean accuracy không giảm quá 1 case do route sai.

**Kill rule:** dừng/đơn giản hóa nếu router hỏi lại quá 15% câu answerable hoặc yêu cầu user nêu table/column.

---

## 4. Paper II — DIN-SQL: phân rã lỗi semantic thay vì bắt một prompt làm mọi việc

**Nguồn:** Pourreza & Rafiei, *DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with
Self-Correction*, NeurIPS 2023. [Proceedings chính thức](https://proceedings.neurips.cc/paper_files/paper/2023/hash/72223cc66f63ca1aa59edaec1b3670e6-Abstract-Conference.html).

### 4.1 Motive và kiến trúc của paper

DIN-SQL đặt giả thuyết rằng Text-to-SQL khó không chỉ vì model yếu, mà vì một prompt duy nhất phải đồng thời
link schema, hiểu độ khó, lập kế hoạch SQL và sửa lỗi. Paper phân rã chuỗi quyết định thành các sub-problem:

```text
schema linking
   → classify EASY / NON-NESTED / NESTED
   → difficulty-specific decomposition and SQL generation
   → self-correction
```

Với ba LLM, decomposition tăng khoảng **10 điểm** so với simple few-shot theo báo cáo của paper. DIN-SQL đạt
**85,3% execution accuracy** trên Spider holdout test tại thời điểm công bố, so với SOTA trước đó 79,9%, và
đạt **55,9%** trên BIRD holdout. Đây là bằng chứng rằng phân rã đúng interface có thể quan trọng hơn việc
fine-tune toàn model; nó không đảm bảo project local sẽ nhận cùng mức tăng.

### 4.2 Weakness của project mà paper giải quyết

Project đã có `LogicalPlan`, nhưng planner vẫn là one-shot, schema-agnostic; chưa có metric đo plan quality.
Khoảng cách easy **77,57%** so với medium **50,94%** và extra-hard **36,36%** cho thấy cùng một generation
path không phù hợp mọi độ khó. `EXECUTION_MISMATCH` hiện cũng quá thô: không biết sai SELECT, join, filter,
grouping, nesting hay set operation.

### 4.3 Phần kiến trúc sẽ lấy và cách chuyển giao

Ta lấy **decomposition interfaces**, không sao chép chuỗi prompt dài hay gọi model cho mọi bước:

1. `SemanticLinkPlan`: entity/metric/dimension/value và evidence owner;
2. `ComplexityDecision`: simple, aggregate, multi-join, nested/set/window;
3. `ClausePlan`: output grain; FROM/join path; WHERE; GROUP/HAVING; ORDER/LIMIT; subquery dependencies;
4. `PlanConsistencyValidator`: identifier ownership, aggregate grain và clause dependency;
5. generator chỉ nhận plan đã typed; corrector nhận clause failure cụ thể.

Các signal deterministic hiện có—AST, FK graph, requested metric/dimension, aggregate words—phải được dùng
trước; chỉ gọi LLM planner nâng cao khi classifier đánh dấu case khó. Điều này giữ triết lý DIN-SQL nhưng phù
hợp P95 và laptop hơn.

### 4.4 Experiment và tiêu chí chấp nhận

Trước implementation, gắn primary root cause cho 70 Spider failures bằng AST/result diff. Sau đó A/B:

- baseline one-shot planner;
- typed clause plan cho mọi case;
- adaptive clause plan chỉ cho medium/hard.

Metric: clause-level F1, plan→SQL consistency, EX theo difficulty, token/latency và paired regression.

**Promote:** medium+hard tăng ≥5 điểm phần trăm, overall tăng ≥2 điểm, easy mất tối đa 1 case, P95 tăng
không quá 20%. **Kill rule:** plan dài hơn nhưng không cải thiện oracle recoverability hoặc tạo error
propagation sang easy cases.

---

## 5. Paper III — CHESS: schema đúng chưa đủ, cần context tối thiểu nhưng đủ nghĩa

**Nguồn:** Talaei et al., *CHESS: Contextual Harnessing for Efficient SQL Synthesis*, 2024/2025.
[Paper](https://arxiv.org/abs/2405.16755) · [mã nguồn tác giả](https://github.com/shayantalaei/chess).

### 5.1 Motive và kiến trúc của paper

CHESS nhắm đến database lớn, nơi model không thể nhận toàn bộ catalog và values. Framework chia bốn vai trò:

1. **Information Retriever:** tìm metadata và database values liên quan;
2. **Schema Selector:** thu hẹp schema theo câu hỏi;
3. **Candidate Generator:** sinh/refine SQL;
4. **Unit Tester:** kiểm tra candidate bằng natural-language unit tests.

Kiến trúc hướng tới “minimal sufficient context”: không chỉ chọn table/column mà còn lấy description và
giá trị giúp nối ngôn ngữ user với data. Paper báo Schema Selector giảm token khoảng **5×** đồng thời tăng
accuracy xấp xỉ **2 điểm** trong setting schema lớn; cấu hình high-compute đạt **71,10%** trên BIRD test.
Số này dùng model/compute và BIRD của CHESS, nên chỉ là bằng chứng cơ chế.

### 5.2 Weakness của project mà paper giải quyết

Project đạt table recall 100% và qualified column recall 99,65%, nhưng:

- join-edge recall chỉ 86,36%; context có cột chưa chắc có đúng connected component;
- incident `customer_unique_id` chứng minh ownership/grain có thể sai dù tên cột được nhận ra;
- semantic alias như “khách quay lại”, revenue, delivery population cần metric contract;
- retrieval P3 từng giảm prompt 41,96% nhưng không tăng accuracy và còn tăng latency do embedding;
- value/entity grounding hiện chưa được đo bằng value recall.

Vì vậy, mục tiêu không phải “retrieval nhiều hơn”, mà là **semantic evidence có provenance**.

### 5.3 Phần kiến trúc sẽ lấy và cách chuyển giao

Ta lấy IR + Schema Selector của CHESS, nhưng thay unit-test LLM đắt bằng validator kết hợp:

```text
query interpretations
  → keyword/entity extraction
  → safe value lookup trên allowlisted columns
  → metric/dimension catalog + aliases + units + time grain
  → FK-connected schema components
  → component scoring theo intent coverage/evidence/complexity
  → token-bounded context với provenance
```

`layer2_grounding/profiler.py`, `schema_linker.py`, `fk_graph.py` và `context_packer.py` là nơi mở rộng tự
nhiên. Value index phải bounded, hash/versioned và tránh PII. Olist semantic views là prior metadata; Spider
không được nhận gold-derived glossary.

### 5.4 Experiment và tiêu chí chấp nhận

Ablation riêng từng nguồn: schema-only; +description; +metric aliases; +values; +FK component. Không gộp tất
cả rồi mới đo.

- value/entity recall@k và metric-link F1;
- join-edge recall và connected-component precision;
- filter/join/grain execution accuracy;
- context tokens, embedding latency, cache hit, RAM/index size;
- privacy fixtures và gold-leakage audit.

**Promote:** filter/join slice +3 điểm hoặc overall +2 điểm, zero leakage, prompt/context không tăng quá 20%,
warm grounding p95 không quá 1 giây. **Kill rule:** retrieval thêm noise làm overall giảm >1 điểm hoặc index
không nằm trong resource envelope.

---

## 6. Paper IV — CHASE-SQL: đa dạng phải là đa dạng logic, không phải đổi seed

**Nguồn:** Pourreza et al., *CHASE-SQL: Multi-Path Reasoning and Preference Optimized Candidate Selection
in Text-to-SQL*, ICLR 2025. [OpenReview](https://openreview.net/forum?id=CvGqMD5OtX).

### 6.1 Motive và kiến trúc của paper

Khi một generator có nhiều mode failure, sinh lại cùng prompt dễ tạo các candidate gần như giống nhau.
CHASE-SQL dùng ba đường reasoning khác nhau:

- divide-and-conquer theo sub-query;
- reasoning dựa trên query execution plan;
- instance-aware synthetic demonstration.

Sau đó một selection agent so sánh candidate theo cặp bằng model preference đã fine-tune. Paper đạt
**73,0% BIRD test** và **73,01% BIRD development** tại thời điểm submission. Kết quả minh họa lợi ích của
candidate diversity + selector, nhưng framework high-compute không thể bê nguyên vào laptop.

### 6.2 Weakness của project mà paper giải quyết

`layer3_generation/service.py` hiện sinh một candidate; correction chỉ được gọi sau khi candidate bị validator
bắt. Với 68 semantic mismatches, phần lớn SQL chạy thành công nên corrector không có signal để can thiệp. Một
candidate cũng không cho biết model đang chắc chắn hay chỉ chọn ngẫu nhiên một interpretation/join path.

### 6.3 Phần kiến trúc sẽ lấy và cách chuyển giao

Ta lấy **multi-path + selection**, nhưng chuyển thành adaptive best-of-3:

- simple/easy: một candidate như hiện tại;
- difficult nhưng answerable: tối đa ba candidate từ `clause-plan`, `divide-and-conquer`, và
  `evidence-constrained alternative`;
- deduplicate theo normalized AST trước execution;
- selector dùng deterministic validation, result-shape invariants, schema/value evidence coverage và candidate
  agreement trước khi cân nhắc một LLM comparison nhỏ;
- nếu disagreement lớn mà không đủ evidence: `CLARIFY` hoặc trạng thái uncertain, không ép chọn.

`contracts/trace.py` đã có `max_candidates=3`, còn `layer3_generation/selector.py` là seam sẵn có. Mọi candidate
phải đi lại toàn bộ Layer 4; selector không được xem benchmark gold.

### 6.4 Experiment và tiêu chí chấp nhận

Đầu tiên đo **oracle pass@3**. Nếu đúng SQL không xuất hiện trong candidate pool thì selector không phải nơi
cần đầu tư.

- candidate AST diversity và result diversity;
- pass@1, oracle pass@3, selected accuracy;
- selector recovery = `(selected - pass@1) / (oracle - pass@1)`;
- calls/query, P50/P95, peak RAM/VRAM, power-stop count;
- correct→wrong selector regressions.

**Promote:** oracle pass@3 cao hơn baseline ≥8 điểm, selector thu ≥50% oracle gap, final overall +3 điểm,
P95/calls không quá 2× trên routed hard slice và aggregate P95 nằm trong budget. **Kill rule:** candidate gần
như đồng nhất, selector không hơn deterministic consensus hoặc laptop chạm resource guard.

---

## 7. Paper V — APEL: non-coder có thể cung cấp supervision mà không đọc SQL

**Nguồn:** Zhong et al., *Non-Programmers Can Label Programs Indirectly via Active Examples: A Case Study
with Text-to-SQL*, EMNLP 2023. [ACL Anthology](https://aclanthology.org/2023.emnlp-main.312/).

### 7.1 Motive và kiến trúc của paper

Nếu chỉ đưa hai SQL cho non-coder, họ khó biết câu nào đúng. APEL chủ động tìm một input đơn giản làm các
candidate tạo output khác nhau, rồi yêu cầu annotator chọn **output** phù hợp. Lựa chọn đó gián tiếp xác định
program đúng và có thể trở thành data huấn luyện. Khi re-annotate Spider, non-programmer đạt cùng annotation
accuracy **75%** như original expert annotators theo báo cáo paper, đồng thời phát hiện lỗi annotation tinh vi.

Motive phù hợp trực tiếp với sản phẩm: user hiểu kết quả, metric và assumption tốt hơn AST/SQL.

### 7.2 Weakness của project mà paper giải quyết

UI hiện lưu feedback gắn run ID nhưng một verdict `correct/incorrect` không nói sai intent, metric, filter,
grain hay presentation. Tự động lấy thumbs-down làm training data sẽ đưa noise và có thể làm benchmark
leakage. Project cũng chưa có flow so sánh hai assumptions bằng output dễ hiểu.

### 7.3 Phần kiến trúc sẽ lấy và cách chuyển giao

Không cần triển khai đầy đủ active database synthesis ngay. Phiên bản local an toàn:

1. khi candidate/interpretation bất đồng, trình bày 2 output cards đã sanitize;
2. giải thích khác biệt bằng metric/filter/time grain, ẩn SQL ở Advanced;
3. user chọn “đúng ý” hoặc reason code: sai metric, sai filter, thiếu dữ liệu, không hiểu;
4. record đi vào review queue với run ID, catalog version, provenance và PII check;
5. chỉ record đã review mới vào verified example store/hard-negative set;
6. LoRA chỉ được thử sau dedup, DB-disjoint split và leakage audit.

### 7.4 Experiment và tiêu chí chấp nhận

Usability study nhỏ nhưng có task cố định cho non-coder và developer:

- agreement với expert label;
- thời gian chọn output/assumption;
- tỷ lệ “không đủ thông tin để chọn”;
- review acceptance rate và label distribution;
- downstream gain của verified examples so với raw thumbs feedback.

**Promote:** non-coder agreement ≥80%, ≥90% record có reason/provenance đầy đủ, expert review acceptance ≥90%,
zero raw-feedback auto-training. **Kill rule:** UI khiến user chọn theo format/row count thay vì semantics hoặc
không thể giải thích khác biệt bằng ngôn ngữ nghiệp vụ.

---

## 8. Kiến trúc hợp nhất đề xuất

Năm paper không tạo năm agent độc lập. Chúng tạo một workflow typed với ba đường thoát sớm:

```text
Raw user question
        │
        ▼
Question Reliability (PRACTIQ)
normalize → interpretations → answerability
        ├── ambiguous ───────────────► CLARIFY
        ├── missing evidence ────────► CANNOT_ANSWER
        ├── unsafe ──────────────────► SAFE_REJECT
        └── answerable
                │
                ▼
Semantic Planning (DIN-SQL)
link intent → complexity → typed clause plan
                │
                ▼
Context Assembly (CHESS)
schema component + FK + values + metric contracts + provenance
                │
                ▼
Adaptive Candidate Engine (CHASE-SQL)
1 candidate for simple; logic-diverse ≤3 for hard
                │
                ▼
Gold-blind evidence selector → Layer 4 validation/execution → bounded correction
                │
                ▼
Answer card: result + meaning + scope + validation state
                │
                ▼
Reviewed output/assumption feedback (APEL-inspired)
                │
                └────► verified examples / hard negatives / optional LoRA
```

### 8.1 Agent boundary hợp lý

Chỉ tách agent khi nó có contract, evidence và budget riêng:

| Agent/module | Input typed | Output typed | Không được phép |
|---|---|---|---|
| Question analyst | raw question + public catalog metadata | interpretations + answerability | sinh SQL hoặc xem gold |
| Semantic planner | accepted interpretation | clause plan + complexity | tự bịa identifier |
| Grounder | plan + runtime catalog/index | evidence package + provenance | dùng benchmark gold |
| Candidate generator | plan + evidence | ≤3 normalized candidates | bypass policy/validation |
| Selector/verifier | candidates + gold-blind evidence/results | selected/uncertain + reasons | dùng self-confidence làm accuracy |
| Feedback curator | sanitized run + user choice | reviewed training record | auto-train từ raw feedback |

Tách như vậy cho phép debug “sai interpretation”, “thiếu evidence”, “plan sai”, “candidate pool không có đáp án”,
và “selector chọn sai” thay vì gom mọi thứ thành `EXECUTION_MISMATCH`.

### 8.2 Resource envelope cho laptop

- concurrency model = 1;
- simple path tối đa 1 planning + 1 generation call;
- hard path chỉ bật sau router, tối đa 3 generation candidates;
- cache normalized question, catalog fingerprint, embedding và deterministic plan signals;
- checkpoint theo case; supervisor vẫn fail-closed;
- ablation chạy subset trước, full Spider-1.034 tiếp tục optional;
- không promote nếu gain nhỏ nhưng P95/calls >2× hoặc gây swap/power stop.

---

## 9. Thiết kế nghiên cứu theo gates

### Gate R0 — Baseline và failure intelligence

**Không đổi runtime.** Rerun locked Spider-200/Olist-60 trên revision hiện tại; phân rã 70 failures theo
intent, retrieval, value, join, clause, generation, selection và evaluator. Báo AST/result diff và paired delta.

**Pass:** 200/200 complete; config/hash/model digest đầy đủ; 100% failure có primary cause; reviewer agreement
≥90%; `make check` pass. Sau gate này mới được coi các score là “trước upgrade” hợp lệ cho code hiện tại.

### Gate R1 — PRACTIQ question contract

Thêm typed interpretations/answerability và challenge set. Không thay generator trước khi route đúng.

**Pass:** ambiguity recall ≥85%, false-refusal ≤3%, clarification success ≥80%, không giảm safety/Olist.

### Gate R2 — DIN-SQL clause planner + CHESS semantic context

Chạy ablation riêng planner và context; chỉ merge nếu biết gain đến từ đâu.

**Pass:** overall Spider +2 điểm hoặc targeted slice +3–5 điểm; easy/Olist regression trong guardrail; warm
grounding p95 ≤1 giây; zero leakage.

### Gate R3 — CHASE adaptive candidates

Chỉ mở khi R0 chứng minh candidate diversity có oracle headroom. Đo oracle trước selector.

**Pass:** oracle +8 điểm, selector thu ≥50% gap, final +3 điểm, aggregate resource nằm trong envelope.

### Gate R4 — APEL-inspired reviewed feedback

Pilot với non-coder, không fine-tune. Chỉ chứng minh label quality và provenance.

**Pass:** non-coder agreement ≥80%, reviewed acceptance ≥90%, không có raw feedback đi vào training.

### Gate R5 — External proof và optional adaptation

Freeze champion trước fresh DB-disjoint release. Chỉ sau data audit mới thử verified ICL hoặc LoRA-7B; so với
không fine-tune ở cùng manifest/hardware.

**Pass gần:** Spider locked-200 ≥70%, Olist ≥95%, safety 100%, P95 không regress >20%.<br>
**Pass nghiên cứu:** gain cùng dấu trên fresh/external set; báo cả accuracy, coverage, false-refusal, latency và
resource. Không gọi subset score là official leaderboard.

---

## 10. Scorecard và formulation

### 10.1 Correctness và selective reliability

Với tập request \(Q\), tập request hệ thống trả lời \(A\), và nhãn correctness \(c_i\):

\[
\text{Accuracy}_{answered}=\frac{\sum_{i\in A}c_i}{|A|},\qquad
\text{Coverage}=\frac{|A|}{|Q|},\qquad
\text{AnswerRisk}=1-\text{Accuracy}_{answered}.
\]

Không báo accuracy mà bỏ coverage. Một hệ thống abstain mọi câu có risk thấp nhưng vô dụng. Báo thêm:

\[
\text{SafeResolution}=\frac{\text{correct ANSWER} + \text{useful CLARIFY} +
\text{correct CANNOT\_ANSWER} + \text{SAFE\_REJECT}}{|Q|}.
\]

Safe Resolution phải đi cùng answerable false-refusal và risk–coverage curve để tránh game metric.

### 10.2 Candidate engine

\[
\text{OraclePass@k}=\frac{1}{N}\sum_i \mathbf{1}[\exists j\le k:c_{ij}=1]
\]

\[
\text{SelectorRecovery}=\frac{Acc_{selected}-Pass@1}{OraclePass@k-Pass@1}.
\]

Nếu mẫu số gần 0, candidate pool không có diversity/headroom; không được diễn giải selector recovery.

### 10.3 Promotion scorecard

| Nhóm | Metric bắt buộc | Guardrail |
|---|---|---|
| Semantic accuracy | Spider EX + test-suite/mutation, Olist result accuracy | paired regressions giữ nguyên denominator |
| Complexity | easy/medium/hard/extra-hard | không che sample size |
| Question reliability | category F1, ambiguity recall, false-refusal, clarification success | coverage luôn đi cùng accuracy |
| Grounding | value recall, metric-link F1, join-edge recall | provenance và leakage audit |
| Candidate/selector | pass@1, oracle@3, selected, recovery | correct→wrong ≤1% |
| Product | task success, comprehension, time-to-useful-answer | non-coder cohort riêng |
| Efficiency | calls, tokens, P50/P95, peak RAM/VRAM, stop count | không swap; fail-closed governor |

---

## 11. Những gì chủ ý chưa làm

- Không đổi ngay sang model 32B/70B: sẽ che lỗi kiến trúc và vượt resource envelope.
- Không sinh nhiều candidate cho mọi câu: P95 hiện đã 85–92 giây.
- Không fine-tune từ raw benchmark failure hoặc raw thumbs feedback: leakage/noise chưa được kiểm soát.
- Không dùng self-confidence 95% làm per-query accuracy.
- Không tiếp tục tối ưu schema recall như mục tiêu chính khi table/column recall đã gần bão hòa.
- Không cộng các gain paper thành một con số kỳ vọng; paper khác benchmark, model và compute.
- Không sửa score lịch sử sau khi code đổi; luôn tạo manifest/revision benchmark mới.

---

## 12. Kết luận và bước tiếp theo duy nhất

Năm paper được chọn không phải vì chúng có score cao nhất, mà vì mỗi paper giải quyết một failure boundary đã
quan sát trong project. PRACTIQ ngăn sinh SQL khi câu hỏi chưa đủ điều kiện; DIN-SQL làm reasoning có cấu trúc;
CHESS biến schema retrieval thành semantic evidence; CHASE-SQL tạo oracle headroom và selection; APEL đóng
vòng học từ non-coder mà không yêu cầu họ đọc code.

**Bước tiếp theo duy nhất là Gate R0:** khóa revision hiện tại, rerun Spider-200/Olist-60 và biến 70 failure
thành taxonomy có AST/result evidence. Chưa triển khai đồng thời cả năm paper. Pareto của R0 sẽ quyết định
R1/R2 ưu tiên phần nào và tạo baseline “trước upgrade” không thể tranh cãi.

---

## Tài liệu tham khảo trọng điểm

1. Dong, M. et al. (2025). [PRACTIQ: A Practical Conversational Text-to-SQL Dataset with Ambiguous and
   Unanswerable Queries](https://aclanthology.org/2025.naacl-long.13/). NAACL 2025, 255–273.
2. Pourreza, M. & Rafiei, D. (2023). [DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with
   Self-Correction](https://proceedings.neurips.cc/paper_files/paper/2023/hash/72223cc66f63ca1aa59edaec1b3670e6-Abstract-Conference.html).
   NeurIPS 2023.
3. Talaei, S. et al. (2024). [CHESS: Contextual Harnessing for Efficient SQL
   Synthesis](https://arxiv.org/abs/2405.16755). arXiv:2405.16755; project code by the authors.
4. Pourreza, M. et al. (2025). [CHASE-SQL: Multi-Path Reasoning and Preference Optimized Candidate
   Selection in Text-to-SQL](https://openreview.net/forum?id=CvGqMD5OtX). ICLR 2025.
5. Zhong, R. et al. (2023). [Non-Programmers Can Label Programs Indirectly via Active Examples: A Case
   Study with Text-to-SQL](https://aclanthology.org/2023.emnlp-main.312/). EMNLP 2023, 5126–5152.
6. Zhong, R. et al. (2020). [Semantic Evaluation for Text-to-SQL with Distilled Test
   Suites](https://aclanthology.org/2020.emnlp-main.29/). EMNLP 2020, 396–411.

### Provenance nội bộ

- [`benchmark_full.md`](../../benchmark_full.md)
- [`docs/evidence/p6_gate.md`](../evidence/p6_gate.md)
- [`docs/evidence/p6_3_query_recovery.md`](../evidence/p6_3_query_recovery.md)
- [`docs/error_analysis.md`](../error_analysis.md)
- [`all_failures_in_project.md`](../../all_failures_in_project.md)
- [`realistic_project_creation_codex.md`](../../realistic_project_creation_codex.md)

Paper cung cấp hypothesis và kiến trúc tham khảo; chỉ evidence tái lập trên revision, data manifest và laptop
của project mới quyết định promote/reject.
