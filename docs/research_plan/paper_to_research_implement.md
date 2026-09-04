# Kế hoạch chuyển giao paper thành implementation cho Agentic Text-to-SQL local

> **Mục đích:** tài liệu review với mentor và kế hoạch thực thi sau Gate P6<br>
> **Ngày chốt hiện trạng:** 2026-08-28<br>
> **Revision đang khảo sát:** `55f8da1e6ab71d9fd9d385a4716d946f45f412dd`<br>
> **Trạng thái:** `PROPOSED`; R0 đã có tooling nhưng chưa có benchmark mới<br>
> **Nguồn chuẩn của project:** [`realistic_project_creation_codex.md`](../../realistic_project_creation_codex.md)

---

## 1. Kết luận điều hành

Project đã hoàn thành một hệ thống Text-to-SQL chạy local có workflow typed, schema retrieval, SQL read-only,
bounded correction, CLI/API/UI và benchmark có gold firewall. Phần engineering đã được xác nhận ở Gate P6.
Tuy nhiên, chất lượng semantic chưa đủ để gọi là một sản phẩm đáng tin cho câu hỏi ngoài demo:

- Spider-200 lịch sử đạt **130/200 = 65,00%**, trong khi **199/200 = 99,50%** case vẫn sinh được SQL hợp lệ;
- **68/70 lỗi** là `EXECUTION_MISMATCH`: SQL chạy được nhưng trả kết quả sai;
- medium chỉ đạt **27/53 = 50,94%**, extra-hard đạt **4/11 = 36,36%**;
- join-edge recall là **86,36%**, thấp hơn table recall **100%** và qualified-column recall **99,65%**;
- P95 là **85,29 giây** trên Spider và **91,62 giây** trên Olist, đều vượt target interactive 60 giây.

Do đó, hướng nghiên cứu không phải là thêm agent hoặc tăng `top_k` một cách đại trà. Kế hoạch đề xuất năm cơ
chế có vai trò tách biệt:

1. **PRACTIQ:** phân biệt `ANSWER / CLARIFY / CANNOT_ANSWER` trước khi sinh SQL;
2. **DIN-SQL:** phân rã intent thành schema links, độ khó và kế hoạch theo clause;
3. **CHESS:** bổ sung metric contract, database values và provenance vào context;
4. **CHASE-SQL:** chỉ với case khó, sinh tối đa ba candidate khác nhau về logic rồi chọn bằng evidence;
5. **APEL:** thu feedback bằng output/assumption mà người không biết SQL vẫn đánh giá được.

Lớp đo lường xuyên suốt dùng execution accuracy, paired transitions và test-suite/mutation evidence. Mỗi
paper chỉ cung cấp **bằng chứng về cơ chế**; score của paper không phải dự báo cho Qwen3-14B Q4 trên laptop.

### Quyết định đề xuất

Không triển khai đồng thời năm paper. Gate kế tiếp duy nhất là **R0 — khóa baseline của code hiện tại và hoàn
thành failure intelligence**. Sau R0, Pareto nguyên nhân lỗi quyết định CHESS hay DIN-SQL được làm trước;
PRACTIQ vẫn là contract sản phẩm cần triển khai trước khi mở multi-candidate.

---

## 2. Cách đọc các con số trong báo cáo

Tài liệu dùng ba loại số và luôn ghi nhãn rõ:

| Nhãn | Ý nghĩa | Có được trình bày như kết quả không? |
|---|---|---|
| **ĐÃ ĐO** | Kết quả có report, revision và manifest tái lập | Có |
| **MỤC TIÊU** | Ngưỡng quyết định promote/reject trước khi chạy | Không |
| **ƯỚC LƯỢNG** | Effort, thời gian máy hoặc gain prior để lập kế hoạch | Không |

Ví dụ, `65,00%` là baseline lịch sử **ĐÃ ĐO**. `≥70%` là **MỤC TIÊU** gần, tương đương ít nhất
`140/200`, tức phải tăng ròng **10 case đúng**. Không được viết “dự kiến đạt 70%” nếu chưa chạy.

### 2.1 Phạm vi claim hiện tại

| Hạng mục | Trạng thái chính xác |
|---|---|
| Core engineering P0–P6 | `VERIFIED` theo completion ledger |
| Spider-200 = 65%, Olist-60 = 95% | Baseline lịch sử của revision `1509faa...`, generator v4/corrector v3 |
| Post-P6 generator v6/corrector v5 | Đã harden một số incident, **chưa có benchmark accuracy mới** |
| R0 failure-analysis tooling | Đã có ở revision `55f8da1...`; chưa có full run/reviewer agreement |
| Full Spider dev 1.034 | `NOT_STARTED`; evaluator self-test 1.034/1.034 không phải model accuracy |
| BIRD Mini-Dev | `NOT_STARTED` |
| Research upgrades R1–R5 trong báo cáo này | Chưa được promote, không được gọi là implemented |

---

## 3. Baseline: hệ thống hiện có gì và đang thiếu gì

### 3.1 Kết quả đã đo

| Chỉ số | Baseline lịch sử | Mẫu số | Diễn giải |
|---|---:|---:|---|
| Spider execution accuracy | **65,00%** | 130/200 | Cross-domain semantic accuracy còn thấp |
| Spider valid candidate | **99,50%** | 199/200 | Parser/runtime không phải bottleneck chính |
| Spider holdout / regression | **67% / 63%** | 100 / 100 | Không có aggregate holdout collapse trong sample |
| Spider easy | **77,57%** | 83/107 | Fast path hiện tại tương đối ổn |
| Spider medium | **50,94%** | 27/53 | Cần reasoning có cấu trúc |
| Spider hard | **55,17%** | 16/29 | Sample nhỏ; chưa được diễn giải quá mức |
| Spider extra-hard | **36,36%** | 4/11 | Candidate diversity có thể có ích nếu có oracle headroom |
| Execution mismatch | **97,14% số lỗi** | 68/70 | SQL hợp lệ nhưng sai nghĩa |
| Table recall@20 | **100,00%** | holdout retrieval | Không ưu tiên tăng schema breadth |
| Qualified-column recall@20 | **99,65%** | holdout retrieval | Column recall gần bão hòa ở metric hiện tại |
| Join-edge recall | **86,36%** | holdout retrieval | Join path/provenance còn thiếu |
| Olist result accuracy | **95,00%** | 57/60 | Domain semantic contracts có hiệu quả |
| Olist first-pass | **85,00%** | 51/60 | Correction từng phục hồi 6 case |
| Spider latency P50 / P95 | **58,51 / 85,29 s** | 200 case | Không thể nhân inference vô điều kiện |
| Olist latency P50 / P95 | **61,92 / 91,62 s** | 60 case | Tail latency chưa đạt target 60 s |

Nguồn nội bộ: [`benchmark_full.md`](../../benchmark_full.md),
[`docs/evidence/p6_gate.md`](../evidence/p6_gate.md),
[`docs/error_analysis.md`](../error_analysis.md) và
[`docs/evidence/p6_3_query_recovery.md`](../evidence/p6_3_query_recovery.md).

### 3.2 Kiến trúc hiện tại

```text
Question
  → Router / Decomposer / Planner
  → Hybrid schema retrieval / Schema linker / Context packer
  → One candidate generator / Normalizer
  → SQLGlot safety / Read-only execution / Semantic validation
  → Bounded correction
  → Result presenter / Trace / Feedback
```

Những thành phần phải giữ nguyên làm guardrail:

- runtime local, không paid API hoặc API key;
- typed contracts và bounded budgets;
- read-only executor và SQLGlot safety policy;
- gold benchmark chỉ tồn tại trong `agentic_text2sql_eval`, không đi vào runtime;
- checkpoint, provenance, resource governor và deterministic tests;
- raw dataset, database, index, trace, prediction và gold report tiếp tục nằm ngoài Git.

### 3.3 Khoảng trống theo từng boundary

| Boundary | Hiện có | Thiếu | Hậu quả |
|---|---|---|---|
| Question | Router query/clarify/unsupported/write | Nhiều interpretation, answerability reason, business clarification | Ép câu mơ hồ thành một SQL |
| Planning | `LogicalPlan` one-shot | Complexity route, clause dependency, output grain contract | Medium/extra-hard giảm mạnh |
| Grounding | Table/column/FK retrieval | Metric semantics, safe values, entity provenance | Đúng cột nhưng sai owner/value/grain |
| Generation | Một candidate | Logic-diverse pool và oracle metric | SQL chạy sai không kích hoạt corrector |
| Validation | Syntax/safety/shape/business signals | Calibrated semantic evidence và disagreement handling | Self-confidence dễ bị hiểu nhầm là xác suất đúng |
| Feedback | Rating/category theo run | Output comparison, review queue, verified label | Thumbs-down không đủ để học |
| Evaluation | EX/result accuracy | Test-suite/mutation, root-cause labels, risk–coverage | Khó biết gain thật đến từ module nào |

---

## 4. Câu hỏi nghiên cứu và giả thuyết

### Câu hỏi trung tâm

> Làm thế nào một hệ Agentic Text-to-SQL dùng model local 14B giảm câu trả lời “SQL chạy được nhưng sai
> nghĩa”, đồng thời hỏi lại hoặc từ chối đúng khi câu hỏi không đủ điều kiện, mà vẫn nằm trong resource
> envelope của laptop?

### Các giả thuyết có thể bác bỏ

| ID | Giả thuyết | Điều gì bác bỏ giả thuyết? |
|---|---|---|
| H0 | Failure taxonomy sẽ cho thấy top-3 cause bao phủ ≥60% số lỗi | Cause phân tán, reviewer agreement <90% |
| H1 | Answerability gate giảm confident-wrong ≥30% trên challenge set | False-refusal >3% hoặc clarification không giúp solve |
| H2 | Clause plan giúp medium+hard tăng ≥5 điểm phần trăm | Overall/easy regress hoặc plan không tăng oracle recoverability |
| H3 | Semantic/value evidence giúp filter/join slice tăng ≥3 điểm | Context tăng nhưng accuracy không tăng hoặc có privacy/leakage |
| H4 | Best-of-3 tạo oracle headroom ≥8 điểm trên routed-hard slice | Candidate trùng logic hoặc oracle gap nhỏ |
| H5 | Output-based feedback cho non-coder đạt agreement ≥80% | User chọn theo format/row count thay vì semantics |

---

## 5. Paper I — PRACTIQ: quyết định có nên sinh SQL hay không

**Nguồn:** Dong et al., *PRACTIQ: A Practical Conversational Text-to-SQL Dataset with Ambiguous and
Unanswerable Queries*, NAACL 2025. [ACL Anthology](https://aclanthology.org/2025.naacl-long.13/).

### 5.1 Paper giải quyết vấn đề gì?

Benchmark truyền thống thường giả định câu hỏi rõ nghĩa và database có đủ dữ liệu. PRACTIQ đưa vào câu hỏi
ambiguous và unanswerable, định nghĩa bốn nhóm ambiguity, bốn nhóm unanswerability và hội thoại bốn lượt:
user hỏi, assistant xin làm rõ, user xác nhận, assistant sinh SQL kèm giải thích kết quả. Baseline paper tách
hai nhiệm vụ: **question-category classification** rồi mới **clarification/SQL prediction**.

Paper có 2.800 conversation. Bảng chính báo Claude 3.5 Sonnet đạt 72,15% execution accuracy,
Llama-3.1-70B đạt 68,55% và Llama-3.1-8B đạt 52,50% trong setting của paper. Các số này chỉ chứng minh bài
toán khó ngay cả với model lớn; chúng không phải target của project.

### 5.2 Phần lấy từ paper

Lấy **decision boundary trước SQL** và conversation contract. Không import PRACTIQ data/code vào runtime.

```text
RawQuestion
  → NormalizedQuestion
  → InterpretationSet[1..3]
  → AnswerabilityDecision
      ANSWER | CLARIFY | CANNOT_ANSWER | SAFE_REJECT
  → SQL pipeline chỉ chạy khi outcome = ANSWER
```

### 5.3 Work breakdown chi tiết

| Task | Việc thực hiện | File dự kiến | Output kiểm chứng |
|---|---|---|---|
| Q1 | Định nghĩa enum outcome và reason codes | `contracts/planning.py` | Pydantic contract frozen, `extra="forbid"` |
| Q2 | Định nghĩa `Interpretation`: metric, dimensions, filters, grain, assumptions | `contracts/planning.py` | 1–3 interpretations; không chứa SQL |
| Q3 | Chuẩn hóa Unicode, không dấu, typo phổ biến và VI/EN alias; giữ raw text | file mới `layer1_reasoning/question_normalizer.py` | Paired input có normalized trace |
| Q4 | Rule-first answerability cho write, unsupported fact, returns/refunds Olist | `layer1_reasoning/router.py` | Deterministic reason code |
| Q5 | LLM chỉ xử lý ambiguity còn lại bằng JSON schema | file mới `layer1_reasoning/question_analyst.py` | Typed response hoặc fail-closed |
| Q6 | Thêm route `CLARIFY` và `CANNOT_ANSWER` vào state graph | `workflow/state.py`, `workflow/graph.py`, `workflow/nodes.py` | Không gọi generator ở early exit |
| Q7 | Presenter tạo một câu hỏi ngắn và 2–3 lựa chọn nghiệp vụ | `layer6_application/result_presenter.py` | Không hỏi tên table/column |
| Q8 | API/UI nhận clarification follow-up và liên kết run trước | application service + Streamlit | Multi-turn state tái lập |
| Q9 | Tạo challenge set versioned, không chứa PII/gold runtime | `evals/configs/` ignored + manifest tracked | Hash, split và review provenance |
| Q10 | Unit/integration tests | `tests/unit/layer1/`, `tests/integration/` | No-generation assertion cho early exit |

### 5.4 Dataset thử nghiệm

Tạo **200 request**: development-100 và locked-test-100. Locked-test gồm 40 answerable, 30 ambiguous và 30
unanswerable; trong mỗi nhóm có VI, EN, VI/EN mix, typo và không dấu. Paraphrase/noise được giữ theo paired
family để đo consistency, không coi chúng là các intent độc lập.

Nhãn do hai reviewer kiểm tra độc lập trên toàn bộ locked-test. Nếu bất đồng, adjudication chỉ xảy ra sau khi
đã tính agreement ban đầu.

### 5.5 Baseline, mục tiêu và cách đo

| Metric | Baseline | Mục tiêu promote | Cách tính |
|---|---:|---:|---|
| Routing macro-F1 | Chưa đo | ≥0,80 | Macro-F1 trên 3 class answer/clarify/cannot |
| Ambiguity recall | Chưa đo | ≥85% | Ít nhất 26/30 ambiguous được phát hiện |
| Answerable false-refusal | Chưa đo | ≤3% | Tối đa 1/40 answerable bị clarify/cannot sai |
| Clarification success | Chưa đo | ≥80% | Ít nhất 24/30 scripted ambiguous được giải quyết sau follow-up |
| Confident-wrong | Chưa đo | Giảm ≥30% | So cùng paired set với pipeline không có gate |
| Clean Spider regression | 130/200 lịch sử; phải khóa B0 mới | Mất tối đa 1 case do route sai | Paired transitions trên cùng manifest |

**Kill rule:** reject hoặc đơn giản hóa nếu hệ thống hỏi lại >15% câu answerable, yêu cầu user biết schema,
hoặc tăng safe-resolution bằng cách abstain hàng loạt.

---

## 6. Paper II — DIN-SQL: lập kế hoạch theo clause cho câu phức tạp

**Nguồn:** Pourreza & Rafiei, *DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with
Self-Correction*, NeurIPS 2023. [Proceedings](https://proceedings.neurips.cc/paper_files/paper/2023/hash/72223cc66f63ca1aa59edaec1b3670e6-Abstract-Conference.html).

### 6.1 Paper giải quyết vấn đề gì?

DIN-SQL tách một prompt phải làm mọi việc thành schema linking, phân loại EASY/NON-NESTED/NESTED,
difficulty-specific decomposition/generation và self-correction. Paper báo decomposition cải thiện khoảng 10
điểm so với simple few-shot trên ba LLM; đạt 85,3% EX Spider holdout test và 55,9% BIRD holdout trong setting
của paper.

Điểm chuyển giao phù hợp với project là **interface phân rã**, không phải chain-of-thought dài hoặc GPT-4.
Khoảng cách easy 77,57% và medium 50,94% cho thấy cùng một planning path chưa phù hợp mọi độ khó.

### 6.2 Contract đề xuất

```text
AcceptedInterpretation
  → SemanticLinkPlan
  → ComplexityDecision(simple | aggregate | multi_join | nested_set_window)
  → ClausePlan
       output_grain
       select_items
       sources_and_join_path
       filters
       group_and_having
       order_and_limit
       subquery_dependencies
  → PlanConsistencyReport
  → Generator
```

### 6.3 Work breakdown chi tiết

| Task | Việc thực hiện | File dự kiến | Test/bằng chứng |
|---|---|---|---|
| P1 | Mở rộng `LogicalPlan` bằng output grain và typed clause plan | `contracts/planning.py` | Serialization và invalid-combination tests |
| P2 | Xây complexity classifier rule-first từ intent, FK, aggregate và operator | file mới `layer1_reasoning/complexity.py` | Labeled fixtures + confusion matrix |
| P3 | Chỉ gọi LLM decomposition khi rule confidence thấp/case khó | `layer1_reasoning/planner.py` | Call-count assertion |
| P4 | Validator owner/scope/FK trước generator | file mới `layer1_reasoning/plan_validator.py` | Invented identifier bị chặn |
| P5 | Kiểm output grain so với aggregate/grouping | cùng validator + `join_grain_analyzer.py` | Scalar/grouped regression tests |
| P6 | Prompt generator nhận typed plan, không nhận free-form CoT | `layer3_generation/prompt_builder.py` | Prompt snapshot và gold-separation test |
| P7 | Corrector nhận clause failure cụ thể | `layer5_correction/correction_planner.py` | Filter/join/grain targeted fixtures |
| P8 | Ghi complexity, plan version và consistency signals vào trace | `contracts/trace.py`, workflow | Trace restart/persistence test |

### 6.4 Experiment

Sau khi R0 gắn nhãn failure, chạy ba nhánh trên cùng manifest và cùng model/config:

1. **B0 control:** planner hiện tại;
2. **P-all:** clause plan cho mọi case;
3. **P-adaptive:** clause plan chỉ cho medium/hard theo classifier.

| Metric | Baseline lịch sử | Mục tiêu promote |
|---|---:|---:|
| Medium + hard accuracy | 43/82 = **52,44%** | Tăng ≥5 điểm phần trăm trên cùng B0 mới |
| Overall Spider-200 | 130/200 = **65,00%** | Tăng ròng ≥4 case = +2 điểm |
| Easy regression | 83/107 đúng | Mất tối đa 1 case |
| Plan→SQL consistency | Chưa đo | ≥95% identifier/clause consistency |
| P95 | 85,29 s lịch sử | Tăng không quá 20% so với B0 mới |

**Kill rule:** plan dài hơn nhưng oracle recoverability không tăng, làm easy regress quá một case, hoặc tạo
thêm LLM call cho phần lớn simple query mà không có gain.

---

## 7. Paper III — CHESS: context tối thiểu nhưng đủ semantic evidence

**Nguồn:** Talaei et al., *CHESS: Contextual Harnessing for Efficient SQL Synthesis*.
[arXiv](https://arxiv.org/abs/2405.16755) · [repository](https://github.com/shayantalaei/chess).

### 7.1 Paper giải quyết vấn đề gì?

CHESS có bốn vai trò: Information Retriever, Schema Selector, Candidate Generator và Unit Tester. Điểm quan
trọng là context không chỉ gồm schema name mà còn có database values/descriptions liên quan. Paper báo Schema
Selector giảm token khoảng 5 lần và tăng xấp xỉ 2 điểm trong setting schema lớn; cấu hình high-compute báo
71,10% BIRD test. Đây là evidence về minimal-sufficient context, không phải lý do sao chép toàn bộ framework.

Project đã có table/column recall gần bão hòa nhưng join-edge recall chỉ 86,36%. Incident
`customer_unique_id` cũng cho thấy tìm thấy tên đúng chưa đủ: phải biết owner, grain và business meaning.

### 7.2 Data contract đề xuất

```text
EvidenceItem
  kind: table | column | fk | metric | dimension | value | description
  owner: database.table.column
  source: introspection | reviewed_catalog | bounded_profile
  catalog_fingerprint
  score
  safe_to_display
```

`EvidencePackage` phải có token budget, provenance và lý do chọn/bỏ. Spider không được nhận glossary được suy
ra từ gold SQL; Olist có thể dùng semantic contract đã review nhưng phải version riêng.

### 7.3 Work breakdown chi tiết

| Task | Việc thực hiện | File dự kiến | Test/bằng chứng |
|---|---|---|---|
| G1 | Inventory cột được phép profile; deny-by-default với PII/free text | `layer2_grounding/profiler.py` | Privacy fixtures |
| G2 | Profile bounded: distinct cap, length cap, time limit, no raw dump | `profiler.py` | Timeout/cap tests |
| G3 | Metric/dimension catalog: alias, unit, grain, population, owner | `contracts/catalog.py` + tracked Olist metadata | Schema/version validation |
| G4 | Value/entity index có hash, DB isolation và provenance | file mới `layer2_grounding/value_index.py` | Cross-DB isolation test |
| G5 | Exact/normalized value lookup trước embedding | `retriever.py` | VI/EN/diacritic fixtures |
| G6 | FK-connected component scoring theo intent coverage | `schema_linker.py`, `fk_graph.py` | Decoy/disconnected-view tests |
| G7 | Context packer cấp budget theo evidence type | `context_packer.py` | Token cap deterministic |
| G8 | Trace evidence provenance, không trace raw sensitive values | `contracts/trace.py` | Serialization/privacy test |
| G9 | Ablation từng nguồn evidence, không bật tất cả một lần | eval scripts | schema/+metric/+value/+FK reports |

### 7.4 Experiment

Thứ tự ablation: `schema-only → +descriptions → +metric aliases → +values → +FK component`. Mỗi nhánh dùng
cùng generator/model/seed và report paired transitions.

| Metric | Baseline lịch sử | Mục tiêu promote |
|---|---:|---:|
| Join-edge recall | **86,36%** | Tăng nhưng không đánh đổi connected precision |
| Value recall@k | Chưa đo | Phải khóa sau R0/R3 dataset; không bịa target |
| Filter/join/grain EX | Chưa có root-cause slice | +3 điểm trên slice sau khi R0 khóa |
| Overall Spider-200 | **65,00%** lịch sử | +2 điểm = tăng ròng ≥4 case so với B0 mới |
| Warm grounding P95 | Chưa đo riêng | ≤1 giây |
| Context size | Baseline phải đo ở R0 | Tăng ≤20% |
| Leakage/privacy | 0 known incident | 100% audit pass |

**Kill rule:** overall giảm >1 điểm, context tăng >30% mà không có gain, index vượt resource envelope hoặc
privacy/leakage test thất bại.

---

## 8. Paper IV — CHASE-SQL: candidate phải khác nhau về logic

**Nguồn:** Pourreza et al., *CHASE-SQL: Multi-Path Reasoning and Preference Optimized Candidate Selection
in Text-to-SQL*, ICLR 2025. [OpenReview](https://openreview.net/forum?id=CvGqMD5OtX).

### 8.1 Paper giải quyết vấn đề gì?

CHASE-SQL dùng ba reasoning path: divide-and-conquer, execution-plan reasoning và instance-aware synthetic
demonstration; sau đó selector so sánh candidate theo cặp. Paper báo 73,01% EX trên BIRD development và
73,0% trên test trong setting high-compute. Ablation của paper cho thấy selector được train tốt hơn
self-consistency/ranker đơn giản trong candidate pool của họ.

Project hiện chỉ sinh một candidate. Khi SQL chạy thành công nhưng sai, corrector thường không có signal để
thử logic khác. Tuy nhiên, P95 hiện đã 85–92 giây nên không thể sinh nhiều candidate cho mọi request.

### 8.2 Phạm vi chuyển giao

- simple/easy: giữ một candidate;
- hard nhưng answerable: tối đa ba candidate từ clause-plan, divide-and-conquer và evidence-constrained path;
- normalize/deduplicate theo AST trước execution;
- mọi candidate đi qua full safety/validation;
- selector ưu tiên deterministic evidence, result-shape invariants và consensus;
- nếu candidate bất đồng mà evidence không đủ: `CLARIFY` hoặc `UNCERTAIN`, không ép chọn.

### 8.3 Work breakdown chi tiết

| Task | Việc thực hiện | File dự kiến | Test/bằng chứng |
|---|---|---|---|
| C1 | Định nghĩa candidate origin, budget và selection evidence | `contracts/sql.py`, `contracts/trace.py` | Max candidate = 3 |
| C2 | Complexity router quyết định 1 hay 3 candidate | Layer 1 + `workflow/budgets.py` | Simple path call count = 1 |
| C3 | Ba prompt path khác nhau về decomposition, không chỉ đổi seed | `layer3_generation/prompt_builder.py` | Prompt-origin snapshots |
| C4 | Normalize và AST fingerprint dedup | `normalizer.py` | Equivalent formatting dedup |
| C5 | Chạy candidate tuần tự, concurrency model = 1 | `layer3_generation/service.py` | Resource/cancellation tests |
| C6 | Tính schema coverage, result agreement, shape và invariant score | `layer3_generation/selector.py` | Gold-blind dependency test |
| C7 | Thêm `UNCERTAIN/CLARIFY` khi selector evidence thấp | workflow + presenter | Không chọn theo self-confidence |
| C8 | Ghi pass@1, oracle@3, selected accuracy và call/latency | eval package | Separate metrics report |

### 8.4 Experiment hai pha

**Pha A — oracle study:** chạy candidate pool trên routed-hard slice, evaluator chỉ tính oracle sau khi
inference đóng. Nếu candidate đúng không xuất hiện, chưa xây selector phức tạp.

**Pha B — selector study:** chỉ làm khi Pha A đạt gate; so deterministic consensus, score-based selector và
LLM pairwise selector nhỏ nếu thật sự cần.

| Metric | Baseline | Mục tiêu promote |
|---|---:|---:|
| Pass@1 | B0 mới | Control |
| Oracle pass@3 | Chưa đo | Cao hơn pass@1 ≥8 điểm trên routed slice |
| Selector recovery | Chưa đo | Thu ≥50% oracle gap |
| Final Spider-200 | B0 mới | Tăng ròng ≥6 case = +3 điểm |
| Correct→wrong regression | 0 ở control | ≤1% tổng sample |
| Calls/P95 routed-hard | 1 call/path hiện tại | Không quá 2 lần control nếu gain đạt |
| Aggregate resource | 6 GPU layers lịch sử, concurrency 1 | Không swap, không power-stop bị bỏ qua |

**Kill rule:** AST/result diversity thấp, oracle gap <8 điểm, selector không hơn consensus, hoặc laptop chạm
resource guard. Không tăng `k` lên 5/8 để cứu một experiment thất bại.

---

## 9. Paper V — APEL: feedback mà người không biết SQL vẫn cung cấp được

**Nguồn:** Zhong et al., *Non-Programmers Can Label Programs Indirectly via Active Examples: A Case Study
with Text-to-SQL*, EMNLP 2023. [ACL Anthology](https://aclanthology.org/2023.emnlp-main.312/).

### 9.1 Paper giải quyết vấn đề gì?

APEL không yêu cầu annotator đọc hai SQL. Hệ thống tìm một input làm các candidate tạo output khác nhau rồi
yêu cầu annotator chọn output đúng. Paper báo non-programmer đạt cùng annotation accuracy 75% như original
expert annotators khi re-annotate Spider và phát hiện nhiều lỗi nhãn tinh vi.

Project hiện lưu rating/category theo run nhưng một thumbs-down không nói rõ sai metric, filter, grain hay
presentation. Đưa raw feedback thẳng vào ICL/fine-tuning sẽ tạo noise và leakage.

### 9.2 Phiên bản local thực tế

Không triển khai active database synthesis đầy đủ ở vòng đầu. Pilot chỉ so sánh **hai output/assumption cards**
đã sanitize trên cùng database hợp lệ:

1. hiển thị câu trả lời và điểm khác nhau về metric/filter/time grain;
2. SQL nằm trong mục Advanced, không bắt buộc đọc;
3. user chọn “đúng ý”, “cả hai sai”, “thiếu dữ liệu” hoặc “không đủ thông tin”;
4. record vào review queue với run ID, catalog version và provenance;
5. chỉ record expert-reviewed mới vào verified example store;
6. không auto-train từ raw feedback.

### 9.3 Work breakdown chi tiết

| Task | Việc thực hiện | File dự kiến | Test/bằng chứng |
|---|---|---|---|
| F1 | Typed feedback reason và comparison contract | file mới `contracts/feedback.py` | Frozen schema/version |
| F2 | Sanitize rows, values và metadata trước display/store | `result_presenter.py` | PII/privacy fixtures |
| F3 | Hai answer cards có cùng format để tránh presentation bias | Streamlit app | UI contract test |
| F4 | Feedback store tách raw/reviewed/rejected | `feedback_store.py`, `example_store.py` | State transition tests |
| F5 | Reviewer UI/CLI và audit log | application layer | Reviewer identity/provenance |
| F6 | Dedup theo question, AST skeleton, catalog và result hash | eval/data tooling | Leakage/dedup report |
| F7 | Export verified examples chỉ sau license/split audit | ignored artifacts + tracked summary | Zero raw-feedback training |

### 9.4 Pilot usability

**Ước lượng:** 5–8 người không chuyên SQL, mỗi người 10–15 task; ít nhất 60 judgment tổng. Một expert label
độc lập làm reference. Đây là formative pilot, không đại diện toàn bộ population.

| Metric | Baseline | Mục tiêu promote |
|---|---:|---:|
| Agreement với expert | Chưa đo | ≥80% |
| Median decision time | Chưa đo | Báo số thật; không đặt target trước pilot |
| Reason/provenance completeness | Chưa đo | ≥90% record |
| Expert review acceptance | Chưa đo | ≥90% |
| Raw feedback auto-training | Không có | Luôn bằng 0 |

**Kill rule:** user chọn theo số dòng/format thay vì semantics, hai card không giải thích được khác biệt bằng
ngôn ngữ nghiệp vụ, hoặc privacy/provenance không bảo đảm.

---

## 10. Lớp đánh giá — không chỉ chấm một database instance

**Nguồn:** Zhong et al., *Semantic Evaluation for Text-to-SQL with Distilled Test Suites*, EMNLP 2020.
[ACL Anthology](https://aclanthology.org/2020.emnlp-main.29/).

Paper chỉ ra execution trên một database hoặc exact SQL có thể phạt query tương đương và bỏ sót query sai
nghĩa. Vì vậy project không thay execution accuracy, mà bổ sung test-suite/mutation evidence và manual review
cho paired regressions.

### 10.1 Metric bắt buộc

Với request set `Q`, tập được trả lời `A` và correctness `c_i`:

```text
answered_accuracy = correct ANSWER / all ANSWER
coverage          = all ANSWER / all requests
answer_risk       = wrong ANSWER / all ANSWER
safe_resolution   = (correct ANSWER + useful CLARIFY
                     + correct CANNOT_ANSWER + SAFE_REJECT) / all requests
```

Không báo accuracy mà bỏ coverage; một hệ thống từ chối mọi câu có thể có answer risk bằng 0 nhưng vô dụng.

Với candidate engine:

```text
oracle_pass_at_3 = cases có ít nhất một candidate đúng / all routed cases
selector_recovery = (selected_accuracy - pass_at_1)
                    / (oracle_pass_at_3 - pass_at_1)
```

Nếu mẫu số gần 0, selector không có headroom và metric không được diễn giải.

### 10.2 Paired report tối thiểu

Mỗi experiment phải báo:

- experiment ID, Git commit, dirty-state, model digest, prompt/index/catalog version, seed và hardware;
- dataset manifest/hash và split status;
- `n/N`, delta điểm tuyệt đối và số case ròng, không chỉ phần trăm;
- bảng `wrong→right`, `right→wrong`, `right→right`, `wrong→wrong`;
- score theo difficulty, DB, language và root-cause cluster;
- first-pass, correction recovery/regression, calls, tokens, P50/P95, RAM/VRAM/power stops;
- EX và test-suite/mutation khi khả dụng;
- danh sách regression để review, giữ nguyên denominator;
- xác nhận runtime không import `agentic_text2sql_eval` hoặc đọc gold.

---

## 11. Kiến trúc đích hợp nhất

```text
Raw question
    │
    ▼
Question Reliability — PRACTIQ
normalize → interpretations → answerability
    ├── ambiguous ──────────────► CLARIFY
    ├── missing fact/evidence ──► CANNOT_ANSWER
    ├── unsafe ─────────────────► SAFE_REJECT
    └── answerable
            │
            ▼
Semantic Planning — DIN-SQL
semantic links → complexity → typed clause plan → plan validation
            │
            ▼
Context Assembly — CHESS
schema/FK + metric contracts + safe values + provenance
            │
            ▼
Adaptive Candidate Engine — CHASE-SQL
one candidate for simple; logic-diverse ≤3 for routed-hard
            │
            ▼
Gold-blind selector → safety → read-only execution → bounded repair
            │
            ├── evidence đủ ────► ANSWER CARD
            └── evidence thiếu ─► CLARIFY / UNCERTAIN
                                      │
                                      ▼
Reviewed Feedback — APEL-inspired
output/assumption choice → review queue → verified examples
```

### 11.1 Agent/module boundary

| Module | Input | Output | Tuyệt đối không được làm |
|---|---|---|---|
| Question analyst | Question + public catalog metadata | Interpretations + answerability | Sinh SQL hoặc đọc gold |
| Semantic planner | Accepted interpretation | Clause plan + complexity | Bịa identifier |
| Grounder | Plan + runtime catalog/index | Evidence package + provenance | Dùng benchmark gold/glossary suy từ gold |
| Candidate generator | Plan + evidence | ≤3 normalized candidates | Bypass policy/validator |
| Selector/verifier | Candidates + gold-blind evidence/results | Selected/uncertain + reasons | Dùng self-confidence làm accuracy |
| Feedback curator | Sanitized run + user choice | Reviewed record | Auto-train raw feedback |

### 11.2 Resource envelope

- model concurrency = 1;
- simple path: tối đa 1 planning call + 1 generation call;
- hard path: tối đa 3 generation candidates, chỉ sau router;
- warm grounding P95 target ≤1 giây;
- không swap; mọi power/temperature breach tiếp tục fail-closed;
- chạy pilot-20 trước dev-100, chỉ sau đó mới locked-200;
- không promote nếu gain nhỏ nhưng aggregate P95/calls tăng quá 2 lần;
- full Spider-1.034 tiếp tục optional trên hardware phù hợp.

---

## 12. Roadmap theo gate và từng bước nhỏ

Trạng thái chỉ dùng `PROPOSED`, `IN_PROGRESS`, `EVALUATED`, `PROMOTED`, `REJECTED`. Chỉ gate
`PROMOTED` mới được tích hợp làm default. Với completion ledger chính, chỉ `make check` và evidence tái lập
mới cho phép chuyển module sang `VERIFIED`.

### Gate R0 — Khóa baseline và failure intelligence

**Mục tiêu:** biết chính xác code hiện tại đạt bao nhiêu và lỗi tập trung ở đâu trước khi đổi thuật toán.

| Bước | Hành động cụ thể | Trạng thái 2026-08-28 | Definition of Done |
|---|---|---|---|
| R0.1 | Chốt commit, model digest, prompt/index/catalog version và manifest | Chưa khóa experiment ID mới | Provenance đầy đủ, clean/dirty state ghi rõ |
| R0.2 | Chạy evaluator self-test và safety suite | Chưa chạy trong gate mới | Evaluator pass; safety 100% |
| R0.3 | Pilot 1 case dưới resource guard | Tooling đã có | Có checkpoint; supervisor vẫn sống; không breach |
| R0.4 | Rerun Spider-200 bằng batch/cooldown/resume | Chưa chạy | 200/200 terminal; không đổi config giữa resume |
| R0.5 | Rerun Olist-60 cùng revision | Chưa chạy | 60/60 terminal; report riêng Spider/Olist |
| R0.6 | So B0 mới với P6 bằng paired comparator | Tooling đã có | Wins/losses/net delta, latency và provenance |
| R0.7 | Sinh AST/result-shape failure evidence offline | Tooling + unit tests đã có | 100% failure có suggested cause, không lưu gold SQL/raw rows |
| R0.8 | Hai reviewer gắn primary cause độc lập | Chưa làm | Exact agreement ≥90%; báo Cohen's kappa |
| R0.9 | Pareto cause × difficulty × DB và owner module | Chưa làm | Top clusters và oracle-recoverability report |
| R0.10 | Viết evidence gate, chạy `make check` | Chưa làm | Evidence link + full check pass |

Lệnh tooling đã có để phân tích sau khi inference đóng:

```bash
uv run python scripts/analyze_spider_failures.py \
  --spider-root data/raw/spider/spider_data \
  --manifest evals/configs/spider-laptop-200.json \
  --release-report evals/reports/<B0_REPORT>.json \
  --output evals/reports/<R0_ANALYSIS>.json \
  --analysis-id <R0_ANALYSIS_ID> \
  --review-a evals/reviews/<REVIEWER_A>.jsonl \
  --review-b evals/reviews/<REVIEWER_B>.jsonl
```

`evals/reports`, reviewer labels chi tiết, predictions và raw Spider tiếp tục gitignored. Evidence tracked chỉ
giữ aggregate, hash và limitations.

**Pass R0:** 200/200 Spider và 60/60 Olist hoàn tất; provenance đầy đủ; 100% failure có primary cause;
review agreement ≥90%; `make check` pass. R0 là measurement gate nên **không đặt yêu cầu tăng accuracy**.

### Gate R1 — Question reliability contract

Thực hiện Q1→Q10 của mục 5 theo thứ tự contract → deterministic rules → LLM fallback → workflow → UI →
challenge evaluation. Không thay generator trong gate này.

**Pass R1:** ambiguity recall ≥85%; false-refusal ≤3%; clarification success ≥80%; confident-wrong giảm
≥30%; safety/Olist không regress ngoài guardrail.

### Gate R2 — Chọn đúng intervention bằng Pareto

- Nếu `filter_or_value` hoặc metric/grain do evidence là cluster lớn nhất: thực hiện CHESS G1→G9.
- Nếu `aggregation_or_grain`, `nesting_or_set` hoặc clause dependency lớn nhất: thực hiện DIN-SQL P1→P8.
- Nếu không cluster nào có đủ sample/effect-size: mở rộng review/fresh diagnostic set, không sửa nhiều module.

Chỉ một intervention được thay đổi trong một experiment để attribution còn hợp lệ.

**Pass R2:** targeted slice +3–5 điểm hoặc overall +2 điểm; easy/Olist/safety/resource trong guardrail; zero
gold leakage.

### Gate R3 — Intervention còn lại

Chỉ chạy sau khi R2 được `PROMOTED` hoặc `REJECTED` có evidence. Rebase baseline thành champion đã khóa, không
so với một working tree không xác định.

**Pass R3:** cùng policy với R2; phải báo marginal gain so với champion, không cộng gain của hai paper trên
giấy.

### Gate R4 — Adaptive candidates

Thực hiện CHASE Pha A oracle trước. Chỉ khi oracle pass@3 có headroom ≥8 điểm mới làm selector Pha B.

**Pass R4:** selector thu ≥50% oracle gap, final +3 điểm trên locked-200, correct→wrong ≤1%, resource budget
không bị phá.

### Gate R5 — Reviewed feedback pilot

Chỉ pilot APEL-style UI/data quality; chưa LoRA. Verified example store chỉ nhận record đã review, dedup và
audit leakage/license.

**Pass R5:** non-coder agreement ≥80%, provenance completeness ≥90%, expert acceptance ≥90%, raw feedback
auto-training = 0.

### Gate R6 — Fresh external proof

Freeze champion trước khi mở fresh DB-disjoint set. Báo Spider, Olist và user challenge riêng; không lấy trung
bình. Full Spider/BIRD chỉ chạy nếu hardware và license/data setup phù hợp.

**Pass gần:** locked Spider-200 ≥140/200 = 70%, Olist ≥57/60 = 95%, safety 100%.<br>
**Pass nghiên cứu tiếp:** fresh/external đạt cùng chiều cải thiện; mục tiêu 150/200 = 75% chỉ là target, không
phải claim trước khi chạy.

---

## 13. Kế hoạch thời gian và effort

Đây là **ước lượng** cho một người làm part-time trên laptop, đã tính thời gian review và rerun; không phải
deadline cam kết.

| Tuần | Gate | Deliverable | Effort người | Thời gian máy ước lượng |
|---:|---|---|---:|---:|
| 1–2 | R0 | B0 mới + failure Pareto + reviewer agreement | 4–6 ngày | 2–4 ngày có cooldown |
| 3–4 | R1 | Question contract + challenge-200 | 7–10 ngày | 8–16 giờ pilot/eval |
| 5–6 | R2 | CHESS hoặc DIN-SQL theo Pareto | 7–10 ngày | 1–3 ngày |
| 7–8 | R3 | Intervention còn lại nếu còn giá trị | 6–9 ngày | 1–3 ngày |
| 9–10 | R4 | Oracle@3 rồi selector | 7–10 ngày | 2–5 ngày |
| 11–12 | R5 | APEL-style pilot + review queue | 6–9 ngày | <1 ngày inference, cộng thời gian user study |
| 13–14+ | R6 | Freeze, fresh validation, report | 5–8 ngày | 2–7 ngày tùy benchmark |

Tổng thực tế: khoảng **12–16 tuần part-time**. Nếu R0 bác bỏ một giả thuyết hoặc một gate bị `REJECTED`, phần
tương ứng không tiếp tục chỉ để hoàn thành timeline.

---

## 14. Scorecard promote/reject

| Nhóm | Primary metric | Guardrail |
|---|---|---|
| Semantic | Spider EX + test-suite/mutation; Olist result accuracy | Giữ denominator, review paired regressions |
| Complexity | Easy/medium/hard/extra-hard | Ghi cả `n/N`, không chỉ % |
| Question reliability | Macro-F1, ambiguity recall, false-refusal, clarification success | Accuracy luôn đi với coverage |
| Grounding | Value recall, metric-link F1, join-edge recall | Provenance, privacy và leakage audit |
| Candidate | Pass@1, oracle@3, selected accuracy, recovery | Correct→wrong ≤1% |
| Product | Task success, comprehension, time-to-useful-answer | Cohort non-coder tách riêng |
| Efficiency | Calls, tokens, P50/P95, RAM/VRAM/power-stop | Không swap; governor fail-closed |
| Reproducibility | Commit/config/hash/digest/seed | `make check`, report và exact commands |

### Promotion ladder

1. **Unit/integration:** contract, safety và no-gold dependency.
2. **Pilot-20:** kiểm plumbing/resource; không claim accuracy.
3. **Development-100:** cần ít nhất +3 correct và không safety regression để có signal.
4. **Locked-200:** research improvement target là +10 correct = +5 điểm; Olist ≥57/60; safety 100%.
5. **Fresh/external:** gain phải cùng dấu trước khi đổi default hoặc công bố kết luận tổng quát.

---

## 15. Rủi ro và phương án kiểm soát

| Rủi ro | Khả năng / tác động | Kiểm soát |
|---|---|---|
| Dùng score 65%/95% cho code v6/v5 | Cao / cao | R0 rerun; mọi bảng ghi revision |
| Gold leakage từ failure analysis | Trung bình / rất cao | Chỉ trong `agentic_text2sql_eval`; dependency test; inference đóng trước evaluator |
| Overfit locked Spider-200 | Cao / cao | Dev/historical/fresh split; freeze trước fresh set |
| Multi-candidate làm latency/power tăng | Cao / cao | Adaptive routing, k≤3, concurrency 1, oracle gate trước selector |
| Value index lộ dữ liệu | Trung bình / cao | Allowlist, cap, hashed provenance, PII fixtures, no raw dump |
| Reviewer label chủ quan | Trung bình / trung bình | Hai reviewer độc lập, agreement + adjudication |
| Accuracy tăng do evaluator artifact | Trung bình / cao | EX + TS/mutation + manual regression review |
| User study quá nhỏ | Cao / trung bình | Gọi là formative pilot, báo sample size/limitations |
| Nhiều thay đổi cùng lúc mất attribution | Cao / cao | Một gate/một independent variable; champion manifest |
| Paper score bị hiểu thành target project | Cao / trung bình | Tách “paper reported” khỏi “project target/result” |

---

## 16. Những việc chủ ý chưa làm

- Không đổi ngay sang model 32B/70B hoặc paid provider.
- Không tăng top-k/schema context khi table/column recall hiện gần bão hòa.
- Không sinh nhiều candidate cho mọi câu.
- Không fine-tune từ raw Spider failure, gold benchmark hoặc raw thumbs feedback.
- Không dùng confidence tự khai của model như xác suất đúng.
- Không gọi subset-200 là official Spider leaderboard hoặc nội suy thành full-1.034.
- Không trộn Spider và Olist thành một accuracy duy nhất.
- Không đánh dấu research module `VERIFIED` trước evidence và `make check`.

---

## 17. Mẫu báo cáo một experiment cho mentor

| Trường | Nội dung bắt buộc |
|---|---|
| Experiment ID / owner / status | Ví dụ `R2-E03`, owner, `EVALUATED` |
| Vấn đề | Root-cause cluster và số case bị ảnh hưởng |
| Paper mechanism | Cơ chế lấy, phần không lấy và lý do |
| Hypothesis | Một thay đổi, một effect-size tối thiểu |
| Baseline/control | Report ID, commit, model/index/prompt digest |
| Dataset/split | Dev/locked/fresh; contamination status |
| Independent variable | Chính xác module/config được đổi |
| Primary metric | `n/N`, delta pp và net cases |
| Guardrails | Olist, safety, latency, calls, RAM/VRAM/power |
| Result | Paired transitions, slices, CI nếu phù hợp |
| Failure review | Case regress và nguyên nhân |
| Decision | `PROMOTED / REJECTED / INCONCLUSIVE` với lý do |
| Next action | Một experiment kế tiếp duy nhất |

---

## 18. Kết luận và hành động kế tiếp

Project không thiếu thêm một framework “agentic” mang tính trình diễn; project thiếu evidence đủ chi tiết để
biết semantic failure xảy ra ở question, plan, evidence, candidate hay selector. Năm paper trong báo cáo được
chọn vì chúng khớp năm boundary đó và có thể chuyển thành typed, bounded, testable modules.

**Hành động tiếp theo duy nhất:** hoàn thành Gate R0 theo R0.1→R0.10. Cụ thể, khóa experiment revision hiện
tại, chạy pilot dưới resource guard, rerun Spider-200/Olist-60, dùng tooling đã có để tạo failure evidence,
review độc lập và xuất Pareto. Chưa sửa thuật toán trước khi R0 có report.

Khi R0 hoàn tất, báo cáo cho mentor phải trả lời được bốn câu bằng số liệu:

1. Code hiện tại đúng bao nhiêu case, trên revision/config nào?
2. Những case nào được sửa hoặc bị regress so với P6?
3. Ba nguyên nhân lớn nhất chiếm bao nhiêu trong tổng số lỗi?
4. Intervention kế tiếp có thể tác động bao nhiêu case và tiêu chí nào khiến nó bị reject?

---

## 19. Tài liệu tham khảo

1. Dong, M. et al. (2025). [PRACTIQ: A Practical Conversational Text-to-SQL Dataset with Ambiguous and
   Unanswerable Queries](https://aclanthology.org/2025.naacl-long.13/). NAACL 2025, 255–273.
2. Pourreza, M. & Rafiei, D. (2023). [DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with
   Self-Correction](https://proceedings.neurips.cc/paper_files/paper/2023/hash/72223cc66f63ca1aa59edaec1b3670e6-Abstract-Conference.html).
   NeurIPS 2023.
3. Talaei, S. et al. (2024/2025). [CHESS: Contextual Harnessing for Efficient SQL
   Synthesis](https://arxiv.org/abs/2405.16755).
4. Pourreza, M. et al. (2025). [CHASE-SQL: Multi-Path Reasoning and Preference Optimized Candidate
   Selection in Text-to-SQL](https://openreview.net/forum?id=CvGqMD5OtX). ICLR 2025.
5. Zhong, R. et al. (2023). [Non-Programmers Can Label Programs Indirectly via Active Examples: A Case
   Study with Text-to-SQL](https://aclanthology.org/2023.emnlp-main.312/). EMNLP 2023.
6. Zhong, R., Yu, T. & Klein, D. (2020). [Semantic Evaluation for Text-to-SQL with Distilled Test
   Suites](https://aclanthology.org/2020.emnlp-main.29/). EMNLP 2020.

### Provenance nội bộ

- [`realistic_project_creation_codex.md`](../../realistic_project_creation_codex.md): canonical specification
  và completion ledger.
- [`benchmark_full.md`](../../benchmark_full.md): benchmark dossier P6 và giới hạn claim.
- [`docs/evidence/p6_gate.md`](../evidence/p6_gate.md): evidence Spider-200/Olist-60.
- [`docs/evidence/p3_1_gate.md`](../evidence/p3_1_gate.md): retrieval metrics/ablation.
- [`docs/evidence/p4_gate.md`](../evidence/p4_gate.md): correction ablation.
- [`docs/evidence/p6_3_query_recovery.md`](../evidence/p6_3_query_recovery.md): post-P6 incident recovery.
- [`docs/error_analysis.md`](../error_analysis.md): failure taxonomy lịch sử.
- [`src/agentic_text2sql_eval/failure_analysis.py`](../../src/agentic_text2sql_eval/failure_analysis.py):
  R0 offline failure evidence contract/tooling.
- [`scripts/analyze_spider_failures.py`](../../scripts/analyze_spider_failures.py): R0 analysis entry point.

> Mọi score mới sau ngày chốt phải thêm experiment ID, revision, manifest và report; không sửa ngược số lịch
> sử trong tài liệu này.
