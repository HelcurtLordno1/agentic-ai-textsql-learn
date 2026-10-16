# Chuyển workspace về P6 baseline và giữ research evidence

**Ngày:** 2026-10-01, Asia/Bangkok. **Phạm vi:** chuyển code/config về baseline, bảo toàn tài liệu và artifacts local; chưa triển khai A1, critic hoặc model mới.

## Trạng thái nguồn code

| Vai trò | Branch / commit | Ý nghĩa |
|---|---|---|
| Workspace hiện tại | `baseline` · `0972e4715f2aa8a64652c3b27d10c80f178bc162` | Nền P6; lịch sử Spider-200 130/200 |
| Workspace trước chuyển | `spider-schema-ablation-20260924` · `1f39654d0c3f4dd09df1071ced379ce03dccd259` | Điểm quay lại local, vẫn giữ branch |
| Archive public | `research_3_128` · `f0852ac88b2bdb3cad150e55bb85beed925946c6` | Đóng gói code/docs/evidence 128/200 |
| Source inference của 128/200 | `389b8154054243ff00ac67e420f5d042b15f34fd` | Snapshot được ghi trong report; packaging không đổi code |
| Checkpoint docs chưa commit trước chuyển | `c9bb6b7700736d34e0c1afea0b414caac689ee15` | Git stash local, giữ nguyên để rollback |

Đã đối chiếu remote `research_3_128` với local archive và kiểm code archive không khác inference source ở `src`, `scripts`, `tests`, `configs`, `evals/configs`, `datasets`, dependency/lockfile và Makefile. Archive có đầy đủ source và tài liệu trong phạm vi research này; dataset/model/index/predictions cần được cung cấp đúng provenance riêng. Không tuyên bố clone Git sẽ tự chứa tất cả dữ liệu hoặc chạy lại chắc chắn đúng 128/200.

Sau switch, `src`, `scripts`, `tests`, `configs`, `datasets`, `evals/configs`, `Makefile`, `.env.example`, `pyproject.toml`, `uv.lock` khớp baseline. Không copy runtime R2/R3 trở lại để giữ docs. `baseline` local/remote head không đổi; chưa tạo commit mới trên baseline.

## Tài liệu vẫn ở workspace

- [codex_answer.md](../../codex_answer.md): giáo án, kiến trúc model nhỏ, critic và A4500 optimization.
- [comparison_new3_to_baseline_vn.md](../../comparison_new3_to_baseline_vn.md): report coverage 128/200, paired gain/loss và phân tích giới hạn.
- [comparison_new2_to_baseline_vn.md](../../comparison_new2_to_baseline_vn.md): report R2/Olist trước đó.
- Các comparison/Paper I/Paper II/research-plan Markdown, slides, DOCX và research HTML đã có tiếp tục được giữ local.
- [research_3_128.md](../../research_3_128.md), [aggregate summary](../evidence/research_3_128_summary.json), [quyết định nền phát triển](next_development_base.md) được lấy từ archive để đối chiếu ngay tại đây.
- [realistic_project_creation_codex.md](../../realistic_project_creation_codex.md) vẫn là canonical ledger; lịch sử research được giữ, §26 ghi active runtime là P6. Tài liệu lịch sử không tự làm R2/R3 code có mặt trong baseline.
- [AGENTS.md](../../AGENTS.md) giữ toàn bộ laptop safety instructions mới, dù baseline lịch sử chưa có đoạn policy đó.

README, architecture và runbook ở đường dẫn chuẩn mô tả nền baseline. Ba phiên bản trước switch được giữ thêm tại:

| Tài liệu trước chuyển | Bản lịch sử local |
|---|---|
| README | [pre-baseline README](../research_history/pre_baseline_2026_10_01/README.md) |
| Architecture | [pre-baseline architecture](../research_history/pre_baseline_2026_10_01/docs/architecture.md) |
| Runbook | [pre-baseline runbook](../research_history/pre_baseline_2026_10_01/docs/runbook.md) |

Các links/code examples trong research docs có thể trỏ tới module R2 chưa có ở P6. Khi review lịch sử, dùng [source archive cố định](https://github.com/HelcurtLordno1/agentic-ai-textsql-learn/tree/f0852ac88b2bdb3cad150e55bb85beed925946c6); không vì missing module mà thêm toàn bộ R2 vào baseline. `BRANCH_PROVENANCE.md` là provenance lịch sử Paper II, không mô tả branch đang active.

## Checkpoint và bảo toàn artifacts

Có backup độc lập của **71 tài liệu** trước switch, gồm private chat/scratch và các sửa chưa commit. SHA-256 được kiểm trước restore; 68 tài liệu được đặt lại ở đường dẫn cũ, ba phiên bản tài liệu chung được lưu thêm trong research history. Các notes vận hành mới trong README/ledger/provenance không sửa benchmark score hoặc nội dung giáo án.

**Backup directory:** `/mnt/d/Desktop_informations/VNPT AI/Agentic_text_to_sql_baseline_backup_20261001T081637Z`.

Trong backup có `checkpoint.json`, `documents/`, `baseline_documents/` và `tracked_changes.patch`. Backup nằm ngoài Git workspace; nội dung private không được push. Stash giữ nguyên như checkpoint bổ sung; không tự `stash pop` lên baseline vì stash có base tree R2. Khi cần hồi phục, đối chiếu manifest và restore đúng file; source cũ vẫn có branch và archive riêng.

Datasets, generated SQLite DBs, indexes, predictions, reports/logs và model store không bị move/xóa bởi công việc này. Ba JSON reports vẫn giữ hashes đã audit:

| Report local | Đúng | SHA-256 |
|---|---:|---|
| `evals/reports/spider-p6-200.json` | 130/200 | `9951ff2e3bb00c42f1eaf6a4c10d3cc701619f91851ca42c7a8908ae129df660` |
| Sibling Spider worktree: `spider-schema-legacy-200-v1.json` | 120/200 | `a1f8313c480b57e2f2f5392718a8c76038c064031b7e52f722269c38a706ae0a` |
| Sibling Spider worktree: `spider-schema-coverage-200-v2.json` | 128/200 | `18f7074b3f0ea8b86ee6dce6c2c30ab6d258bdb2d4d17580a229b29b1a60076c` |

Archive worktree `../Agentic_text_to_sql_research_3_128` và Spider worktree `../Agentic_text_to_sql_spider700` vẫn được giữ. Chưa commit/push các docs overlay của workspace baseline; điều này giữ nguyên P6 commit làm control.

## Quy tắc cho bước phát triển kế tiếp

1. **Gate đang chọn là E0 — audit offline.** Review call graph P6, actual prompts, plan→SQL→validator/corrector và evaluator; dùng artifacts cũ để tìm bottleneck, chưa chạy model hoặc đổi kiến trúc.
2. Giữ hai trục nhãn: error family và originating component. Audit 70 failure P6, sáu P6-correct→coverage-wrong, bốn chiều ngược lại và sample câu đúng; 66 shared failures không phải tập độc lập để cộng vào 70.
3. Mỗi intervention phải có hypothesis, code seam, evidence runtime không gold, counterexample/negative fixtures, expected cost, regression budget và điều kiện bác bỏ trước implementation.
4. Chỉ sau audit mới tạo nhánh phát triển từ baseline, ví dụ `research_local_sql_architecture`. Không phát triển trực tiếp bằng commit vào baseline control; không merge nguyên R3.
5. Trước bất kỳ local-model run mới, port/review guard, global budget, checkpoint/provenance, hard-cap checks và cleanup đáp ứng AGENTS. Profile P6 hiện tại có ngưỡng cũ 105 W/76°C/VRAM lớn hơn policy; không được dùng để chạy chỉ vì tests pass.
6. Thiết kế matched safe P6 control rồi mới ablate A1, một SQL-specialist 7B, critic shadow và một repair. Không đổi model, retrieval, planner, correction và profile đồng thời rồi kết luận một module có lợi.
7. Spider-200/Olist-60 đã exposed chỉ là development/regression diagnostics. Freeze variant và kiểm schema mới trước promotion; báo gain/loss, oracle/selected score, coverage và P95 theo budget.

Gate R2/coverage vẫn `IN_PROGRESS`, không `VERIFIED`; việc checkout thành công không chứng minh pipeline production mới hoặc accuracy P6 đã được chạy lại hôm nay.

## Verification của bước chuyển

**`make check` pass:** Ruff, format 234 files, strict mypy 104 source files; **168 tests passed, 1 Ollama test deselected**, một Starlette/httpx deprecation warning. Không có local-model run hoặc benchmark mới. Số test nhỏ hơn R3 vì code/tests đang đúng tree baseline, không mang theo experimental modules.

Đã xác nhận 71 tài liệu có bản giữ lại, 69 bản khớp SHA-256 byte-for-byte; hai file ledger/provenance có thêm context notes và bản gốc vẫn trong backup. Các overlays README/runbook là notes vận hành, phiên bản cũ được giữ ở history. Mọi source/config paths khớp `0972e47`; index không có staged changes, baseline HEAD và remote archive HEAD giữ nguyên. Ba report JSON 130/120/128 giữ nguyên hashes. Links mới trong transition/history đã được kiểm tồn tại.

Research Markdown đã được khôi phục có thể hiện `untracked` trên baseline vì commit P6 lịch sử không chứa chúng; file vẫn ở workspace và bản public tương ứng ở research archive. Khi mở development branch mới, chọn riêng docs cần commit; private chat/scratch và generated artifacts tiếp tục local. Tài liệu này ghi bước chuyển đã kiểm tra, không đánh dấu một architecture/research module `VERIFIED`.
