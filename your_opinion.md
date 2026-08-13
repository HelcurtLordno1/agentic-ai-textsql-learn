# Ý kiến kiến trúc sau Gate P3.1

**Thời điểm đánh giá:** 2026-08-10

**Trạng thái được đánh giá:** `GATE_P3_1_HARDENED_VERIFIED`

**Quyết định:** **GO có điều kiện cho Phase 4 / Gate P4**

## Kết luận ngắn

Project **đã đủ trưởng thành để bắt đầu P4 (Guided Error Correction)**. Tuy nhiên, con số
`14/18 = 77.78%` mới là một baseline nhỏ, có kiểm soát và tái lập được; nó **chưa đủ để tuyên bố hệ
thống đã đạt accuracy cấp production hoặc đã hoàn thiện**.

Đây không phải lý do trì hoãn P4. Ngược lại, bốn lỗi còn lại đã ổn định qua cả full-schema và
grounded run, nên hiện tại chính là thời điểm hợp lý để xây correction. Điều kiện quan trọng là P4
không được bắt đầu bằng một vòng LLM retry mù. Trước Corrector cần hoàn thiện tín hiệu validation
mà Corrector dựa vào.

## Evidence dẫn đến quyết định

| Hạng mục | Kết quả hiện tại | Nhận định |
|---|---:|---|
| Olist result accuracy | `14/18 = 77.78%` ở cả full và grounded | Grounding không làm giảm accuracy; baseline ổn định để đo correction off/on |
| Typed terminal | `20/20` | Workflow không crash và có contract trạng thái rõ |
| Expected status | Full `18/20`; grounded `19/20` | Grounding cải thiện khả năng đi tới execution, nhưng execution thành công chưa đồng nghĩa đúng nghĩa |
| Prompt estimate | `2,116.00 -> 1,228.06` | Giảm `41.96%`, đủ tốt để giữ grounded context |
| P95 end-to-end | `32.12 s -> 46.40 s` | Vẫn dưới deadline `60 s`, nhưng chỉ còn khoảng `13.60 s` headroom cho correction |
| Spider holdout hybrid@20 | table `1.0000`; qualified column `0.9965`; schema `0.9975` | Retrieval đã đủ mạnh để P4 tập trung vào generation/validation/correction |
| Holdout FK/join conditional | `0.8906` / `0.8636` | Tốt nhưng chưa hoàn hảo; Corrector không được giả định schema evidence luôn đầy đủ |

Hai lưu ý khi đọc số liệu:

1. Spider ở đây đo **schema retrieval**, không phải end-to-end SQL execution accuracy; không được
   dùng `99.75% schema recall` như thể đó là độ chính xác của hệ thống Text-to-SQL.
2. Olist chỉ có 18 query case được tính result accuracy. Với mẫu nhỏ này, khoảng tin cậy Wilson 95%
   cho `14/18` xấp xỉ `54.8%–91.0%`; vì vậy `77.78%` là baseline đáng tin cho regression, chưa phải
   ước lượng production đủ chặt.

## Bốn lỗi hiện tại là đầu vào tốt cho P4

Grounded run vẫn giữ đúng bốn failure ID, nhưng chúng đại diện cho những lớp lỗi khác nhau:

- `olist_vi_007`: SQL chạy thành công và con số đúng, nhưng trả thừa một cột (`[[2997, 2997]]` thay
  vì `[[2997]]`). Logical-plan/result-shape validator có thể bắt lỗi này mà không cần gold.
- `olist_vi_009`: sai population definition (`7826` thay vì `7827`). Đây là lỗi business metric /
  null semantics; cần glossary và deterministic invariant, không nên chỉ dựa vào SQLite error.
- `olist_en_010`: SQL chạy thành công nhưng trả nhiều review score thay vì một scalar average. Có thể
  phát hiện bằng aggregate intent và result cardinality.
- `olist_vi_013`: `UNKNOWN_COLUMN` do dùng `o.customer_state` thay vì cột của customer alias. Đây là
  lỗi correction trực tiếp, có tín hiệu policy rõ và khả năng phục hồi cao.

Việc có cả lỗi syntax/schema-observable và lỗi “successful-but-semantically-wrong” là một bộ kiểm
tra P4 hữu ích hơn nhiều so với chỉ inject lỗi tên cột.

## Khoảng trống phải xử lý trước Corrector

Trong completion matrix hiện tại, `L4-M3 Execution Validator` và `L4-M4 Semantic Validator` vẫn là
`NOT_STARTED`, trong khi Layer 5 nhận `ValidationReport` làm đầu vào. Đây là dependency kiến trúc
thực sự, không chỉ là thiếu một module phụ.

Nếu bỏ qua khoảng trống này:

- các câu chạy thành công nhưng sai nghĩa sẽ không có trigger hợp lệ để repair;
- Corrector có thể retry cả câu đúng, tạo correct-to-wrong regression;
- offline gold vô tình trở thành trigger runtime, vi phạm nguyên tắc chống gold leakage;
- thêm một LLM call có thể vượt deadline `60 s`, đặc biệt với grounded P95 `46.40 s`.

Vì vậy, công việc đầu tiên trong Phase 4 nên là **P4.0 — Validation Foundation**:

1. Hoàn thiện typed `ExecutionValidationReport` và `SemanticValidationReport`.
2. Rule deterministic trước: output shape/cardinality, aggregate intent, top-k/order/limit, referenced
   schema so với selected evidence, fan-out risk, duplicate risk và business glossary invariants.
3. Phân biệt rõ `FAILED`, `SUSPICIOUS` và `VALID`; empty result không tự động bị coi là sai.
4. Không dùng gold SQL, gold rows hoặc benchmark labels trong runtime signal.
5. Chỉ sau đó mới nối Error Classifier -> Correction Plan -> Corrector -> full safety revalidation.

Đây vẫn là triển khai Phase 4, không phải quay lại thay đổi mục tiêu của các gate đã verified.

## Cấu hình correction tôi khuyến nghị

- Bắt đầu với `max_repairs = 1` cho live/e2e path; chỉ nâng lên `2` sau khi có evidence về recovery,
  latency và loop stopping. Spec có thể giữ hard maximum là 2.
- Rule-based classifier/planner cho lỗi đã định danh; chỉ gọi LLM cho bước tạo lại full SQL khi thực
  sự đủ điều kiện retry.
- Không repair `POLICY_VIOLATION`, `WRITE_BLOCKED`, `CLARIFY`, unsupported-data hoặc câu đã `VALID`.
- Mỗi candidate sửa phải quay lại parser, policy, read-only execution và semantic validation đầy đủ.
- Dừng khi trùng SQL fingerprint, trùng error fingerprint, hết call budget hoặc không còn đủ deadline.
- Dùng deadline còn lại của toàn run; không reset đồng hồ khi bước vào correction.
- Correction nên ở trạng thái feature flag/off-by-default cho tới khi ablation đạt tiêu chuẩn dưới đây.

## Tiêu chuẩn tôi đề nghị để duyệt Gate P4

Các điều kiện canonical hiện tại (`no budget overflow`, report recovery theo category, gold leakage
pass) là cần thiết nhưng chưa đủ để kết luận correction có ích. Tôi đề nghị Gate P4 chỉ được bật mặc
định khi đồng thời đạt:

1. `make check` pass; contract, unit, integration, property/fault tests đều tái lập được.
2. `20/20` typed terminal; không crash, không loop vô hạn, không run nào vượt call/repair budget.
3. DB checksum không đổi; safety/policy regression bằng `0`; policy violation không được repair.
4. Gold leakage test pass và runtime package không import evaluator/gold benchmark data.
5. Correction-off tái lập baseline grounded `14/18` trên cùng frozen cases.
6. Correction-on đạt tối thiểu `15/18`, tức phục hồi ít nhất một lỗi thật, và **không làm sai bất kỳ
   case nào vốn đúng** trên frozen set. Nếu chỉ pass injection nhưng không tăng net accuracy, module
   có thể được coi là experimental, chưa nên bật mặc định.
7. Injection suite bao phủ từng supported error class; recovery được báo theo cả numerator và
   denominator, kèm regression rate và stop reason. Mục tiêu hợp lý ban đầu là recovery >= `80%`
   trên các lỗi được đánh dấu eligible, nhưng safety invariant phải đạt `100%`.
8. P95 end-to-end vẫn <= `60 s`; report thêm correction-added latency, số LLM calls và deadline
   exhaustion. Nếu chưa đạt, correction phải fail closed/typed và tiếp tục off-by-default.
9. Báo riêng recovery của lỗi execution-observable và semantic-suspicion; không gộp chúng thành một
   accuracy đẹp nhưng khó giải thích.

## Điều tôi chưa hài lòng, nhưng không chặn việc bắt đầu P4

- `77.78%` còn dưới mục tiêu chấp nhận end-to-end `>= 80%` và mẫu Olist quá nhỏ để suy rộng.
- Grounding giảm token nhưng P95 tăng khoảng `44.5%`; optimization latency cần được theo dõi, không
  thể chỉ nhìn token saving.
- Correction sẽ xử lý symptom ở Layer 5; failure analysis vẫn phải quyết định lỗi nào nên sửa tận
  planner, glossary, semantic view hoặc generator prompt để tránh retry vĩnh viễn.
- Chưa có end-to-end execution benchmark đủ lớn và untouched. Sau P4 nên chạy Olist holdout lớn hơn
  (ít nhất 60 query cases theo roadmap), giữ correction-off/on cùng model, prompt và data snapshot.

## Phán quyết cuối cùng

**Có, project phù hợp để tiến lên Phase 4.** Kiến trúc hiện tại có baseline tái lập, retrieval mạnh,
typed terminal ổn định, safety boundary và bốn lỗi thật đủ đa dạng để đo recovery. Nhưng P4 phải đi
theo thứ tự **Validation Foundation -> bounded correction -> off/on ablation**, không phải thêm một
LLM retry loop trực tiếp sau executor.

Accuracy hiện tại là **đủ để bước vào phase cải thiện accuracy**, không phải đủ để dừng cải thiện.
Nếu Gate P4 đáp ứng các threshold nêu trên, tôi sẽ coi correction là một nâng cấp kiến trúc có bằng
chứng; nếu không, nó chỉ nên tồn tại dưới feature flag và không được bật mặc định.

## Nguồn evidence trong repository

- `docs/evidence/p3_1_gate.md`
- `evals/reports/olist-full-p3_1.json`
- `evals/reports/olist-grounded-p3_1.json`
- `data/artifacts/p3_1/spider-holdout-100_schema_recall.json`
- `realistic_project_creation_codex.md` — Layer 4, Layer 5, Phase 4 và completion matrix
