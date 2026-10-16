# Quyết định nền phát triển tiếp theo

**Ngày:** 2026-10-01. **Trạng thái:** quyết định thiết kế đã báo người dùng, chưa chuyển workspace hoặc triển khai kiến trúc mới.

**Chọn nền `baseline` (`0972e47`), phát triển ở nhánh mới từ baseline, ví dụ `research_local_sql_architecture`. Giữ `research_3_128` làm đối chứng lịch sử 128/200.**

## Vì sao chọn baseline?

| Tiêu chí | P6 baseline | R3 coverage |
|---|---|---|
| Evidence quan sát Spider-200 | 130/200 | 128/200, paired +4/−6 |
| Trạng thái | Release evidence P6 | Research `IN_PROGRESS`, chưa promote |
| Diễn giải gain | Đối chứng đã khóa | Coverage cứu R2 120→128, chưa vượt P6 |
| Chi phí đổi sang A1/specialist/critic | Mở từng seam từ nền có ít experimental dependencies | Phải kiểm thêm hybrid routes/semantic catalog/incumbent sharing và legacy candidate |
| Module đáng giữ | Core planning/grounding/generation/validation | Coverage, guard/launcher/provenance, typed contracts và tests có thể port riêng |

Chênh hai câu chưa chứng minh P6 superior ngoài mẫu; latency bị confound offload/guard. Quyết định dựa thêm vào khả năng cô lập giả thuyết, bảo toàn control và giảm chi phí maintenance, không chọn nhánh bằng score đơn lẻ.

## Cách bắt đầu đúng

1. Giữ baseline lịch sử không đổi, dựng development worktree riêng khi bước đó được thực hiện.
2. Trước inference, đưa resource guard/checkpoint/provenance/budget/cleanup cần thiết từ R3 sang nền P6 qua dependency review và deterministic tests; **không chạy profile GPU/power lịch sử của baseline**.
3. Review thêm test portability: một số test semantic của R3 phụ thuộc database Olist local chưa được đánh dấu optional đầy đủ; chuyển test thuần contract sang synthetic fixtures ở gate riêng nếu phù hợp, không đổi archive để che dependency. Dựng matched safe P6 control trên policy hiện hành. Sau đó thử A1 bằng cùng model, một specialist 7B bằng adapter đúng, critic shadow rồi một repair. Không merge nguyên R3 hoặc bật tất cả cùng lúc.
4. Port coverage/semantic compiler chỉ khi một ablation chứng minh lợi ích phù hợp scope. Một phần Olist-specific proof không tự chuyển sang Spider/new schemas.
5. Freeze variant và kiểm fresh schema, accuracy/coverage/regressions/latency/resources trước promote.

Máy RTX A4500 Laptop 16 GB dùng quantized inference, concurrency 1, explicit bounded offload và profile pilot riêng; kế hoạch chi tiết ở [codex_answer.md, §7.4](../../codex_answer.md). Một model vừa VRAM nhưng vượt power/thermal hoặc quá chậm vẫn không đạt deployment target.

## Vì sao không hứa production success?

Production reliability cần evidence trên scope mới, semantic checks có coverage, timeout/resource policy và latency phù hợp. Không kiến trúc hoặc nhánh Git nào bảo đảm điều đó trước thực nghiệm. Nền baseline là lựa chọn tăng khả năng xác định đúng bottleneck và rollback với chi phí thấp hơn; có thể reconsider nếu matched/fresh evidence cho thấy nền khác tốt hơn.

Workspace chính được giữ nguyên branch và các thay đổi đang có. Lượt này chỉ tạo/publish archive worktree riêng; chưa checkout baseline hoặc tạo development branch mới. Đây là điểm báo trước theo yêu cầu người dùng.
