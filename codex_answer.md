# Progress phục hồi Paper II và nguyên tắc phát triển tiếp

**Cập nhật: 2026-09-13**  
**Trạng thái hiện tại:** đã phục hồi và đóng checkpoint code của **Revision E — 28/31** tại commit
`80e94eced52049fd7019fe468c5e23122610edd4`. Revision G đạt 7/10 đã bị reject nhưng được lưu riêng
tại `c4851eb` để điều tra, không còn là code đang được phát triển tiếp.

## 1. Đính chính mốc tốt nhất

Mốc người dùng yêu cầu là 28/31. Có hai run đạt cùng số đúng:

| Run | Kết quả | First pass | Correction | DIN/proof cases | Nhận định |
|---|---:|---:|---:|---:|---|
| Revision D `olist-r2d-proof-fastpath-v1` | 28/31 | 19/31 | cứu 9/11 | 2 | đúng nhiều nhờ correction, chưa dùng proof compiler rộng |
| Revision E `olist-r2e-proof-compiler-v1` | **28/31** | **21/31** | cứu 7/9 | **5** | checkpoint được chọn vì proof path đóng góp rõ hơn |
| Revision G `olist-r2g-global-proof-hybrid-v1` | 7/10 | 7/10 | cứu 0/1 | 8 | reject: semantic proof bị kích hoạt quá rộng |

Revision E là checkpoint đúng cần giữ. Artifact local:

- prediction: `evals/predictions/olist-r2e-proof-compiler-v1.jsonl`, SHA-256
  `a6dadb5e0cce96e18f7c01e4cb675e03be5f176a3e3e195b95f8c2acaf7ef5da`;
- report: `evals/reports/olist-r2e-proof-compiler-v1.progress.json`, SHA-256
  `cc0bdbc1fdf15de2a1b36672d3fa54bbabb3184d837597bfea242d7546ec6414`;
- 31/31 terminal, 30/31 valid candidate, development 28/30, regression 0/1;
- English 13/15, Vietnamese 15/16; easy 21/22, medium 7/9;
- p50 68,91 s, p95 202,07 s.

Đây là **prefix score**, không phải full Olist score. Sau ba lỗi, cận trên là 28 + 29 = 57/60,
không thể đạt research target 58/60 nên evaluator dừng đúng accuracy gate. Không được viết 28/31
thành 90,32% full benchmark hoặc claim đã vượt baseline. Baseline P6 vẫn là champion đã tái lập đầy
đủ: 57/60 tại commit `0972e47`.

## 2. Code đã được phục hồi như thế nào

Trước khi revert, trạng thái 7/10 được commit với nhãn rejected (`c4851eb`) để không mất lịch sử.
Sau đó runtime được đưa về call graph Revision E:

```text
question
  -> frozen P6 planner v2
  -> conservative dependency router
       BASELINE_PRESERVE
         -> P6 hybrid retrieval -> generator v4 -> validator/corrector
       DIN_SQL_ENHANCE
         -> grounded semantic binding -> typed DIN plan
         -> deterministic compile chỉ khi binding == PROVEN
         -> nếu proof thiếu: grounded DIN model path
  -> shared read-only execution + bounded correction
```

Các thay đổi gây 7/10 đã bị bỏ khỏi checkpoint:

- không chạy semantic resolver trước planner/retrieval cho mọi câu;
- không dùng `PROVEN_SEMANTIC_BINDING` để ép mọi one-owner query vào compiler;
- không bypass P6 bằng zero-model global fast path;
- không giữ payment/freight/product-category rule thêm sau khi đã nhìn failure;
- không giữ ngoại lệ validator mới chỉ để làm case đã biết pass;
- không giữ exact benchmark phrases cho payment type và freight.

Gate phục hồi: Ruff pass, format pass, mypy pass trên 111 source files, pytest non-Ollama
**260 passed, 1 Ollama test deselected**. Vì vậy `80e94ec` là checkpoint code có thể quay lại, thay vì
một trạng thái chỉ tồn tại trong chat hoặc artifact.

## 3. Vì sao code downgrade từ 28/31 xuống 7/10

Revision E có một ranh giới an toàn: planner baseline chạy trước, semantic/DIN chỉ vào cuộc khi câu
hỏi bộc lộ dependency phức tạp. Revision G đảo thứ tự và cho semantic catalog quyết định trước cả
retrieval lẫn model. Hậu quả:

1. Catalog coverage chưa đủ nhưng được đối xử như ontology hoàn chỉnh.
2. Alias match chứng minh một cụm từ, không chứng minh toàn bộ entity, population, grain và output
   shape.
3. Deterministic compiler làm lỗi ổn định và nhanh, nhưng ổn định không đồng nghĩa đúng.
4. Validator lexical phản đối SQL đúng do compiler sinh, rồi corrector model timeout.
5. Lỗi ngẫu nhiên của model bị trộn với lỗi kiến trúc, khiến vá từng case ngày càng giống hard prompt.

Ba lỗi trong prefix 10 của G là `olist_acc_005`, `olist_acc_007` (MODEL_ERROR) và `olist_acc_010`
(weighted-average SQL nhưng validator/corrector không hoàn tất). Do đó 7/10 không chứng minh Paper II
sai; nó chứng minh **global proof-first với catalog hẹp là sai integration boundary**.

## 4. Audit hard prompting và quy tắc cấm overfit

Không phải mọi semantic metadata đều là hard prompt. `orders -> olist_orders_dataset`, grain một row
mỗi order, hay `customer_unique_id` là business/schema contract hợp lệ nếu khai báo trước và kiểm
chứng bằng catalog. Phần nguy hiểm là thêm nguyên câu benchmark hoặc regex sau khi nhìn đáp án để ép
đúng riêng case đó.

Từ checkpoint này áp dụng:

1. Runtime không chứa case ID, gold SQL, expected hash hoặc import `agentic_text2sql_eval`.
2. Không thêm alias nguyên câu từ failure. Alias mới phải là thuật ngữ business ngắn, có provenance
   độc lập và paraphrase/counterexample tests.
3. Không thêm `if Olist question contains X then SQL Y`. Rule phải biểu diễn bằng typed operator,
   entity, dimension, predicate, population và source grain.
4. Fix chỉ được giữ nếu pass positive paraphrases, adversarial negative, schema-tamper và ít nhất một
   cross-domain synthetic test.
5. Development/regression failure chỉ dùng để thiết kế abstraction; holdout 46–60 không được tune.
   Mỗi revision dùng evaluation ID mới, không nối checkpoint từ code cũ.
6. Report phải ghi full/prefix, valid rate, first pass, correction gain, latency và route coverage.

## 5. Hướng đúng từ checkpoint 28/31

Không vá ba lỗi 20/30/31 bằng phrase rule. Revision kế tiếp phải là intervention tổng quát:
**Revision H — typed role/grain proof with bounded fallback**.

### H1 — role/grain proof, không benchmark phrase

Xây proof từ decomposition + schema/catalog types:

- population owner: bảng/view sở hữu tập dòng cần đếm;
- entity identity: khóa định danh được hỏi;
- measure: cột hoặc row count;
- source grain: một dòng đại diện cho gì;
- output grain: scalar, một row mỗi dimension, hay distribution;
- operator skeleton: aggregate, ranking, group filter, nested scalar.

Resolver chỉ trả `PROVEN` khi mọi obligation có evidence ID và table/column tồn tại. Nếu còn hai owner
hợp lệ hoặc không chứng minh được grain, trả `AMBIGUOUS/INCOMPLETE`, không đoán.

### H2 — verifier theo AST lineage, không lexical exception

So sánh typed plan với SQL AST theo clause và lineage. View đã được chứng minh “one row per
customer_unique_id” được phép đáp ứng identity obligation dù literal đó không nằm trong SELECT cuối.
Ngược lại, tên cột xuất hiện trong SQL không tự chứng minh đúng population. Đây là cách sửa class lỗi
case 31 nhưng vẫn áp dụng được cho database khác.

### H3 — bounded backtracking khi model/infrastructure lỗi

Nếu DIN planner timeout hoặc structured output lỗi, backtrack một lần về frozen P6 plan/generator;
không sửa prompt, không tăng vô hạn timeout, không best-of-N. Trace ghi
`DIN_TIMEOUT -> BASELINE_FALLBACK`. Nếu fallback cũng lỗi thì dừng typed `MODEL_ERROR`. Cách này xử lý
class lỗi case 30 mà không biết case 30 là gì.

### H4 — shadow routing trước promotion

Chạy proof route ở shadow mode trên development: vẫn trả kết quả P6 nhưng ghi quyết định/SQL của
specialist. Chỉ mở execution route khi precision `PROVEN` đủ cao trên synthetic + development khóa
trước. Recall thấp có thể fallback; false-positive proof mới là lỗi nguy hiểm.

## 6. Papers và phần được sử dụng

- [DIN-SQL — NeurIPS 2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/72223cc66f63ca1aa59edaec1b3670e6-Abstract-Conference.html): decomposition và difficulty-specific specialist.
- [DART-SQL — Findings ACL 2024](https://aclanthology.org/2024.findings-acl.120/): database-aware execution refinement và bounded retry.
- [Multi-grained Error Identification — COLING 2025](https://aclanthology.org/2025.coling-main.289/): system/skeleton/value taxonomy; project thêm grain/population.
- [DAC — Findings EMNLP 2025](https://aclanthology.org/2025.findings-emnlp.22/): entity/skeleton comparison trước correction, chuyển thành typed obligations.
- [SQLens — NeurIPS 2025](https://proceedings.neurips.cc/paper_files/paper/2025/hash/c57812dee8acade8c5e385260b2cde28-Abstract-Conference.html): clause-level database/model signals; project ưu tiên database/AST signal.
- [RoSL — EMNLP Industry 2025](https://aclanthology.org/2025.emnlp-industry.122/): recall-oriented decomposed schema linking cho specialist và Spider nhiều join.

Paper là prior thiết kế, không phải bằng chứng project đạt gain của paper. Code triển khai độc lập và
chỉ claim bằng artifact local.

## 7. Gate tiếp theo

1. Giữ `0972e47` là production baseline và `80e94ec` là research checkpoint 28/31.
2. Implement Revision H trong commit mới; không amend hai checkpoint.
3. `make check` và property/metamorphic/cross-domain tests trước khi chạy model.
4. Guarded one-case pilot: GPU layer 1, batch 1, unload/cooldown, monitor liên tục.
5. Chạy source-locked development/regression; dừng theo upper-bound gate.
6. Chỉ mở full 60 khi còn khả năng đạt >=58/60; không tune holdout sau khi mở.
7. Promote khi full Olist >=58/60, không regression hệ thống so paired P6, và báo latency/resource
   trung thực. Sau đó mới dùng Spider để đo generalization.

Kết luận: mốc 28/31 đã được phục hồi thật và có commit riêng. Hướng tiếp theo không phải thêm prompt
để nhớ Olist, mà là proof role/grain chặt, validator hiểu lineage, và uncertainty backtrack về
baseline. Đây mới là dependency structure có khả năng tăng accuracy lẫn giá trị paper.
