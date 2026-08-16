# Nhật ký toàn bộ failure, bug và bài học của dự án

Cập nhật: 2026-08-17

Phạm vi revision: `c748621` (P0/P1) đến `68fde00` (hậu P6.3)

Nguồn sự thật: `realistic_project_creation_codex.md`, `docs/evidence/`, lịch sử Git và các report
benchmark đã khóa.

## Cách đọc tài liệu này

Đây là bộ nhớ kỹ thuật được dựng lại từ evidence còn lưu trong repository, không phải transcript
nguyên văn của mọi phiên terminal. Một sự cố chỉ được ghi là **đã sửa** khi có regression test,
live evidence hoặc gate check tương ứng. Những hạn chế accuracy/latency chưa được giải quyết được
ghi là **còn mở**, không được biến thành bug “đã hết” bằng cách đổi cách tính điểm.

Các nhãn dùng trong tài liệu:

- **FIXED**: root cause đã được sửa và có evidence tái lập.
- **MITIGATED**: đã kiểm soát được rủi ro nhưng giới hạn nền tảng vẫn còn.
- **HISTORICAL**: số đo đúng với revision cũ, không đại diện code hiện tại.
- **OPEN**: vấn đề nghiên cứu/hiệu năng vẫn còn.
- **REJECTED**: phương án đã thử và có lý do không được dùng.

## Bản đồ các gate và bonus gate

| Gate | Failure chính buộc kiến trúc thay đổi | Kết quả |
|---|---|---|
| P0 | Ollama không biên dịch được JSON grammar do regex của Pydantic | Adapter làm sạch schema, live smoke pass |
| P1 | Loader sai cardinality; SQLite trên `/mnt/d` cực chậm; hiểu sai anomaly review | Atomic build ở ext4, 20/20 validation |
| P2 | Parser chấp nhận text không phải query; prompt/schema/router/latency chưa đúng | Direct baseline typed 20/20, accuracy 77,78% |
| P3 | Retrieval chạy được nhưng metric và protocol còn sai | Chỉ giữ làm historical evidence |
| **P3.1 bonus** | Mini-100 chỉ có 99 unique; metric unqualified; FK denominator và latency sai; index publication yếu | Benchmark/retrieval hardening, holdout tách biệt |
| P4 | SQL chạy được vẫn sai semantic; corrector có thể lặp lại SQL | Validator + bounded gold-blind correction |
| P5 | UI/API hoàn chỉnh nhưng Olist chỉ 78,33%; p95 cao; full-GPU làm laptop mất ổn định hai lần | Guarded runner, checkpoint và audit UI |
| **P5.1 bonus** | GPU snapshots bỏ sót power spike; semantic rules chưa đủ; validator tự chặn scalar MAX | Governor 0,5 s, 6-layer profile về sau, hardening semantic |
| P6 | Full Spider-1.034 không phù hợp laptop; benchmark dài và có power stop | Spider-200 stratified + resume; full-1.034 optional |
| **P6.2 bonus** | Schema context trộn component, model bịa join key; SQLite/Streamlit trên WSL chậm | Coherent component, runtime DB cache, non-blocking UI |
| **P6.3 bonus** | Free-form returning-customer sai scope; correction sai shape; validator false positive | Metric/dimension-aware linking, scalar contract, correction-on mặc định |

---

## P0 — Foundation và local model contract

### F-P0-01 — Pydantic JSON Schema làm Ollama grammar compiler thất bại

- **Triệu chứng:** live structured smoke đầu tiên không sinh được JSON dù model và service đang chạy.
- **Root cause:** Pydantic phát ra inline-regex `pattern`; grammar compiler của Ollama không hỗ trợ
  keyword này trong schema request.
- **Sửa:** provider bỏ các grammar-only `pattern` trước khi gửi; Pydantic vẫn validate model đầy đủ
  sau khi nhận response nên không hạ contract của ứng dụng.
- **Evidence:** unit test của adapter và live Vietnamese structured smoke trả
  `{"language":"vi","sql":"SELECT 1 AS ket_qua","read_only":true}`.
- **Trạng thái:** **FIXED** — `docs/evidence/p0_gate.md`.

### F-P0-02 — Không thể dùng GPU/Ollama trong CI thông thường

- **Vấn đề:** nếu test mặc định phụ thuộc model, Kaggle hoặc GPU thì CI và máy khác sẽ không tái
  lập được.
- **Giải pháp kiến trúc:** fake transport + synthetic SQLite deterministic; live Ollama test có
  marker riêng; `ollama-smoke` là acceptance test rõ ràng.
- **Trạng thái:** **MITIGATED**. Live-model quality vẫn phải chạy local, không được suy ra từ CI.

## P1 — Olist data foundation

### F-P1-01 — Loader order-item cấp phát thiếu derived columns

- **Triệu chứng:** staged build dừng giữa chừng.
- **Root cause:** loader cấp một vị trí trong khi cần hai cột cents dẫn xuất.
- **Sửa:** sửa cardinality và thêm regression test; database chỉ publish sau toàn bộ validation.
- **Trạng thái:** **FIXED**.

### F-P1-02 — SQLite random I/O trên WSL `/mnt/d` quá chậm

- **Triệu chứng:** build/index/validation dành phần lớn thời gian ở `p9_client_rpc`; thao tác tưởng
  bị treo dù RAM không cao.
- **Root cause:** SQLite random I/O đi qua Windows-mounted filesystem.
- **Sửa:** build và validation trong Linux ext4 temporary storage, kiểm tra xong mới copy sang file
  sibling `.tmp` rồi atomic rename.
- **Evidence:** full build thứ hai 5 phút 43 giây, peak RSS khoảng 48 MiB; validation sau staging
  khoảng 12 giây; hai build có cùng logical SHA-256.
- **Trạng thái:** **FIXED** cho build; cùng nguyên nhân xuất hiện lại ở runtime và được xử lý P6.2.

### F-P1-03 — Hiểu sai con số review duplication

- **Triệu chứng:** specification ban đầu coi 551 là số order bị ảnh hưởng.
- **Root cause:** 551 là số row dư, trong khi chỉ có 547 order bị ảnh hưởng.
- **Sửa:** định nghĩa cả “excess rows” và “affected orders” riêng, có invariant test.
- **Trạng thái:** **FIXED**.

### F-P1-04 — Các phép join Olist dễ làm phình doanh thu

- **Failure mode:** join item × payment, item × review hoặc geolocation thô tạo fan-out; dùng
  `customer_id` thay `customer_unique_id` làm sai repeat customer.
- **Sửa:** semantic views theo grain, cents integer, geolocation centroid, glossary và canonical
  query regressions. Tổng item revenue/freight/payment được khóa bằng invariant.
- **Trạng thái:** **MITIGATED**. Generator vẫn cần Layer 4 semantic checks vì SQL hợp lệ có thể chọn
  sai grain.

### F-P1-05 — Source/build hỏng có thể tạo database tưởng là hợp lệ

- **Failure paths đã dự phòng:** archive hash sai, ZIP có member thừa, thiếu/sai header, count sai,
  build lỗi giữa chừng và database bị mutation.
- **Sửa:** pin hash cho ZIP và chín CSV, kiểm tất cả file, transaction/staging/atomic publication,
  read-only checksum tests.
- **Trạng thái:** **FIXED/PREVENTED**.

## P2 — Direct reasoning/generation baseline

### F-P2-01 — SQLGlot parse `not sql` nhưng AST không phải query

- **Triệu chứng:** text vô nghĩa vượt qua bước parse syntax.
- **Root cause:** “parse thành AST” không đồng nghĩa “AST là SELECT/query”.
- **Sửa:** normalizer bắt buộc root là `exp.Query`.
- **Trạng thái:** **FIXED**.

### F-P2-02 — JSON Schema bị render như Python dict

- **Triệu chứng:** prompt chứa representation không phải JSON chuẩn, làm structured generation kém
  ổn định.
- **Sửa:** serialize schema thành JSON hợp lệ.
- **Trạng thái:** **FIXED**.

### F-P2-03 — Router hiểu nhầm từ “Return” trong yêu cầu trình bày

- **Triệu chứng:** câu như “Return the type…” bị nhầm với nghiệp vụ returns/refunds mà Olist không
  có facts.
- **Sửa:** route clarification chỉ theo các concept `return rate`, `returns`, `returned`, refund,
  không theo động từ presentation chung.
- **Trạng thái:** **FIXED**.

### F-P2-04 — Qwen thinking phá ngân sách latency

- **Triệu chứng:** canary đầu mất 95,6 giây.
- **Root cause:** reasoning/thinking không cần thiết cho structured calls kéo dài decode.
- **Sửa:** `think=false`, temperature 0, context 4096; cùng canary còn 20,2 giây.
- **Trạng thái:** **FIXED** cho baseline; model inference vẫn là bottleneck chính hiện tại.

### F-P2-05 — Terminal failure không ghi total latency

- **Triệu chứng:** report success có latency nhưng failure path thiếu, làm percentile/taxonomy lệch.
- **Sửa:** mọi return path ghi total latency; evaluator có fallback cho artifact lịch sử.
- **Trạng thái:** **FIXED**.

### F-P2-06 — Bốn lỗi semantic của baseline 14/18

1. repeat customer trả thêm một cột count trùng;
2. late delivery lọc `order_status='delivered'`, trả 7.826 thay vì population timestamp 7.827;
3. dùng `review_score` trên view `order_review_summary` không sở hữu cột;
4. dùng `customer_state` trên orders mà thiếu customer join.

Hai lỗi ownership bị policy chặn an toàn; hai lỗi còn lại chứng minh “SQL chạy được” chưa chắc đúng.
Chúng trở thành input cho P3/P4, không bị xóa khỏi baseline 77,78%.

## P3 — Retrieval đầu tiên và lý do phải có P3.1

### F-P3-01 — “Mini-100” thực tế chỉ có 99 unique cases

- **Root cause:** selection/manifest có duplicate nhưng metric chỉ nhìn số row.
- **Tác hại:** benchmark được gọi là 100 nhưng sample thực tế nhỏ hơn.
- **Sửa P3.1:** pin đúng 100 dev index + case hash unique; thêm invariant test.
- **Trạng thái:** **FIXED**; toàn bộ P3 figures được gắn historical.

### F-P3-02 — Column recall match tên cột mà không qualify table

- **Tác hại:** `id`, `name`, `status` ở table sai vẫn được tính hit.
- **Sửa:** gold extraction resolve scope/alias bằng SQLGlot và chấm `table.column`, case-insensitive
  theo SQLite.
- **Trạng thái:** **FIXED**.

### F-P3-03 — No-join cases được cho FK recall = 1

- **Tác hại:** macro FK recall bị nâng giả tạo.
- **Sửa:** loại case không có FK/join khỏi denominator tương ứng; báo FK và general join edge riêng.
- **Trạng thái:** **FIXED**.

### F-P3-04 — Retrieval latency bỏ query embedding

- **Tác hại:** report p95 chỉ vài ms dù mỗi embedding thực tế khoảng 5 giây.
- **Sửa:** tách cold build, query embedding và warm rank/link; đưa embedding vào grounded E2E.
- **Evidence:** query embedding recorded p50 4,461 s, p95 5,027 s; warm rank/link p95 <3 ms.
- **Trạng thái:** **FIXED**.

### F-P3-05 — Schema linker bỏ qua LogicalPlan và P2 bypass grounding

- **Tác hại:** Layer 2 tồn tại nhưng không thực sự chi phối final generation; context không
  plan-sensitive.
- **Sửa:** plan terms tham gia linking; generator nhận typed grounded context và lưu exact evidence.
- **Trạng thái:** **FIXED**.

### F-P3-06 — Hybrid RRF 0,01 gần như dense-only

- **Kết quả bị loại:** BM25-heavy ban đầu thấp hơn dense; cấu hình BM25 weight 0,01 chỉ “không giảm”
  nhưng không phải hybrid có ý nghĩa.
- **Sửa P3.1:** equal-weight RRF; trên disjoint holdout hybrid tăng qualified column/schema recall
  mà không giảm table/FK recall.
- **Trạng thái:** **REJECTED/FIXED**.

### F-P3-07 — Index publication xóa bundle cũ trước rename; BM25 pickle không phù hợp trust boundary

- **Rủi ro:** failed rebuild có thể mất active index; pickle có executable deserialization risk;
  bundle từ database/model khác có thể bị load nhầm.
- **Sửa:** immutable `versions/<id>`, atomic `active.json`, SHA-256 mọi artifact, model digest/vector
  dimension/doc count/db_id checks, BM25 JSON, transactional embedding cache và build lock.
- **Trạng thái:** **FIXED/PREVENTED**.

### F-P3-08 — Grounding giảm token nhưng không tăng accuracy và tăng p95

- **Evidence:** full schema và grounded đều 14/18; prompt giảm 41,96%, nhưng p95 tăng 32,12 → 46,40
  giây do embedding.
- **Bài học:** không được tuyên bố retrieval “cải thiện accuracy” chỉ vì schema recall cao.
- **Trạng thái:** **HISTORICAL LIMITATION**.

## P4 — Validation và correction

### F-P4-01 — Execution success bị nhầm với answer correctness

- **Root cause:** syntax/policy/executor không bắt được sai population, grain, top-k hoặc scalar shape.
- **Sửa:** `VALID/SUSPICIOUS/FAILED`, shape validator và các semantic rules gold-blind.
- **Trạng thái:** **MITIGATED**; không validator nào chứng minh được correctness cho mọi free-form
  question.

### F-P4-02 — Corrector lặp lại đúng SQL sai

- **Triệu chứng:** `olist_en_010` vẫn non-scalar; corrector trả lại cùng SQL.
- **Sửa:** fingerprint/repeated-SQL stop, repeated-error stop, một LLM correction call mặc định,
  shared deadline, mọi candidate sửa phải chạy lại toàn bộ policy/executor/validator.
- **Evidence:** dừng `REPEATED_SQL`, không loop vô hạn; frozen run phục hồi 3/4.
- **Trạng thái:** **MITIGATED**. Stochastic corrector vẫn có thể không sửa được.

### F-P4-03 — Correction variance làm kết quả không lặp hoàn toàn

- **Evidence:** frozen off/on đạt 17/18, nhưng diagnostic rerun chỉ phục hồi 1/3 repair được trigger.
- **Quyết định:** P4 giữ feature-flagged; không lấy một run đẹp làm cam kết tuyệt đối.
- **Trạng thái:** **OPEN MODEL VARIANCE**.

### F-P4-04 — So sánh latency correction on/off dễ kết luận sai

- **Vấn đề:** correction-on run nhanh hơn lịch sử vì warm state/runtime khác, không phải vì thêm
  correction làm hệ thống nhanh hơn.
- **Sửa tài liệu:** report số thật nhưng không gán causal claim.
- **Trạng thái:** **FIXED về evaluation integrity**.

## P5 — Application/UI và acceptance đầu tiên

### F-P5-01 — Olist-60 chỉ đạt 47/60 (78,33%)

- **Chi tiết:** first-pass 43/60; 11 query `SUCCEEDED` nhưng sai rows; 2 shape mismatch; lỗi tập trung
  ở ranking/order, population/filter, aggregation grain và extra output shape.
- **Tác động:** chưa đạt mục tiêu 9/10 application fitness dù workflow 60/60.
- **Sửa tiếp:** P5.1 bổ sung planner v2, generator v3, semantic checks và correction guidance.
- **Trạng thái:** **HISTORICAL**. Revision P6 sau đó đạt 57/60, nhưng code hậu P6.3 cần benchmark
  mới trước khi kế thừa con số 95%.

### F-P5-02 — P95 82,35 giây vượt target interactive 60 giây

- **Root cause chính:** planner/generator/correction model inference, cộng embedding/model load.
- **Tình trạng:** **OPEN**. Kiến trúc UI hiện không block navigation, SQLite được tăng tốc, nhưng
  một answer mới vẫn thường mất 70–100 giây trên profile laptop.

### F-P5-03 — Continuous full-GPU acceptance làm laptop mất ổn định hai lần

- **Triệu chứng:** host/laptop bị văng/sập trong các lượt chạy dài; accuracy run phải chia profile.
- **Root cause:** power/thermal/load transient không thấy được qua snapshot thủ công, cộng model
  residency và batch liên tục.
- **Sửa ban đầu:** checkpoint mỗi case, unload model, cooldown 20 giây, parallelism/model count 1,
  CPU affinity/nice, independent monitor RAM/swap/VRAM/temp/power.
- **Evidence:** guard bắt pilot 139,12 W trước khi checkpoint tiến lên.
- **Trạng thái:** **MITIGATED**, rồi tiếp tục harden tại P5.1/P6.

### F-P5-04 — Run/API có thể dở dang hoặc UI bypass boundary sau restart

- **Rủi ro kiến trúc:** run giữ `RUNNING` vĩnh viễn; browser gửi arbitrary path/edited SQL; SSE mất
  trace khi reconnect.
- **Sửa:** persistent application SQLite/WAL, registered `db_id` only, immutable configs/events,
  restart recovery sang typed terminal, SSE replay và một worker bounded.
- **Trạng thái:** **PREVENTED/TESTED**.

## P5.1 — Bonus laptop và accuracy hardening

### F-P5.1-01 — Snapshot monitoring bỏ sót power spikes

- **Thử nghiệm 12/14 layers:** snapshot đôi lúc an toàn và nhanh hơn 10–18%, nhưng monitor độc lập
  bắt 108,02 W và 137,65 W.
- **Thử nghiệm 10 layers:** pilot ngắn tốt, nhưng run dài đạt 101,93 W.
- **Thử nghiệm 8 layers:** từng 99,53 W; về P6 một pilot dài lên 113,77 W ở case 34.
- **Quyết định:** 12/14/10/8 không dùng làm P6 production profile; hiện dùng **6 layers**.
- **Trạng thái:** **REJECTED** cho profile cao; supervisor sample 0,5 s và kill process group.

### F-P5.1-02 — Tải bị dồn CPU/RAM khi giảm GPU

- **Trade-off:** partial offload an toàn hơn nhưng inference chậm, CPU phải làm phần lớn layers.
- **Sửa:** 12 low-priority logical cores, parallel 1, context 4096, Flash Attention, q8_0 KV,
  BGE query embedding CPU, max loaded models 1–2 tùy profile.
- **Trạng thái:** **MITIGATED**, không thể vừa tăng offload vô hạn vừa giữ power envelope laptop.

### F-P5.1-03 — Validator tự reject SQL scalar MAX đúng

- **Triệu chứng:** SQL `MAX(...)` đúng nhưng plan cũ vẫn giữ ranking `LIMIT 1`, validator tự chặn.
- **Root cause:** intent representation giữa planner và output shape không đồng bộ.
- **Sửa:** scalar maximum xóa ranking shape trong plan; exact case rerun pass first-pass.
- **Trạng thái:** **FIXED**.

### F-P5.1-04 — Không được tune trên holdout đã xem

- **Vấn đề:** hai P5 holdout failures đã bị inspect nên không còn “fresh”.
- **Quyết định:** chỉ tune 11 dev/regression failures; giữ immutable report 10/11 và dùng Spider
  disjoint holdout tại P6.
- **Trạng thái:** **FIXED về protocol**.

## P6 — Release benchmark trên laptop

### F-P6-01 — Full Spider-1.034 quá dài và không phù hợp tải laptop

- **Triệu chứng/rủi ro:** 1.034 cases với khoảng một phút/case kéo dài nhiều giờ, tích lũy nhiệt,
  model/cache load và tăng xác suất host crash.
- **Quyết định:** Spider-200 stratified gồm regression-100 + disjoint holdout-100, đủ 20 DB;
  reorder theo DB để reuse index; checkpoint/resume/cooldown. Full-1.034 là P6.1 optional.
- **Trạng thái:** **MITIGATED**. Không được gọi Spider-200 là full Spider.

### F-P6-02 — Guard stop trong benchmark dài

- **Evidence:** hai isolated power-sensor breaches làm supervisor tắt model; checkpoint được giữ,
  resume cùng commit/seed/digest/index/config.
- **Kết quả:** không mất prediction, laptop không sập; safe segments 60–61°C, ~2,7 GiB VRAM,
  swap 0.
- **Trạng thái:** **EXPECTED CONTROLLED STOP**, không phải benchmark crash.

### F-P6-03 — Spider accuracy 65%, extra-hard 36,36%

- **Chi tiết:** 130/200; 68 execution mismatches, 1 unknown runtime error, 1 write blocked; holdout
  67% không collapse so với regression 63%.
- **Root cause thống kê:** bottleneck là semantic generation cho nested/aggregate/join queries,
  không phải workflow completion (200/200).
- **Trạng thái:** **OPEN RESEARCH LIMITATION**. Không che 70 failures và không nới safety để lấy điểm.

### F-P6-04 — P95 vẫn vượt 60 giây

- Spider p95 85,29 s; Olist p95 91,62 s.
- **Trạng thái:** **OPEN**. Đây là lý do release engineering đạt nhưng stretch latency chưa đạt.

### F-P6-05 — Benchmark evaluator có thể đúng code nhưng sai protocol

- **Phòng ngừa:** exact-gold self-test 1.034/1.034; manifest pin question/schema/DB hashes; inference
  đóng trước khi evaluator mở gold; Olist và Spider không blend thành một accuracy.
- **Trạng thái:** **PREVENTED/VERIFIED**.

## P6.2 — Bonus schema coherence và UI latency

### F-P6.2-01 — `Unknown column: order_item_totals.product_id`

- **Câu incident:** `Top 5 danh mục theo doanh thu sản phẩm, tách phí vận chuyển, giải thích`.
- **Triệu chứng:** `POLICY_BLOCKED` sau 26,43 s.
- **Điều đã loại trừ:** bỏ chữ `giải thích` vẫn lỗi; câu suffix không phải nguyên nhân.
- **Root cause:** grounded context trộn raw tables có FK đúng với aggregate view
  `order_item_totals` bị disconnected; model bịa `product_id` trên view.
- **Sửa:** chọn best connected FK component độc lập rank, prompt bắt exact ownership/FK; metric view
  thiếu dimension/path phải đổi sang raw connected source.
- **Live evidence:** run `3e49bb05...` thành công, dùng items + products và FK `product_id`, trả
  revenue/freight riêng.
- **Trạng thái:** **FIXED**.

### F-P6.2-02 — Schema-invalid SQL bị gắn nhãn `POLICY_BLOCKED`

- **Tác hại:** user tưởng câu bị chặn vì safety thay vì model dùng sai schema.
- **Sửa:** schema/syntax/dialect → `INVALID_SQL`; chỉ safety violation thực sự → `POLICY_BLOCKED`.
- **Trạng thái:** **FIXED**.

### F-P6.2-03 — Runtime SQLite trên `/mnt/d` chậm khoảng 160 lần

- **Evidence cùng query:** 30,774 s trên `/mnt/d`, 0,192 s trên `/tmp`.
- **Sửa:** lazy copy registered DB sang immutable, atomic, read-only Linux temp cache; cache key gồm
  source path/size/mtime ns và reject source đổi trong lúc copy.
- **Trạng thái:** **FIXED** cho SQLite execution. E2E vẫn lâu vì LLM.

### F-P6.2-04 — Streamlit blocking polling làm chuyển workspace chậm

- **Root cause:** whole-script sleep/poll, history payload mang result JSON lớn, HTTP client không
  reuse và heavy UI deps load sớm.
- **Sửa:** fragment polling, cached bounded metadata, history summaries, lazy result detail,
  persistent HTTP connection, native lightweight charts.
- **Evidence:** sau first render, History 0,057 s; Benchmark 0,162 s; System Center 0,081 s; Query
  Studio 0,038 s; zero AppTest exceptions.
- **Trạng thái:** **FIXED** cho navigation.

### F-P6.2-05 — `streamlit-sortables` làm first load nặng

- **Evidence:** dependency import khoảng 9,36 s trong diagnostic; AppTest initial 24,22 s.
- **Sửa:** drag organizer opt-in/lazy; keyboard selector luôn sẵn. Initial render còn 14,62 s.
- **Trạng thái:** **MITIGATED**. Drag vẫn có giá tải khi user bật.

### F-P6.2-06 — WSL Streamlit file watcher nhận TCP nhưng bỏ đói HTTP

- **Triệu chứng:** port mở nhưng health/root response treo hoặc rất lâu.
- **Root cause:** poll-based source watcher trên repository ở Windows mount.
- **Sửa:** `.streamlit/config.toml` tắt watching; sửa code UI thì restart Streamlit thủ công.
- **Evidence:** health 0,001 s, root 0,012 s.
- **Trạng thái:** **FIXED**.

### F-P6.2-07 — Native chart config regression trong AppTest

- **Triệu chứng:** chart sorting option không tương thích (`sort="-x"`) làm UI test lỗi.
- **Sửa:** thay bằng native progress/lightweight bars tương thích.
- **Trạng thái:** **FIXED trước release**.

## P6.3 — Bonus free-form scalar query recovery

### F-P6.3-01 — Returning-customer query tham chiếu cột sai subquery scope

- **Câu incident:** `Có bao nhiêu khách hàng quay lại theo customer_unique_id? cho tôi biết đủ`.
- **Triệu chứng:** `UNKNOWN_COLUMN`, 0 rows, 71,92 s.
- **Root cause:** generator dùng `customer_unique_id` bên trong subquery chỉ có
  `olist_orders_dataset`; cột thuộc customer table. Policy chưa bắt ambiguous implicit outer scope
  sớm và correction interactive mặc định đang off.
- **Sửa:** scope-local ownership rule; component scoring theo dimensions/metrics/intent; bổ sung
  plan-matching catalog columns; repeat-customer semantic contract.
- **Trạng thái:** **FIXED**.

### F-P6.3-02 — Corrector sửa ownership nhưng trả nhiều row `COUNT=1`

- **Root cause:** GROUP BY/HAVING đúng ở group level nhưng không wrap để đếm số group; scalar intent
  bị mất.
- **Sửa:** generator v6/corrector v5 bắt scalar exactly one row; grouped result phải được bọc rồi
  `COUNT(*)`; validator signal `SCALAR_AGGREGATE_ROW_COUNT` hướng repair.
- **Trạng thái:** **FIXED**.

### F-P6.3-03 — Validator false-positive với semantic view đúng

- **Triệu chứng:** SQL canonical trên `customer_order_facts` vẫn bị yêu cầu text
  `customer_unique_id` xuất hiện.
- **Root cause:** rule chỉ nhìn token SQL, không hiểu view đã group theo identity.
- **Sửa:** glossary khai báo contract view + `order_count > 1`; validator chấp nhận view chỉ khi có
  repeat filter.
- **Trạng thái:** **FIXED**.

### F-P6.3-04 — Fix singleton semantic view làm regression revenue query

- **Triệu chứng trong quá trình sửa:** scoring mới chọn dimension-only translation table cho câu
  ranking revenue, bỏ metric source/FK component.
- **Sửa:** score joint dimension + metric + intent + retrieval quality + complexity; có opposite
  regression test cho revenue/freight.
- **Evidence:** run `dc1c66e3...` trả 5 rows bằng products + items/FK đúng.
- **Trạng thái:** **FIXED**.

### F-P6.3-05 — API/UI correction mặc định off làm Layer 5 bị skip

- **Tác hại:** một candidate lỗi kết thúc ngay dù kiến trúc có corrector.
- **Sửa:** interactive API/UI default correction on, hard cap vẫn một repair/call; benchmark/ablation
  vẫn set explicit. CLI `ask` hiện vẫn cần `--correction` nếu muốn bật.
- **Trạng thái:** **FIXED cho API/UI**.

### F-P6.3-06 — “95% confidence” dễ bị hiểu thành per-query accuracy

- **Vấn đề:** không có gold/reference cho câu user tự do nên không thể tính accuracy trung thực.
- **Sửa:** UI ghi rõ model self-confidence và validation status; benchmark accuracy ở tab/report
  riêng; failed run hiện attempted SQL/schema/error/repair diagnostics.
- **Trạng thái:** **FIXED về UX/evaluation honesty**.

### F-P6.3-07 — GitHub CI fail sau code đúng do async integration test race

- **Triệu chứng:** local logic đúng nhưng CI fail khi test reload application store.
- **Root cause:** test bắt đầu run async thứ hai rồi đóng TestClient/container trước terminal event,
  gây race/duplicate trace sequence lúc restart.
- **Sửa:** test chờ SSE terminal của run thứ hai trước khi reload.
- **Evidence:** commit `68fde00`; GitHub Actions run `31962809864` success.
- **Trạng thái:** **FIXED**.

## Những điểm chưa được phép tuyên bố là đã giải quyết

1. **Code hiện tại chưa có aggregate accuracy mới.** Olist 95% và Spider 65% thuộc revision
   `1509faa`, generator v4/corrector v3. Hậu P6.2/P6.3 đang dùng generator v6/corrector v5.
2. **Free-form query không có per-query accuracy %.** Chỉ có model confidence + deterministic
   validation; accuracy cần independent expected result.
3. **Latency answer vẫn cao.** UI navigation nhanh, SQLite nhanh, nhưng planner/generator trên local
   Qwen-14B partial offload thường chiếm 70–100 giây.
4. **Spider complex semantics còn yếu.** 68/70 release failures là execution mismatch; extra-hard
   36,36%.
5. **Correction là bounded recovery, không phải guarantee.** Một lần sửa có thể lặp SQL, sai shape
   hoặc hết deadline; dừng typed tốt hơn loop vô hạn.
6. **Full Spider-1.034 chưa chạy.** Chỉ evaluator self-test 1.034/1.034; release inference là 200.
7. **Ứng dụng local chưa được harden để public Internet.** Không có auth/rate-limit/TLS/multi-user
   isolation; chỉ bind loopback.

## Checklist tránh tái phạm

- Trước thay đổi: đọc canonical ledger, evidence gate liên quan và failure ID trong file này.
- Với retrieval: test cả semantic singleton và connected raw component đối nghịch.
- Với semantic rule: phải có positive + negative regression để tránh validator tự chặn SQL đúng.
- Với benchmark: pin revision/model digest/prompt/index/manifest/DB; checkpoint inference trước gold.
- Với laptop: chạy `hardware-health`, một pilot case, supervisor độc lập; không tăng GPU layers dựa
  trên snapshot ngắn.
- Với WSL: giữ SQLite/runtime cache ở Linux filesystem, không chạy random I/O trực tiếp trên
  `/mnt/c` hoặc `/mnt/d`.
- Với UI async: chờ terminal event trước teardown/reload; history chỉ lấy summaries.
- Trước commit: `make check`; trước push: kiểm tra Git chỉ chứa source/docs, không chứa raw data,
  DB, index, predictions, traces, model blobs hoặc secrets.

## Evidence index

- P0–P6: `docs/evidence/p0_gate.md` … `docs/evidence/p6_gate.md`
- Bonus P3.1: `docs/evidence/p3_1_gate.md`
- Bonus P5.1: `docs/evidence/p5_1_gate.md`
- Bonus P6.2: `docs/evidence/p6_2_hardening.md`
- Bonus P6.3: `docs/evidence/p6_3_query_recovery.md`
- Benchmark score: `benchmark_full.md`
- Failure taxonomy: `docs/error_analysis.md`
- Canonical roadmap/completion ledger: `realistic_project_creation_codex.md`
