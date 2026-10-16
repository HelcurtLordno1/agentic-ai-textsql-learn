# Novelty assessment và cơ chế triển khai — 2026-10-03

**Kết luận:** project có một câu hỏi thực nghiệm đáng làm, nhưng hiện chưa đủ bằng chứng
để gọi là phương pháp có novelty mạnh hoặc kết quả publication. Code opt-in được mở rộng;
không chạy test, dataset, model hay benchmark trong lượt này theo yêu cầu người dùng.
Ledger duy nhất vẫn là `realistic_project_creation_codex.md`; gate `IN_PROGRESS`.

## 1. Vấn đề gốc và giới hạn khi chuyển paper về laptop

SQL chạy thành công vẫn có thể sai population, grain, binding hoặc ranking. Vì thế cần tách
**phát hiện lỗi**, **đề xuất sửa** và **quyết định nhận bản sửa**. Một critic phán sai có thể
kéo generator từ query đúng sang query sai, đặc biệt khi generator và critic dùng cùng model.
[SQLCritic v4](https://arxiv.org/html/2503.07996v4) nghiên cứu critic được huấn luyện theo
clause; prompt critic trên model local hiện tại không tương đương trained critic đó.
Project dùng taxonomy/feedback để thiết kế trách nhiệm, không nhận gain của paper làm gain của mình.

Không cần giả định task càng khó thì nên thêm call. Với join grain hoặc population chưa bind,
thêm một lời phê bình có thể vẫn không cung cấp evidence đủ để chọn bản sửa. Ngược lại, một lỗi
ranking đơn giản có thể sửa AST mà không cần model phê bình hoặc sinh lại SQL.
Đây là **suy luận thiết kế của project**, chưa phải kết luận đã được thực nghiệm xác nhận.

## 2. Prior art giới hạn claim novelty

| Nghiên cứu | Ý tưởng đã có | Điều project không nên claim là mới |
|---|---|---|
| [SQLCritic v4](https://arxiv.org/html/2503.07996v4) | Critique lỗi SQL theo clause, trained critic và refinement | Clause critic hoặc structured feedback tự thân |
| [DAC](https://aclanthology.org/2025.findings-emnlp.22/) | Decomposition giúp localization/feedback để self-correct SQL | Feedback cụ thể hơn self-reflection chung |
| [EllieSQL](https://arxiv.org/html/2503.22402v1) | Router chọn pipeline theo độ khó, đánh giá chi phí token | Adaptive routing hoặc giảm calls tự thân |
| [CHESS](https://arxiv.org/html/2405.16755v2) | Retrieval, schema selection, candidate refinement/testing | Pipeline nhiều module + execution feedback |
| [Distilled test suites](https://arxiv.org/abs/2010.02840) | Đánh giá nghĩa bằng nhiều trạng thái database | Execution đúng trên một DB là semantic proof |

Danh sách này là đối chiếu các paper liên quan, không phải systematic review đủ để xác nhận
không có prior art khác. Clock cap, tmux, checkpoint và guard là đóng góp engineering/reproducibility,
không được tính riêng thành algorithmic novelty.

## 3. Research question cụ thể hơn

**Với cùng generator local, schema evidence và giới hạn requests, cấp compute theo khả năng
sửa có bằng chứng và hợp đồng AST có giảm correct→wrong và chi phí so với routing theo rủi ro,
trong khi giữ chất lượng trên schema chưa dùng để thiết kế rule, hay không?**

Hai câu hỏi phụ: (1) bỏ planner LLM có cải thiện first-pass/cost không; (2) sửa ranking bằng CPU
có thay thế được lượt repair LLM trong cùng phạm vi, và coverage thực tế có đủ để đáng dùng không?
Đừng gộp model specialization, topology, retrieval và correction thành một intervention rồi
quy toàn bộ gain cho critic. Chưa có SQL-specialist checkpoint mới được cài trong lần code này.

Hidden value là đo **ranh giới của hành động có thể bảo vệ bằng evidence**: bao nhiêu lỗi phát hiện
được nhưng chưa sửa được; bao nhiêu compute chỉ tạo critique không giúp chọn; bao nhiêu bản sửa
đúng bị admission từ chối. Kết quả âm vẫn có giá trị nếu cho thấy coverage quá nhỏ hoặc cost không
giảm end-to-end. Giảm call mà accuracy giảm đáng kể không tự thành thành công nghiên cứu.

## 4. Cơ chế đã viết trong source

Flag `TEXT2SQL_COMPUTE_POLICY=obligation` bật controller mới; mặc định vẫn `legacy`, P6 vẫn default.
`TEXT2SQL_DETERMINISTIC_REPAIR=true` bật CPU edit cho contract đủ điều kiện. Cả critic mode `repair`
và correction phải bật để có sửa. Trong source:

1. Sinh một draft; safety/identifier/SQLite validation vẫn độc lập với semantic checks.
2. Bind metric từ question và **toàn catalog**, không dùng draft chọn metric khi catalog mơ hồ.
   Binding hiện là lexical: case/underscore và simple English plural normalization. Chưa có
   synonym/tiếng Việt/ontology binding rộng; không tự suy diễn từ confidence của model.
3. Compile `RepairContract`: evidence IDs, question spans, contradiction codes, allowed AST
   fields, metric và một planned SQL. Phạm vi đầu tiên là explicit top-K, highest/lowest,
   một source, không aggregate/join/nested scope/window/offset/distinct, K≤200.
4. Nếu có contract: không gọi critic chỉ để nhắc lại lỗi đã kiểm; chọn CPU edit hoặc một repair
   LLM để làm ablation. Nếu không có contract: giữ semantic UNKNOWN; chỉ mẫu shadow cố định
   có thể gọi critic tham khảo. Operational errors đủ phân loại vẫn có một repair LLM riêng.
5. Revalidate; AST candidate phải khớp planned edit, contradiction giảm và không thêm code UNKNOWN.
   Projection, predicate, source, metric/order keys phụ không được tự đổi. Không admit thì giữ draft.
6. Trace v3 ghi origin, contract, actual requests, repair source và lựa chọn. Semantic status
   vẫn UNVERIFIED sau scoped repair: contract không chứng minh toàn bộ query đúng nghĩa.

Ví dụ: `top 1 highest scores`, catalog chỉ có một `score`, draft thiếu ORDER BY và LIMIT sai:
controller có thể thêm ORDER BY `scores.score DESC`, LIMIT 1 bằng CPU. Nếu draft order theo `id`,
hoặc `score` là alias của `-score`, checker không phán rằng đảo ASC→DESC đã giải lỗi metric.
Nếu nhiều bảng có `score`, binding giữ ambiguous; không dùng generated SQL làm evidence độc lập.

Đây là một **đóng góp phương pháp tiềm năng**, còn hẹp. Giữ untargeted AST chỉ bảo vệ không
thay phần đó; nó không chứng minh phần đó đã đúng. Cần mở rộng population/grain qua evidence
độc lập trước khi claim general semantic repair. Không thêm những rules đó bằng phỏng đoán.

## 5. Ablation và tiêu chí bác bỏ

| Variant | Tác động cần đo |
|---|---|
| P6 mới dưới cùng guard | Control topology; không gán score lịch sử cho source mới |
| A1 off | First-pass khi bỏ planner LLM |
| A1 shadow | Detection/FPR, localization, UNKNOWN, routing blind spots |
| A1 legacy repair | Controller rủi ro + critic + một repair |
| Obligation risk / risk CPU | Giữ risk routing, cùng contract/admission và LLM/CPU edit với treatments |
| Obligation LLM | Repairability routing + edit admission, không CPU synthesis |
| Obligation CPU | Cùng contract/controller, thay rank repair LLM bằng CPU |

Giữ model digest/template, seed, inputs/retrieval, deadline/context/output cap, residency,
manifest và resource limits giống nhau giữa các A1 variants. Actual calls gồm retries, không
chỉ đếm stage. Báo cả cap lẫn used compute; equal cap không có nghĩa các variants đã dùng equal compute.
Generic-feedback control đã có flag riêng; chạy bằng experiment paths mới.

`TEXT2SQL_REPAIRABILITY_ROUTING=false` tạo risk-routing control trên **cùng contract**; managed
variants `obligation-risk`/`obligation-risk-cpu` đã có. So risk vs repairability trong từng edit
backend trước, rồi LLM vs CPU tại cùng routing. Legacy vs obligation thay cả admission và
routing nên chỉ là bundle comparison, không đủ để quy gain cho routing riêng.

Đo first-pass/final EX, paired gain/loss, correct→wrong, contract coverage, pool oracle,
admission false rejection, critic precision/recall/FPR theo review độc lập, calls/tokens,
P50/P95, setup, wall time gồm hashing/checkpoint/cooldown và resource peaks. Case timeout/row cap
khi chấm candidate offline giữ unscored, không biến thành gold semantic error chắc chắn.

Source eval mới tách saved draft/pool khỏi selected output. Olist giữ phép so preview với gold;
Spider chấm normalized SQL đầy đủ nhưng giới hạn 10s/100.000 rows. Đây là hai metric khác nhau.
Spider v2 chỉ xét outer ORDER khi quyết định thứ tự kết quả; so lịch sử phải re-score cả hai
predictions bằng cùng evaluator nếu muốn paired claim. Oracle gồm CPU candidate nên phải báo origins.
Gold/candidate labels chỉ xuất hiện trong evaluation package sau inference; không vào runtime.

Freeze rules trước holdout schema; tạo fixtures đổi tên schema, ambiguous columns, negative intent,
alias/aggregate/nested cases. Fixtures hiện đã viết nhưng chưa chạy. Đừng gọi phần holdout đã dùng
phân tích thất bại lịch sử là fresh untouched test set. Cần tập schema mới cho claim transfer mạnh.
Chốt non-inferiority margin và regression tolerance trước benchmark; không chọn sau khi xem score.
Nếu coverage quá thấp, net gain≤0, loss tăng, hoặc chỉ call count giảm mà wall latency không giảm,
hạ claim hoặc dừng hướng này. Một top-K rule đơn độc chưa đủ cho claim tổng quát/paper mạnh.

## 6. Latency và trạng thái thực tế

Đã giảm topology A1 xuống một draft; obligation CPU không thêm generation request cho rank edit;
operational recovery có thể thêm một request; hard cap A1 vẫn tối đa 3 gồm retries. Setup và
runtime end-to-end đã được ghi riêng; wrapper ghi wall per batch có cooldown. Chưa có số đo mới.
Unloading giữa calls và 60s cooldown từng case là yêu cầu an toàn, có chi phí lớn. Worker một case
cũng phải khởi tạo runtime, hash DB/index và với Olist copy DB; chưa có cache tối ưu các chi phí này.
Manager pin Python interpreter và spawn worker trực tiếp thay vì lặp lại `uv run` từng batch;
đây là giảm launcher overhead trong source, chưa có số đo tốc độ thực tế.
Không nới residency/resource policy để làm số latency đẹp. Không claim đã tối ưu latency hoàn toàn.

Tmux manager có frozen plan, pause tại checkpoint boundary, cooldown state, process-group
stale detection và full-report validation trước `SUCCESS FINISH ALL`. Thoát client tmux giữ
workload; mất điện/SIGKILL chỉ bảo toàn checkpoint đã ghi và yêu cầu recovery pilot, không hứa
giữ case đang tính. Resource latch không bị chuyển thành pause và không bị resume tự xóa.

**Construction đã viết; chưa chạy make check hoặc kiểm chứng cơ chế/tmux/hardware.** Các commands
cho người dùng chạy cuối nằm trong [run guide](../a1_run_after_coding.md).
