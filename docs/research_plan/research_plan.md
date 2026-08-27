<!-- GENERATED FILE. Edit generate_research_plan.py, then regenerate. -->
# Kế hoạch nghiên cứu tăng accuracy — Agentic Text-to-SQL

> **Vai trò:** Data Scientist · **Trạng thái:** research plan, chưa triển khai experiment<br>
> **Survey cutoff:** 2026-08-22 · **Generated:** 2026-08-22<br>
> **North star:** tăng Spider generalization có kiểm chứng; giữ Olist semantic quality và safety.

## 1. Kết luận điều hành

Project đã hoàn tất Gate P6 về engineering, nhưng chưa thể gọi là “đúng với mọi câu user hỏi”.
Schema retrieval cơ bản đã mạnh: Spider holdout có table recall@20 `100,00%` và
qualified column recall@20 `99,65%`. Tuy vậy, 68/70 lỗi Spider là
`EXECUTION_MISMATCH`—SQL chạy được nhưng sai nghĩa. Ngoài benchmark, câu user thật còn có typo,
paraphrase, nhiều cách hiểu hoặc không thể trả lời từ database. Vì vậy thứ tự nghiên cứu đúng là:

1. khóa baseline của code hiện tại;
2. biến failures thành dữ liệu có nhãn nguyên nhân;
3. xây question contract để normalize, phát hiện ambiguity/unanswerable và hỏi làm rõ;
4. tăng semantic/value evidence rồi mới A/B model chuyên SQL và clause planning;
5. thêm verified examples, adaptive candidates và calibrated verifier;
6. chỉ cuối cùng mới dùng feedback đã review để LoRA/RL và external release.

**Target gần:** từ 65% lên **≥70%** trên locked Spider-200 (ít nhất +10 case), Olist không giảm dưới
95%, safety giữ 100%. **Target tiếp:** 75% trên fresh release set/full Spider sau khi freeze. Các gain
của paper là bằng chứng định hướng, **không phải cam kết** cho Qwen local/laptop này.

## 2. Baseline đã lưu và phạm vi claim

| Benchmark | Accuracy | Slice/guardrail | Latency |
| --- | ---: | --- | ---: |
| Spider-200 | **130/200 = 65,00%** | holdout 67/100; valid 199/200 | p50 58,51 s; p95 85,29 s |
| Olist-60 | **57/60 = 95,00%** | holdout 15/15; first-pass 51/60 | p50 61,92 s; p95 91,62 s |

- Benchmark revision: `1509faa786534f36d33df34d4d5c4a9ed5fc1c54`; gate completion: `0972e4715f2aa8a64652c3b27d10c80f178bc162`.
- Checkout được chụp khi lập plan: `46a9c95cffa101f3198b44a49589a68c7fba08c4`.
- Điểm 65%/95% **chỉ thuộc revision benchmark**, generator v4/corrector v3. Hardening v6/v5 hiện tại
  phải rerun trước khi nhận score mới.
- Full Spider-dev 1.034 chưa chạy; evaluator self-test 1.034/1.034 không phải model accuracy.
- Olist và Spider đo hai mục tiêu khác nhau, không lấy trung bình.

### Evidence fingerprint

| Artifact | Path | SHA-256 |
| --- | --- | --- |
| Master specification / ledger | [`realistic_project_creation_codex.md`](../../realistic_project_creation_codex.md) | `2d901b878ad4f2957c762a44338559ac7208b4e8ea38f6ab17f7bd3c7b661364` |
| P6 benchmark dossier | [`benchmark_full.md`](../../benchmark_full.md) | `584008aa93b0e80618edf8fbe648239e45d9d0363e17b8ac418caf3b3d7b3aa4` |
| P6 gate evidence | [`docs/evidence/p6_gate.md`](../../docs/evidence/p6_gate.md) | `50de5ec272a1c34c67a12baf4ae23d787625f16e7e321bbc7c5a5e6dfa6d5371` |
| P3.1 retrieval evidence | [`docs/evidence/p3_1_gate.md`](../../docs/evidence/p3_1_gate.md) | `e5f839d6e734af22038feb86270646a9be95f8e387f7bc0bb6a0cea80bbbdc13` |
| P4 correction evidence | [`docs/evidence/p4_gate.md`](../../docs/evidence/p4_gate.md) | `100bd6b812a2994aa801bba160f14fa7f190191daab9f447fd10fb326950e3e2` |
| Post-P6 query recovery | [`docs/evidence/p6_3_query_recovery.md`](../../docs/evidence/p6_3_query_recovery.md) | `875e54ee9eab86fb3fe949749ec999947230d181b58fe92686cf036212bc3ab4` |
| Project failure memory | [`all_failures_in_project.md`](../../all_failures_in_project.md) | `4b1e22e529cef3712840ff7c6342ae48e731372aef2c120666a958784fa37ad2` |
| Error analysis | [`docs/error_analysis.md`](../../docs/error_analysis.md) | `3511b4092c317a74c0e3584a99f6b69ff583e7253852ef856f963b9754c9f5d6` |

Fingerprint này bảo toàn *evidence aggregate*, không copy raw dataset, database, trace, prediction
hay gold data vào Git.

## 2.1 Blueprint path và target architecture

| Gate | Track | Thời gian | Mục tiêu | Deliverable | Decision gate |
| --- | --- | --- | --- | --- | --- |
| B0 | shared | Tuần 0–1 | Đóng băng tài sản hiện tại | Tag/manifest, Spider-200, Olist-60, TS/EX, latency, evidence fingerprint. | Config/hashes đầy đủ; 100% workflow; không claim score v6 trước rerun. |
| B1 | shared | Tuần 1–2 | Failure intelligence | Taxonomy, AST/result diff, Pareto causes, owner module, oracle recoverability. | 100% labeled; review agreement ≥90%; top-3 causes bao phủ ≥60%. |
| U1 | core | Tuần 2–4 | Question reliability contract | Interpretations, assumptions, answerability reason, clarification options, challenge set. | Ambiguity recall ≥85%; false-refusal ≤3%; user không cần biết SQL jargon. |
| D1 | data | Tuần 3–4 | Semantic context factory | Safe profile, value index, descriptions, aliases, lineage và quality dashboard. | Value recall tăng; overall +2 điểm hoặc filter slice +3; zero leakage. |
| C1 | core | Tuần 3–5 | Specialist model + clause reasoning | Specialist 7B/14B comparison, plan rubric, difficulty router, clause metrics. | Spider +5 điểm hoặc latency -25% ở cùng accuracy; Olist giảm ≤1 case. |
| D2 | data | Tuần 5–7 | Verified example memory | Example store, AST skeleton index, dedup, DB-disjoint split, provenance. | Overall +3 điểm hoặc rare-skeleton +5; leakage audit 100% pass. |
| C2 | core | Tuần 7–9 | Adaptive candidate engine | pass@3 oracle, diversity policy, result consensus, selector, semantic verifier. | Final +3 điểm; selector thu ≥50% oracle gap; p95/calls không quá 2×. |
| D3 | data | Tuần 9–12+ | Clean curriculum & hard negatives | Data card, synthetic SQL→question, hard negatives, LoRA-7B pilot. | Data accept ≥95%; external DB-disjoint +3; không catastrophic forgetting. |
| B2 | shared | Sau freeze | Champion integration & external proof | Ablation ladder, fresh manifest/full Spider, Dr.Spider, Olist fresh holdout. | Spider ≥70% rồi ≥75%; Olist ≥95%; safety 100%; gain cùng dấu external. |

Target architecture có bốn planes:

1. **Question Reliability:** normalize → interpretations → answerability → clarification/assumptions.
2. **Core Accuracy Engine:** complexity router → clause plan → semantic context assembler
   (schema + values + descriptions + examples) → adaptive candidate engine → semantic verifier/
   selector → safe execute/repair/abstain.
3. **LLM Data Factory:** metadata/value profiling → failure intelligence → execute/review/dedup/
   leakage gates → verified example memory → clean curriculum → optional LoRA.
4. **Evaluation & Product Trust:** frozen manifests, gold firewall, paired A/B metrics, robustness,
   calibrated risk–coverage, clarification success, answer comprehension, lineage và
   fresh release set. Gold SQL/result không bao giờ đi ngược vào runtime.

## 3. Chẩn đoán ưu tiên

| Tín hiệu hiện tại | Kết luận DS | Quyết định |
| --- | --- | --- |
| Schema macro holdout@20 `99,75%` | Retrieval cơ bản gần bão hòa | Không tiếp tục vặn BM25/FAISS như ưu tiên số 1 |
| Join-edge recall `86,36%` | Join evidence còn khoảng trống | Phân tích failure join trước khi thay retriever |
| 68/70 lỗi là execution mismatch | Semantic reasoning/selection là bottleneck | R1, R4, R6, R7 đứng trước refactor |
| Medium 50,94%; extra-hard 36,36% | Complexity gap lớn | Adaptive path chỉ cho case khó |
| Olist 95%; holdout 100% lịch sử | Domain contracts có hiệu quả | Dùng Olist làm non-regression guardrail |
| P95 85–92 giây | Tốc độ chưa đạt target | Accuracy ưu tiên, nhưng reject giải pháp >2× latency nếu gain nhỏ |

### 3.1 Contract dành cho user không biết code

Hệ thống không nên có duy nhất hai trạng thái “ra SQL” hoặc “lỗi”. Mỗi request phải kết thúc bằng
một trong bốn outcome có ích:

| Outcome | Khi nào dùng | UI phải nói gì | Không được làm |
| --- | --- | --- | --- |
| `ANSWER` | Một interpretation chiếm ưu thế, evidence đủ, SQL và result qua validation | Câu trả lời trước; metric/time grain/filter; assumption; confidence đã calibrate; link SQL/trace nâng cao | Không dùng self-confidence như accuracy |
| `CLARIFY` | Có từ hai interpretation hợp lý hoặc thiếu một business assumption quyết định | Một câu hỏi ngắn + 2–3 lựa chọn bằng ngôn ngữ nghiệp vụ | Không hỏi table/column name |
| `CANNOT_ANSWER` | Database thiếu fact, thời gian, metric hoặc relationship bắt buộc | Nói chính xác thiếu dữ liệu gì và gợi ý câu có thể trả lời | Không bịa proxy metric |
| `SAFE_REJECT` | Write/destructive/out-of-scope hoặc safety policy | Lý do an toàn, phạm vi read-only và lựa chọn thay thế | Không nới policy để tăng completion |

Answer card cho non-coder dùng progressive disclosure: **Kết quả → cách hiểu → phạm vi dữ liệu →
độ tin cậy/validation → SQL và trace ở mục Advanced**. Với bảng lớn, hiển thị summary và đơn vị
trước raw rows. Feedback không chỉ là 👍/👎: user chọn “đúng ý”, “sai metric”, “sai filter”, “thiếu
dữ liệu” hoặc chọn giữa hai output/assumption dễ hiểu.

### 3.2 Challenge matrix cho câu hỏi khó đoán

| Family | Ví dụ cần sinh/test | Expected behavior |
| --- | --- | --- |
| Paraphrase | đồng nghĩa, đảo trật tự, văn nói, thêm “giải thích” | Cùng interpretation và result fingerprint |
| Noisy input | typo, thiếu dấu, VI/EN mix, viết tắt | Normalize có trace; không đổi metric |
| Lexical ambiguity | “khách hàng”, “doanh thu”, “gần đây”, “tốt nhất” | Dùng glossary hoặc hỏi làm rõ |
| Structural ambiguity | hai join paths, top theo count hay value | Đưa lựa chọn nghiệp vụ, không đoán im lặng |
| Unanswerable | return/refund khi DB không có facts | `CANNOT_ANSWER` + missing-evidence reason |
| Adversarial schema | cột đồng tên, decoy view, identifier lạ | Exact ownership/FK component; không invented key |
| Long-tail SQL | nested, set operation, ratio, cohort | Enhanced plan/candidate path có budget |
| Result ambiguity | empty, null, tie, unordered rows | Nêu assumption; deterministic presentation |

### 3.3 Hai scorecard, tuyệt đối không trộn

**Research scorecard** giữ EX/TS theo từng benchmark, paired delta và robustness slices. **Product
scorecard** đo task outcome thực tế:

- `answer risk = wrong ANSWER / all ANSWER`;
- `coverage = ANSWER / all requests`;
- `clarification success = clarified requests solved / clarification requests`;
- `safe resolution = correct ANSWER + useful CLARIFY + correct CANNOT_ANSWER + SAFE_REJECT` chia
  toàn bộ request;
- ECE/Brier chỉ được báo khi confidence đã calibrate bằng held-out labels;
- time-to-first-status, time-to-answer, số clarification turns và user comprehension.

Không tối ưu “safe resolution” đơn độc vì hệ thống có thể game bằng cách abstain mọi câu. Báo
đồng thời **risk–coverage curve**, answerable false-refusal và accuracy trên answered requests.

## 4. Sheet roadmap experiments

| ID | P | Workstream | Experiment | Expected | Effort | Gate promote |
| --- | --- | --- | --- | --- | --- | --- |
| R0 | P0 | Đo lường | Khóa baseline hiện tại và rerun revision mới | Đo lường, không hứa gain | 2–3 ngày máy | 200/200 hoàn tất, config/hash đầy đủ, safety 100%; đây là mốc B0, chưa đòi tăng điểm. |
| R1 | P0 | Dữ liệu | Biến 70 lỗi Spider thành failure dataset có nhãn nguyên nhân | Giảm rủi ro nghiên cứu sai hướng | 3–5 ngày | Mọi lỗi có evidence và một owner module; chọn R2–R6 theo dữ liệu, không theo cảm tính. |
| R2 | P0 | Công nghệ lõi | Question contract: normalize, answerability và clarification | Tăng reliability/user success; benchmark gốc có thể trung tính | 5–8 ngày | Ambiguity recall ≥85%, answerable false-refusal ≤3%, confident-wrong giảm ≥30% trên challenge set. |
| R3 | P1 | Dữ liệu | Semantic catalog + bounded value/entity grounding | +1 đến +4 điểm | 5–8 ngày | ≥+3 điểm trên slice value/filter và ≥+2 điểm overall; không leakage, không vượt budget. |
| R4 | P1 | Công nghệ lõi | Plan theo clause và query skeleton cho case medium/extra-hard | +2 đến +5 điểm | 5–7 ngày | ≥+5 điểm medium+hard aggregate, ≥+2 overall, easy regression ≤1 case. |
| R5 | P1 | Dữ liệu | Verified few-shot retrieval theo structure, chống leakage | +2 đến +5 điểm | 6–9 ngày | ≥+3 điểm overall hoặc ≥+5 điểm rare-skeleton; không exact/paraphrase leakage. |
| R6 | P1 | Công nghệ lõi | Adaptive best-of-3 với logic diversity và selector | +3 đến +7 điểm, compute cao | 7–10 ngày | Oracle pass@3 ≥ baseline +8 điểm và selector thu ≥50% oracle gap; final +3 điểm overall. |
| R7 | P2 | Công nghệ lõi | Semantic verifier, calibrated repair và safe abstention | +2 đến +5 điểm | 8–12 ngày | Precision ≥90%, recall ≥35%, net +2 điểm, correct→wrong ≤1%. |
| R8 | P2 | Dữ liệu | Verified data flywheel + hard negatives; LoRA chỉ sau audit | +3 đến +10 điểm, rủi ro/cost cao | 3–6 tuần | Data acceptance ≥95%; external DB-disjoint +3 điểm; không giảm Olist/robustness >1 điểm. |
| R9 | P2 | Đánh giá | Robustness + no-code user release ladder | Release proof, không trực tiếp hứa gain | 1–3 tuần máy | Gain cùng dấu external; no-code task success ≥85%; safety 100%; không che abstention. |
| R10 | P1 | Công nghệ lõi | A/B model chuyên Text-to-SQL: 7B trước 14B | A/B đo được; không dùng paper score làm dự báo local | 3–6 ngày | Spider +5 điểm hoặc accuracy ngang nhưng p95 giảm ≥25%; Olist mất tối đa 1 case. |

> Expected gain là **prior để xếp hàng**, không cộng dồn và không phải kết quả. Mỗi hàng chỉ được
> chuyển `PROPOSED → PILOT → EVALUATED → PROMOTED/REJECTED` khi có report tái lập.

## 5. Experiment cards

### R0 — Khóa baseline hiện tại và rerun revision mới

- **Vì sao bây giờ:** Điểm 65%/95% thuộc generator v4/corrector v3 tại commit 1509faa; code hiện tại đã là generator v6/corrector v5 nên chưa có accuracy hợp lệ.
- **Project đã có:** P6 đã có manifest/hash/seed/model digest, 200/200 typed terminal và gold separation.
- **Thế giới đã làm:** Test-suite accuracy cho thấy single denotation có thể đánh giá sai semantics.
- **Giả thuyết:** Baseline v6 khóa lại sẽ phân biệt gain thật với regression do hardening/model variance.
- **Thiết kế thử nghiệm:** Tạo experiment ID mới; rerun Spider-200 và Olist-60 không đổi dữ liệu; thêm TS/mutation score; lưu aggregate + per-case delta ngoài Git theo policy.
- **Metric chính:** Spider EX/TS; Olist result accuracy; paired per-case delta; p50/p95.
- **Promote:** 200/200 hoàn tất, config/hash đầy đủ, safety 100%; đây là mốc B0, chưa đòi tăng điểm.
- **Kill/stop:** Dừng nếu commit/model/index/prompt không khóa hoặc evaluator self-test không pass.
- **Ước lượng:** Đo lường, không hứa gain; effort `2–3 ngày máy`.

### R1 — Biến 70 lỗi Spider thành failure dataset có nhãn nguyên nhân

- **Vì sao bây giờ:** 68/70 lỗi là EXECUTION_MISMATCH; taxonomy runtime hiện không nói được sai join, aggregate, filter value, nesting, set operation hay output grain.
- **Project đã có:** Đã có difficulty/database slices; retrieval recall gần bão hòa; report giữ đủ denominator.
- **Thế giới đã làm:** Dr.Spider dùng 17 perturbations; SQL-of-Thought dùng taxonomy logic để correction có mục tiêu.
- **Giả thuyết:** Top 3 semantic causes sẽ bao phủ ít nhất 60% lỗi và quyết định đúng experiment kế tiếp.
- **Thiết kế thử nghiệm:** Offline-only: AST diff predicted/gold, result-shape diff, schema/value evidence, nhãn primary + secondary cause; review tay sample 20%; tạo dashboard error × complexity × DB.
- **Metric chính:** Coverage nhãn 100%; agreement review ≥90%; top-cluster coverage; oracle recoverability.
- **Promote:** Mọi lỗi có evidence và một owner module; chọn R2–R6 theo dữ liệu, không theo cảm tính.
- **Kill/stop:** Không dùng gold label trong runtime/prompt; artifact chi tiết tiếp tục gitignored.
- **Ước lượng:** Giảm rủi ro nghiên cứu sai hướng; effort `3–5 ngày`.

### R2 — Question contract: normalize, answerability và clarification

- **Vì sao bây giờ:** User không-code sẽ hỏi thiếu chuẩn, nhiều nghĩa hoặc ngoài dữ liệu; đoán một SQL tạo answer sai nhưng có vẻ hợp lý.
- **Project đã có:** Router đã có QUERY/CLARIFY/UNSUPPORTED/WRITE và hỗ trợ VI/EN, nhưng chưa có ambiguity confidence hay multi-turn contract.
- **Thế giới đã làm:** AmbiQT, PRACTIQ, CoSQL và Know What I Don't Know đều yêu cầu biểu diễn nhiều interpretation hoặc hỏi làm rõ.
- **Giả thuyết:** Tách interpretation trước SQL sẽ giảm confident-wrong và tăng task success cho câu paraphrase/ambiguous.
- **Thiết kế thử nghiệm:** Canonicalize typo/VI-EN mix; tạo 1–3 interpretation có assumptions; classifier answerable/ambiguous/unanswerable; sinh một câu hỏi làm rõ với options không chứa jargon SQL.
- **Metric chính:** Routing macro-F1; ambiguity recall; clarification success; answer coverage; selective risk; paraphrase consistency.
- **Promote:** Ambiguity recall ≥85%, answerable false-refusal ≤3%, confident-wrong giảm ≥30% trên challenge set.
- **Kill/stop:** Clarify quá 15% câu answerable hoặc bắt user biết tên table/column.
- **Ước lượng:** Tăng reliability/user success; benchmark gốc có thể trung tính; effort `5–8 ngày`.

### R3 — Semantic catalog + bounded value/entity grounding

- **Vì sao bây giờ:** Schema recall cao không đồng nghĩa hiểu business metric, enum, alias, date format, unit hay cell value—đặc biệt ở filter, identity và population.
- **Project đã có:** Safe Profiler L2-M2 và verified example store vẫn NOT_STARTED; catalog đã có type/FK/hash.
- **Thế giới đã làm:** DART-SQL, PET-SQL, CHESS và BIRD đều cho thấy database content là tín hiệu quan trọng.
- **Giả thuyết:** Metric contracts cùng top/exact/rare-value retrieval đúng column giảm lỗi filter, identity, population và grain.
- **Thiết kế thử nghiệm:** Profile allowlisted columns; metric/dimension registry; normalize aliases/units/time grain; value index có provenance và caps; ablate từng evidence type.
- **Metric chính:** Value recall@k; metric-link F1; filter/grain slice EX; context tokens; privacy fixtures.
- **Promote:** ≥+3 điểm trên slice value/filter và ≥+2 điểm overall; không leakage, không vượt budget.
- **Kill/stop:** Value context làm overall giảm >1 điểm, context tăng >30% mà không gain, hoặc lộ value nhạy cảm.
- **Ước lượng:** +1 đến +4 điểm; effort `5–8 ngày`.

### R4 — Plan theo clause và query skeleton cho case medium/extra-hard

- **Vì sao bây giờ:** Medium chỉ 50,94%, extra-hard 36,36%; current plan chưa được đo bằng plan-quality oracle.
- **Project đã có:** Planner v2 typed và generator v6 đã có scalar/ranking/owner/scope constraints.
- **Thế giới đã làm:** CoT chuyên Text-to-SQL +5,2 điểm; DIN-SQL và SQL-of-Thought nhấn mạnh decomposition/plan.
- **Giả thuyết:** Plan ngắn, kiểm được theo SELECT/FROM/WHERE/GROUP/HAVING/ORDER/set sẽ giảm lỗi cấu trúc.
- **Thiết kế thử nghiệm:** Tạo plan rubric từ R1; thêm SQL skeleton không chứa identifier gold; validate clause consistency; chỉ kích hoạt enhanced plan cho medium/hard classifier.
- **Metric chính:** Clause F1 offline; EX theo difficulty; plan→SQL consistency; output tokens; latency.
- **Promote:** ≥+5 điểm medium+hard aggregate, ≥+2 overall, easy regression ≤1 case.
- **Kill/stop:** Reasoning dài tăng latency >25% hoặc tạo error propagation mà EX không tăng.
- **Ước lượng:** +2 đến +5 điểm; effort `5–7 ngày`.

### R5 — Verified few-shot retrieval theo structure, chống leakage

- **Vì sao bây giờ:** L6-M2 chưa làm; generator hiện không tận dụng kho ví dụ đã execute và review.
- **Project đã có:** Có 60 Olist reviewed cases, Spider train và contract provenance; chưa có example store.
- **Thế giới đã làm:** DAIL-SQL dùng skeleton similarity; PET-SQL dùng question-SQL retrieval; Solid-SQL dùng two-round ICL.
- **Giả thuyết:** 1–3 ví dụ cùng skeleton giúp small/local model ánh xạ intent→SQL tốt hơn prompt zero-shot.
- **Thiết kế thử nghiệm:** Chỉ ingest train/dev được phép; canonical AST skeleton; dedup question/schema/SQL; split theo DB và template; retrieve question + skeleton proxy; ablate 0/1/3 examples và order.
- **Metric chính:** EX/TS; retrieval relevance; leakage audit 100%; prompt tokens; gain theo skeleton rarity.
- **Promote:** ≥+3 điểm overall hoặc ≥+5 điểm rare-skeleton; không exact/paraphrase leakage.
- **Kill/stop:** Gain mất trên database-disjoint set hoặc prompt >4096/token budget.
- **Ước lượng:** +2 đến +5 điểm; effort `6–9 ngày`.

### R6 — Adaptive best-of-3 với logic diversity và selector

- **Vì sao bây giờ:** Một candidate deterministic bỏ lỡ pass@k; các biến thể token gần nhau không tạo semantic diversity hữu ích.
- **Project đã có:** Candidate budgets, policy, read-only executor và trace đã sẵn; laptop chỉ cho parallelism 1.
- **Thế giới đã làm:** AmbiQT LogicalBeam đa dạng logic; PET-SQL dùng cross-consistency; CHASE-SQL dùng multi-path reasoning và candidate selection.
- **Giả thuyết:** Sinh 3 candidate đa dạng chỉ ở case khó rồi chọn gold-blind sẽ chuyển pass@3 thành EX gain.
- **Thiết kế thử nghiệm:** Đo pass@3 oracle trước; diversify theo interpretation/plan chứ không chỉ seed; group result fingerprints; rank AST/evidence/invariants; chạy tuần tự chỉ cho hard/ambiguous cases.
- **Metric chính:** pass@1/pass@3; selector accuracy; final EX; candidate diversity; calls/latency/energy.
- **Promote:** Oracle pass@3 ≥ baseline +8 điểm và selector thu ≥50% oracle gap; final +3 điểm overall.
- **Kill/stop:** Pass@3 gap <5 điểm hoặc p95/calls >2× mà gain <3 điểm.
- **Ước lượng:** +3 đến +7 điểm, compute cao; effort `7–10 ngày`.

### R7 — Semantic verifier, calibrated repair và safe abstention

- **Vì sao bây giờ:** 68 execution mismatches không phát sinh runtime error nên current corrector phần lớn không được gọi.
- **Project đã có:** Đã có validator intent/shape/Olist invariants và bounded correction; recovery Olist P6 là 6/6.
- **Thế giới đã làm:** CHESS dùng natural-language unit tests; DART-SQL dùng execution-guided refinement.
- **Giả thuyết:** Verifier theo cluster R1 có thể giảm confident-wrong nếu threshold ANSWER/REPAIR/CLARIFY/ABSTAIN được calibrate trên held-out data.
- **Thiết kế thử nghiệm:** Mutation checks; NL↔SQL intent reconstruction; result invariants; verifier ensemble; calibrate decision thresholds, không dùng raw model self-confidence như probability.
- **Metric chính:** Detection AUROC/AUPRC; ECE/Brier; selective risk@coverage; repair recovery; correct→wrong; net EX.
- **Promote:** Precision ≥90%, recall ≥35%, net +2 điểm, correct→wrong ≤1%.
- **Kill/stop:** False-positive >5%, gold-derived signal lọt runtime, hoặc correction regression >gain.
- **Ước lượng:** +2 đến +5 điểm; effort `8–12 ngày`.

### R8 — Verified data flywheel + hard negatives; LoRA chỉ sau audit

- **Vì sao bây giờ:** Fine-tune sớm trên noisy/leaky data có thể làm benchmark đẹp nhưng generalization kém.
- **Project đã có:** Repo có run/feedback lineage, synthetic fixture và reviewed Olist; chưa có training corpus/versioned data card.
- **Thế giới đã làm:** OmniSQL cho thấy synthetic scale; ReViSQL nhấn mạnh verified data; APEL cho phép non-programmers chọn output phân biệt thay vì đọc SQL.
- **Giả thuyết:** Dữ liệu sạch, diverse, DB-disjoint và có error pairs giúp 7B/14B tăng semantic reasoning.
- **Thiết kế thử nghiệm:** Capture question/clarification/outcome; APEL-style output/assumption choice; expert review queue; execute/dedup/leakage gates; LoRA 7B pilot chỉ sau data card.
- **Metric chính:** Validity, dedup rate, coverage, reviewer acceptance; EX/TS external; robustness; forgetting.
- **Promote:** Data acceptance ≥95%; external DB-disjoint +3 điểm; không giảm Olist/robustness >1 điểm.
- **Kill/stop:** Không đủ license/provenance, contamination audit fail, hoặc chỉ tăng train-like Spider slice.
- **Ước lượng:** +3 đến +10 điểm, rủi ro/cost cao; effort `3–6 tuần`.

### R9 — Robustness + no-code user release ladder

- **Vì sao bây giờ:** 65% Spider chưa đo typo/paraphrase/ambiguity/unanswerable, task completion hoặc việc người không-code có hiểu answer/assumptions hay không.
- **Project đã có:** Gold-aware evaluator tách runtime; user đã lưu paper Dr.Spider; BIRD là optional roadmap.
- **Thế giới đã làm:** Dr.Spider/Solid-SQL đo perturbation; PRACTIQ/CoSQL đo clarification; Spider 2.0 mở rộng tới enterprise workflows.
- **Giả thuyết:** Một cải tiến thật phải giữ gain khi đổi cách diễn đạt và domain, không chỉ khớp Spider.
- **Thiết kế thử nghiệm:** Locked Dr.Spider-lite + PRACTIQ-like local set + fresh bilingual Olist; test 5–8 no-code users; Spider 2.0-lite chỉ sau core freeze.
- **Metric chính:** EX/TS; perturbation consistency; task success; clarification turns; answer comprehension; time-to-insight.
- **Promote:** Gain cùng dấu external; no-code task success ≥85%; safety 100%; không che abstention.
- **Kill/stop:** Không trộn dataset/metric thành một score; dừng nếu disk/compute vượt laptop budget.
- **Ước lượng:** Release proof, không trực tiếp hứa gain; effort `1–3 tuần máy`.

### R10 — A/B model chuyên Text-to-SQL: 7B trước 14B

- **Vì sao bây giờ:** Qwen3-14B là model tổng quát; specialist có thể tăng first-pass hoặc giảm latency.
- **Project đã có:** Provider typed, digest pin, laptop governor và deterministic prompt contracts đã có.
- **Thế giới đã làm:** OmniSQL công bố model 7B/14B/32B từ SynSQL-2.5M; paper score không chuyển thẳng vì model đã train với Spider/BIRD.
- **Giả thuyết:** Specialist 7B có thể nằm trên Pareto frontier tốt hơn generalist 14B ở cùng evidence.
- **Thiết kế thử nghiệm:** Audit license/runtime; pilot 20; greedy one-candidate cùng context; 14B chỉ khi 7B có signal; chạy external robustness để kiểm train familiarity.
- **Metric chính:** Paired EX/TS; first-pass; Dr.Spider slice; Olist; latency/W/RAM/VRAM.
- **Promote:** Spider +5 điểm hoặc accuracy ngang nhưng p95 giảm ≥25%; Olist mất tối đa 1 case.
- **Kill/stop:** Không fit guarded profile, license không hợp hoặc gain chỉ tồn tại trên familiar set.
- **Ước lượng:** A/B đo được; không dùng paper score làm dự báo local; effort `3–6 ngày`.


## 6. Data Science workstream

### 6.1 Kho dữ liệu nên có

| Dataset/artifact | Vai trò | Trạng thái hiện tại | Hành động |
| --- | --- | --- | --- |
| Olist-60 | Application + bilingual semantic guardrail | Reviewed 30/15/15; historical 95% | Giữ locked; tạo fresh cases cho release sau tuning |
| Spider regression-100 | Development/tuning | Đã nhìn kết quả | Cho phép failure analysis và prompt tuning |
| Spider holdout-100 cũ | Historical validation | Đã mở và phân tích | Không gọi là untouched nữa |
| Spider dev còn lại | Fresh validation/release pool | Chưa dùng trong P6-200 | Khóa manifest mới trước khi experiment |
| Failure dataset | Supervision/diagnostic | Chưa có semantic labels | R1 tạo offline, provenance tới run/case |
| User-query challenge set | Typo/paraphrase/ambiguity/unanswerable VI/EN | Chưa có locked set | R2 tạo từ templates + reviewed real feedback, không chứa PII |
| Verified example store | ICL | `NOT_STARTED` | R5, chỉ dữ liệu cho phép và chống leakage |
| Value/description index | Grounding | Safe Profiler `NOT_STARTED` | R3, bounded + allowlisted |
| Synthetic/hard-negative corpus | SFT/LoRA | Chưa có | R8 sau audit license/quality |
| Feedback review queue | Product learning | Có rating/category store, chưa thành verified data | APEL-style outcome choice → expert review → dataset version |

### 6.2 Quality pipeline bắt buộc

| Stage | Contract |
| --- | --- |
| 1. Inventory | Nguồn, license, hash, dialect, ngôn ngữ, domain, split, reviewer. |
| 2. Normalize | Unicode/date/literal policy; SQLGlot parse; canonical AST và result shape. |
| 3. Execute | Read-only run, timeout/cap; loại query lỗi; lưu result hash ngoài Git. |
| 4. Verify | Question↔SQL semantic review; grain/join/filter/aggregate; reviewer confidence. |
| 5. Deduplicate | Exact text, paraphrase embedding, AST skeleton, result equivalence, template family. |
| 6. Split | Database-disjoint trước; sau đó template/semantic family; khóa tuning/validation/release. |
| 7. Package | Data card, provenance, version, quality metrics; raw/generated corpus gitignored. |
| 8. Learn | Feedback → outcome/assumption choice → expert review; không train trực tiếp từ thumbs. |
| 9. Monitor | Slice coverage, label drift, contamination scan và failure-to-training lineage. |

### 6.3 Quality metrics

- **Validity:** parse rate, execute rate, timeout rate, result non-degeneracy.
- **Semantic quality:** reviewer accept rate, clause accuracy, grain/join/filter correctness.
- **Diversity:** domain/schema/template/SQL-operator/language distributions; long-tail coverage.
- **Leakage:** exact hash, normalized question, AST skeleton, result hash và embedding near-duplicate.
- **Label uncertainty:** reviewer confidence, disagreement, ambiguous/multi-answer flag.
- **Lineage:** source → transform → reviewer → dataset version → experiment ID.
- **Product coverage:** answerability class, language/noise family, clarification outcome và user role.

## 7. Protocol đánh giá và ra quyết định

### 7.1 Dataset discipline

1. `development`: regression-100 + labeled failures; được nhìn và tune.
2. `historical validation`: P6 holdout-100; dùng so regression nhưng không còn untouched.
3. `fresh validation`: manifest mới từ phần Spider chưa dùng; chỉ mở khi experiment freeze.
4. `release`: full Spider-1.034 hoặc manifest external cuối; không chạy lặp để tune.
5. Olist giữ riêng; thêm fresh bilingual holdout sau mọi thay đổi data/prompt lớn.
6. `user-challenge`: typo/paraphrase/ambiguity/unanswerable giữ riêng; không chấm mọi clarification
   là failure và cũng không coi mọi abstention là success.

### 7.2 Một experiment hợp lệ phải báo

- config/hash/model digest/prompt/index/seed và hardware profile;
- accuracy `n/N`, delta điểm tuyệt đối, recovered/lost case—not chỉ phần trăm;
- paired transition table: wrong→right, right→wrong, McNemar exact và bootstrap 95% CI;
- score theo difficulty/database/error cluster/language;
- first-pass, correction recovery/regression, calls, tokens, p50/p95 và energy guard;
- pass@k **tách** selector accuracy và final accuracy;
- risk–coverage, false-refusal, clarification success và calibration trên held-out labels;
- paired paraphrase consistency: câu gốc đúng nhưng biến thể sai phải được tính là regression;
- failure list giữ nguyên denominator; không dùng gold để trigger runtime correction.

### 7.3 Promotion policy

- **Pilot 20:** plumbing + safety, không claim accuracy.
- **Dev 100:** promote signal khi ≥+3 correct, không safety regression; lặp 3 seed nếu sampling.
- **Locked 200:** research target khi ≥+10 correct (+5 điểm), Olist ≥95%, safety 100%.
- **Fresh set:** gain cùng dấu và CI/paired transitions hợp lý; nếu không, ghi `REJECTED/INCONCLUSIVE`.
- **User challenge:** confident-wrong giảm ≥30%, ambiguity recall ≥85%, answerable false-refusal ≤3%.
- **No-code pilot:** task success ≥85%; user hiểu metric/filter/time grain mà không cần mở SQL.
- Chỉ thay default khi hiệu quả nằm trên Pareto frontier accuracy–latency–resource.

## 8. Lịch 14+ tuần theo gates

| Gate | Thời gian | Experiment | Deliverable |
| --- | --- | --- | --- |
| Gate A | Tuần 1 | R0 | Khóa B0 cho code hiện tại; snapshot provenance và evaluator. |
| Gate B | Tuần 2 | R1 | Failure dataset 70 case; Pareto nguyên nhân và oracle study. |
| Gate C | Tuần 3–4 | R2 | Answerability/ambiguity challenge set và clarification contract. |
| Gate D | Tuần 4–6 | R3 hoặc R4 | Chọn đúng top failure cluster: value/metric hoặc structure. |
| Gate E | Tuần 6 | R10 | A/B specialist 7B; chỉ thử 14B nếu pilot có signal. |
| Gate F | Tuần 7 | R5 | Verified examples + leakage audit. |
| Gate G | Tuần 8–9 | R6 | Adaptive pass@3 và selector; đo Pareto accuracy/latency. |
| Gate H | Tuần 10–11 | R7 | Verifier calibrated; ANSWER/REPAIR/CLARIFY/ABSTAIN. |
| Gate I | Tuần 12–14+ | R8/R9 | Chỉ train sau data audit; robustness, no-code UX và fresh release. |

Thứ tự Gate D có điều kiện: nếu R1 cho thấy filter/value là cluster lớn nhất thì R3 trước; nếu
aggregate/nested/set operation lớn nhất thì R4 trước. Không chạy song song nhiều thay đổi vào cùng
baseline vì sẽ mất khả năng attribution.

## 9. Mẫu hàng theo dõi mentor

| Field | Nội dung phải điền |
| --- | --- |
| Experiment ID / owner / status | Ví dụ `R4-E02`, DS, `PILOT` |
| Vấn đề và evidence | Failure cluster, số case, report/hash |
| Paper/idea tham chiếu | Link + reported metric + khác biệt model/data/compute |
| Hypothesis | Một câu có hướng và effect-size tối thiểu |
| Independent variable | Chính xác một thay đổi |
| Baseline/control | Experiment ID bất biến |
| Dataset/split | Dev/validation/release; contamination status |
| Primary metric | EX hoặc TS, n/N và delta pp |
| Guardrails | Olist, safety, latency, calls, resources |
| Result | Paired delta + CI + slices + failures |
| Decision | Promote / iterate / reject + lý do |
| Next action | Một experiment kế tiếp, không phải danh sách mở |

## 10. Survey thế giới và khả năng chuyển giao

| Nguồn chính | Kết quả được báo cáo | Áp dụng có chọn lọc |
| --- | --- | --- |
| [Spider](https://aclanthology.org/D18-1425/) | 10.181 câu hỏi, 200 CSDL, split cross-domain theo database. | Giữ làm benchmark generalization chính, nhưng không gọi subset-200 là leaderboard. |
| [Test-suite accuracy](https://aclanthology.org/2020.emnlp-main.29/) | Single-database/ESM có false negative trung bình 2,5%, tệ nhất 8,1%. | Bổ sung TS hoặc mutation tests trước khi tối ưu theo score. |
| [Cross-domain benchmark audit](https://aclanthology.org/2023.emnlp-main.99/) | Underspecification, assumptions và nhiều SQL tương đương có thể làm metric chuẩn đánh giá sai; manual re-evaluation còn đổi thứ hạng model. | Gắn nhãn ambiguity/uncertainty và review paired regressions; không tối ưu mù theo một gold SQL. |
| [AmbiQT](https://aclanthology.org/2023.emnlp-main.436/) | Hơn 3.000 câu có hai SQL hợp lý do lexical/structural ambiguity; LogicalBeam đa dạng logic top-k hiệu quả hơn token beam tới 2,5 lần. | Tách semantic interpretations trước candidate SQL; nếu hai interpretation đều hợp lý thì hỏi user. |
| [PRACTIQ](https://aclanthology.org/2025.naacl-long.13/) | Benchmark hội thoại cho câu ambiguous/unanswerable, dùng chu trình hỏi làm rõ rồi mới sinh SQL và giải thích kết quả. | Thêm answerability gate và clarification contract thay vì bắt hệ thống luôn phải đoán một SQL. |
| [Know What I Don't Know](https://aclanthology.org/2023.findings-acl.352/) | Phân loại sáu nhóm câu ambiguous/unanswerable và đề xuất Detecting-Then-Explaining thay vì luôn sinh một SQL có vẻ hợp lý. | Huấn luyện/evaluate router trên counterfactual negatives và yêu cầu reason code có thể giải thích. |
| [DIN-SQL](https://arxiv.org/abs/2304.11015) | Decomposition + self-correction báo 85,3% EX trên Spider test. | Mượn phân loại độ khó và plan theo clause; không mượn model GPT-4. |
| [DAIL-SQL](https://arxiv.org/abs/2308.15363) | Structural example selection đạt 86,6% EX Spider và chú trọng token efficiency. | Thử verified examples theo SQL skeleton sau khi có leakage audit. |
| [CoT-style prompting for Text-to-SQL](https://aclanthology.org/2023.emnlp-main.327/) | Prompt reasoning chuyên biệt tăng 5,2 điểm tuyệt đối trên Spider dev. | Thiết kế plan ngắn theo clause; tránh reasoning dài gây error propagation. |
| [DART-SQL](https://aclanthology.org/2024.findings-acl.120/) | Database-content rewriting + execution refinement tăng trung bình 12,41% cho DAIL-SQL. | Ưu tiên value grounding và rewrite có kiểm soát cho filter/entity. |
| [PET-SQL](https://arxiv.org/abs/2403.09732) | Cell values + two-round refinement + cross-consistency báo 87,6% EX Spider. | Thử hai vòng chỉ cho case khó; không random cell values không giới hạn. |
| [CHESS](https://arxiv.org/abs/2405.16755) | Schema selector báo khoảng +2 điểm, giảm token 5 lần; BIRD test 71,10%. | Học entity/value retrieval và unit-test verifier; schema pruning không phải bottleneck hiện tại. |
| [CHASE-SQL](https://arxiv.org/abs/2410.01943) | Multi-path generation + pairwise selector đạt 73,01% EX BIRD dev. | Adaptive best-of-3 trên case khó thay vì nhân compute cho mọi câu. |
| [OmniSQL / SynSQL-2.5M](https://www.vldb.org/pvldb/vol18/p4695-li.pdf) | OmniSQL-14B greedy: 81,4% TS Spider dev, 64,2% EX BIRD dev; synthetic data giúp OmniSQL-7B +4,3 điểm Spider dev và +8,8 BIRD dev. | A/B model 7B rồi 14B; dùng external/robustness set vì model đã train với Spider/BIRD. |
| [Dr.Spider](https://arxiv.org/abs/2301.08881) | 17 perturbations; model mạnh nhất vẫn giảm 14,0% tổng và 50,7% ở perturbation khó nhất. | Dùng làm diagnostic robustness, không trộn với accuracy Spider gốc. |
| [BIRD](https://arxiv.org/abs/2305.03111) | 12.751 cặp, 95 CSDL/33,4 GB; nhấn mạnh dirty values và external knowledge. | Chỉ Mini-Dev sau Spider; học cách chuẩn bị database descriptions và value index. |
| [APEL for non-programmers](https://aclanthology.org/2023.emnlp-main.312/) | Người không biết SQL chọn output trên input phân biệt candidate đạt cùng annotation accuracy 75% như expert annotators và phát hiện lỗi annotation tinh vi. | Thiết kế feedback bằng result/assumption choice, không bắt user đọc SQL hay bấm đúng/sai mơ hồ. |
| [CoSQL](https://aclanthology.org/D19-1204/) | 30k+ lượt hội thoại trên 200 DB gồm clarify ambiguity, báo unanswerable và diễn giải execution result. | Định nghĩa dialog acts ANSWER/CLARIFY/CANNOT_ANSWER/REPHRASE cho UI không-code. |
| [PICARD](https://aclanthology.org/2021.emnlp-main.779/) | Incremental parsing loại token không thể tạo chương trình SQL hợp lệ trong lúc decode. | Giữ như phương án constrained decoding cho model fine-tuned; hiện invalid syntax không phải bottleneck nên không ưu tiên trước semantic verifier. |
| [Spider 2.0](https://openreview.net/forum?id=XmProj9cPs) | 632 workflow thực tế, schema trung bình 812 cột, nhiều dialect và context từ docs/codebase; ICLR 2025 báo model mạnh vẫn có success rate thấp. | Dùng làm north-star enterprise sau khi SQLite single-query core ổn; không đưa ngay vào laptop gate. |
| [ReViSQL (2026 preprint)](https://arxiv.org/abs/2603.20004) | Audit sửa 61,1% subset BIRD Train; verified data tăng single-generation 8,2–13,9 điểm trong cùng RLVR setup. | Đặt data verification trước RL/LoRA; kết quả model lớn không chuyển trực tiếp sang laptop. |
| [SQL-of-Thought](https://arxiv.org/abs/2509.00581) | Báo 91,59% EX Spider dev; mini ablation giảm ít nhất 5 điểm nếu bỏ plan và 8–10 điểm nếu bỏ correction. | Giữ taxonomy-guided repair, nhưng phải tái kiểm chứng bằng Qwen local và evaluator khóa. |
| [BIRD noise audit](https://aclanthology.org/2024.acl-short.34/) | ACL 2024 tìm thấy noise ở question/gold SQL đủ để đổi thứ hạng giữa zero-shot và prompting methods sau correction. | Thêm label uncertainty, gold review và benchmark-quality gate trước khi tin score. |
| [Automatic Metadata Extraction](https://arxiv.org/abs/2505.19988) | Khảo sát profiling, query logs và SQL-to-text metadata; profiling-only từng đứng đầu BIRD theo thời điểm paper. | Thiết kế bounded profiler + value/description evidence thay cho mô tả thủ công ad hoc. |
| [Solid-SQL](https://aclanthology.org/2025.coling-main.654/) | Structural two-round example retrieval đạt 82,1% Spider, 58,9% BIRD và cải thiện trung bình 11,6% trên robustness variants. | Kết hợp structure-aware examples với paraphrase robustness, nhưng khóa leakage theo DB. |

### Cách đọc bảng survey

- EX, TS, dev/test, dataset và model khác nhau nên không so số ngang hàng tuyệt đối.
- Paper dùng GPT-4/Claude/model 32B+/nhiều candidate chỉ cung cấp **evidence về mechanism**.
- OmniSQL đã dùng Spider/BIRD train nên Spider score có contamination/familiarity risk đối với mục
  tiêu đánh giá năng lực tổng quát; cần external robustness và Olist fresh holdout.
- ReViSQL 2026 là preprint và dùng model/compute lớn; insight chuyển giao là *verified data first*.
- SQL-of-Thought có cost/model khác project; ablation phải tái lập trên Qwen local trước khi tin.

## 11. Những việc chưa nên ưu tiên

1. Refactor thêm agent/LangGraph khi chưa có failure cluster chứng minh cần.
2. Tăng `top_k`, đổi embedding hoặc nhét full schema khi qualified recall đã ~99,65%.
3. Fine-tune ngay trên toàn Spider/Olist trước dedup, DB-disjoint split và contamination audit.
4. Sinh 8–16 candidates cho mọi câu trên laptop; phải đo pass@3 oracle và dùng adaptive routing trước.
5. Tối ưu latency bằng cách làm yếu safety/validator; accuracy là ưu tiên nhưng safety là constraint cứng.
6. Công bố full-Spider/SOTA bằng phép nội suy từ 200 case hoặc trộn Olist/Spider thành một score.

## 12. Bước tiếp theo duy nhất

Thực hiện **R0**, không sửa thuật toán: tạo baseline experiment mới cho generator v6/corrector v5,
rerun locked Spider-200 + Olist-60, rồi dùng **R1** phân nhãn 70 lỗi. Chỉ sau Pareto failure analysis
mới chốt R2/R3/R4 là intervention đầu tiên. Đây là cách giữ đúng vai trò Data Scientist: mọi thay đổi
đều xuất phát từ dữ liệu, có control, effect size và kill criterion. Sau R1, triển khai R2 vì
answerability/clarification là product safety contract; Pareto failure sau đó quyết định R3, R4 hoặc
model A/B R10 là accuracy intervention đầu tiên.

---

Regenerate: `uv run python docs/research_plan/generate_research_plan.py`<br>
Check: `uv run python docs/research_plan/generate_research_plan.py --check`
