# Accuracy Research Lab

Bộ tài liệu này là blueprint nghiên cứu sau Gate P6 cho Agentic Text-to-SQL. Nó nối mục tiêu benchmark với
độ tin cậy khi người dùng thực tế hỏi câu khó đoán, thiếu thông tin, sai chính tả hoặc không biết SQL.

## Đọc theo nhu cầu

- [`paper_to_research_implement.md`](paper_to_research_implement.md): luận đề chính theo format
  paper → motive/architecture → weakness đo được → phần chuyển giao → experiment gate.
- [`research_plan.html`](research_plan.html): bản trình bày tương tác, responsive, có dark/light theme và reading mode.
- [`research_plan.md`](research_plan.md): bản blueprint có thể review/diff trong Git.
- [`nghien_cuu_data_science.md`](nghien_cuu_data_science.md): protocol thực thi thí nghiệm, metric và data flywheel.
- [`generate_research_plan.py`](generate_research_plan.py): single source tạo lại Markdown và HTML từ evidence đã chốt.

## Tạo lại và kiểm tra

```bash
uv run python docs/research_plan/generate_research_plan.py
uv run python docs/research_plan/generate_research_plan.py --check
```

Mở `research_plan.html` trực tiếp trong trình duyệt; tài liệu không cần server, CDN, API key hoặc kết nối mạng.
Thêm `?theme=light` hay `?theme=dark` vào URL nếu cần chụp/kiểm định một theme xác định.

## Quy ước bằng chứng

- Số baseline trong trang gắn với commit và evidence local cụ thể; chúng không phải leaderboard claim.
- Nguồn paper là prior cho giả thuyết, không phải lời hứa rằng model local sẽ đạt điểm của paper.
- Mỗi cải tiến phải qua experiment card, paired regression review và resource guardrail.
- Runtime không được đọc gold benchmark; raw data, DB, index, trace và prediction không được commit.
- Chỉ cập nhật trạng thái gate sau khi generator check và `make check` đều pass.

Để tránh drift, hãy sửa dữ liệu/nội dung sinh tự động trong `generate_research_plan.py`, sau đó regenerate; không sửa
trực tiếp `research_plan.md` hoặc `research_plan.html`.
