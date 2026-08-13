# Agentic Text-to-SQL — Master Project Plan

> Tài liệu nguồn chính duy nhất để thiết kế, xây dựng, kiểm thử và theo dõi hoàn thành project.  
> Loại project: cá nhân, học tập, nghiên cứu và portfolio; không liên quan đến VNPT hoặc bất kỳ công ty nào.  
> Nguyên tắc chi phí: 100% local và miễn phí; không cần OpenAI, Claude, Gemini hoặc API trả phí.  
> Cập nhật nền tảng và quyết định dataset: 2026-08-06.

---

## 0. Cách sử dụng tài liệu này

File này là master specification và completion ledger. Khi code và tài liệu khác mâu thuẫn với file này, phải:

1. kiểm tra bằng test/evidence;
2. cập nhật quyết định trong file này;
3. sau đó mới sửa code;
4. không giữ hai kế hoạch cạnh tranh nhau.

Mỗi module có ID, dependency, đầu ra, bài test và Definition of Done. Trạng thái chỉ dùng bốn giá trị:

- `NOT_STARTED`: chưa làm;
- `IN_PROGRESS`: đang triển khai nhưng chưa đủ evidence;
- `VERIFIED`: code, test và tài liệu đều đạt;
- `BLOCKED`: không thể tiếp tục nếu thiếu input hoặc môi trường cụ thể.

Không đánh dấu `VERIFIED` chỉ vì code chạy một lần. Cần test tái lập và evidence được ghi trong completion matrix ở cuối tài liệu.

### 0.1 Chuẩn “10/10” dùng trong project

“10/10” không có nghĩa là hứa accuracy tuyệt đối hoặc production enterprise. Trong tài liệu này, nó có nghĩa là một project cá nhân **hoàn chỉnh, trung thực, tái lập và xây được ngay** trên máy hiện có:

- có một vertical slice ứng dụng thật từ tải dữ liệu đến UI;
- mỗi quyết định kiến trúc có owner/module, contract, test và evidence;
- dataset, license, provenance, checksum và business semantics được quản lý;
- benchmark tách biệt khỏi application acceptance test và không leakage;
- failure path, security boundary, resource budget và stop condition được kiểm thử;
- setup mới có thể chạy theo runbook mà không cần API trả phí;
- số đo thật, giới hạn thật và failed cases đều xuất hiện trong report.

Nếu thiếu một trong các mục trên, project chưa được tự gọi là hoàn chỉnh dù demo có chạy.

---

## 1. Tuyên bố sứ mệnh

Xây dựng một Data Analyst Bot chạy hoàn toàn trên máy cá nhân, nhận câu hỏi tiếng Việt hoặc tiếng Anh, tự tìm schema liên quan, lập kế hoạch, sinh SQL, chạy trên database read-only, phân loại lỗi và tự sửa với số vòng lặp giới hạn.

Project nhằm giúp chủ project:

- học thực chất cách thiết kế agent workflow thay vì chỉ gọi một prompt;
- hiểu schema linking, hybrid retrieval và giới hạn context;
- hiểu text-to-SQL generation, SQL parsing và database execution;
- xây feedback loop có kiểm soát;
- biết thiết kế benchmark và tránh data leakage;
- tạo một portfolio có architecture, tests, metrics và demo kiểm chứng được.

### Câu demo mục tiêu

> “Đây là hệ thống Agentic Text-to-SQL tôi tự xây. Nó chạy local bằng Ollama, tìm schema trong database nhiều bảng, lập kế hoạch, sinh SQL, tự chạy và sửa lỗi có giới hạn. Tôi có benchmark, trace và ablation để chứng minh module nào thực sự tạo ra cải thiện.”

---

## 2. Vấn đề project giải quyết

### 2.1 Vấn đề người dùng

- Database có nhiều bảng/cột nên khó nhớ schema và đường join.
- Chatbot thông thường có thể viết SQL sai tên cột, sai join hoặc sai dialect.
- Việc copy lỗi từ SQL editor trở lại chatbot tốn nhiều vòng thao tác.
- Nhét toàn bộ schema vào prompt gây context overflow và nhiễu.
- Một SQL chạy được vẫn có thể sai logic.

### 2.2 Value proposition

Người dùng hỏi:

> “Trong các danh mục có ít nhất 500 order-item đã bán, hãy tìm 5 danh mục có doanh thu sản phẩm cao nhất nhưng điểm review trung bình dưới 3; tách riêng doanh thu sản phẩm và phí vận chuyển.”

Hệ thống sẽ:

1. xác định đây là câu hỏi truy vấn phân tích;
2. lập logical plan;
3. tìm các bảng/cột/foreign key liên quan;
4. sinh một SQL candidate;
5. chặn SQL không an toàn;
6. chạy SQL trên database read-only;
7. nếu có lỗi như sai `product_id`, đưa lỗi đã chuẩn hóa cho Corrector;
8. sửa tối đa số lần cho phép;
9. trả SQL, result preview, schema evidence, assumptions và trace.

---

## 3. Phạm vi cố định

### 3.1 Core scope

| Hạng mục | Quyết định |
|---|---|
| Chi phí | Hoàn toàn miễn phí, không gọi paid API |
| License code project | MIT; tách biệt với license dataset/model/dependency |
| LLM serving | Ollama local |
| LLM chính | `qwen3:14b-q4_K_M` |
| LLM fallback nhanh | `llama3.1:8b` đã có trên máy |
| Embedding | `bge-m3:latest` đã có trên máy |
| Dataset ứng dụng chính | Olist Brazilian E-Commerce, 9 bảng gốc |
| Database ứng dụng | SQLite được project tự build từ CSV Olist chính thức |
| Dataset trong Git/CI | Synthetic Commerce Tiny do project tự sinh |
| Benchmark đầu tiên | Spider dev |
| Benchmark thứ hai | BIRD Mini-Dev hoặc subset sau khi Spider ổn định |
| Dialect đầu tiên | SQLite dialect |
| PostgreSQL | Extension phase sau core completion |
| Agent logic | LangGraph state machine có giới hạn |
| UI | Streamlit local |
| API | FastAPI local, sau core CLI |
| Vector search | FAISS CPU |
| Keyword search | BM25 |
| SQL parser/policy | SQLGlot |
| Storage trace/config | SQLite + JSON/JSONL artifacts |
| Platform | WSL2/Linux, NVIDIA RTX A4500 Laptop 16 GB |

### 3.2 Không thuộc core scope

- Không có user/tenant doanh nghiệp, SSO, Kubernetes, cloud deployment hoặc billing.
- Không query database công ty hoặc dữ liệu VNPT.
- Không hỗ trợ write SQL, DDL, stored procedure hoặc multi-statement.
- Không hỗ trợ tất cả dialect ngay từ đầu.
- Không train RL/MARS-SQL đầy đủ trên laptop.
- Không dùng Pinecone, Weaviate, LangSmith hoặc dịch vụ quan sát trả phí.
- Không copy source code từ research repo không có license rõ.
- Không dùng gold SQL/gold result để Corrector sửa query trong inference.

### 3.3 Target và Definition of Done

`Execution Accuracy > 80%` trên Spider dev là **stretch research target**, không phải điều kiện giả tạo để phủ nhận một project đã hoàn thành về engineering. Local 14B quantized không được bảo đảm đạt mức này.

Core project được coi là hoàn thành khi:

1. toàn bộ module `CORE` trong completion matrix là `VERIFIED`;
2. chạy end-to-end local không cần Internet sau khi model/data đã tải;
3. safety suite chặn 100% fixture write/multi-statement nguy hiểm;
4. benchmark full Spider dev chạy được và xuất report tái lập;
5. report ghi score thực, không sửa số và không dùng gold leakage;
6. có ít nhất một ablation cho retrieval và một ablation cho correction;
7. demo UI, README, architecture và runbook hoạt động;
8. một máy/venv sạch có thể dựng project từ hướng dẫn.
9. Olist downloader/build/validation tái lập được, không commit raw data;
10. tối thiểu 60 câu Olist acceptance có gold SQL hoặc deterministic invariants và report theo độ khó;
11. các semantic trap Olist (customer identity, fan-out, revenue grain, multi-payment, delivery/null) có regression test;
12. không có tính năng hay câu hỏi nào tuyên bố Olist có returns/refunds.

Research target được theo dõi riêng:

| Mức | Phạm vi | Target |
|---|---|---:|
| Smoke | 20 case được chọn cố định | pipeline pass 100%, accuracy chỉ ghi nhận |
| Mini | 100 case cố định, stratified | ≥ 60% execution accuracy ban đầu |
| Baseline | Full Spider dev | đo trung thực, không áp target trước |
| Improvement | Full Spider dev | tăng ≥ 5 điểm tuyệt đối so với direct-generation baseline |
| Stretch | Full Spider dev | > 80% execution/test-suite accuracy |

Application quality gate cho nhãn portfolio-complete “10/10”:

| Gate | Ngưỡng |
|---|---:|
| Olist build/integrity/data-contract | 100% checks pass |
| Safety fixtures | 100% blocked đúng, DB checksum không đổi |
| Olist 60-case workflow completion | 100% có typed final status, không crash |
| Olist regression + holdout result accuracy | ≥ 80% |
| Easy Olist cases | ≥ 90% |
| Deterministic semantic invariants trên accepted queries | 100% |
| Local interactive latency | p95 ≤ 60 giây theo run deadline, báo cả p50/p95 |
| Correction | không giảm overall accuracy; báo recovery và regression rate |

Nếu accuracy chưa đạt, project vẫn có thể `Core Engineering Complete` nhưng chưa gắn nhãn portfolio-complete “10/10”; tiếp tục failure analysis theo module thay vì sửa số hoặc nới holdout.

---

## 4. Kiến trúc tổng thể sáu layers

```text
User question (Vietnamese / English)
                 |
                 v
+-------------------------------------------------------------+
| LAYER 1 — REASONING & PLANNING                              |
| Router -> Decomposer -> Structured Planner                  |
+---------------------------+---------------------------------+
                            |
                            v
+-------------------------------------------------------------+
| LAYER 2 — KNOWLEDGE RETRIEVAL & SCHEMA GROUNDING            |
| Introspector -> BM25 + FAISS -> FK expansion -> Linker      |
+---------------------------+---------------------------------+
                            |
                            v
+-------------------------------------------------------------+
| LAYER 3 — SQL GENERATION                                    |
| Prompt builder -> Generator -> Candidate normalizer         |
+---------------------------+---------------------------------+
                            |
                            v
+-------------------------------------------------------------+
| LAYER 4 — EXECUTION & VALIDATION                            |
| SQLGlot policy -> Read-only Executor -> Result Validator    |
|                         | error                              |
+-------------------------+-----------------------------------+
                          |
                          v
+-------------------------------------------------------------+
| LAYER 5 — GUIDED ERROR CORRECTION                           |
| Error Classifier -> Correction Planner -> Corrector         |
|                    bounded loop back to Layer 3/4           |
+---------------------------+---------------------------------+
                            |
                            v
+-------------------------------------------------------------+
| LAYER 6 — MEMORY, EVALUATION & APPLICATION                  |
| Run store, traces, benchmark, CLI/API/UI, reports           |
+-------------------------------------------------------------+
```

### Agent và deterministic component

Không phải mọi box đều cần là một agent gọi LLM.

| Thành phần | Loại | Lý do |
|---|---|---|
| Router | Rule trước, LLM fallback | Các intent đơn giản không cần tốn inference |
| Planner Agent | LLM structured output | Cần hiểu câu hỏi và lập logical plan |
| Schema Linker | Retrieval code + optional LLM rerank | Search phải đo được và deterministic phần lớn |
| Generator Agent | LLM structured output | Nhiệm vụ sinh SQL chính |
| SQL Policy | Code/AST | An toàn không giao cho prompt |
| Executor | Code/database | Phải deterministic, read-only và có timeout |
| Error Classifier | Rule/error mapping trước | Lỗi SQLite có pattern rõ |
| Corrector Agent | LLM structured output | Cần semantic repair dựa trên lỗi/schema |
| Evaluator | Official/local code | Gold chỉ được dùng sau final output |

### Olist vertical slice đi qua sáu layers

| Layer | Olist input | Output/evidence bắt buộc |
|---|---|---|
| 1 Planning | question + business glossary concepts | metric/dimension/filter/grain/ambiguity; nhận ra returns không có trong domain |
| 2 Grounding | 9 raw tables, semantic views, FK graph, aliases Việt/Anh | table/column/join evidence; profile `raw-only` hoặc `semantic` |
| 3 Generation | plan + packed Olist schema + metric definitions | một SQLite candidate có used columns và assumptions |
| 4 Validation | candidate + Olist catalog/invariants | AST safety, read-only result, fan-out/grain/metric checks |
| 5 Correction | normalized failure + same evidence budget | full corrected candidate; không bịa `returns` hay đổi metric im lặng |
| 6 Application | result/trace + acceptance/evaluator config | UI answer, SQL, provenance, latency; Olist UAT report tách Spider report |

Vertical slice đầu tiên phải chạy một Olist question qua đủ sáu layer trước khi mở rộng benchmark hoặc dialect. Không xây sáu subsystem biệt lập rồi mới ghép ở cuối.

---

## 5. Layer 1 — Reasoning & Planning

### 5.1 Mục tiêu học

- Phân biệt routing, decomposition và planning.
- Thiết kế output có schema thay vì parse văn bản tự do.
- Biết khi nào cần hỏi lại thay vì đoán.

### 5.2 Modules

#### `L1-M1` Query Router

Input: `question`, conversation context tối thiểu.  
Output: `QUERY`, `CLARIFY`, `UNSUPPORTED` hoặc `WRITE_REQUEST`.

Rules:

- Chặn yêu cầu `INSERT/UPDATE/DELETE/DROP/...` ở mức intent.
- Greeting/non-data request trả `UNSUPPORTED` hoặc message phù hợp.
- Câu hỏi thiếu đối tượng/metric quan trọng trả `CLARIFY`.
- Chỉ gọi LLM classifier nếu rules không xác định được.

Tests:

- Bảng fixture ít nhất 30 utterances Việt/Anh.
- 100% explicit write requests được nhận diện.
- Malformed structured output được retry tối đa một lần rồi fail typed.

#### `L1-M2` Decomposer

Input: câu hỏi đã được route là `QUERY`.  
Output: clause-level intent: metric, dimension, filters, sort, limit, time range, set operation.

Không sinh SQL. Không yêu cầu model lưu raw chain-of-thought. Chỉ lưu structured rationale ngắn có thể audit.

#### `L1-M3` Planner Agent

Output contract:

```python
class LogicalPlan(BaseModel):
    question_language: Literal["vi", "en", "other"]
    task_type: Literal["lookup", "aggregation", "ranking", "comparison", "set"]
    metrics: list[str]
    dimensions: list[str]
    filters: list[str]
    sort: list[str]
    limit: int | None
    required_concepts: list[str]
    ambiguities: list[str]
    assumptions: list[str]
```

Planner chạy trước retrieval ở mức schema-agnostic, rồi có thể được enrich một lần sau retrieval. Không loop tự do.

### 5.3 Layer 1 Definition of Done

- `L1-M1..M3` có Pydantic contracts.
- Unit tests và malformed-output tests pass.
- Planner không sinh executable SQL.
- 20 smoke questions tạo plan hợp lệ.
- Prompt version được lưu cùng run.

---

## 6. Layer 2 — Knowledge Retrieval & Schema Grounding

### 6.1 Mục tiêu học

- Introspection SQLite và biểu diễn schema.
- Dense retrieval, lexical retrieval và rank fusion.
- Foreign-key graph expansion.
- Đo table/column recall thay vì chỉ nhìn demo.

### 6.2 Catalog document format

Mỗi database tạo artifacts versioned:

```text
catalog.json
tables.jsonl
columns.jsonl
relationships.jsonl
documents.jsonl
faiss.index
bm25.json
manifest.json
```

P3.1 lưu bundle bất biến dưới `db_id/versions/<version_id>/` và publish `active.json` bằng
`os.replace`. Không deserialize pickle. Manifest pin catalog hash, document template, model tag,
Ollama model digest, embedding dimension, document count và SHA-256 từng artifact. Embedding cache
dùng SQLite transaction; build lỗi không thay active bundle trước đó.

Một document không chỉ là tên cột:

```json
{
  "document_id": "olist.olist_products_dataset.product_id",
  "db_id": "olist",
  "kind": "column",
  "table": "olist_products_dataset",
  "column": "product_id",
  "type": "TEXT",
  "description": "primary key of products; joins order items",
  "neighbors": ["olist_order_items_dataset.product_id"],
  "catalog_hash": "..."
}
```

### 6.3 Modules

#### `L2-M1` SQLite Schema Introspector

Đọc `sqlite_master`, `PRAGMA table_info`, `PRAGMA foreign_key_list`, index và view. Không đọc toàn bộ row.

Output: `CatalogSnapshot` với database ID, tables, columns, types, PK/FK và hash.

#### `L2-M2` Safe Profiler

Tạo metadata tùy chọn: row count xấp xỉ, null rate, min/max và top values cho column an toàn. Với benchmark công khai có thể bật; vẫn giới hạn sample/value count.

#### `L2-M3` Embedding Indexer

- Model: `bge-m3:latest` qua Ollama embeddings API, pin cả model digest.
- Dense index: FAISS CPU.
- Embedding cache theo hash của document + model ID.
- Rebuild khi catalog/model/document template thay đổi.

#### `L2-M4` Keyword Indexer

- BM25 trên identifiers đã tokenize, snake_case split, comments và aliases.
- Giữ exact identifier boost cao.
- Có normalization cho tiếng Việt nhưng không làm mất identifier gốc.

#### `L2-M5` Hybrid Retriever

1. retrieve top-k BM25;
2. retrieve top-k dense;
3. fuse bằng Reciprocal Rank Fusion;
4. filter đúng `db_id`;
5. schema linker tìm minimal FK closure tối đa 2 hops;
6. serialize context cuối cùng rồi enforce token budget trên đúng context đưa vào generator.

#### `L2-M6` Schema Linker

Input: `LogicalPlan` + retrieved candidates.  
Output: `SchemaContext` gồm selected tables, columns, joins và evidence IDs.

Optional LLM rerank chỉ nhận top candidates, không nhận toàn bộ database.

Từ P3.1, linker bắt buộc dùng `LogicalPlan`, thêm join columns, ưu tiên evidence theo plan terms,
không expand toàn bộ one-hop neighbors và trả `rendered_context` cùng `estimated_tokens`.

### 6.4 Evaluation Layer 2

- qualified `table_recall@k`, `column_recall@k` tại k=5/10/20;
- `foreign_key_recall`
- `join_edge_recall` tách khỏi declared-FK recall;
- `context_precision`
- average context tokens
- cold/warm indexing, query embedding, lookup/linking và end-to-end latency tách riêng;
- macro/micro và số case có gold column/join/FK.

Gold schema được suy ra từ gold SQL chỉ trong offline evaluator. Gold schema tuyệt đối không được đưa vào inference state.

### 6.5 Layer 2 Definition of Done

- Index build/reload cho Olist và ít nhất 5 Spider databases.
- Catalog hash ổn định và rebuild đúng khi schema đổi.
- BM25-only, dense-only và hybrid đều có test/report.
- Không retrieve document của database khác.
- Hybrid schema recall tốt hơn hoặc bằng best single retriever trên mini set; nếu không, giữ kết quả trung thực và điều chỉnh fusion.
- Context pack không vượt token budget.
- Mini manifest có đúng 100 unique IDs/hash; tuning/regression set không được gọi là untouched
  holdout. P3.1 có thêm 100-row disjoint holdout chỉ chạy sau khi code/fusion freeze.
- Grounded generation phải được so với full-schema cùng prompt/model version; giữ làm default chỉ
  khi không regression accuracy và trade-off token/latency được report.

---

## 7. Layer 3 — SQL Generation

### 7.1 Mục tiêu học

- Prompt contract cho text-to-SQL.
- Few-shot retrieval và candidate generation.
- Kiểm soát model output bằng structured response và parser.

### 7.2 Modules

#### `L3-M1` Prompt Builder

Prompt gồm:

1. nhiệm vụ và SQLite dialect;
2. hard constraint chỉ một read-only query;
3. question;
4. logical plan;
5. selected schema + FK evidence;
6. verified examples nếu có;
7. output JSON schema.

Không nhét full schema nếu Layer 2 đã chọn subset. Không dùng ví dụ chứa test answer của cùng case.

#### `L3-M2` Generator Agent

Output:

```python
class SqlCandidate(BaseModel):
    sql: str
    used_tables: list[str]
    used_columns: list[str]
    assumptions: list[str]
    confidence: float
```

Defaults:

- model `qwen3:14b-q4_K_M`;
- temperature `0` hoặc `0.1`;
- context baseline `4096`; thử `8192` chỉ sau VRAM/latency benchmark;
- một candidate trên fast path;
- candidate thứ hai chỉ khi validation fail hoặc confidence thấp;
- không mặc định self-consistency 16 trajectories.

#### `L3-M3` Candidate Normalizer

- Loại markdown fence và trailing semicolon.
- Không “sửa” logic bằng regex.
- Parse một statement bằng SQLGlot.
- Gắn fingerprint cho loop detection.

#### `L3-M4` Candidate Selector — optional research

Chỉ thêm sau one-candidate baseline. Selector không dùng gold result. Nó có thể dùng parse validity, schema coverage, execution status, invariant hoặc majority result.

### 7.3 Layer 3 Definition of Done

- Generator trả output đúng contract trên 20 smoke cases.
- Không có SQL text ngoài field `sql` sau parse.
- Mọi candidate mang model/prompt/catalog version.
- Direct generation baseline được lưu trước khi thêm correction.
- Candidate budget không bao giờ bị vượt.

---

## 8. Layer 4 — Execution & Validation

### 8.1 Mục tiêu học

- SQL AST inspection và defense in depth.
- Read-only SQLite execution, timeout và result cap.
- Phân biệt syntax validity, execution validity và semantic correctness.

### 8.2 Modules

#### `L4-M1` SQLGlot Parser và Safety Policy

Các rule core:

- đúng một statement;
- root là `SELECT`, `UNION` hoặc `WITH` kết thúc bằng read query;
- reject `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP`, `ALTER`, `CREATE`, `ATTACH`, `DETACH`, `PRAGMA` từ user query;
- reject data-modifying CTE;
- reject referenced table/column không tồn tại trong full catalog/database allowlist; khác biệt với retrieved subset chỉ là semantic suspicion để tránh Layer 2 miss làm chặn một query hợp lệ;
- reject multi-statement/comment obfuscation;
- reject extension loading, unsafe table-valued functions và access tới SQLite internal tables ngoài allowlist;
- enforce result limit hợp lý khi query không phải scalar aggregate.

SQLGlot là lớp app policy, không phải bằng chứng SQL đúng semantics.

#### `L4-M2` Read-only SQLite Executor

- Mở URI `file:path?mode=ro` với `uri=True`.
- Bật `PRAGMA query_only=ON` từ application và dùng SQLite authorizer callback deny write/attach/detach/pragma/function nguy hiểm; user SQL không được tự gửi PRAGMA.
- Dùng progress handler/deadline để interrupt query dài.
- Result cap theo rows và serialized bytes.
- Không cho model điều khiển database path.
- Mỗi attempt dùng connection lifecycle rõ và luôn close.

#### `L4-M3` Execution Validator

Kiểm tra:

- execute thành công;
- schema output/column count hợp lý;
- result không vượt limit;
- empty result được đánh dấu chứ không tự coi là sai;
- runtime/timeouts được chuẩn hóa.

#### `L4-M4` Semantic Validator

Core không dùng gold result khi phục vụ query. Các signal hợp lệ:

- selected schema và referenced schema có khớp;
- aggregate/non-aggregate shape;
- requested `top k` có `ORDER BY` + `LIMIT`;
- query hỏi khách quay lại phải dùng `customer_unique_id`, không dùng `customer_id`;
- revenue/payment/freight phải theo đúng metric definition trong business glossary;
- multi-table join phải kiểm tra fan-out giữa items, payments và reviews;
- duplicate risk từ join;
- optional deterministic invariants do dataset/user khai báo.

Gold result chỉ chạy trong offline benchmark sau khi agent đã dừng.

#### `L4-M5` Error Normalizer

Map SQLite/SQLGlot errors thành taxonomy ổn định:

- `SYNTAX_ERROR`
- `UNKNOWN_TABLE`
- `UNKNOWN_COLUMN`
- `AMBIGUOUS_COLUMN`
- `TYPE_OR_FUNCTION_ERROR`
- `JOIN_ERROR`
- `FILTER_OR_VALUE_ERROR`
- `AGGREGATION_ERROR`
- `DIALECT_ERROR`
- `POLICY_VIOLATION`
- `TIMEOUT`
- `EMPTY_RESULT_SUSPECTED`
- `UNKNOWN_RUNTIME_ERROR`

### 8.3 Layer 4 Definition of Done

- Safety property tests pass 100%.
- DB file không thay đổi checksum sau test execution suite.
- Timeout và result cap có integration test.
- Error normalization không đưa stack trace dài/raw secret vào Corrector.
- Gold evaluator không import vào runtime execution package.

---

## 9. Layer 5 — Guided Error Correction

### 9.1 Mục tiêu học

- Thiết kế feedback loop có taxonomy.
- Ngăn retry loop, token explosion và “sửa lùi”.
- Đo correction recovery thay vì chỉ xem ví dụ thành công.

### 9.2 Modules

#### `L5-M1` Error Classifier

Rule-based mapping từ `ValidationReport` trước. Chỉ dùng LLM để phân tích semantic suspicion không thể map bằng rule.

Taxonomy research 31 subcategories có thể lưu làm reference, nhưng operational code bắt đầu bằng taxonomy nhỏ phía Layer 4. Chỉ thêm category khi failure analysis chứng minh cần.

#### `L5-M2` Correction Planner

Input:

- question;
- logical plan;
- schema evidence;
- failed normalized SQL;
- sanitized error class/message;
- previous attempt summaries.

Output:

```python
class CorrectionPlan(BaseModel):
    error_class: str
    suspected_cause: str
    changes_required: list[str]
    evidence_ids: list[str]
    should_retry: bool
```

#### `L5-M3` Corrector Agent

Sinh SQL mới theo correction plan. Không trả patch fragment; trả full candidate để Layer 3 normalize và Layer 4 kiểm lại từ đầu.

#### `L5-M4` Feedback Loop Controller

Hard constraints:

- `max_repairs = 2` mặc định;
- `max_llm_calls` toàn run;
- deadline toàn run;
- cùng SQL fingerprint lần hai thì dừng;
- cùng error fingerprint hai lần thì dừng;
- `POLICY_VIOLATION` không retry;
- infrastructure transient retry tách khỏi semantic repair;
- mỗi candidate luôn quay lại full Layer 4 safety gate.

### 9.3 Injection tests cho correction

Tạo incorrect candidates có chủ ý:

- sai tên cột;
- sai alias;
- thiếu join;
- sai aggregate/group by;
- sai value format;
- SQLite function không tồn tại;
- malicious write query.

Đo:

- recovery rate theo error class;
- average repairs;
- regression rate: first candidate đúng nhưng correction làm sai;
- loop-stop reasons;
- extra latency.

### 9.4 Layer 5 Definition of Done

- Corrector sửa được bộ lỗi injection tối thiểu đã định nghĩa.
- Không repair policy violation.
- Không run nào vượt budget trong fuzz/fault tests.
- Benchmark so sánh correction off/on.
- Gold SQL/result không xuất hiện trong correction prompt.

---

## 10. Layer 6 — Memory, Evaluation & Application

### 10.1 Mục tiêu học

- Trace stateful workflow và tái lập experiment.
- Xây benchmark đúng phương pháp.
- Đưa model ra một demo portfolio dễ hiểu.

### 10.2 Modules

#### `L6-M1` Run State và Short-term Memory

LangGraph `QueryState` giữ:

```python
class QueryState(TypedDict):
    run_id: str
    question: str
    db_id: str
    budget: QueryBudget
    logical_plan: LogicalPlan | None
    schema_context: SchemaContext | None
    candidates: list[SqlCandidate]
    validation_reports: list[ValidationReport]
    result_preview: ResultPreview | None
    repair_count: int
    stop_reason: str | None
```

Short-term memory chỉ trong một run/conversation. Không tự động biến chat cũ thành knowledge.

#### `L6-M2` Verified Example Store

Long-term examples chỉ được thêm nếu:

- có question, SQL, db/schema version;
- đã chạy và được evaluator/human xác nhận;
- có provenance;
- không thuộc test case đang đánh giá theo cách gây leakage.

#### `L6-M3` Trace Store

SQLite/JSONL lưu:

- run ID, timestamps;
- model tag/digest và Ollama options;
- prompt versions;
- catalog/index hash;
- retrieved evidence IDs/scores;
- candidates, error class, stop reason;
- latency per layer;
- token counts nếu Ollama trả;
- final status.

#### `L6-M4` Benchmark Harness

Phải tách hai process logic:

```text
Inference: question + DB + schema -> final SQL
Evaluation: final SQL + gold SQL/result -> metrics
```

Evaluator không được feedback gold result về agent.

Metrics:

- execution accuracy;
- Spider test-suite accuracy nếu evaluator chính thức được tích hợp;
- valid SQL rate;
- table/column recall;
- first-pass success;
- correction recovery;
- latency và LLM calls/query.

#### `L6-M5` CLI

Commands dự kiến:

```bash
text2sql doctor
text2sql data download olist
text2sql data build olist
text2sql data validate olist
text2sql ingest --db path/to/database.sqlite --db-id example
text2sql ingest --db data/processed/olist.sqlite --db-id olist
text2sql ask --db-id example --question "..." --execute
text2sql trace show RUN_ID
text2sql eval --config evals/configs/spider-mini.yaml
text2sql report --run-group GROUP_ID
```

#### `L6-M6` FastAPI

Local endpoints:

- `GET /health`
- `GET /models`
- `POST /catalogs/ingest`
- `POST /queries`
- `GET /queries/{run_id}`
- `GET /queries/{run_id}/events` qua SSE

API chỉ nhận `db_id` đã đăng ký; không nhận arbitrary filesystem path từ request. `POST /catalogs/ingest` trong local admin mode chỉ resolve path từ server-side dataset registry và mặc định tắt khi không cần.

#### `L6-M7` Streamlit UI

UI tối thiểu:

- chọn database;
- nhập question;
- xem plan;
- xem schema evidence;
- xem từng SQL attempt/error;
- xem final SQL và result table;
- xem latency/module trace;
- nút feedback đúng/sai;
- trang benchmark/report.

#### `L6-M8` Documentation và Portfolio

- README quickstart;
- architecture diagram;
- module walkthrough;
- benchmark methodology;
- limitations;
- screenshots/GIF;
- video demo script;
- CV bullet có số liệu thật.

### 10.3 Layer 6 Definition of Done

- CLI chạy toàn flow.
- Mỗi run tái truy được config/artifacts.
- Benchmark tách inference/evaluation.
- UI demo ít nhất 3 case: first-pass success, corrected success, safely blocked.
- Fresh-install runbook được thử.
- Report không che failed cases.

---

## 11. End-to-end state machine

```text
START
  -> route
     -> unsupported/write? -> safe_response -> END
     -> ambiguous? -> clarification -> END
  -> decompose_and_plan
  -> retrieve_and_link_schema
  -> generate_candidate
  -> parse_and_policy
     -> policy violation -> blocked -> END
     -> parse/schema/runtime error -> classify_error
     -> allowed -> execute_readonly
  -> validate_result
     -> accepted -> answer -> persist -> END
     -> repairable and budget remains -> correction_plan
       -> corrected_candidate -> parse_and_policy
     -> budget exhausted/not repairable -> failed_answer -> persist -> END
```

### Budget mặc định

```yaml
max_llm_calls: 5
max_candidates: 3
max_repairs: 2
max_schema_documents: 40
max_schema_context_tokens: 2200
model_context_tokens: 4096
query_timeout_seconds: 10
run_deadline_seconds: 60
max_result_rows: 200
max_result_bytes: 2000000
max_concurrent_llm_runs: 1
trace_retention_days: 30
```

Budget được config và log. Không node nào tự tăng budget. Local API dùng semaphore một LLM run tại một thời điểm để tránh VRAM thrashing; request thừa được queue có giới hạn hoặc trả `429`, không âm thầm chạy song song.

---

## 12. Local LLM và Ollama

### 12.1 Cấu hình máy đã xác minh

- CPU: Intel Core i7-12800H, 20 logical CPUs.
- GPU: NVIDIA RTX A4500 Laptop, 16 GB VRAM.
- WSL `.wslconfig`: `memory=24GB`, `swap=16GB`.
- Ollama: đã cài, version quan sát `0.30.10`.
- Ollama server thực tế chạy phía Windows và được WSL truy cập qua `OLLAMA_BASE_URL`/`OLLAMA_HOST`; tại lần kiểm tra là `http://172.27.208.1:11434`. Project không được hard-code IP này vì IP WSL/Windows host có thể đổi.
- Model đã có trước project: `bge-m3`, `nomic-embed-text`, `llama3.1:8b` và một Gemma coder 12B GGUF.
- `qwen3:14b-q4_K_M` đã pull thành công: 9.3 GB, digest `bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`.
- Smoke test Ollama API đã pass với JSON Schema, câu hỏi tiếng Việt và SQLite SQL; cold request khoảng 8.55 giây, model load khoảng 5.69 giây, `ollama ps` báo 100% GPU ở context 4096.

### 12.2 Model roles

| Role | Model | Lý do |
|---|---|---|
| Planner/Generator/Corrector chính | `qwen3:14b-q4_K_M` | 14B Q4 vừa GPU 16 GB tốt hơn model 30B; hỗ trợ đa ngôn ngữ/reasoning |
| Fast/debug fallback | `llama3.1:8b` | Đã có, nhanh hơn để test plumbing |
| Embedding | `bge-m3:latest` | Đã có, multilingual và phù hợp hybrid retrieval |
| Alternative experiment | Gemma coder 12B đã có | Chỉ A/B sau baseline |

### 12.3 Commands

```bash
ollama pull qwen3:14b-q4_K_M
ollama list
ollama run qwen3:14b-q4_K_M
```

Smoke prompt phải test tiếng Việt, structured JSON và SQLite SQL. Sau pull, lưu exact model digest vào `configs/models.yaml`/eval manifest.

Khi WSL không kết nối được Ollama, kiểm tra theo thứ tự:

```bash
printf '%s\n' "$OLLAMA_BASE_URL" "$OLLAMA_HOST"
curl -sS "${OLLAMA_BASE_URL}/api/version"
ollama list
```

Không chạy `ollama serve` với `OLLAMA_HOST` là IP Windows từ bên trong WSL vì tiến trình Linux không thể bind địa chỉ không thuộc interface của nó. Nếu muốn chạy một daemon Linux riêng, override tạm `OLLAMA_HOST=127.0.0.1:11434` và dùng model store Linux riêng; core project mặc định tái sử dụng Windows Ollama đã có model.

### 12.4 VRAM/context rule

Package Q4 khoảng 9,3 GB nhưng KV cache và runtime vẫn dùng thêm VRAM. Ollama đã tự chọn context 4096 trên GPU 16 GB; lấy `num_ctx=4096` làm baseline. Chỉ nâng lên 8192 sau benchmark VRAM/latency/accuracy. Không chọn Q8 16 GB hoặc 30B Q4 làm default vì không còn đủ headroom.

### 12.5 Fully-free guarantee

Core code không import OpenAI/Anthropic/Google SDK. Không có API key trong `.env.example`. Provider abstraction vẫn có thể tồn tại, nhưng chỉ `OllamaProvider` là core implementation. Cloud provider chỉ được thêm ở một fork/optional extra nếu sau này chủ project đổi yêu cầu.

### 12.6 Paths và WSL storage

Không hard-code `D:\...`, `/mnt/d/...` hoặc Ollama host IP trong code. Mọi path đi qua settings (`PROJECT_ROOT`, `TEXT2SQL_DATA_DIR`, `TEXT2SQL_ARTIFACT_DIR`). Repo có thể nằm trên ổ D; nếu full benchmark/index I/O chậm trên `/mnt/d`, đặt generated data/artifacts ở WSL ext4 và giữ source trong workspace. Doctor phải in resolved paths, free disk và quyền read/write nhưng không in secrets.

---

## 13. Technology stack theo layer

| Layer | Applications/libraries | Chức năng |
|---|---|---|
| 1 Planning | LangGraph, Pydantic, Ollama/Qwen3 | route, decompose, structured plan |
| 2 Grounding | `sqlite3`, SQLAlchemy inspector, `rank-bm25`, `faiss-cpu`, BGE-M3 | catalog, lexical+dense search, FK graph |
| 3 Generation | Ollama Python client/HTTP, Pydantic, Jinja2 prompt templates | SQL candidate generation |
| 4 Validation | SQLGlot, SQLite read-only connection, timeout handler | AST policy, execution, validation |
| 5 Correction | LangGraph conditional edges, Qwen3, error taxonomy YAML | bounded repair loop |
| 6 Application | Typer, FastAPI, Streamlit, SQLite/JSONL, pandas/Plotly | CLI/API/UI, trace, benchmark/report |
| Testing | pytest, pytest-asyncio, Hypothesis, coverage | unit/property/integration/safety |
| Tooling | Python 3.12, `uv`, Ruff, mypy, pre-commit | reproducible local development |

Docker không bắt buộc cho SQLite/Ollama core. Docker Compose chỉ được thêm khi mở rộng PostgreSQL để giảm setup complexity trong core learning path.

Dependency policy trong `pyproject.toml`:

- default runtime: Pydantic v2/Settings, LangGraph, Ollama client hoặc `httpx`, SQLGlot, Jinja2, Typer, PyYAML, NumPy, `rank-bm25`, `faiss-cpu`;
- `ui` extra: FastAPI, Uvicorn, Streamlit, pandas, Plotly;
- `eval` extra: benchmark/report dependencies, không được runtime import;
- `postgres` extra: SQLAlchemy/psycopg chỉ ở extension;
- `dev` dependency group: pytest, pytest-asyncio, Hypothesis, coverage, Ruff, mypy, pre-commit.

Pin bằng `uv.lock`, không pin giả version trong planning. Khi scaffold phải chọn versions giải được cùng nhau, lưu lockfile và để Dependabot/Renovate ngoài core scope; update dependency chỉ qua PR/test run có evidence.

---

## 14. Repository structure chính thức

### 14.1 Canonical scaffold tree

Ký pháp `{a,b}.py` bên dưới nghĩa là tạo hai file `a.py` và `b.py`; không tạo thư mục/file chứa dấu ngoặc nhọn.

```text
agentic-text-to-sql/
├── AGENTS.md
├── README.md
├── LICENSE                         # license code; không phủ Olist raw
├── CITATION.cff
├── CHANGELOG.md
├── pyproject.toml
├── uv.lock
├── .env.example                    # không có paid API key
├── .gitignore
├── .pre-commit-config.yaml
├── Makefile
├── docker-compose.postgres.yml     # optional extension
├── .github/workflows/
│   ├── ci.yml
│   └── docs.yml
├── configs/
│   ├── app.yaml
│   ├── models.yaml
│   ├── budgets.yaml
│   ├── logging.yaml
│   ├── safety_policy.yaml
│   ├── error_taxonomy.yaml
│   ├── datasets/{olist,synthetic_tiny,spider}.yaml
│   └── prompts/{planner,schema_linker,generator,corrector}_v1.j2
├── src/agentic_text2sql/
│   ├── __init__.py
│   ├── settings.py
│   ├── exceptions.py
│   ├── contracts/
│   │   ├── catalog.py
│   │   ├── planning.py
│   │   ├── retrieval.py
│   │   ├── sql.py
│   │   ├── validation.py
│   │   └── trace.py
│   ├── layer1_reasoning/{service,router,decomposer,planner}.py
│   ├── layer2_grounding/
│   │   ├── service.py
│   │   ├── introspector.py
│   │   ├── profiler.py
│   │   ├── document_builder.py
│   │   ├── embedding_index.py
│   │   ├── keyword_index.py
│   │   ├── fk_graph.py
│   │   ├── rank_fusion.py
│   │   ├── context_packer.py
│   │   ├── retriever.py
│   │   └── schema_linker.py
│   ├── layer3_generation/{service,prompt_builder,generator,normalizer,selector}.py
│   ├── layer4_validation/
│   │   ├── service.py
│   │   ├── parser.py
│   │   ├── policy.py
│   │   ├── executor.py
│   │   ├── result_validator.py
│   │   ├── join_grain_analyzer.py
│   │   ├── semantic_checks.py
│   │   └── error_normalizer.py
│   ├── layer5_correction/{service,classifier,correction_planner,corrector,loop_controller}.py
│   ├── layer6_application/
│   │   ├── query_service.py
│   │   ├── run_store.py
│   │   ├── example_store.py
│   │   ├── feedback_store.py
│   │   ├── trace.py
│   │   └── result_presenter.py
│   ├── adapters/
│   │   ├── llm/{base,ollama_provider}.py
│   │   ├── embeddings/ollama_embeddings.py
│   │   ├── database/{base,sqlite_adapter}.py
│   │   └── persistence/{sqlite_run_store,sqlite_checkpointer}.py
│   ├── workflow/{state,graph,nodes,budgets}.py
│   └── interfaces/
│       ├── cli/{app,commands}.py
│       └── api/
│           ├── app.py
│           ├── dependencies.py
│           ├── schemas.py
│           └── routes/{health,catalogs,queries,feedback}.py
├── src/agentic_text2sql_eval/      # package gold-aware tách khỏi runtime
│   ├── inference_runner.py
│   ├── result_comparator.py
│   ├── schema_metrics.py
│   ├── spider_adapter.py
│   ├── olist_acceptance.py
│   └── report.py
├── apps/streamlit_app.py           # gọi QueryService/API, không query DB trực tiếp
├── data/
│   ├── README.md
│   ├── raw/{olist,spider,bird}/     # gitignored
│   ├── interim/olist/               # gitignored
│   ├── processed/olist.sqlite       # gitignored
│   ├── indexes/                     # gitignored
│   ├── artifacts/                   # gitignored
│   └── samples/
│       ├── synthetic_commerce_tiny.sqlite
│       └── synthetic_commerce_tiny.sql
├── datasets/
│   ├── olist/
│   │   ├── README.md
│   │   ├── source_manifest.yaml
│   │   ├── schema.sql
│   │   ├── indexes.sql
│   │   ├── derived_views.sql
│   │   ├── business_glossary.yaml
│   │   ├── semantic_invariants.yaml
│   │   ├── expected_counts.yaml
│   │   └── questions/{dev,regression,holdout.template}.jsonl
│   ├── synthetic_commerce/{generator.py,seed.yaml}
│   └── spider/{README.md,pinned_revision.yaml}
├── evals/
│   ├── configs/{olist-smoke,olist-full,spider-smoke-20,spider-mini-100}.yaml
│   ├── manifests/
│   ├── predictions/
│   ├── reports/
│   └── failures/
├── tests/
│   ├── unit/{layer1,layer2,layer3,layer4,layer5,layer6}/
│   ├── property/
│   ├── integration/{test_olist_build,test_olist_vertical_slice,test_workflow}.py
│   ├── safety/
│   ├── golden/{olist,spider}/
│   └── fixtures/{databases,llm_responses}/
├── scripts/
│   ├── doctor.py
│   ├── download_olist.py
│   ├── verify_olist_source.py
│   ├── build_olist_sqlite.py
│   ├── validate_olist.py
│   ├── generate_synthetic_fixture.py
│   ├── download_spider.py
│   ├── build_indexes.py
│   ├── run_smoke.py
│   ├── run_benchmark.py
│   └── export_demo_artifacts.py
└── docs/
    ├── architecture.md
    ├── adr/{0001-olist-primary,0002-sqlite-first,0003-local-ollama-only,0004-gold-separation}.md
    ├── data/{olist_data_card,license_and_attribution,metric_definitions}.md
    ├── learning_notes.md
    ├── benchmark_methodology.md
    ├── error_analysis.md
    ├── threat_model.md
    ├── runbook.md
    ├── troubleshooting.md
    └── demo_script.md
```

Dependency rule:

```text
contracts <- layer services <- workflow <- interfaces
                     ^              |
                  adapters <--------+

agentic_text2sql_eval -> runtime public contracts/interfaces
runtime -X-> evaluator/gold data
apps -> API hoặc QueryService
apps -X-> sqlite3 trực tiếp
```

`contracts` không phụ thuộc framework; adapters thực thi ports; workflow chỉ orchestration. Không tạo `utils.py` tổng hợp. `agentic_text2sql_eval` được tách package để runtime không thể vô tình import gold SQL/result.

---

## 15. Data và benchmark strategy

### 15.0 Quyết định dataset canonical

| Vai trò | Dataset | Trạng thái | Mục đích |
|---|---|---|---|
| Primary application | Olist Brazilian E-Commerce | CORE | build, demo, UAT, semantic validation |
| Repository/CI fixture | Synthetic Commerce Tiny | CORE | test không Internet, license do project kiểm soát |
| Generalization benchmark | Spider dev | CORE evaluation | so sánh text-to-SQL đa domain |
| Secondary benchmark | BIRD Mini-Dev | OPTIONAL | database contents/evidence, khó hơn |
| Enterprise extension | WideWorldImporters | OPTIONAL | multi-dialect/schema rộng sau core |

Olist là dataset đại diện duy nhất của application. Spider/BIRD không được dùng để định nghĩa business feature của ứng dụng và Olist không được dùng để thay thế benchmark generalization.

### 15.1 Olist source, license và storage contract

- Nguồn canonical duy nhất: [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), không dùng bản SQLite do bên thứ ba convert.
- Snapshot hiện có 9 CSV, khoảng 100.000 orders giai đoạn 2016–2018; license metadata: `CC BY-NC-SA 4.0`.
- Đã đo snapshot: ZIP `42.64 MiB`, CSV giải nén `120.34 MiB`, tổng `1,550,922` data rows. Working set dự kiến `300–600 MiB`; reserve `< 1 GiB`.
- Project cá nhân/phi thương mại phù hợp mục tiêu hiện tại, nhưng phải attribution và tuân thủ non-commercial/share-alike. Nếu mục đích chuyển sang thương mại, phải review license lại trước release.
- Không commit ZIP, raw CSV, full SQLite hoặc generated indexes. Commit downloader, source URL, license notice, schema, expected counts, checksum manifest và synthetic fixture.
- Downloader không chứa Kaggle credential. Hỗ trợ Kaggle CLI/API credential qua environment và hướng dẫn manual-download fallback; log source/version nhưng không log secret.

`source_manifest.yaml` bắt buộc có:

```yaml
dataset_id: olistbr/brazilian-ecommerce
source_url: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
license: CC-BY-NC-SA-4.0
snapshot_version: 2
downloaded_at: null
archive_sha256: null
files: {}               # filename -> sha256, bytes, expected headers
redistribution: false
```

### 15.2 Olist raw schema và data contract

| Bảng gốc | Expected data rows | Grain/khóa nghiệp vụ |
|---|---:|---|
| `olist_orders_dataset` | 99,441 | một order; PK `order_id` |
| `olist_customers_dataset` | 99,441 | customer record của order; PK `customer_id`; repeat person dùng `customer_unique_id` |
| `olist_order_items_dataset` | 112,650 | một item sequence trong order; PK `(order_id, order_item_id)` |
| `olist_order_payments_dataset` | 103,886 | một payment sequence; PK `(order_id, payment_sequential)` |
| `olist_order_reviews_dataset` | 99,224 | review row; `review_id` không unique (814 duplicate occurrences), 551 order rows lặp theo `order_id`; dùng surrogate `review_row_id` |
| `olist_products_dataset` | 32,951 | một product; PK `product_id` |
| `olist_sellers_dataset` | 3,095 | một seller; PK `seller_id` |
| `olist_geolocation_dataset` | 1,000,163 | nhiều coordinate cho một zip-prefix; không dùng trực tiếp như dimension 1-row/key |
| `product_category_name_translation` | 71 | map Portuguese category sang English |

Build pipeline phải:

1. verify archive/file SHA-256 và exact headers;
2. load raw tables trong một transaction vào temporary database;
3. parse price/freight/payment bằng `Decimal` và lưu integer cents trong canonical derived columns; giữ raw text để audit, không dùng binary float cho equality;
4. giữ timestamp theo source dưới dạng ISO-8601 timezone-naive; timezone được ghi là unknown, không tự gắn UTC;
5. tạo PK/FK/index rõ ràng và chạy `PRAGMA foreign_key_check` + `PRAGMA integrity_check`;
6. chạy expected counts/ranges/null-profile và uniqueness checks;
7. tạo derived artifacts sau khi raw validation pass;
8. atomic rename temp database thành `data/processed/olist.sqlite`;
9. ghi build manifest gồm source hash, schema hash, row counts, code commit và build time;
10. build lần hai từ cùng input phải cho cùng logical contents; file byte hash không bắt buộc giống nếu SQLite metadata khác.

Known source anomalies phải được test và document, không “clean” im lặng:

- translation CSV có UTF-8 BOM; header reader phải dùng `utf-8-sig`;
- `review_id` không phải primary key và review/order không luôn 1:1; raw table cần surrogate row ID. Snapshot có 551 review rows lặp vượt quá row đầu trên cùng `order_id`, thuộc 547 orders có nhiều review rows;
- 610 products thiếu category; `pc_gamer` và `portateis_cozinha_e_preparadores_de_alimentos` chưa có translation trong snapshot;
- 278 customer rows (157 distinct zip-prefix) và 7 seller rows không match geolocation;
- source có typo columns như `product_name_lenght`; raw giữ nguyên để provenance, semantic view cung cấp alias đúng chính tả;
- các FK order/customer/item/product/seller/payment/review đã kiểm tra không có orphan trong snapshot đo được; zip-prefix và category translation là optional relationship, không ép FK làm mất row.

Indexes tối thiểu: mọi PK/FK join key; `orders.order_purchase_timestamp`; `orders.order_status`; `customers.customer_unique_id`; state/zip-prefix columns. Chỉ thêm compound index sau `EXPLAIN QUERY PLAN` chứng minh cần.

### 15.3 Derived semantic layer cho Olist

Không sửa dữ liệu raw. Tạo views/materialized derived tables có lineage:

- `geo_zip_centroids`: một centroid cho mỗi zip-prefix sau khi lọc coordinate bất hợp lý;
- `order_item_totals`: pre-aggregate item price và freight theo `order_id`;
- `order_payment_totals`: pre-aggregate payment value, count rows và distinct payment types theo `order_id`;
- `order_review_summary`: aggregate review an toàn theo `order_id`;
- `order_delivery_facts`: purchase/approved/carrier/delivered/estimated timestamps, delay days và distance nếu tính được;
- `customer_order_facts`: customer identity đúng bằng `customer_unique_id`, first order và order count.

Các view này phục vụ application correctness và glossary, nhưng evaluation retrieval phải báo rõ profile:

- `raw-only`: chỉ 9 bảng gốc;
- `semantic`: raw + derived views;
- `wide-schema`: synthetic distractor schema/enterprise extension để stress Layer 2.

Không tuyên bố Olist có `returns`, `refunds` hoặc `return_items`. `canceled`/`unavailable` không phải returned. Nếu nghiên cứu returns, tạo extension synthetic tách namespace và không dùng nó để mô tả dataset thật.

### 15.4 Business glossary và semantic invariants

`business_glossary.yaml` là input được version cho planner/linker/validator, tối thiểu định nghĩa:

| Concept | Định nghĩa canonical |
|---|---|
| Product revenue | `SUM(order_items.price)` trên population/status được câu hỏi xác định |
| Freight | `SUM(order_items.freight_value)`, luôn tách khỏi product revenue trừ khi hỏi GMV/payment |
| Paid value | pre-aggregate `SUM(order_payments.payment_value)` theo order trước khi join items |
| Repeat customer | `COUNT(DISTINCT order_id) > 1` theo `customer_unique_id` |
| Multi-payment method | `COUNT(DISTINCT payment_type) > 1`; khác multiple payment rows |
| Late delivered | delivered timestamp lớn hơn estimated delivery date; chỉ xét delivered có đủ timestamp |
| Cancellation rate | canceled orders / population đã định nghĩa; không gọi return rate |
| Review score | aggregate sau khi xử lý cardinality review/order theo contract |

Invariant tests bắt buộc:

- join items + payments không làm nhân metric;
- tổng item revenue từ view bằng tổng raw item price;
- repeat-customer query không group theo `customer_id`;
- geolocation join không nhân order rows;
- date metric loại/ghi rõ null population;
- top-k phải có deterministic tie-breaker trong gold queries;
- mọi answer hiển thị metric definition và assumptions quan trọng.

### 15.5 Olist application acceptance set

Tối thiểu 60 câu hỏi Việt/Anh do project quản lý:

- 30 `dev`: được dùng phát triển prompt/module;
- 15 `regression`: cố định sau khi bug được sửa;
- 15 `holdout`: chỉ mở khi chạy release candidate, không đưa vào example store.

Phủ select/filter, 2–5 table join, aggregation, ranking, time series, cohort, anti-join hợp lệ, CTE/subquery, payment, delivery, review, customer và seller. Mỗi case có:

```json
{
  "id": "olist_vi_001",
  "language": "vi",
  "question": "...",
  "difficulty": "medium",
  "required_concepts": ["product_revenue"],
  "gold_sql": "...",
  "result_order_matters": false,
  "tolerance": 0.01,
  "invariants": ["no_item_payment_fanout"],
  "reviewed": true
}
```

Gold SQL phải được chạy, review grain/metric và lưu expected-result hash; hash được evaluator dùng sau final stop, không đưa vào runtime. Metrics application: result accuracy, valid/read-only rate, first-pass success, correction recovery, semantic-invariant pass, p50/p95 latency và LLM calls.

### 15.6 Representative demo questions hợp lệ

1. Top category theo product revenue, tách freight và yêu cầu minimum order count.
2. Seller có late-delivery rate cao, chỉ so seller có đủ sample size.
3. Cohort repeat customers theo tháng mua đầu tiên dùng `customer_unique_id`.
4. Orders dùng hơn một distinct payment type.
5. Category revenue cao nhưng average review thấp, tránh item-review fan-out.
6. Delivery delay theo customer state và khoảng cách seller–customer.
7. Cancellation/unavailable rate theo tháng, không gọi là return rate.
8. So sánh product revenue, freight và paid value, giải thích population khác nhau.

Ít nhất một demo cố ý tạo fan-out candidate để Layer 4 phát hiện và Layer 5 sửa; một demo hỏi “return rate” phải trả clarification/unsupported-data thay vì bịa bảng.

### 15.7 Spider trước, BIRD sau

Spider phù hợp core vì SQLite, schema đa domain và evaluator công khai. Spider dev có 1.034 question-SQL pairs theo paper SQL-of-Thought. Spider official hiện dùng Test Suite Accuracy làm metric chính thức; cần pin evaluator commit.

BIRD lớn hơn và chứa database contents/evidence. Chỉ bắt đầu BIRD sau khi full Spider pipeline verified. Dùng BIRD Mini-Dev trước để tránh thời gian/dung lượng quá lớn.

### 15.8 Benchmark partitions

- `smoke-20.json`: cố định, bao phủ select/filter/join/aggregate/subquery/set.
- `mini-100.json`: stratified theo difficulty, không đổi giữa experiments.
- `spider-dev-full`: evaluator chính.
- `correction-injection.json`: query lỗi nhân tạo để test Layer 5.
- `safety.json`: malicious/non-read queries.

Olist acceptance files và benchmark partitions không trộn lẫn. Olist đo application fitness; Spider/BIRD đo generalization.

### 15.9 Experiment manifest

Mỗi run benchmark lưu:

```yaml
experiment_id: spider-dev-qwen3-14b-hybrid-v1
git_commit: null
dataset_hash: null
evaluator_commit: null
model_name: qwen3:14b-q4_K_M
model_digest: null
embedding_model: bge-m3:latest
prompt_versions:
  planner: v1
  generator: v1
  corrector: v1
retrieval:
  mode: hybrid
  top_k: 20
correction:
  enabled: true
  max_repairs: 2
seed: 42
```

Null fields phải được điền trước khi report được coi là final.

### 15.10 Required baselines/ablations

1. Direct generation + full schema (nếu vừa context).
2. Planning + direct generation.
3. BM25 grounding.
4. Dense grounding.
5. Hybrid grounding + FK expansion.
6. Hybrid + correction off.
7. Hybrid + correction on.
8. Optional 8B vs 14B model.
9. Olist raw-only vs semantic views.
10. Olist full schema vs retrieval; kỳ vọng retrieval không nhất thiết thắng vì chỉ có 9 bảng.

### 15.11 Leakage rules

- Không đưa gold SQL, gold tables, gold columns hoặc gold result vào agent.
- Không dùng execution-result equality với gold làm trigger correction.
- Không retrieve example là cùng benchmark test question hoặc paraphrase gần-identical.
- Chỉ evaluator nhìn gold sau final stop.
- Report phải ghi rõ có dùng benchmark `evidence` field hay không; baseline core mặc định không dùng oracle evidence.

---

## 16. Implementation roadmap có gates

Thời gian là gợi ý học tập, gates mới quyết định được đi tiếp.

### 16.0 Target command path từ fresh clone đến demo

Khi core đã được implement, một fresh clone phải đi đúng một đường chính:

```bash
uv sync --frozen --extra ui --extra eval --group dev
uv run text2sql doctor
uv run text2sql data download olist
uv run text2sql data build olist
uv run text2sql data validate olist
uv run text2sql ingest --db data/processed/olist.sqlite --db-id olist
uv run text2sql eval --config evals/configs/olist-smoke.yaml
uv run text2sql ask --db-id olist --question "Top danh mục theo doanh thu sản phẩm" --execute
uv run uvicorn agentic_text2sql.interfaces.api.app:create_app --factory --host 127.0.0.1 --port 8000
uv run streamlit run apps/streamlit_app.py
```

`download` là bước duy nhất cần Internet/Kaggle access. Sau khi model và data đã có, build/index/query/eval/demo phải chạy offline. Scripts trong `scripts/` chỉ là thin wrappers gọi cùng application services với CLI, không chứa một implementation thứ hai.

### Phase 0 — Environment và repository

Tasks:

- Pull Qwen3 14B Q4 và smoke test Ollama.
- Scaffold `uv`, Python package, Ruff, mypy, pytest, pre-commit.
- Tạo `AGENTS.md`, configs và typed base contracts.
- Viết `doctor` kiểm tra Ollama/model/GPU/RAM/disk/data.
- Tạo test CI local command.
- Tạo canonical directory tree, data `.gitignore`, license/attribution skeleton.
- Viết Olist source manifest và synthetic fixture generator trước khi tải raw data.

Gate P0:

- `doctor` pass;
- structured JSON smoke response từ Qwen3;
- unit test skeleton pass;
- không paid provider dependency.
- CI chạy hoàn toàn bằng synthetic fixture, không cần Olist/Kaggle/model thật.

### Phase 1 — Olist data foundation và Layer 4 skeleton

Tasks:

- Download, hash, build và validate Olist SQLite từ nguồn canonical.
- Tạo schema/indexes/glossary/invariants và derived views.
- Introspect Olist SQLite và synthetic fixture.
- Viết read-only executor, SQLGlot safety policy và error normalizer.
- Test checksum, timeout, row cap và malicious SQL.

Gate P1:

- Olist build manifest/count/integrity checks pass;
- 10 canonical Olist SQL chạy đúng expected result;
- write query bị chặn hai lớp;
- safety suite pass.

Lý do làm executor/policy sớm: mọi agent về sau cần một environment phản hồi an toàn.

### Phase 2 — Olist vertical slice: Layer 1 và Layer 3 direct baseline

Tasks:

- Router, decomposer, structured planner.
- Prompt builder, generator và normalizer.
- Direct flow trên Olist full schema và synthetic fixture.
- Chạy Olist smoke set, gồm ambiguity “returns”, và lưu baseline.

Gate P2:

- 20/20 Olist smoke run có final status rõ;
- không malformed output crash;
- report direct baseline có result accuracy/latency và semantic failures.

### Phase 3 — Layer 2 schema grounding và generalization setup

Tasks:

- Catalog documents, BGE-M3 embedding cache, FAISS và BM25.
- RRF, FK expansion, context packer, schema linker.
- Raw-only/semantic Olist ablation.
- Sau khi Olist pass, download/pin Spider và tạo gold-schema offline evaluator.

Gate P3:

- indexes rebuild/reload tái lập;
- no cross-db retrieval;
- Olist retrieval report và Spider mini-100 schema recall report;
- hybrid được giữ chỉ khi có evidence.

P3 ban đầu hoàn thành implementation nhưng audit sau gate phát hiện mini có 99 unique rows,
unqualified column matching, no-join cases được tính FK recall=1 và latency loại query embedding.
`docs/evidence/p3_gate.md` được giữ làm lịch sử; các số P3 đó đã bị supersede, không dùng làm current
benchmark.

### Phase 3.1 — Retrieval hardening và grounded-generation integration

Tasks:

- Pin mini-100 manifest đúng 100 unique rows và tạo disjoint untouched holdout-100.
- Qualified SQLGlot scope metrics, declared-FK/join-edge metrics, macro/micro và k=5/10/20.
- Immutable versioned indexes, atomic active pointer, digest pin, SQLite cache, no pickle.
- Plan-aware minimal join closure và budget trên serialized context cuối.
- Nối grounding vào Generator; chạy full-schema/grounded Olist cùng prompt/model version.

Gate P3.1:

- mini và holdout đều 100/100 unique, overlap 0;
- corruption/cross-db/dimension/rollback/budget tests pass;
- hybrid chỉ được giữ nếu ít nhất bằng dense trên disjoint holdout;
- grounded Olist không giảm result accuracy, prompt token và latency được báo trung thực;
- `make check` pass và evidence nằm tại `docs/evidence/p3_1_gate.md`.

### Phase 4 — Layer 5 correction

Tasks:

- Error classifier, correction planner, corrector, loop controller.
- Injection benchmark và loop/fault tests.
- Correction off/on evaluation.

Gate P4:

- no budget overflow;
- recovery report theo category;
- gold leakage test pass.
- correction mặc định feature-flagged cho tới khi multi-run/Olist-60 chứng minh ổn định;
- evidence tại `docs/evidence/p4_gate.md`.

### Phase 5 — Layer 6 application

Tasks:

- Run store/trace, CLI, FastAPI và Streamlit.
- Olist acceptance/report page và benchmark report page tách nhãn.
- Three-case demo.

Gate P5:

- local end-to-end demo;
- Olist acceptance set tối thiểu 60 case chạy hoàn chỉnh;
- trace hiển thị đủ sáu layers;
- restart app vẫn đọc được previous run;
- UI không bypass safety policy.

### Phase 6 — Full evaluation và portfolio completion

Tasks:

- Olist release acceptance gồm holdout và full Spider dev inference/evaluation.
- Required ablations.
- Error analysis top categories.
- README, diagrams, learning notes, demo video script.
- Fresh environment rehearsal.

Gate P6 — Core Complete:

- tất cả core module `VERIFIED`;
- Olist data build/UAT/semantic regression đều `VERIFIED`;
- full report có manifest/hashes;
- limitations và failed cases được ghi;
- demo/reproduction pass.

### Phase 7 — Research improvements

Chỉ chọn từng experiment một:

- verified example retrieval;
- LLM reranking;
- multi-candidate selection;
- query-plan refinement;
- semantic invariants;
- PostgreSQL adapter;
- BIRD Mini-Dev;
- LoRA/SFT 7B/14B nếu data và thời gian cho phép.

Mỗi experiment phải có hypothesis, baseline, budget, metric và kill criterion.

---

## 17. Modular recheck protocol

### 17.1 Recheck một module

Đối với mỗi module ID:

1. đọc responsibility và dependency;
2. kiểm tra contract input/output;
3. chạy unit tests của module;
4. chạy integration test với upstream/downstream gần nhất;
5. chạy một failure-path test;
6. kiểm tra trace/evidence;
7. cập nhật status và evidence path;
8. chỉ sau đó mới đánh dấu `VERIFIED`.

### 17.2 Recheck một layer

Một layer chỉ complete khi:

- tất cả core modules trong layer verified;
- layer-level Definition of Done đạt;
- test coverage không phải bằng chứng duy nhất;
- có ít nhất một artifact/report hoặc demo output;
- không còn blocker không được ghi.

### 17.3 Recheck toàn project

Run theo thứ tự:

```bash
uv sync
uv run ruff check .
uv run mypy src
uv run pytest tests/unit
uv run pytest tests/property tests/safety
uv run pytest tests/integration
uv run text2sql doctor
uv run python scripts/validate_olist.py --db data/processed/olist.sqlite
uv run text2sql eval --config evals/configs/olist-smoke.yaml
uv run text2sql eval --config evals/configs/spider-smoke-20.yaml
uv run text2sql eval --config evals/configs/spider-mini-100.yaml
```

Full Spider dev chạy ở release candidate, không cần mọi commit vì local inference tốn thời gian.

### 17.4 Bug completion rule

Mỗi bug quan trọng cần:

- minimal reproduction;
- root cause;
- regression test fail trước/fix sau;
- ghi category vào error analysis;
- recheck modules chịu ảnh hưởng.

---

## 18. Completion matrix

> Đây là bảng sống. `Evidence` sẽ là test path, report path hoặc command output khi implementation bắt đầu.

| ID | Module | Core | Dependency | Status | Evidence |
|---|---|---:|---|---|---|
| P0-M1 | Environment doctor | Yes | — | VERIFIED | `uv run text2sql doctor --json`; `docs/evidence/p0_gate.md` |
| P0-M2 | Ollama provider + structured smoke | Yes | model pull | VERIFIED | provider unit tests + live `uv run text2sql ollama-smoke`; `docs/evidence/p0_gate.md` |
| P0-M3 | Project scaffold/tooling | Yes | — | VERIFIED | `uv sync --frozen`, Ruff, mypy strict, pytest; `docs/evidence/p0_gate.md` |
| D-M1 | Olist source manifest/downloader | Yes | P0-M3 | VERIFIED | pinned ZIP/9 CSV contracts + download/failure tests; `docs/evidence/p1_gate.md` |
| D-M2 | Olist SQLite builder/schema/indexes | Yes | D-M1 | VERIFIED | two full builds share logical hash; atomic rollback tests; `docs/evidence/p1_gate.md` |
| D-M3 | Olist integrity/data-contract validator | Yes | D-M2 | VERIFIED | 20/20 full-data checks; `data validate olist`; `docs/evidence/p1_gate.md` |
| D-M4 | Olist glossary/semantic views/invariants | Yes | D-M3 | VERIFIED | canonical queries + semantic regression tests; `docs/evidence/p1_gate.md` |
| D-M5 | Synthetic Commerce Tiny generator | Yes | P0-M3 | VERIFIED | `tests/unit/test_synthetic_generator.py`; logical hash in `docs/evidence/p0_gate.md` |
| D-M6 | Olist acceptance set ≥60 reviewed cases | Yes | D-M4 | NOT_STARTED | — |
| L1-M1 | Query Router | Yes | P0-M2 | VERIFIED | 30+ bilingual fixtures, write/returns regression; `docs/evidence/p2_gate.md` |
| L1-M2 | Decomposer | Yes | L1-M1 | VERIFIED | clause-hint unit tests, no SQL/CoT output; `docs/evidence/p2_gate.md` |
| L1-M3 | Planner Agent | Yes | L1-M2 | VERIFIED | JSON Schema live plans, typed malformed path, prompt version evidence |
| L2-M1 | SQLite Introspector | Yes | P0-M3 | VERIFIED | stable catalog hash/composite FK/view/index tests; Olist + synthetic introspection |
| L2-M2 | Safe Profiler | No | L2-M1 | NOT_STARTED | — |
| L2-M3 | Embedding Indexer | Yes | L2-M1, P0-M2 | VERIFIED | immutable FAISS bundles, digest/cache/shape/checksum/rollback; `docs/evidence/p3_1_gate.md` |
| L2-M4 | Keyword Indexer | Yes | L2-M1 | VERIFIED | JSON artifact, identifier/Vietnamese BM25 and exact boost tests |
| L2-M5 | Hybrid Retriever | Yes | L2-M3, L2-M4 | VERIFIED | equal-weight RRF wins qualified column recall on disjoint holdout; db isolation |
| L2-M6 | Schema Linker | Yes | L1-M3, L2-M5 | VERIFIED | plan-aware minimal FK closure, join columns, final serialized budget |
| L3-M1 | Prompt Builder | Yes | L1-M3, L2-M6 | VERIFIED | full/grounded prompt v2; live no-regression Olist ablation |
| L3-M2 | Generator Agent | Yes | L3-M1, P0-M2 | VERIFIED | 20-case live typed baseline, one candidate budget; `docs/evidence/p2_gate.md` |
| L3-M3 | Candidate Normalizer | Yes | L3-M2 | VERIFIED | fence/semicolon/multi-statement/non-query/fingerprint tests |
| L3-M4 | Candidate Selector | No | baseline complete | NOT_STARTED | — |
| L4-M1 | Parser + Safety Policy | Yes | P0-M3 | VERIFIED | `tests/unit/layer4/test_policy.py`, `tests/safety/test_sql_safety.py` |
| L4-M2 | Read-only Executor | Yes | L4-M1 | VERIFIED | RO URI/query_only/authorizer, timeout/caps/checksum tests; canonical Olist queries |
| L4-M3 | Execution Validator | Yes | L4-M2 | VERIFIED | typed shape/warning reports; `tests/unit/layer4/test_semantic_validation.py`; `docs/evidence/p4_gate.md` |
| L4-M4 | Semantic Validator | Yes | L4-M3 | VERIFIED | gold-blind intent/shape/business signals; P4 Olist ablation |
| L4-M5 | Error Normalizer | Yes | L4-M1 | VERIFIED | `tests/unit/layer4/test_error_normalizer.py` |
| L5-M1 | Error Classifier | Yes | L4-M5 | VERIFIED | rule-first eligibility; policy/timeout no-repair tests |
| L5-M2 | Correction Planner | Yes | L5-M1 | VERIFIED | typed plan and signal-specific deterministic guidance |
| L5-M3 | Corrector Agent | Yes | L5-M2, P0-M2 | VERIFIED | structured full-candidate local repair; gold separation test |
| L5-M4 | Feedback Loop Controller | Yes | L5-M3, L4 | VERIFIED | call/repair/deadline/fingerprint stops; full L4 revalidation |
| L6-M1 | Query State/short memory | Yes | L1–L5 contracts | NOT_STARTED | — |
| L6-M2 | Verified Example Store | No | baseline complete | NOT_STARTED | — |
| L6-M3 | Trace Store | Yes | L6-M1 | NOT_STARTED | — |
| L6-M4 | Benchmark Harness | Yes | L4, L6-M3 | NOT_STARTED | — |
| L6-M5 | CLI | Yes | workflow | NOT_STARTED | — |
| L6-M6 | FastAPI | Yes | L6-M5 | NOT_STARTED | — |
| L6-M7 | Streamlit UI | Yes | L6-M6 | NOT_STARTED | — |
| L6-M8 | Documentation/portfolio | Yes | reports/demo | NOT_STARTED | — |
| E-M1 | Olist smoke/UAT report | Yes | D-M6, L1–L6 | NOT_STARTED | — |
| E-M2 | Spider smoke-20 | Yes | L1–L6 | NOT_STARTED | — |
| E-M3 | Spider mini-100 | Yes | E-M2 | NOT_STARTED | — |
| E-M4 | Full Spider dev report | Yes | E-M3 | NOT_STARTED | — |
| E-M5 | Retrieval ablation | Yes | L2 | VERIFIED | qualified k=5/10/20, raw/semantic, mini + disjoint holdout; `docs/evidence/p3_1_gate.md` |
| E-M6 | Correction ablation | Yes | L5 | VERIFIED | frozen Olist 14/18 off vs 17/18 on; `docs/evidence/p4_gate.md` |
| E-M7 | BIRD Mini-Dev | No | core complete | NOT_STARTED | — |
| X-M1 | PostgreSQL adapter | No | core complete | NOT_STARTED | — |

Overall project status tại thời điểm cập nhật master plan: `GATE_P4_VERIFIED_FEATURE_FLAGGED`. P0
environment, P1 data/safety, P2 direct baseline, P3.1 grounded retrieval và P4 bounded correction
có evidence từ `docs/evidence/p0_gate.md` đến `docs/evidence/p4_gate.md`. P4 correction tăng frozen
Olist run từ 14/18 lên 17/18 nhưng vẫn opt-in vì diagnostic rerun cho thấy model variance.
Application layers chưa được triển khai.

---

## 19. Test inventory bắt buộc

### Data foundation

- Download resume/failure, bad archive hash và missing/extra CSV/header.
- Build rollback: lỗi giữa chừng không để lại database được coi là valid.
- Exact row counts, PK uniqueness, FK/integrity check và expected null/range profile.
- Build idempotency theo logical content hash.
- Geolocation centroid không tạo nhiều row/zip-prefix.
- Item/payment/review pre-aggregation không làm đổi totals.
- Synthetic fixture deterministic theo seed và chứa đủ edge cases.

### Layer 1

- Việt/Anh router fixtures.
- Ambiguity and unsupported prompts.
- Malformed JSON/timeout/model unavailable.

### Layer 2

- Composite PK/FK, no-FK database, view, quoted identifier.
- Embedding cache hit/miss.
- BM25/dense/RRF deterministic fixtures.
- Cross-database isolation.
- Token context cap.

### Layer 3

- Markdown/noisy response normalization.
- Wrong schema hallucination.
- Candidate budget.
- Prompt snapshot/version tests.

### Layer 4

- Safe `SELECT`, CTE, aggregate, union.
- DML/DDL/ATTACH/PRAGMA/multi-statement/data-changing CTE.
- Timeout, huge result, empty result, locked/corrupt DB.
- DB checksum unchanged.
- Olist join-grain regression: item × payment, item × review và geolocation fan-out.
- Customer identity, revenue/freight/payment và delivery-null invariants.
- Câu hỏi return/refund phải clarify/unsupported-data, không hallucinate table.

### Layer 5

- Error injection by category.
- Same SQL loop.
- Same error loop.
- Policy violation no-retry.
- Repair budget/deadline.
- No-gold-in-prompt assertion.

### Layer 6

- Trace persistence/reload.
- Eval separation.
- CLI exit codes.
- API validation/SSE completion.
- UI calls API/workflow, never raw DB directly.
- Olist application report và Spider benchmark report không gộp thành một accuracy.
- Holdout case không xuất hiện trong prompt/example retrieval/trace trước release evaluation.

---

## 20. Rủi ro và cách xử lý

| Rủi ro | Tác động | Xử lý |
|---|---:|---|
| Local 14B không đạt >80% | Cao về target, không phá engineering | Báo score thật, ablation, error analysis; target là stretch |
| Model chậm ở full dev | Cao | Cache embeddings/plans có kiểm soát, checkpoint eval, resume, smoke/mini trước |
| Context vượt VRAM | Cao | 8k context, schema retrieval, one candidate, đo VRAM |
| SQL chạy được nhưng sai logic | Rất cao | semantic checks, test-suite accuracy, invariants, user assumptions |
| Gold leakage | Rất cao | process/package separation, assertion tests, manifest disclosure |
| Correction loop vô hạn | Cao | max 2 repairs, fingerprint/deadline/call budget |
| Benchmark repo/data đổi | Trung bình | pin commit/hash và evaluator version |
| Research code không license | Cao | chỉ học ý tưởng/paper; tự viết code |
| Overengineering làm không xong | Cao | SQLite/Spider/CLI first; optional modules không chặn core |
| WSL RAM chỉ 24 GB | Trung bình | không dùng 30B; giữ embedding CPU, Qwen14B Q4 GPU |
| Ollama/model update đổi kết quả | Trung bình | lưu model digest/options trong manifest |
| Olist license bị dùng sai mục đích | Cao | attribution, raw gitignored, non-commercial scope; review lại trước mọi commercial release |
| Nhầm canceled với returned | Rất cao về semantics | glossary + unsupported-data test; không có return KPI trong Olist core |
| `customer_id` làm sai repeat customer | Cao | contract bắt buộc `customer_unique_id` + regression query |
| Join items/payments/reviews làm nhân doanh thu | Rất cao | pre-aggregate theo order, join-grain analyzer và invariant totals |
| Geolocation làm nhân rows/đo sai distance | Cao | centroid zip-prefix có lineage; Haversine precompute và validation |
| Olist chỉ 9 bảng nên retrieval trông tốt giả tạo | Trung bình | report full-schema baseline; Spider + wide-schema stress riêng |
| Kaggle download/auth/network hỏng | Trung bình | manual-download fallback, resume, checksum; CI chỉ dùng synthetic fixture |

---

## 21. Kế hoạch học sáu tuần

| Tuần | Project work | Kiến thức phải tự giải thích lại được |
|---|---|---|
| 1 | P0 + Olist data foundation + Layer 4 skeleton | data contracts, SQLite metadata, read-only execution, AST policy |
| 2 | Olist vertical slice qua Layer 1 + Layer 3 | business grain, structured prompting, planning vs generation |
| 3 | Layer 2 BM25/FAISS/FK + Spider setup | embeddings, hybrid retrieval, schema recall, application vs benchmark |
| 4 | Layer 5 correction loop | taxonomy, retry budgets, failure analysis |
| 5 | Layer 6 CLI/API/UI + Olist acceptance + mini benchmark | orchestration, trace, experiment reproducibility |
| 6 | Olist holdout + full Spider, ablation, docs/demo | benchmark validity, limitations, portfolio storytelling |

Nếu một gate chưa đạt, không ép chuyển tuần. Mục tiêu là hiểu và verified từng module, không hoàn thành theo lịch giả.

---

## 22. Portfolio deliverables

### README phải trả lời

- Project giải quyết vấn đề gì?
- Vì sao cần agentic workflow thay vì một prompt?
- Sáu layers hoạt động ra sao?
- Fully local/free bằng model nào?
- Safety và correction loop được giới hạn thế nào?
- Benchmark dùng metric gì, có tránh leakage không?
- Score/latency thật là bao nhiêu?
- Những failure mode còn lại là gì?
- Vì sao chọn Olist, license/provenance/dung lượng và cách build SQLite?
- Business glossary ngăn `customer_id`, revenue và fan-out sai như thế nào?
- Vì sao Olist acceptance và Spider benchmark là hai report khác nhau?

### Demo ba tình huống

1. Olist query đúng ngay: revenue/review theo category, cho thấy planning + grounding + generation.
2. Olist candidate bị item-payment fan-out rồi sửa: cho thấy semantic invariant + bounded correction.
3. Câu hỏi “return rate” được clarify là dataset không có returns; sau đó query `DROP/DELETE` bị policy chặn. Hai nhánh này chứng minh trung thực dữ liệu và safety.

### CV bullet template

> Built a fully local six-layer Agentic Text-to-SQL system using LangGraph, Ollama/Qwen3, BGE-M3 hybrid schema retrieval, SQLGlot validation and bounded error correction; evaluated on Spider with reproducible execution accuracy, schema-recall and latency ablations.

Chỉ điền số liệu thật sau full report.

---

## 23. Research references và nguyên tắc sử dụng

- [SQL-of-Thought paper](https://arxiv.org/html/2509.00581): planning, guided error taxonomy và correction loop. Paper dùng Claude 3 Opus và 2 H100 80 GB; score không thể chuyển nguyên sang laptop local.
- [SQL-of-Thought repository](https://github.com/shollercoaster/SQL-of-Thought): chỉ đọc để hiểu artifact; không copy code khi license chưa rõ.
- [CHESS](https://github.com/Relaxed-System-Lab/Text2SQL-CHESS): information retrieval, schema selector, candidate generation và unit testing.
- [APEX-SQL](https://github.com/Tencent/APEX-SQL-Project): agentic schema exploration; chỉ optional research sau core.
- [MARS-SQL](https://github.com/YangHaolin0526/MARS-SQL): multi-agent RL và multiple trajectories; không train core trên laptop.
- [Spider official repository](https://github.com/taoyds/spider): dataset/evaluator.
- [Spider 2.0](https://spider2-sql.github.io/): future enterprise-scale stress test, không phải core.
- [BIRD](https://bird-bench.github.io/): secondary benchmark sau Spider.
- [LangGraph documentation](https://langchain-ai.github.io/langgraph/index.html): stateful bounded workflow.
- [SQLGlot](https://github.com/tobymao/sqlglot): SQL parser/AST/dialects.
- [Ollama Qwen3 tags](https://ollama.com/library/qwen3/tags): local model artifacts.
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs): JSON Schema/Pydantic contract cho Planner/Generator/Corrector.
- [Ollama embeddings](https://docs.ollama.com/capabilities/embeddings): local batch embedding API; indexing và querying phải dùng cùng model.
- [BGE-M3 model card](https://huggingface.co/BAAI/bge-m3): multilingual dense/sparse representation reference.
- [Olist Brazilian E-Commerce — canonical dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce): 9-table application dataset, source description và license metadata.
- [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/): điều kiện attribution, non-commercial và share-alike áp dụng cho Olist snapshot theo metadata.
- [Olist Marketing Funnel](https://www.kaggle.com/datasets/olistbr/marketing-funnel-olist): optional extension, không thuộc core 9-table build.
- [SQLite URI filenames](https://www.sqlite.org/uri.html): `mode=ro` connection; kết hợp authorizer/progress handler/app policy theo defense in depth.
- [LangGraph documentation](https://langchain-ai.github.io/langgraph/index.html): low-level stateful orchestration, persistence và bounded workflow; project không dùng LangSmith paid service.

Ý tưởng paper được tái hiện độc lập. Không clone-copy-xóa code như một cách né license. Nếu một repo không có license rõ, chỉ đọc paper/README và tự viết implementation dựa trên concept.

---

## 24. Quyết định cuối cùng đã chốt

- Đây là project cá nhân, không liên quan VNPT.
- Core phải chạy miễn phí và local.
- Codex được phép pull model Ollama và chạy benchmark trên máy.
- Olist 9 bảng gốc + SQLite tự build là application vertical slice và đường hoàn thành đầu tiên.
- Olist không có returns/refunds; mọi câu hỏi loại này phải clarify hoặc dùng extension synthetic được gắn nhãn.
- Raw Olist/full SQLite/indexes không commit; CI dùng Synthetic Commerce Tiny.
- Olist application acceptance và Spider/BIRD benchmark luôn tách report.
- Spider dev là generalization benchmark core sau Olist vertical slice; BIRD là extension.
- PostgreSQL + BIRD là extensions, không làm core bị kéo dài.
- Kiến trúc phải thể hiện đầy đủ sáu layers.
- Mỗi module phải có test/evidence trước khi verified.
- Corrector không được nhìn gold answer.
- Safety do code + read-only database thực thi, không do prompt.
- Score >80% là stretch goal; score thực và độ hiểu hệ thống quan trọng hơn việc làm đẹp số.
- File này tiếp tục được cập nhật như master plan cho đến khi project đạt Core Complete.
