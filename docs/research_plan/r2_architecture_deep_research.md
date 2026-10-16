# Kiến trúc Text-to-SQL monotonic cho Olist và transfer sang Spider

## Tóm tắt điều hành

P6 đạt 57/60 trên Olist nên một revision mới chỉ có ba đơn vị regression budget trên toàn suite.
Revision E đạt 28/31, sửa hai lỗi baseline nhưng làm hỏng ba case baseline đúng. Kết quả này không
cho thấy cần fine-tune thêm; nó cho thấy integration boundary không bảo toàn incumbent. Khi router
chọn specialist, hệ thống giữ P6 logical plan nhưng bỏ P6 SQL candidate trước khi specialist chứng
minh candidate mới tốt hơn. Một lỗi grounding, planning, generation, validation hoặc deadline của
specialist vì thế có thể biến một câu P6 trả đúng thành terminal failure.

Intervention phù hợp là kiến trúc champion--challenger: luôn tạo và giữ một incumbent P6; chạy tối
đa một challenger có cấu trúc khác; ghi cả hai trong shadow mode; chỉ promote một proof class sau
evidence dev/regression có đủ support, 100% challenger-correct, ít nhất một improvement và không có
regression. Runtime không đọc gold, case ID hay evaluator. Đây là chiến lược tối ưu precision của
quyết định promote, thay vì tối ưu recall của semantic routing.

Construction H3.1--H6 đã được triển khai và vượt `make check`: Ruff, format, strict mypy trên 114
source files và 281 test non-Ollama pass, một Ollama test deselected. Chưa có accuracy claim mới vì
không chạy local model hoặc acceptance suite trong construction.

## 1. Câu hỏi nghiên cứu

Câu hỏi không phải “làm sao ép Qwen nhớ thêm ba câu Olist”, mà là:

> Làm sao một specialist semantic có thể tạo net gain trên baseline 95% mà không dùng benchmark
> identity, không làm regression các câu incumbent đã xử lý đúng, và vẫn mang abstraction sang
> schema chưa thấy của Spider?

Ba giả thuyết có thể bác bỏ:

1. **Candidate preservation:** nếu P6 candidate được giữ đến commit gate, failure của specialist sẽ
   không còn tự động làm mất đáp án incumbent.
2. **Typed contradiction:** nếu intent được biểu diễn bằng owner, grain, operator, predicate và
   result shape, AST incumbent có thể được kiểm tra bằng named contradictions chính xác hơn regex
   hoặc confidence do model tự báo.
3. **Proof-class certification:** nếu promotion được cấp cho operator class sau shadow evidence,
   thay vì cấp cho phrase/rule/case, improvement có cơ hội transfer và regression có thể bị chặn.

Target promotion là ít nhất 58/60. 57/60 chỉ là non-regression/tie với champion, không phải gain.

## 2. Bằng chứng nội bộ và causal decomposition

Theo artifact Revision E được tổng hợp trong `comparison_new2_to_baseline_vn.md`, paired prefix có
hai improvement (`olist_acc_014`, `olist_acc_023`) và ba regression (`olist_acc_020`, `030`, `031`).
Không có case sai ở cả hai hệ thống trên prefix đó. Điều này quan trọng: specialist có tín hiệu hữu
ích, nhưng integration đã tiêu nhiều accuracy hơn phần reasoning tạo ra.

### 2.1 Population owner không đồng nghĩa topic match

Case 20 hỏi payment type có nhiều payment records nhất. View `order_payment_totals` liên quan mạnh
tới payment nhưng có grain một dòng mỗi order và không sở hữu `payment_type`. Alias hoặc retrieval
similarity chỉ trả lời “relation này liên quan”, không trả lời “mỗi row đại diện cho population nào”.
Proof phải gắn đồng thời entity, dimension column, physical owner và row grain.

### 2.2 Fallback logic đúng nhưng đến quá muộn

Case 30 nhận ra derived average nhưng DIN planning không hoàn tất. Trước H3.1, chỉ một số exception
planner mới quay về baseline; grounding error và plan-consistency rejection vẫn terminal. Ngay cả
khi fallback tồn tại, specialist có thể đã tiêu hết deadline cần cho baseline generation hoặc
correction. Resource/deadline admission phải là control-plane invariant, không phải prompt hint.

### 2.3 Semantic evidence bị đứt ở validator

Case 31 compile đúng `MAX(order_count)` từ view một dòng mỗi `customer_unique_id`, nhưng validator
đòi literal identity xuất hiện trong final SQL. Đây là lỗi duplicate semantics: compiler tin typed
lineage, validator tái suy luận từ lexical occurrence. Evidence chain phải đi xuyên từ binding sang
AST validation; validator không được tạo ontology thứ hai bằng regex.

### 2.4 First-pass và correction

Revision E chỉ có 21/31 first-pass correct và correction cứu 7/9 attempt. Specialist không thể được
phép tiêu hết budget trước lớp recovery đang đóng góp một phần lớn score. Đồng thời execution success
không phải correctness: một query có thể chạy hoàn hảo trên sai population hoặc sai aggregation
order. Vì vậy chỉ tăng retries hoặc chọn candidate chạy được là không đủ.

## 3. Tổng hợp nghiên cứu gốc

IRNet tách schema linking, intermediate representation SemQL và deterministic SQL inference để thu
hẹp khoảng cách giữa natural-language intent và chi tiết SQL.^1 Đây là precedent cho typed binding
và compiler, nhưng project cần fail-closed khi IR không đủ thông tin thay vì giả định mọi binding là
hoàn chỉnh.

PICARD loại token không hợp lệ trong lúc decoding, cho thấy giá trị của việc biến output sai cấu
trúc thành không biểu diễn được.^2 Project không kiểm soát token-level decoder Ollama, nhưng áp dụng
cùng nguyên lý tại contract boundary: plan/table/column/join trái catalog bị reject trước execution;
challenger thiếu proof không thể được promote.

DIN-SQL dùng difficulty decomposition, schema linking và self-correction.^3 Kết quả Revision G của
project cho thấy decomposition không nên trở thành global control plane khi catalog coverage hẹp.
DIN phù hợp làm specialist sau incumbent, không phải replacement mặc định.

DART-SQL báo gain từ question rewriting kết hợp execution-guided refinement trên nhiều benchmark.^4
Điểm project giữ lại là database feedback và bounded refinement; điểm không suy diễn là execution
feedback có thể chứng minh semantic correctness. Runtime vẫn cần population/grain checks.

Multi-grained Error Identification tách system, skeleton và value errors.^5 DAC tiếp tục cho thấy
so entity và skeleton decomposed dễ hơn yêu cầu LLM đánh giá trực tiếp SQL opaque, với average gain
được báo trên Spider, BIRD và KaggleDBQA.^6 Project mở rộng taxonomy bằng population/grain và dùng
named AST contradictions làm input cho arbitration/correction.

SQLens kết hợp database và model signals ở clause level, báo error-detection F1 cao hơn self-
evaluation và cải thiện execution accuracy của hệ thống nền.^7 Đây là support cho clause signals,
không phải support cho một binary model judge. Với laptop/local-free constraint, project ưu tiên
catalog, AST và execution evidence deterministic.

Error Detection for Text-to-SQL cho thấy deep parsers có thể over-confident và structural error
features có giá trị cross-parser.^8 Vì vậy model confidence bị loại khỏi commit rule. G3R cho thấy
AST/grammar structure và reranking có thể giúp cross-domain generation,^9 nhưng beam reranking không
phù hợp regression budget và laptop budget hiện tại. Project chỉ dùng một incumbent và một
structurally distinct challenger, không best-of-N.

Nghiên cứu schema generalizability cho thấy cùng câu hỏi nhưng schema structure thay đổi có thể làm
performance giảm đáng kể.^10 Spider-DK cũng chỉ ra domain knowledge hiếm gặp là một failure axis
riêng của cross-domain Text-to-SQL.^11 Do đó test paraphrase trên cùng schema chưa đủ; abstraction
phải qua rename/split/merge/schema-tamper variants.

## 4. Kiến trúc đã triển khai

```text
question
  -> incumbent: frozen P6 plan -> grounding -> generation -> validation/correction
  -> admission gate: còn đủ challenger reserve?
       no  -> SKIP_CHALLENGER, trả incumbent
       yes -> challenger: adaptive DIN/proof -> full validation/correction
  -> typed arbitration
       shadow: luôn KEEP_INCUMBENT, persist cả hai
       enforce:
         proof chưa certified                  -> KEEP_INCUMBENT
         challenger không success/proven       -> KEEP_INCUMBENT
         incumbent success, không contradiction -> KEEP_INCUMBENT
         certified + typed contradiction        -> PROMOTE_CHALLENGER
         certified + incumbent terminal         -> PROMOTE_CHALLENGER
```

### 4.1 H3.1: control-plane backtracking

Specialist grounding error, DIN planning error và rejected DIN plan đều xóa specialist context và
quay đúng một lần về frozen P6. Signal ghi rõ failure stage. DIN không retry và không tạo vòng lặp
fallback qua lại.

### 4.2 H4: shadow ledger

`CandidateArbitration` lưu mode, decision, reason, hai status, hai fingerprints, hai candidate,
bounded result rows, proof kind, rule IDs và incumbent contradictions. Shadow mode luôn trả nguyên
incumbent; challenger chỉ là durable evidence. Offline evaluator sau đó mới mở expected results và
báo paired improvements, regressions, both-correct/both-wrong và slice theo proof kind.

### 4.3 H5: typed arbitration và certification

`validate_sql_against_binding` kiểm tra AST với binding cho:

- source owner;
- aggregate operator và target column;
- `COUNT(*)` so với `COUNT(DISTINCT ...)`;
- frequency dimension/group/count/order/tie-break/limit;
- typed predicates;
- requested rounding.

Không có phrase Olist hoặc case ID trong validator. Unit tests dùng schema `music` và `shipping` để
chứng minh operator contract không phụ thuộc domain name.

Certification chạy hoàn toàn trong `agentic_text2sql_eval`, chỉ dùng partition dev/regression.
Default gate cho một proof kind là support ≥5, challenger accuracy 100%, improvement ≥1 và regression
=0. Artifact certification không được runtime tự đọc; orchestrator chỉ truyền tên operator class
được chứng nhận qua bounded setting. Runtime settings chỉ chấp nhận tập proof kind cố định như
`frequency_ranking` hoặc `aggregate:max`, nên case ID/benchmark phrase không thể lọt qua interface.

### 4.4 H6: budget và laptop safety

Hai path chạy tuần tự; generation và embedding không chạy đồng thời. Challenger bị skip nếu sau
incumbent không còn tối thiểu 45 giây trong admission budget 300 giây. External guarded batch có hard
timeout 360 giây, checkpoint một case, monitor mỗi 0,5 giây, unload models giữa batch và cooldown 60
giây. Qwen luôn nhận explicit `TEXT2SQL_OLLAMA_NUM_GPU=1` qua profile
`olist-paper1-ultrasafe`.

Guard từ chối start/stop khi RAM, swap, VRAM, temperature, power hoặc graphics clock chạm ngưỡng.
Nó không tự retry resource/thermal breach. Infrastructure retry cũ vẫn bị giới hạn một lần và không
áp dụng cho resource stop.

## 5. Vì sao đây không phải hard prompting

Runtime không chứa case ID, gold SQL, expected hash hoặc import evaluator. Promotion unit là operator
class, không phải question phrase hay semantic rule ID. Binding vẫn có thể dùng domain catalog, nhưng
catalog chỉ mô tả stable business semantics và phải khớp introspected schema.

Các hàng rào chống overfit:

1. Shadow output không thay baseline.
2. Gold chỉ được mở offline sau durable predictions.
3. Holdout không tham gia certification.
4. Proof class cần nhiều case, không thể được bật từ một isolated diagnostic.
5. Một regression làm class không được chứng nhận.
6. Settings từ chối string ngoài closed operator vocabulary, bao gồm case ID.
7. Cross-domain AST tests dùng schema không phải Olist.
8. Source digest ngăn resume artifact sau khi code/config/manifest đổi.

## 6. Transfer sang Spider

Thành phần có khả năng transfer là typed operator, AST scope, PK/FK topology, uniqueness,
nullability, join connectivity, population owner và row/output grain. Olist alias, business glossary
và named semantic views chỉ là domain adapter. Trên Spider không có semantic catalog tương ứng, proof
sẽ thường `INCOMPLETE` và incumbent P6 được giữ; đây là expected fail-closed behavior chứ không phải
lỗi recall.

Transfer gate kế tiếp sau Olist promotion phải đo ba lớp riêng:

| Lớp | Metric cần đo | Failure cần tránh |
|---|---|---|
| Grounding | table/column/join recall | đúng operator nhưng thiếu owner |
| Structure | skeleton/clause agreement | executable SQL sai grouping/subquery |
| Arbitration | paired net change và regression | challenger thay incumbent đúng |

Không dùng Spider aggregate score để che một lỗi Olist population/grain. Ngược lại, Olist 58/60
cũng không chứng minh Spider gain; nó chỉ mở quyền đo transfer trên manifest đã khóa.

## 7. Protocol đánh giá hoàn chỉnh

One-command runner thực hiện:

1. `make check`;
2. source digest/provenance lock;
3. guarded shadow run trên dev+regression, không mở holdout;
4. offline proof-class certification với thresholds predeclared;
5. stop nếu không class nào đủ evidence;
6. guarded enforce run Olist-60 với accuracy kill criterion 58/60;
7. checkpoint từng case, unload/cooldown liên tục.

Nếu suite bị dừng bởi accuracy gate, claim hợp lệ chỉ là measured prefix và upper bound. Nếu resource
guard chạm threshold, không resume cho tới khi stale jobs vắng, idle sample an toàn và—nếu chạm 78 W
của exception—OS/NVIDIA Administrator hard cap đã active, sau đó phải chạy one-case pilot mới.

## 8. Giới hạn còn lại

Architecture không thể đảm bảo trước 58/60. Silent semantic errors ngoài vocabulary typed hiện tại
vẫn có thể lọt qua cả hai path. Certification 100% trên dev/regression giảm risk nhưng không chứng
minh holdout precision. Champion--challenger tăng latency và model calls; admission gate có thể skip
challenger ở máy nóng/chậm, làm accuracy quay về P6 thay vì tăng.

AST binding validator hiện cover subset compiler đã typed, không cover arbitrary multi-join,
correlated subquery, window function hoặc set semantics. Những shape này phải được thêm như contract
và test cross-domain trước khi có proof kind mới; không mở promotion bằng regex question.

## 9. Kết luận

Revision mới chuyển vấn đề từ “router đoán path nào tốt hơn” sang “challenger phải chứng minh quyền
thay incumbent”. Đây là thay đổi quan trọng nhất để làm việc gần trần 95%: specialist failure không
còn xóa đáp án baseline; silent replacement cần typed contradiction; promotion cần evidence theo
operator class; holdout không được dùng để tuning. Fine-tuning chỉ nên được xem xét sau khi control
plane này được đo và failure còn lại thật sự là model capacity, không phải lost semantics hoặc
regression do orchestration.

## Sources

1. Guo et al. “[Towards Complex Text-to-SQL in Cross-Domain Database with Intermediate
   Representation](https://aclanthology.org/P19-1444/).” ACL 2019.
2. Scholak, Schucher, and Bahdanau. “[PICARD: Parsing Incrementally for Constrained Auto-Regressive
   Decoding from Language Models](https://aclanthology.org/2021.emnlp-main.779/).” EMNLP 2021.
3. Pourreza and Rafiei. “[DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with
   Self-Correction](https://proceedings.neurips.cc/paper_files/paper/2023/hash/72223cc66f63ca1aa59edaec1b3670e6-Abstract-Conference.html).” NeurIPS 2023.
4. Mao et al. “[Enhancing Text-to-SQL Parsing through Question Rewriting and Execution-Guided
   Refinement](https://aclanthology.org/2024.findings-acl.120/).” Findings of ACL 2024.
5. Xu et al. “[Boosting Text-to-SQL through Multi-grained Error
   Identification](https://aclanthology.org/2025.coling-main.289/).” COLING 2025.
6. Wang et al. “[DAC: Decomposed Automation Correction for
   Text-to-SQL](https://aclanthology.org/2025.findings-emnlp.22/).” Findings of EMNLP 2025.
7. Gong et al. “[SQLens: An End-to-End Framework for Error Detection and Correction in
   Text-to-SQL](https://proceedings.neurips.cc/paper_files/paper/2025/hash/c57812dee8acade8c5e385260b2cde28-Abstract-Conference.html).” NeurIPS 2025.
8. Chen et al. “[Error Detection for Text-to-SQL Semantic
   Parsing](https://aclanthology.org/2023.findings-emnlp.785/).” Findings of EMNLP 2023.
9. Xiang et al. “[G3R: A Graph-Guided Generate-and-Rerank Framework for Complex and Cross-domain
   Text-to-SQL Generation](https://aclanthology.org/2023.findings-acl.23/).” Findings of ACL 2023.
10. Li et al. “[Exploring Schema Generalizability of
    Text-to-SQL](https://aclanthology.org/2023.findings-acl.87/).” Findings of ACL 2023.
11. Gan, Chen, and Purver. “[Exploring Underexplored Limitations of Cross-Domain Text-to-SQL
    Generalization](https://aclanthology.org/2021.emnlp-main.702/).” EMNLP 2021.
