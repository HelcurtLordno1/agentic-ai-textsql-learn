# Sổ tay thực thi nghiên cứu Data Science

> Tài liệu đồng hành với [`research_plan.md`](research_plan.md). Blueprint quyết định **nghiên cứu gì**;
> sổ tay này quy định **nghiên cứu như thế nào** để kết luận có thể kiểm chứng, tái lập và đưa vào sản phẩm.

## 1. North star và ranh giới

North star không phải là “luôn trả về SQL”. Hệ thống tốt phải tối đa hóa số câu hỏi được giải quyết an toàn:

1. `ANSWER`: trả lời được, kết quả đã qua validation và có assumptions/phạm vi.
2. `CLARIFY`: câu hỏi thiếu thông tin; hỏi lại bằng ngôn ngữ tự nhiên, không bắt user biết schema.
3. `CANNOT_ANSWER`: dữ liệu hiện có không đủ; chỉ rõ thiếu dữ liệu gì.
4. `SAFE_REJECT`: yêu cầu vi phạm read-only/policy hoặc vượt resource budget.

Không được đánh đổi an toàn bằng cách ép mọi input thành SQL. Cũng không được “tăng accuracy” giả tạo bằng cách
từ chối quá nhiều câu hỏi: luôn báo cáo đồng thời **accuracy, coverage và false-refusal rate**.

## 2. Một đơn vị thí nghiệm chuẩn

Mỗi thí nghiệm phải có một experiment card trước khi chạy:

```yaml
id: R?-YYYYMMDD-slug
hypothesis: "Nếu thay đổi X thì metric Y tăng vì cơ chế Z"
baseline_commit: <git-sha>
treatment_commit: <git-sha>
dataset_manifest: <immutable-manifest-or-hash>
hardware_profile: <cpu-gpu-ram-power-profile>
seed_set: [17, 29, 43]
resource_budget:
  max_concurrency: 1
  max_vram_gb: <bounded>
  max_ram_gb: <bounded>
  timeout_s: <bounded>
primary_metric: <one metric>
guardrails: [workflow_completion, valid_sql, p95_latency, peak_ram, peak_vram]
stop_rule: <pre-registered pass/fail rule>
artifacts: <ignored local artifact directory>
decision: pending
```

Quy tắc:

- Mỗi run chỉ thay đổi một biến chính. Nếu phải thay nhiều biến, thêm ablation để tách đóng góp.
- Không chọn checkpoint theo test/holdout. Development set dùng để chọn; holdout chỉ dùng ở gate review.
- Luôn lưu manifest/hash, commit, config và hardware profile; không commit raw data, DB, trace hoặc prediction.
- Không kết luận từ một run nóng máy. Warm-up có kiểm soát, cùng power profile, và theo dõi thermal throttling.

## 3. Taxonomy lỗi tối thiểu

| Lớp lỗi | Câu hỏi chẩn đoán | Evidence cần lưu | Owner |
|---|---|---|---|
| Intent | Có hiểu sai metric, dimension, filter, grain hay “giải thích” không? | normalized intent + assumptions | Question contract |
| Answerability | Schema có đủ dữ liệu không, hay câu hỏi mơ hồ? | outcome + reason code | Question contract |
| Retrieval | Bảng/cột/join cần thiết có trong top-k không? | recall@k + selected schema | Grounding |
| Value/entity | Literal, tên riêng, đơn vị, ngày tháng có map đúng không? | candidate values + match reason | Grounding |
| Planning | Decomposition có đúng grain và join path không? | typed plan | Planner |
| Generation | SQL có sai clause, alias, dialect hay hallucinate identifier không? | candidate + parser findings | Generator |
| Validation | Có lọt unknown column, unsafe SQL, cardinality anomaly không? | validator verdicts | Verifier |
| Execution | Timeout, OOM, DB error hay result shape sai? | bounded runtime telemetry | Executor |
| Semantics | SQL chạy được nhưng trả lời sai ý hoặc chọn sai trong nhiều SQL tương đương? | result comparison + reviewer label | Evaluator |
| Presentation | User có hiểu kết quả, assumptions, độ chắc chắn và bước tiếp theo không? | usability task outcome | Product |

Một case có thể có nhiều triệu chứng nhưng chỉ gắn **một primary root cause** và các contributing factors. Đây là
điều kiện để Pareto chart có ý nghĩa và tránh sửa nhầm tầng.

## 4. Challenge set cho câu hỏi thực tế

Mỗi canonical intent cần một family bất biến ngữ nghĩa:

- paraphrase tự nhiên và đảo trật tự câu;
- tiếng Việt không dấu, typo, viết tắt, VI/EN code-switch;
- thêm yêu cầu trình bày như “giải thích”, “cho tôi biết đủ”, “vẽ bảng”;
- synonym nghiệp vụ và tên thực thể/value gần đúng;
- underspecified filter/time grain cần clarification;
- unanswerable do thiếu bảng/cột hoặc dữ liệu ngoài catalog;
- schema distractor và identifier gần giống để bắt hallucination;
- long-tail SQL: nested query, set operation, window/time logic nếu schema hỗ trợ.

Không suy diễn gold mới chỉ bằng LLM rồi coi là đúng. Variant phải qua semantic invariant check, execution check và
review sample. Giữ family ID để split theo **intent family**, không split ngẫu nhiên từng câu gây leakage.

## 5. Scorecard hai tầng

### Research scorecard

| Nhóm | Metric bắt buộc |
|---|---|
| Correctness | execution/test-suite accuracy; paired wins/losses |
| Robustness | paraphrase consistency; robustness drop; VI/EN gap |
| Reliability | answerability recall; false-refusal; risk–coverage curve; ECE/Brier sau calibration |
| Pipeline | valid candidate; workflow completion; repair success; unknown-identifier escape rate |
| Efficiency | p50/p95; tokens; peak RAM/VRAM; energy/power profile nếu đo được |

### Product scorecard

| Nhóm | Metric bắt buộc |
|---|---|
| Task success | safe resolution rate = correct answer + successful clarification |
| Clarity | user hiểu metric, scope, đơn vị và time grain |
| Recovery | clarification success; retry success; time-to-useful-answer |
| Trust | false certainty; harmful/unsafe execution = 0; evidence discoverability |
| Inclusion | completion rate của non-coder; keyboard/mobile accessibility |

Confidence hiển thị cho user không được lấy trực tiếp từ câu “tôi tự tin 90%” của LLM. Nó phải được hiệu chỉnh từ
observable signals như candidate agreement, schema coverage, validator outcomes, execution/result invariants và
historical correctness trên calibration split.

## 6. Quy trình quyết định sau mỗi run

1. Kiểm tra integrity: đúng commit/config/manifest, không throttling/OOM, đủ sample.
2. Kiểm tra guardrail: workflow, valid SQL, latency và resource không regress ngoài ngưỡng.
3. So sánh paired cases, không chỉ nhìn aggregate score.
4. Đọc toàn bộ regressions hoặc sample phân tầng nếu quá lớn; gắn root cause.
5. Tính uncertainty phù hợp: bootstrap confidence interval cho tỷ lệ; McNemar/paired bootstrap cho paired outputs.
6. Chỉ promote nếu primary metric đạt stop rule và không phá guardrail.
7. Ghi `adopt`, `revise` hoặc `reject`, kèm lý do và thí nghiệm kế tiếp.

Với tập nhỏ, chênh một vài câu có thể chỉ là noise. Báo cả numerator/denominator và khoảng bất định; không chỉ báo
phần trăm đẹp. Với nhiều lần thử, ghi toàn bộ experiment family để tránh chỉ công bố run tốt nhất.

## 7. Data flywheel có kiểm soát

Luồng khuyến nghị:

`query + catalog snapshot → outcome/intent → candidates → validators → execution evidence → reviewer decision → dedup/leakage gate → versioned dataset → ICL/adaptation experiment`

Feedback từ UI chỉ là tín hiệu xếp hàng review, không phải ground truth. Một feedback record hữu ích cần:

- immutable run ID và catalog version;
- user chọn output/assumption nào đúng hoặc chỉ ra expected intent;
- reason code thay vì chỉ thumbs up/down;
- trạng thái review và provenance;
- PII/redaction check;
- split assignment theo intent/database family trước khi dùng huấn luyện.

Thứ tự đầu tư dữ liệu: sửa catalog/alias → hard negative → verified example memory → challenge family → SFT/LoRA.
Chỉ fine-tune khi lỗi còn lại lặp lại đủ nhiều và prompt/retrieval/validator không giải quyết hiệu quả hơn.

## 8. Checklist trước khi tuyên bố cải thiện

- [ ] Hypothesis và stop rule được ghi trước run.
- [ ] Không có gold/eval import trong runtime.
- [ ] Dataset manifest và split không leakage.
- [ ] Baseline/treatment cùng hardware và resource budget.
- [ ] Báo numerator/denominator, CI và paired regressions.
- [ ] Accuracy đi cùng coverage, false refusal và latency/resource.
- [ ] Regression set có thêm case vừa sửa.
- [ ] Non-coder có thể hiểu outcome mà không đọc SQL.
- [ ] Generator docs `--check` pass và `make check` pass.
- [ ] Chỉ sau đó mới commit/push và kiểm tra CI.

## 9. Nhịp review đề xuất

- **Mỗi experiment:** integrity + paired regression review.
- **Hàng tuần:** Pareto lỗi, resource envelope, quyết định thí nghiệm tiếp theo.
- **Mỗi gate:** frozen holdout, challenge suite, no-code task test và architecture decision record.
- **Mỗi release:** failure drill, rollback rehearsal, accessibility/performance smoke test.

Blueprint này chủ ý tách “tín hiệu nghiên cứu” khỏi “cam kết sản phẩm”: paper cung cấp prior và phương pháp; chỉ
evidence tái lập trên đúng dữ liệu, model và laptop của dự án mới được phép quyết định kiến trúc.
