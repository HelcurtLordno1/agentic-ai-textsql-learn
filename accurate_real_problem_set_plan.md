# Kế hoạch phục hồi accuracy từ V4 bằng các thay đổi nhỏ có đối chứng

Ngày chốt thiết kế: 2026-10-16. Nền: `663879a`, snapshot V4 đo được, không lấy V6
làm nền. Tài liệu này triển khai yêu cầu mới của người dùng; ledger chuẩn vẫn là
[realistic_project_creation_codex.md](realistic_project_creation_codex.md).

## 1. Quyết định và nghĩa của “bắt buộc tăng”

Chọn **sửa mất cơ hội trả lời trước, sửa suy luận ngữ nghĩa sau**. Đợt hiện tại chỉ
phục hồi selected relation thiếu cột và false rejection của derived column. Mỗi
thay đổi có công tắc riêng; V4 control vẫn có thể chạy cùng code/harness. Không
thêm planner/critic agent, model, dịch vụ, câu gọi LLM bắt buộc hoặc prompt hướng
nghĩa mới. Không mặc định chuyển default ứng dụng khỏi P6.

Không thể chứng minh trước accuracy của LLM trên câu chưa chạy. Ràng buộc thực sự
có thể thực thi là: **candidate không được promote nếu chưa đo tăng accuracy,
không đạt non-regression, vượt token/latency budget hoặc thiếu safety evidence**.
Nếu không đạt, giữ control và loại candidate; không sửa tiêu chí sau khi xem điểm.
Tests pass, SUCCEEDED và SQL executable là ba quan sát khác semantic correctness.

Đây là nghiên cứu nhỏ theo gate, không phải cam kết điểm benchmark. Hai sửa hẹp
không đủ cơ sở hứa khôi phục toàn bộ Olist57/60 hoặc sửa mọi lỗi semantic.

## 2. Những gì đã đọc và bằng chứng nền

Đọc audit [what_best_thing_to_do.md](what_best_thing_to_do.md), report
[comparison_new4_to_baseline_vn.md](comparison_new4_to_baseline_vn.md), canonical
ledger, V4 reproduction, kế hoạch V5/V6 và evidence power-stop; đối chiếu thêm
`docs/research_plan/local_sql_a1_2026_10_03.md`, lịch sử semantic-proof/backtracking,
monotonic-champion/challenger, data card/metric definitions và business glossary.
Các đề xuất cũ là lịch sử, không mặc nhiên được mang lại vào code hiện hành.

| Quan sát | Ý nghĩa kỹ thuật | Quyết định |
|---|---|---|
| V4 Spider142/200; Olist41/60; P6 Olist57/60 | V4 tốt hơn lịch sử trên Spider nhưng application regression lớn | Báo hai benchmark riêng; không dùng tổng điểm che Olist |
| 8 Olist GROUNDING_ERROR trước generation | Context renderer có fallback column nhưng selected_columns không có; PK-free view bị evidence builder từ chối | Ưu tiên một invariant có thể tái hiện model-free |
| Spider0795 saved draft đúng local nhưng UNKNOWN_COLUMN(avg_pop) | Flat resolver coi derived output là physical column | Sửa đúng lexical scope; không đổi SQL/row-limit policy |
| V4→V6 cùng12Spider:10→9đúng, không gain;13checkpoints chỉ19unique diagnostic IDs toàn nghiên cứu | Tập nhỏ/exposed không phải full/blind evidence | Không dùng selected diagnostic để quảng cáo gain tổng quát |
| Cùng draft ở0098:230rows→LIMIT200 | Policy có thể đổi đáp án mà vẫn cho chạy | Full-result và exact normalized-SQL preservation là gate độc lập |
| Prompt654tokens không đổi mà service13.97→85.63s | Phần lớn chậm nằm ở prefill hybrid/offload/batch, không phải “reasoning sâu” | Giữ full GPU; không dùng hybrid/CPU-only làm accuracy fix |
| Olist001 từng SUCCEEDED nhưng wrong population/count | Scalar shape không chứng minh count đúng | Không thêm scalar/count compiler trong đợt này |
| Critic/CPU edits coverage0 trong full V4 | Nhiều cấu trúc hơn chưa tạo utility | Không thêm critic bắt buộc hoặc broad semantic contracts |

8 failures grounding là opportunity pool tối đa, **không phải8gain đã có**. Khi
được generation, model vẫn có thể sai. Một CTE đúng local cũng chỉ là một case
đã exposed; không chuyển nó thành rule theo ID/schema hoặc chứng minh toàn cục.

## 3. Papers: lấy cơ chế phù hợp, không lấy điểm của paper làm cam kết

Nguồn sơ cấp được kiểm tra lại qua web trong lượt này:

1. [DIN-SQL, 2023](https://arxiv.org/abs/2304.11015): decomposition/schema linking
   giúp các mô hình trong nghiên cứu của tác giả. Không suy ra thêm một lượt plan
   cho Qwen14B hiện tại sẽ có lợi; history của repo đòi hỏi ablation chi phí trước.
2. [CHESS, 2024/2025](https://arxiv.org/abs/2405.16755): retrieval và lựa chọn schema
   nhằm giữ phần đủ dùng trong context nhỏ. Áp dụng ý tưởng đủ thông tin, có budget;
   không sao chép bộ nhiều agents/generate-select loops lên laptop.
3. [The Death of Schema Linking?, v2](https://arxiv.org/html/2408.07702v2): filtering
   có thể bỏ mất cột cần thiết; full schema có lợi trong điều kiện model/context
   của nghiên cứu. Với context4096 của repo, không mở full database vô điều kiện.
4. [SQLCritic, v4](https://arxiv.org/html/2503.07996v4): self-refinement có thể sinh
   lỗi mới; phương pháp có critic được huấn luyện. Một prompted local critic không
   tự thừa hưởng năng lực ấy. Chỉ xét repair khi có evidence lỗi độc lập và paired gain.
5. [Semantic Evaluation with Distilled Test Suites, 2020](https://arxiv.org/abs/2010.02840):
   matching trên một database không đủ đảm bảo equivalence. Dùng synthetic fixtures
   với nulls, duplicate rows, >200rows, nested SQL để bắt lỗi scope/multiplicity.
6. [Lost in the Middle, 2023](https://arxiv.org/abs/2307.03172): nhiều context không
   đảm bảo dùng thông tin tốt hơn. Đây là động cơ kiểm token/utility, không phải
   số đo trực tiếp của Qwen14B trong project.

Tổng hợp cho repo là suy luận thiết kế của chúng ta: **đừng mất required evidence,
đừng đổi incumbent đang đúng, đừng trả thêm token/requests khi chưa cần**. Không
paper nào ở đây chứng minh hai patch sẽ tăng điểm Qwen14B trên mọi schema.

## 4. Failure taxonomy và thứ tự ưu tiên

| Ưu tiên | Lớp lỗi | Evidence/runtime cần có | Đợt hiện tại |
|---|---|---|---|
| P0a | Selected table/view không có grounded columns | Catalog thật, selection/FK/PK, prompt cap | Triển khai recovery hẹp |
| P0b | False UNKNOWN_COLUMN ở CTE/derived output | Source scope + named outputs, negative sibling/alias fixtures | Triển khai resolver hẹp |
| P1a | Read intent chứa metadata “create dates” | Grammar intent và actual write negatives, không bỏ AST/write guard | Kế hoạch sau, không gộp |
| P1b | Invalid owner column/repair không admitted | Chỉ sửa invalid draft theo error; không thay executable draft chỉ vì confidence | Ablation sau |
| P2a | Scalar/group/rank/top-one/output column order | Question evidence độc lập + output contract; ties/negation/multioutput | Chưa triển khai |
| P2b | Population/grain/filter/relation direction/set membership | Owner/lineage/multiplicity proof; counterexamples null/one-many | Chưa triển khai |

Các013/020/043 có cùng biểu hiện ranking nhưng không đồng nghĩa một rule thêm
LIMIT1 luôn đúng. “Average freight” phải phân biệt average item với average order;
review rows không đồng nghĩa distinct orders; customer_id khác customer_unique_id;
COUNT(*) trên customer facts không thay được count orders. Đó là lý do không viết
regex theo vài câu hỏi rồi ép SQL. User có thể hỏi tương tự với population khác.

## 5. Gate E0 — đóng băng control và an toàn vận hành

- Control algorithms: V4 tại663879a; baseline reports/predictions/incident latches
  chỉ đọc và hash trước/sau. Worktree đang có tài liệu người dùng chưa commit:
  không reset/clean/stash phá chúng, không commit dataset/DB/index/traces/secrets.
- Thêm opt-in flags cho hai patch. Variants: `obligation-cpu` (control),
  `v4-grounding` (chỉcontext), `v4-scope` (chỉresolver), `v4-reliability` (cảhai).
- Sửa monitor clock drift là infrastructure gate riêng, tái dùng cơ chế request-ID
  freshness của nghiên cứu trước sau khi review; không nới sensor timeout/threshold.
  Monotonic elapsed-time bounds và Windows Stopwatch heartbeat, không so timestamp
  wall clocks giữa Windows/WSL để quyết định sample freshness.
- Cap300–600MHz được user xác nhận. Profile thử mới
  `qwen14b-v4-600-b16`:GPU41,CPU8,num_batch16,context4096,deadline180/request120s.
  Đây là pilot thực thi mới so với full-GPU600batch64/hybrid600 đã breach; **không
  resume chúng**. Đổi batch không được ghi nhận là lợi ích của thuật toán SQL.
- Giữ RAM>=8GiB,swap<0.25GiB,VRAM<14GiB,temp<68C,power<70W,clock<=600MHz,
  batch benchmark1,unload,cooldown>=60s;monitor dualWindows/WSL liên tục0.5s.
  Một pilot không chứng minh không có transient; mọi actual breach dừng cảchuỗi.
- Source/config/HEAD freeze trước inference; fresh experiment paths; không sửa
  source hoặc move HEAD giữa chạy. Live docs để uncommitted. Không auto-retry breach.

## 6. Gate E1 — complete context chỉ khi evidence chắc chắn sẽ fail

**Hypothesis:** loại bỏ đúng terminal cơ học “Selected relation has no grounded
columns” tạo cơ hội sinh SQL mà không đụng prompt các câu đang hoạt động.

Thuật toán:

1. Validate context identity/catalog và selected names như V4.
2. Tính effective columns theo quy tắc V4: selected + PK + FK giữa selected relations.
3. Nếu mỗi relation đã có cột: trả nguyên context, không reorder/render/prompt lại.
4. Chỉ cho relation thực sự rỗng: lấy các cột từ catalog của chính relation ấy;
   không thêm bảng mới, không đoán tên/cột/ngữ nghĩa, không kéo full schema.
   Table-level retrieval evidence là căn cứ để relation ở selection, không phải
   căn cứ khẳng định mỗi cột mới relevant. Ghi nguồn completion rõ trong trace.
5. Re-render typed context, kiểm schema budget1200 và full prompt2800 trước model.
   Nếu overflow/empty catalog/unknown names: typed GROUNDING_ERROR, zero generation;
   không cắt bừa relation, giảm safeguards hay nâng context/token cap.

Không chọn cột đầu tiên chỉ để né exception: cột ấy có thể không đủ trả lời. Giữ
all columns **chỉ của relation rỗng**, có hard budget, là tradeoff minh bạch và nhỏ.
Nếu relation quá rộng, abstain chứ không bịa relevance. Nghiên cứu packer tốt hơn
chỉ mở sau khi đo overflow thực sự.

Evidence gate: renamed schemas, PK-free views, composite/implicit FKs, unknown
columns/cross-catalog, wide relation overflow và no-change prompt fixtures. Replay
260saved contexts: mọi prompt V4 xây được phải byte-identical;8known failures phải
đến được bounded prompt hoặc báo rõ overflow. Không coi hồi phục prompt là gain accuracy.
Chạy `make check` trước khi ghi E1 VERIFIED.

## 7. Gate E2 — nhận diện derived output mà không đụng SQL semantics

**Hypothesis:** một column không có trong physical catalog có thể hợp lệ nếu được
expose bởi source CTE/derived table trong chính lexical scope của reference.

Chỉ mở ngoại lệ tại nhánh legacy UNKNOWN_COLUMN cho unqualified reference khi
resolve được duy nhất source có named output. Không dùng global tập tấtcảaliases,
không cho sibling CTE alias lọt vào scope, không đoán output từ SELECT* không rõ.
Giữ nguyên policy cấm write/internal tables/functions, bounded read-only executor,
SQL normalization và điều kiện LIMIT V4. Unknown/ambiguous unsupported case vẫn fail
closed hoặc để executor xác định lỗi trong boundary hiện có; không claim resolver
này giải quyết đầy đủ SQLite name-resolution.

Tests bắt buộc: nested CTE, derived table, explicit output list (abstain nếu renderer làm mất binding), alias shadow,
sibling leakage, unknown physical column, ambiguous sources, CTE có hidden write,
window/nested aggregate và >200rows. Với mọi V4 candidate policy đã allow:
**allowed không đổi và normalized SQL phải giống hệt**, không chỉ so status.
Chạy lại full-result với saved prior-correct bị tác động; đặc biệt không lặp0098.
`make check` và replay riêng E1/E2 trước combined candidate; không gọi2patch là
một causal mechanism duy nhất.

## 8. Gate E3 — giao thức đo, chống overfitting và tiêu chí bác bỏ

### 8.1 Offline trước model

- SavedSQL/context replay dùng để kiểm cơ chế, không giả làm generation mới.
- Không runtime import evaluator/gold/case IDs. Real cases ở ignored artifacts;
  committed tests dùng synthetic/renamed schemas và negative counterexamples.
- Hash baseline reports/predictions/stops trước/sau; logs của candidate fresh.
- Đếm prompt unchanged/changed/recovered/overflow, token p50/p95/max, SQL mutations,
  prior-correct losses, model requests thêm và scope false allowances/rejections.
- Không phát triển semantic heuristic theo gold khi offline đang đọc nhãn chấm.

### 8.2 Pilot và full execution

1. Safe idle/no stale Windows+WSL jobs, resident models empty, sensors hoạt động.
2. Freeze source. Chạy đúng1caseSpider và1caseOlist bằng guarded sequence, rồi
   pause clean để kiểm checkpoint/cleanup và chấm offline; không auto-full khi pilot
   chỉ SUCCEEDED mà chưa kiểm semantic result.
3. Qua hai pilot thì thêm3batch ở prefix gốc, pause/chấm lại: tối thiểu5iterations sạch trước full. Sau đó tiếp tục cùng profile/source và manifest200+60. Nếu pilot
   sai hoặc thêm regression: dừng quality gate; không sửa source rồi nối checkpoint.
4. Hardware pilot có thể bác bỏ profile ngay. Sau actual resource/sensor breach,
   latch giữ nguyên, không tự đổi clocks/offload/batch/threshold để tiếp tục.
5. Không cần đợi full nhiều giờ trong phiên tương tác: chỉ handoff khi tmux thực sự
   chạy và state được kiểm; cung cấp attach/status/pause/resume. Không ghi COMPLETE
   trước khi đủ reports, manifest IDs và cleanup validated.

Control matched trên cùng profile/budgets là chuẩn causal. Saved V4 450MHz là
historical reference, không phải matched600MHz latency control. Dùng flags để chạy
matched V4 trên cùng profile khi cần xác nhận; không quy chênh hardware vào patch.
Full run mới là candidate evaluation, không phải automatic promotion. Nếu chưa có
matched control/ablation cần thiết, trạng thái nghiên cứu vẫn IN_PROGRESS.

### 8.3 Promotion contract chốt trước kết quả

- Full cases giữ đủ denominator200/60, không bỏ failures hoặc chọn lần rerun đẹp.
- Tối thiểu cải thiện **riêng cảhai** so V4(>142/200 và>41/60) cho candidate combined;
  patch context riêng không đòi Spider gain nếu đã chứng minh Spider untouched.
- Zero known prior-correct losses trong affected-path replay; full paired report
  liệt kê mọi gain/loss và nhóm language/schema/difficulty. Không dùng net gain
  để giấu regression; loss mới phải điều tra trước promotion.
- Prompt các unaffected cases byte-identical; recovered cases<=2800estimatedtokens,
  context<=4096,output768,maxrequests3 không tăng. Không có mandatory extra LLM call.
- Matched service median<=1.20×,p95<=1.25×control; tách setup/load/prefill/decode,
  cooldown,batchwall và operator gaps. Không so mean200 với mean12.
- Safety: zero resource/sensor failures cho qualification run, cleanup verified.
- Đủ paired significance/interval mới claim superiority; exposed260cases là
  regression/development evidence. Fresh schemas/paraphrases chưa dùng để thiết kế
  phải được khóa trước acceptance riêng, không mượn “holdout” cũ sau nhiều lần xem.
- Không đạt bất kỳ mục nào: không promote; giữ control. Không sửa ngưỡng để hợp kết quả.

## 9. Sau đợt này: lộ trình nhỏ, không biến thành rewrite

Chỉ khi E1/E2 đo có utility mới mở **một** lớp lỗi tiếp theo. Ưu tiên false read
intent hoặc operational unknown-column repair trước semantic override. Một patch
mỗi vòng: definition→negative fixtures→saved replay→makecheck→guardedpairedtest.

Đối với population/grain/rank, trước hết cần independent reviewed labels, owner
binding và counterexamples; detector UNKNOWN được phép abstain. Có sẵn executable
incumbent thì không thay bằng SQL mới chỉ vì model confidence/plan nghe hợp lý.
Không dùng COUNT(*)/LIMIT1 compiler phủ cảmodels để cứu vài câu đã biết.

Hướng tới Olist57/60 là mục tiêu ứng dụng, không là điều kiện để cố mở rộng patch
hiện tại. Nếu phục hồi context vẫn sai, báo failure mới và thử một hypothesis nhỏ;
không mang toàn bộ V5/V6 trở lại hoặc lặp benchmark cho đến khi có điểm đẹp.

## 10. Sổ thực hiện (bổ sung bằng evidence, không tự coi plan là kết quả)

- E0: VERIFIED (offline) — make check:269passed/1Ollamadeselected; Ruff/format304files và mypy120sources pass. Request-ID monitor/RAW deadline/cooldown tests pass; mock HTTP xác nhận GPU41/batch16/context4096/output768/keepalive0, các profile cũ giữ batch64. Calibration5batch ở§10.5; không chứng nhận safety toànfull.
- E1: VERIFIED (offline) — make check280passed/1deselected; 251prompt byte-identical/khớp savedSHA,8context recovered,1case không có context; maxprompt1724estimatedtokens. Evidence local: `data/artifacts/v4-reliability-20261016/context-replay.json`. Evidence engineering không dùngmodel.
- E2: VERIFIED (offline) — make check303passed/1Ollamadeselected; Ruff/format307files,mypy120sources. Replay255policy evaluations:249allowed giữ nguyên toàn bộ decision/SQL;2formerly-rejected evaluations cùng1CTE mới được allow, local equivalent539rows. Nested aggregate prior-correct0098 vẫn230rows;23input hashes giữ nguyên.
- E3: IN_PROGRESS — workloadfullGPU600b16RESOURCE_STOP;fullGPU600b16 dừngSpider30+Olist1 vì73.39W;§11 là remediationhiện hành,khôngresumeprofileđó.

Lệnh chạy/handoff và số đo thật sẽ được bổ sung sau kiểm tra. Không resume bất kỳ
checkpoint V5/V6 cũ bằng code/profile của kế hoạch này.


### 10.1 Evidence và cách tái lập offline

```bash
make check
uv run --frozen --extra ui --group dev python -m scripts.audit_v4_reliability
```

Audit không tạo RuntimeBundle, không gọi generation/embedding; evaluator chỉ đọc
SQL đã checkpoint và frozen labels/gold sau inference lịch sử. Chi tiết local ở
`data/artifacts/v4-reliability-20261016/offline-replay.json`;0modelrequests.
Các23hash đầu vào gồm4baselinefiles và19incidentlatches giữ nguyên. Count2newly
allowed evaluations là draft/repair trùngSQL của **1case**, không phải2gains.

Phát hiện trong negative tests: pinnedSQLGlot renderer làm mất explicitCTEoutput
list (`WITH x(c) AS ...`), vì vậy resolver hẹp abstain dạng này, không mở permission
rồi thực thi SQL đã đổi binding. Không sửa globalrenderer hoặc LIMIT để né test.
New flags chỉ bật qua variantsoptin; application default/champion vẫnP6.

### 10.2 Handoff chạy laptop

Branch mới `v4_incremental_reliability_20261016`, HEAD663879a; source thay đổi chưa
commit và được pin bằng digest/backup local trước inference. Không sửa code/.env/
indexes/manifests hoặc chuyểnHEAD khi đang chạy và khi muốn resume cùng checkpoint.
Tên experiment mới: `v4-smallfix600b16-20261016`; profile `qwen14b-v4-600-b16`.
Model/context/request/tokenbudgets không đổi; chỉbatch16/cap600 khác hardwareV4
historical. Chưa claim matched latency gain hay end-to-end accuracy improvement.

```bash
cd '/mnt/d/desktop_informations/vnpt ai/agentic_text_to_sql'
# Lệnh tạo mới do agent thực hiện sau preflight; không chạy lại tên này nếu đã tồn tại.
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks run \
  --name v4-smallfix600b16-20261016 --variant v4-reliability \
  --profile qwen14b-v4-600-b16 --models-dir /mnt/c/Users/ADMIN/.ollama/models \
  --max-batches 2
# Sau2pilots sạch/chấm offline, resume --max-batches 3 để đủ5iterations, rồi chấm lại trước full.
tmux attach -t v4-smallfix600b16-20261016
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks status --name v4-smallfix600b16-20261016
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks pause --name v4-smallfix600b16-20261016
# Chờ PAUSED + cleanup xong trước resume:
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume --name v4-smallfix600b16-20261016
```

Ctrl+b rồi d chỉ detach; không dừng job. Sau unexpectedshutdown: xác nhận không còn
stalejobs,safeidle vàcap đã active, dùng `resume --name v4-smallfix600b16-20261016
--recovery-pilot`, kiểm1caseguarded rồi mới ordinaryresume. Resource/sensor stop có
latch: lệnhresume sẽ từ chối; không xóa latch hoặc dùng recoverypilot để bypass.
Vẫn cần remediation được xác nhận và experiment mới sau actualbreach.

Kết quả pilot/full thực tế sẽ được ghi bên dưới; lệnh tồn tại không có nghĩa đã chạy
hoặc đã hoàn tất benchmark. Mục tiêu promotion ở§8.3 giữ nguyên khi biết kết quả.


### 10.3 Freeze đã thực hiện trước inference

HEAD `663879ab034dce1c604784a45504a03753926282`; runtime sourceSHA
`582d2e7bff583e365ab8cf1dd8e7e2bd9d4b47aac700991f416721d81062d622`.
Local source backup `data/artifacts/v4-reliability-20261016/frozen-source.tar.gz`;
`preflight-and-freeze.json` pin profile/digests và10dualmonitoridle samples:
RAMmin17.815GiB,tempmax50C,powermax18.29W,VRAMmax1152MiB,modelsresidentempty;
không có staleWSLjob/nativeLLMrunner. HaiPowerShellscripts syntaxpass.
Tmuxsequence đã launch ởPILOT với --max-batches2; thông tin này không claim pilot
đã pass hoặc full đã chạy. Code/HEAD giữ nguyên saulaunch; chỉdocs/evidence cập nhật.


### 10.4 Hai pilot đã kiểm tra

Spider1/200 vàOlist1/60 đều resource/cleanup VERIFIED, dừngPAUSED sạch;
chấm offline2/2đúng, V4cũng2/2,0gain/0loss,1generationrequest/case.
Source/config/HEAD và251unaffectedprompthashes được giữ. Guard119observations,
powerpeak67.76W,temp59C,clock600MHz,RAMmin16.388GiB;native371samples,peak67.74W.
Service15.035s/15.545s sohistorical12.793s/11.900s; không claim matched-profile
latency gain. Đổi batch có chi phí thấy được; full median/p95 và matchedcontrol
vẫn cần cho promotion. Đây không là chứng nhận ổn định260cases hoặc tăngaccuracy.
Evidence local:`prefix-2-quality.json`,runlogs/guardjournals.
Đã yêu cầu thêm3batchgiữ nguyênsource/profile trước full; mọi breach vẫnstop.

**Kiểm chi phí token bổ sung:**251drafts V4 có tổng225651estimatedinputtokens.
8prompts vừa phục hồi có tổng12157, tương đương+5.39% nếu mỗi câu gọi đúng1draft.
Đây là chi phí trả lời8câu trước đó fail trướcgeneration, không phải bơm thêmtoken
vào251câu đã hoạt động (delta0 trên cácprompt ấy). Không phải token đo Ollama hoặc
dự báo tổng gồmrepair/output. Sharedcap3requests và input2800/output768 không đổi.
Nếu full xuất hiện repair nhiều hoặc latency vượt acceptance, không promote dù
context invariant đã được sửa. Không xem “không tăngcap” là “không tăngtotalcompute”.


### 10.5 Năm iterations đã chấm; tiếp tục full

Sau5guardedbatches, sequence PAUSED sạch ởSpider4/200+Olist1/60, toàn bộownedPIDsnull.
Offline5/5đúng vsV4cùng5/5,0gains/0losses,1request/case;294guardobservations,
powerpeak68.48W,temp59C,clock600MHz,RAMmin16.388GiB. Tấtcảunload/cooldown/cleanup
hoàn tất,khôngresource/sensorstop. Evidence:`prefix-5-quality.json`.
Đây là calibration/development evidence trên5caseđãexposed, không phải accuracygain
hoặc chứng nhận poweran toàn cho260cases. Các2patch không được exercised đủ bởi5
prompt này; utility của8groundingrecoveries/CTE còn phải đo trongfull.

Đã yêu cầu ordinaryresume **khôngmaxbatches** để hoàn tấtSpider rồiOlist tuần tự.
E3full/accuracy/promotion vẫnIN_PROGRESS; E0/E1/E2 chỉVERIFIEDởengineeringoffline.
Không đổi code/profile/GitHEAD giữapilot vàfull. Commandsattach/status/pause/resume
ở§10.2 dùng đúngexperimentnày. Nếu fullgặpactualbreach:stop vàgiữlatch,khôngretry.

**Livehandoff đã xác nhận:** sequenceRUNNING,2pilot_passed=true,worker/server/proxy
PIDs alive,tmuxpane_dead0,noresource/pause/cleanuplatch;HEAD/source/23priorhashes
không đổi. Nativeownedserver readyOllama0.30.10. Snapshot:live-handoff.json.
Full kế tiếp Spider0499;guard đang hoạt động,không suy ra fullsuccess từsnapshot.

## 11. Khắc phục sau power stop 73,39 W — supersedes live handoff ở§10

### 11.1 Incident đã xác nhận trước khi sửa code

`v4-smallfix600b16-20261016` hiện **RESOURCE_STOP**, Spider30/200+Olist1/60,
không còn đang chạy. Case kế tiếp `spider_regression_0038` (concert_singer, hard)
bị ngắt trước checkpoint. Guard49samples ghi73.39W ở600MHz,56C,VRAM10103MiB,
RAMmin17.036GiB,swap0.08456GiB;cleanup_error=null. Native owner xác nhận server/
job/runners đã đóng; mọiownedPIDnull. Giữ toàn bộ30+1predictions,latch vàjournals.
`KeyboardInterrupt` nằm ởsocketrecv vìguard ngắtrequest, không là căn cứ sửahttpx
hoặc tăngnetworktimeout để bỏ powerstop. Không resume sequence này.

Năm pilot chỉ là5observations, không phải bằng chứng boundedpowercho260cases.
Trướcfailedcase còn có30Spider/1Olist hoàn tất vàguardpower<=69.15W;không lấy
thành tíchprefix làm đảm bảo transient kếtiếp. Giao trướcfull là snapshotđangchạy,
không chứng nhận fullổnđịnh; lần này phải ghi rõ exposure/unknown và nguyênnhân dừng.

### 11.2 Capability check và lựa chọn remediation

Đọc nativeWindowsNVSMI, không chỉ bảnWSL:RTX A4500Laptop,driver597.06,
GPUCurrentPowerLimit82.54W,Default80W;capgraphics600MHz không đổi wattceiling.
Thử `nvidia-smi.exe -i 0 -pl 60` cho thông báo **not supported in current scope**
nhưng exitcode0. Vì vậy **exit0 không đủ xác nhận hardpowercap**. Không claim60W đã
active,không chạy lạiCUDAprofile đãbreach. Audit ở`data/artifacts/v4-stability-20261016/`.
[NVIDIA docs](https://docs.nvidia.com/deploy/nvidia-smi/index.html) phân biệt clock
locking với wattlimit; hỗ trợ thaypowerlimit phụ thuộc thiếtbị/quyền. Không dùng
smoothing/debounce/averageonly hoặc nâng70W để “sửa” incident.

User mới yêu cầu ổnđịnh nhất vớicap600 và triểnkhai/chạy lại. Với driverhiệntại,
remediation chọn **Qwen14B CPU-only**,explicitGPU0,CPU8,promptbatch64;giữcap600
nhưng không đưa generation sangCUDA. Đây là thayđổi execution làm mất nguồn tảiGPU
chính, khác việc thử giảm batch/offload vài tầng đãfail. Giữ nguyênSQLpipeline,
2mechanicalpatches,weights/seed/context4096/input2800/output768/maxrequests3.
Không đổi sangmodelnhỏ,không thêmprompt/agent/semanticcompiler.

CPU không miễnphí vềtime/RAM: đo thực tế pilot,trìnhbày tradeoff trước full. Không
quảngcáo CPU nhanh hơn hoặc accuracycao hơn. BoundedCPUcase900s/request300s nhằm
tránh dùngdeadlineGPU180s để épCPUtimeout;không tăngrequests/output/context. Chỉ
CPU0 được phép bound>180,profileGPUcũ giữ120/180. NếuCPU pilot vượtRAM8GiB/swap0.25GiB
hoặc bất kỳ sensor/resource threshold nào:stopkhôngretry,không nới limit để épfull.
Không có bảo đảm toán học mọiphầncứng/OS sẽ khôngfail;guardphải được giữ cảCPU.

### 11.3 Gate R0 — preservation, idle, launch contracts

- Hash31oldpredictions cùng reports/latch/plan/runtimeidentities trước/sau; không
  migrate/mixCPU vào checkpointGPU. Fresh experiment `v4-cpu600-stable-20261016`.
- No staleWindows/WSLjobs,residentmodels empty vàsafeidle dualmonitor trướcpilot.
- Newprofile `qwen14b-cpu600-stable`:GPU0,CPU8,batch64,f16KV,flashattentionoff,
  case900/request300;RAM>=8GiB,swap<0.25GiB,VRAM<14GiB,temp<68C,power<70W,
  graphics<=600MHz,batchcase1,unload,cooldown60s,dualmonitor0.5s.
- Native launcher phải nhậnFA/KV từprofile;không hardcodeq8/FAon khiCPUprofile
  yêu cầuf16/off. Verify actualHTTPGPU0 và launcharguments bằng deterministictests.
- Cleanupwait có boundcase+cooldown+grace,heartbeatgiữsuốtcleanup;khôngkillworker
  sau200s khiCPUcase hợp lệ cònchạy. Core requestbudget vẫnmax3,đếm cảretries.
- `make check` trước claimR0VERIFIED;freeze source/HEAD/config trướcinference.

### 11.4 Gate R1 — màn hình tmux sống độc lập, không che workload stop

Worker đượcphép exit khi COMPLETE/PAUSED/RESOURCE_STOP; đó là kếtquả kiểmsoát được.
Thêm cửa sổmonitor độc lập trongcùngtmuxsession,mặc địnhattach vàomonitor. Monitor
chỉđọcstate,journals vàtailrunlog;không generation,khôngresume/retry,không xóa latch.
Nếu worker dừng,màn hình vẫn hiển thị **RESOURCE_STOP/FAILED**,observedreason,
checkpoint và hướngxửlý;không dùng “monitoralive” làm “benchmarkhealthy”. Latch
có độưutiên hơnstateRUNNING cũ. Monitorerrors=>UNKNOWN,khôngsuyđoán COMPLETE.

Test statusrendering,latchedstoppriority,missing/invalidstate,liveness,tmuxwindow
selection vàresumevẫn chặnincidentlatch. Đây là usabilityfix,không powerremediation.
`make check` lại trướcR1VERIFIED. Giữexitcode workerthật trong cửa sổworker/log.

### 11.5 Gate R2 — calibration có đo chi phí, rồi full tuần tự

1. Newsource/profile/freshpaths. MộtguardedcaseSpider vàmộtOlist rồiPAUSEDcleanup;
   chấmoffline sau inference. VerifyGPU0 ởHTTP/runtime/runnerprocessor telemetry,
   Power/RAM/swap toànrequest vàprefill/decode/load/service/cooldown.
2. Nếu2pilotpass,no losssoV4,đủ budget/RAMheadroom:3batch tiếp theo ởprefixgốc,
   PAUSED/chấm lại đủ5iterations. Không coi5pass là lời hứa không cóstopvềsau.
3. Chỉ khi gatespass mới ordinaryresume fullSpider200+Olist60 tuần tự,khôngmaxbatch.
   Monitor tới checkpointfullmới saucalibration trướchandoff `tmux attach`.
4. Đánh giá stoppedcase0038 saufull bằngprefixthứ31 theođúngmanifest;khônghardcode
   caseID vào runtime,không dùnggoldtronggeneration. Có thểdiagnose savedcontext
   model-free trước; không đổi manifestfull để giả là chưaexposed.
5. Anyactualbreach=>stopboth,preserveevidence,noretry. Dashboardvẫnphải báostoprõ.
   Không có”catchallcontinue”,”whiletrue rerun”,timeoutdài vôhạn hayfalse COMPLETE.

R0/R1/R2: IN_PROGRESS/NOT_STARTED/NOT_STARTED khi bổ sungplan này, chưa cóCPUmodelrun.
Fullaccuracy vẫnchưađượcchứngminh vàpromotioncontract§8.3giữnguyên. CPUlatencyđược
báo riêng,không dùngfullGPU450historical làm matchedCPUperformancecontrol. Nếu CPU
quá chậm nhưng muốnCUDA600, điều kiện tiếp theo làhardpowercap hỗ trợ/đượcverify;
không quay lại profile600b16 chỉvì màn hìnhmonitorđãđẹp hơn.

**R0 offline VERIFIED:**makecheck311passed/1Ollamadeselected,46.00s;Ruff/format308files,
mypy120sourcespass. MockHTTPCPU0/batch64/context4096/output768/timeout300;native
launchGPUprofiles giữFA1/q8,CPU nhậnFA0/f16. CPUdeadline900bounded,901rejected,
GPUdeadline>180rejected. Cleanupheartbeatthrough960s tested. NativePSsyntaxpass.
23oldincidentfileshashpreserved;6dualidle samplesSAFE,RAM>=17.766GiB,power<=17.91W.
NoCPUmodelrequest yet. R1 persistentmonitor IN_PROGRESS.

**R1 offline/integration VERIFIED:**makecheck317passed/1Ollamadeselected,42.17s,
Ruff/format311files,mypy120sourcespass. Actualtmuxsmoke oldincident:monitorpane
alive,workerstop/latch nguyêntrạng,RESOURCE_STOP+73.39W+30/200+1/60 hiểnthịrõ.
Lỗi tmuxdisplay-message khiwindowkhôngtồn tại được phát hiện bằng integration;
fixdùnglist-windows,tránhrespawnsaiwindow. UI cắt logtheosizeterminal đểstatus
khôngbịJSON/traceback đẩykhỏimàn.6monitor testsbao gồmstoppriority/readonly/
unknown/cleanup/reportvalidation/windowselect/viewport. R2CPUcalibration tiếp theo.
Đã thu hồiWSLfilecache nhànrỗi,không đóng app hoặc restartWSL;RAMidle~18.25GiB.
CPUmodelweights metadata8.639GiB;RAMrunning>=8 vẫnfailclosed,không nới để thử.


### 11.6 Hai CPU pilots đã đo và chấm offline

Freshsequence `v4-cpu600-stable-20261016`,sourceSHA
`b5e80887c0636c911119cc2feaf81f30cf881c52ea1109223205d6e886e60eab`,HEAD663879a.
Hai pilotPAUSED sạch1Spider+1Olist,ownedPIDsnull;offline2/2correctsoV4same2/2,
0gains/losses,1generationrequesteach. ActualOllamaPS xác nhậnQwen14Bdigestđúng,
size_vram0/context4096;runtime gửiGPU0/CPU8/batch64/case900/request300.
Guard460observations,powermax26.09W,temp52C,VRAM<=1142MiB,RAMmin8.606GiB,
khôngbreach/monitor/cleanupfail;native ghipeak27.75W. RAMheadroom tớilimit8GiB
còn~0.6GiB trongpilot;khônghứa cácappkhác khôngảnhhưởngđếnresourceguard.

ServiceSpider80.138s vàOlist109.529s;đây làchi phístability fallback,không speedup.
PrefillSpider54.183s/decode20.133s/load9.921s. Không bỏcostCPU hoặcđánhđồngvới
profileGPU15s. CPUfull sẽchậmhơn nhiều và tiếp tục bịquality/accuracygates ràngbuộc.
MaxCPUdeadline900 khônglàm modelthôngminhhơn,chỉcho budgetthờigian bounded;
input/output/requests vàretrieval/prompt vẫngiữnguyên. Khôngclaimcalibration5/260
hoặcfullaccuracygain từ2pilot. `prefix-2-quality.json` làevidence local.

Đã requestthêm3prefixbatches,cùngsource/profile;chưaresumeGPU30+1 hoặccopy chúng
sangCPUcheckpoint. Màn hìnhtmuxmonitor alivevàhiểnthịđúngphase;khônginference/retry
trongmonitor. Full chỉcontinuation sau5batchpass/chấmlại vàcleanup.


### 11.7 Commands của CPU remediation — dùng thay§10.2

```bash
cd '/mnt/d/desktop_informations/vnpt ai/agentic_text_to_sql'
tmux attach -t v4-cpu600-stable-20261016
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks status --name v4-cpu600-stable-20261016
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks pause --name v4-cpu600-stable-20261016
# Chỉ sau PAUSED + cleanup sạch:
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume --name v4-cpu600-stable-20261016
# Nếu chỉ đóng nhầm monitor, mở lại monitor mà không restart workload:
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks monitor --name v4-cpu600-stable-20261016
```

Attach mở cửa sổmonitor,Ctrl+b rồi0 xemrawworkerlog;Ctrl+b rồi d detach.
MonitorCtrl+C chỉđóngviewer,khôngđổiworkload;dùngpausecommand đểyêucầu dừngsạch.
Sau unexpectedshutdown:verifycap600,nostalejobs,safeidle,`resume --name
v4-cpu600-stable-20261016 --recovery-pilot` rồi kiểm1guardedcase trướcordinaryresume.
Resource/sensorlatch luônchặnresume;không dùngrecoverypilot đểxóahaybypassstop.
KhôngresumeGPUexperiment30+1 vớiCPUcode/profile. Source/HEAD vẫnfreeze;
backupCPU localở`data/artifacts/v4-stability-20261016/frozen-source.tar.gz`.


### 11.8 CPU calibration5 đã chấm, full continuation

CleanPAUSEDSpider4+Olist1,ownedPIDsnull. Offline5/5correctsohistoricalV4same5/5,
0gains/0losses,1request/case. Guard1061samples,max33.96W/52C,minRAM8.606GiB,
swap<0.25,VRAM~1142MiB;0resource/sensor/cleanuperrors,unload/cooldownvalidated.
ServiceCPU78–110s trên5case; khôngclaimlatencygain. APIQwen14Bsize_vram0đãghi
bằngchứng;modelweights/prompts/context/budgets khôngđổi.

Rerun `scripts.audit_v4_reliability` cũnggiữnguyên251workingprompts/249oldallowed
policydecisions+SQL,8contextrecoveries/1CTErecovery;old0098full230rowskhôngtruncated
bằngSQL. Goldchỉđọcoffline sauCPUinference đãPAUSED. Tấtcảoldincident23hashes
vàsource/HEADfreeze đượckiểmtracònđúng. Evidence:`prefix-5-quality.json`,
`offline-replay.json`,`incident-preservation.json` trongCPUartifactdirectory.

Đã requestresume khôngmaxbatch đểchạyfullSpider200rồiOlist60. R2fullIN_PROGRESS,
calibrationpass khôngchứngminh260cases hoặcunseenaccuracy;mọisafetyguard cònnguyên.
Nextfullcase0499 đượcquan sát tiếp trướcfinalhandoff. Nếusensor/resourcebreach,
workerphảistop,monitorcònhiểnthịnguyênnhân;khôngauto-retryhoặcđổiprofilegiữachừng.


### 11.9 Live handoff đã kiểm lại sau full batch đầu

SequenceRUNNING tạiSpider5/200+Olist1/60;6guardedbatches/1292observations hoàn tất,
0resource/sensor/cleanuperrors. Maxguard33.96W,minRAM8.606GiB. Firstfullcase0499
đãcheckpoint/unload/cooldown;batch kếtiếp đangchạy. Nămcalibrationcaseđãchấm5/5;
không tựgáncorrectness chocasefullchưachấm. Monitorpanealive/selected,ownedworker/
server/proxyalive,khônglatch/pausemarker,HEAD/sourcefreeze và23oldincidenthashes
unchanged. Snapshot `data/artifacts/v4-stability-20261016/live-handoff.json`.

Đây làtrạngtháiđangchạy đãquan sát,khôngphải fullCOMPLETE hoặc lời hứa khôngcó
lỗihardware/OS/resourcevềsau. Guardstopgiữnguyên vìan toàn;monitor độc lập giữ
khảnăngquan sát nếu cóstop. Người dùng dùngcommand§11.7;khôngresumeGPUexperimentcũ.


## 12. Phục hồi lỗi cảm biến sau checkpoint Spider44 — kế hoạch trước khi sửa

User yêu cầu sửa nhóm lỗi liên quan và tiếp tục benchmark tới hết. Incident
`v4-cpu600-stable-20261016`: Spider44/200 + Olist1/60, timeout nvidia-smi WSL
0.5s ở preflight case45, samples=0/observed_peak=null/cleanup_error=null.
Không có bằng chứng resource vượt ngưỡng trong incident này. Latch và toàn bộ
checkpoint cũ được giữ nguyên. Đây là phê duyệt sửa lỗi và calibration mới,
không phải quyền bỏ guard, nâng ngưỡng hoặc tự retry sau một safety stop mới.

### 12.1 Phạm vi và nguyên nhân cần kiểm chứng

- WSL sample_resources và Windows Get-Text2SqlSample đều tạo process nvidia-smi
  mỗi vòng; chi phí khởi động lặp lại có thể vượt deadline dù driver hoạt động.
- Startup cảm biến phải hoàn tất trước inference, có timeout bounded riêng;
  khi đang chạy vẫn yêu cầu mẫu tươi, không dùng cached-safe để che lỗi.
- Thay process-per-poll bằng stream nvidia-smi persistent ở cả WSL/Windows,
  đọc mỗi 200ms, kiểm malformed/EOF/nonzero exit/stale/missing/NaN/negative/
  multipleGPU/utilization/clock; giữ max cả power average và instant. Giữ
  peak các sample giữa hai lần guard đọc, không mất một spike đã quan sát.
- Kiểm mọi nhánh cleanup: lỗi startup, lỗi giữa request, Ctrl+C, childfail,
  unloadfail; cảm biến owned phải được đóng, stop cũ không bị ghi đè.
- Không sửa generator/retrieval/prompt/SQL policy/model/tokens/deadlines/profile.

### 12.2 Gate S0 — provenance và resume có bằng chứng

Backup/hash read-only sequenceplan/state/latches/predictions/runtime/backend/
provenance/logs trước sửa. Source snapshot cũ phải khớp runtime digest.
Vì source digest bao gồm guard, không sửa runtime.json tại chỗ hoặc xóa latch.
Tạo continuation experiment mới, copy đúng byte prefix44+1, giữ model/backend/
settings/resource profile/manifest/DB/index/GitHEAD; chỉ cho migration khi diff
source nằm trong allowlist monitor/orchestration. Ghi migration ledger với
old/newsource, hashes từng file thay đổi, hashes prefix và incident, per-suite
prefix length. Báo cáo cuối phải giữ lineage; không ngụy tạo rằng prefix cũ
được chạy bằng source mới. Từ chối unknown source/config drift, active owners,
invalid/truncated/duplicate/wrong prefix, có finalreport, tên đích đã tồn tại.
Source và GitHEAD freeze sau migration, không thay đổi khi model đang chạy.

### 12.3 Gate S1 — deterministic verification

Tests dùng fake stream/clock: delayed boundedstartup trước spawn, immediate
midrun EOF/error/stale, invalid metrics, transient power peak không bị mẫu an
 toàn mới ghi đè, child bị stop/unload khi sensorfail, cleanup không orphan,
latch bất biến. Test migration fail-closed và byte-identical prefix. Kiểm parser
PowerShell và actual stream idle cả native+WSL. Chạy make check trước modelrun.
Không thêm exception kiểu catch-and-continue, retry vòng lặp hoặc vô hiệu sensor.

### 12.4 Gate S2 — calibration và full continuation

Safeidle liên tục/no stale owned runners, verify clockcap600. Một guarded case
mỗi benchmark rồi PAUSED/cleanup; đối chiếu source/backend/checkpoint/guard logs.
Tiếp ít nhất 5 iterations ổn định trước full, mọi sample/resource bounds giữ nguyên:
GPU0/CPU8/Qwen14B/context4096/input2800/output768/max3requests/case900/request300,
RAM>=8GiB,swap<0.25GiB,VRAM<14GiB,temp<68C,power<70W,clock<=600MHz,
batchcase1/unload/cooldown>=60s. Chấm gold chỉ offline khi inference PAUSED/COMPLETE.
Full Spider200 rồi Olist60; theo dõi tới hết, validate đủ IDs/finalreports/cleanup
trước claim COMPLETE. Mọi actual sensor/resource stop mới: dừng, giữ evidence,
không tự retry; nếu cần remediation khác thì ghi rõ trước calibration mới.

S0/S1/S2 hiện IN_PROGRESS/NOT_STARTED/NOT_STARTED; không claim đã sửa hết mọi lỗi
hoặc accuracy tăng trước khi có kiểm thử và full paired results.


### 12.5 Kết quả S1 trước calibration

make check:341passed/1Ollamadeselected,53.27s;Ruff316files,mypy121sources,
PowerShell parserpass.24tests mới kiểm stream delayedstartup0.6s (khônglaunch
lạiprocess), EOF/malformed/nonfinite/stale/frozenstream, intermediate power spike,
guard khôngspawn khistartupfail vàstop/unload/close khimidrunfail. Migrationtest
copybyteidentical/khôngđổiparent,refusesemantic/datadrift/badprefix/powerstop/
activeowners/destinationreuse. Nativeidle20samples dùngcùngPID7324,readmax120.21ms,
powermax18.16W;pending dualidle240samples trướccalibration.

Sourceaudit táilập đúngparentSHA b5e80887c0636c911119cc2feaf81f30cf881c52ea1109223205d6e886e60eab;
chỉ7monitorinfrastructurefiles khácsnapshotcũ,khôngđổiQwen/profile/prompts/policy.
NewSHA76a2c89a21778e0d0bed0812c9b5343bf366ec85b59e1b7020d60e76b761990a.
Evidence localignored `data/artifacts/v4-sensor-recovery-20261016/`.
S1offline VERIFIED;S0migration vàS2modelcalibration/full vẫnIN_PROGRESS/NOT_STARTED.


### 12.6 S0 hoàn tất, bắt đầu S2

Dualidle240samples/120s PASS,RAMmin20.956GiB,powermax23.9W,tempmax51C,
WindowsRPCmax26.86ms,oneWSLGPUstreamPID79017,cleanupreturn0. Nativeidle20samples
onePID7324,readmax120.21ms. Nativemodelprocesslist chỉ có defaultOllamaapp/server;
oldownedserver/runners đãclosed,khôngnativeincident/cleanupfail.

Continuation `v4-cpu600-stream-20261016` tạo từ parentstop44Spider+1Olist;
byte-identicalprefix,oldfileshashes giữ nguyên. Source chỉ7monitorinfrastructurefiles
khác;original source/HEAD/model/backend/options/prompts/data/index/profile giữ lineage.
Khôngxóalatch hoặcchạylạiparent. `continuation.json` làauditrecord trongexperimentdir.
S0/S1 VERIFIED; S2calibration IN_PROGRESS. Source76a2c89a...1990a,HEAD663879a freeze.

```bash
tmux attach -t v4-cpu600-stream-20261016
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks status --name v4-cpu600-stream-20261016
# Chỉ cleanPAUSED, khôngresource/sensorstop:
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume --name v4-cpu600-stream-20261016
```


### 12.7 S2 calibration hoàn tất — full continuation

CleanPAUSED48Spider+2Olist,ownedserver/worker/proxynull;nativejob+runners+sensor
closed.5newbatches/1090WSLguardsamples,noresource/sensor/cleanupfail;
powermax31.23W,tempmax52C,RAMmin11.835GiB. Nativejournal liên tục xuyênsuốt
calibration;Qwen14BAPI size_vram0/context4096/digestbdbd181c... đãverify.
Parent23fileshashunchanged và44+1prefixbytes vẫnnguyên sau5newappends.

Offline50case:Spider36/48 vsV4same35/48,Olist2/2 vs2/2;1gain0334,0losses.
Gain nằmtronginheritedprefix,khôngquykết cải thiện cho sensorpatch hoặcproof
mechanicalpatchcausality. Fullaccuracy/generality chưađượcchứngminh. Scorer chỉ
chạysaukhiPAUSED/allownersnull,khôngđụngpredictions hoặcđưa gold vàoinference.
Source76a2c89a...1990a vàHEAD663879a vẫnfreeze. `prefix-50-quality.json` lưu evidence.

Fullcontinuation từ48+2 đượcuserauthorized;ordinaryresume khôngmaxbatch,
Spider200rồiOlist60. S2full IN_PROGRESS;khôngđánhCOMPLETEtrướckhiđủ260IDs,
finalreportsvalidated vàownedcleanupcompleted. Anynewbreachstopboth/noretry.


### 12.8 User-requested clean pause — 2026-10-17, checkpoint96

User yêu cầu dừng qua95 vàmai tiếp tục. Khi nhậnlệnh case96 đãcheckpoint;
đã gửioperatorpause vàchờ đủunload/cooldown. FinalPAUSED96Spider/200+2Olist/60,
worker/server/proxyPIDsnull;nativejob/runners/sensorcleanlystopped. Khônglaunchcase97.
Khôngresource/sensorlatch mới;oldparentincidentvẫn nguyên. Head/source vẫnfreeze.
Handoff `data/artifacts/v4-sensor-recovery-20261016/pause-handoff-96.json` ghihashes
predictions96+2,parentpreservation,guardstatistics. FullS2 vẫnIN_PROGRESS vàđãuserpause;
khôngtựresume trongđêm. Model/caseprofile vàsourcekhôngđổi.

Ngàymai:giữcode/.env/index/datasets/GitHEADnguyên. Nếu rebootWindows,cầnapplylại
Administrator `nvidia-smi -i 0 -lgc 300,600`. TrongWSL:

```bash
cd '/mnt/d/desktop_informations/vnpt ai/agentic_text_to_sql'
# Sau reboot, hoặc muốn kiểmtra1case trước:
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume --name v4-cpu600-stream-20261016 --recovery-pilot
tmux attach -t v4-cpu600-stream-20261016
# PilotđãPAUSEDsạch,khônglatch:Ctrl+b,d;tiếp tụcfull:
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume --name v4-cpu600-stream-20261016
tmux attach -t v4-cpu600-stream-20261016
```

Nếu khôngreboot/WSLrestart vàmôitrườnggiữnguyên,cóthểordinaryresume trực tiếp.
Recoverypilot khôngxóahoặcbypasslatch. Pilotpassphảixongcleanup/cooldown trướcfull.
Còn104Spider+58Olist=162cases;khôngquaylạiparentCPUstophoặcGPUstop.

### 12.9 User-authorized full resume after reboot — 2026-10-17

User confirmed Administrator `nvidia-smi -i 0 -lgc 300,600` success and requested
full continuation. No stale owned jobs; original prediction hashes at96+2,
source/config/manifest/database/index identity and HEAD663879a all matched.
Default Windows Ollama app was restarted with no resident model. Dual idle20samples
passed: Windows RAMmin20.363GiB,swap0,powermax22.1W,tempmax50C.

Spider recoverypilot succeeded at97/200, then unloaded/cooled and cleanlyPAUSED;
228guard samples,powermax28.74W,tempmax51C,clockmax600MHz,
RAMmin11.139GiB,swapmax0.01536GiB,no resource/cleanup failure.
Full continuation resumed from97+2; source/runtime settings/profile and HEAD unchanged.

Both suite checkpoints retained the old WSL boot identity. To give each suite its
required recovery case without changing frozen source or editing checkpoint state,
an external controller runs these stages once: Spider recovery1 → remainingSpider103
with a suite-boundary pause → Olist recovery1 → remainingOlist57 without a batch limit.
Every transition requires a clean checkpoint, finished cleanup, a dead worker pane
and no stop latch. Any failed stage, operator pause or safety latch stops the controller;
it never retries or clears evidence. Total remaining at full launch:161cases.

Ignored local controller/audit:
`data/artifacts/v4-sensor-recovery-20261016/resume-controller-20261017.{py,json,log}`;
preflight:`resume-20261017-preflight.json` in the same directory.
Controller tmux session:`v4-cpu600-resume-control-20261017`.

```bash
tmux attach -t v4-cpu600-stream-20261016:monitor
# Ctrl+b then0: raw worker log; Ctrl+b thend: detach without stopping.
```

FullS2 remainsIN_PROGRESS until260IDs, validated finalreports and owned cleanup.
No scoring/gold access during inference; no new gate completion claimed.

### 12.10 Full completion and V5 report audit — 2026-10-17

Final sequence `v4-cpu600-stream-20261016` and its controller are COMPLETE at
Spider200/200 + Olist60/60. Both suites COMPLETE, cleanup_pending=false,
child_pid=null; sequence worker/server/proxy PIDs null, recovery_required=false.
Both reports and cleanup validated; no new resource/cleanup latch in continuation.
S2 full workload/provenance verification is VERIFIED, scoped to this execution.

Results: Spider143/200 (71.50%), Olist50/60 (83.33%). Common-evaluator offline
re-score of current/V4/P6 preserves every correctness label:143/142/130 Spider,
50/41/57 Olist. VsV4: Spider5gains/4losses, Olist9gains/0losses. Eight previously
blocked Olist contexts are recovered and correct; CTE0795 is admitted and correct.
This does not prove component causality or satisfy all promotion requirements.

`make check`: Ruff pass,318formatted files,mypy121sources,341tests passed,
1Ollama test deselected,103.71s test time. Offline replay:251byte-identical working
prompts,8recoveries,249old-allowed decisions/SQL unchanged,539-row CTE equivalent,
230-row0098 result preserved. Actual full-run draft hashes preserve199Spider+
52Olist prompts. Current source76a2c89a...1990a/HEAD663879a unchanged; DB/index
identities,byte-identical44+1parentprefix and23parent-file hashes verified.

CPU lineage has260unique successful batches and55,481guard observations:
RAMmin8.547GiB,swapmax0.09067GiB,VRAMmax1187MiB,tempmax52C,powermax33.96W.
Native journals have88,745samples,RAMmin8.5407GiB,tempmax53C,powermax29.28W.
Parent sensor timeout with0samples remains preserved; continuation215batches clean.
Total successful batchwall39,896.40s includes15,600s mandatory cooldown;
do not equate the roughly24h observation span with continuous inference.

Report: [comparison_new5_to_baseline_vn.md](comparison_new5_to_baseline_vn.md),
using the V4 report's0–9structure. “V5” names this report/current upgrade; actual
measured variant is `v4-reliability`, profile `qwen14b-cpu600-stable`,num_gpu0,
CPU8,batch64,context4096,input2800/output768,max3requests,case900/request300.
No new model run or runtime change was made for this report. Reproduction scripts,
same-evaluator results,paired/resource/latency summaries,replay andmake-check log:
`data/artifacts/comparison-new5-20261017/` (ignored local artifacts).

E3 accuracy/promotion and A1 research remain IN_PROGRESS: current Olist still trails
P6 by7cases; four Spider prior-correct V4 losses need review, matched safe controls,
mechanism ablations and fresh acceptance evidence remain absent. P6 stays default.

### 12.11 User-requested V5 source publication — 2026-10-17

User requested new branch `best_research_v5`, then the same snapshot on `main`, with
complete reproducible code/setup. Publication includes all changed/new source and tests,
locked dependencies, prompts and dataset contracts, guarded scripts, V5 report/aggregate
evidence, portable CPU recipe, `.env.v5.example` and `docs/v5_reproduction.md`.
Raw datasets/DBs/indexes/weights/predictions/traces/secrets remain excluded.

Fresh staged Git archive without local data or .env: `make sync` and `make check` pass,
336tests passed,5dataset integrations skipped,1Ollama deselected,10.03s. Ruff314files,
mypy121sources pass. SourceSHA remains76a2c89a...1990a, exactly the measured runtime.
Recipe/profile/variant and checkpoint settings match; examples parse offline. Full
data-equipped341-test verification remains recorded in the V5 report. No inference rerun.

Previous remote maincebfeb1 belongs to an older implementation; retain it as ancestry
while selecting the tested V5 tree for the publication merge, without force-push or
mixing the older pipeline into the measured code. Git release HEAD is distinct from
measurement663879a; completed checkpoints retain historical identities. P6 stays default.
See `docs/evidence/v5_release_verification.md` for reproduction and publication boundaries.
