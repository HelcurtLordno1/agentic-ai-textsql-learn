# So sánh kiến trúc Paper II / DIN-SQL với baseline Olist đã đóng băng

**Trạng thái thí nghiệm:** đã dừng theo tiêu chí ngắt accuracy được định trước

**Ngày:** 2026-09-06 (Asia/Bangkok)

**Quyết định:** **LOẠI biến thể DIN-SQL tích hợp hiện tại khỏi vị trí kiến trúc tốt nhất cho
Olist.** Giữ baseline P6 đã đóng băng làm kiến trúc thắng; không chạy Spider cho biến thể đã thua
gate Olist.

## 1. Kết luận điều hành

Baseline P6 hoàn thành Olist-60 với **57/60 kết quả đúng (95,00%)**. Paper II được dừng sau case 8
vì đã có bốn lỗi kết quả. Ngay cả khi toàn bộ 52 case còn lại đều đúng, điểm tối đa cũng chỉ là
**56/60 (93,33%)**, thấp hơn baseline.

Prefix được evaluator offline chấm sau khi inference dừng và model đã unload: Paper II đạt
**4/8 (50,00%)**, trong khi baseline đạt **8/8 (100%)** trên đúng tám case đầu. Đây là hồi quy paired
4 case / 50 điểm phần trăm. Không tuyên bố score đủ 60 case, holdout score hoặc Spider score cho
Paper II.

## 2. Các hệ thống được so sánh

Hai hệ thống dùng cùng manifest `olist-acceptance-60.jsonl`, database Olist do project build,
Qwen3-14B Q4_K_M local, seed 42, runtime gold-blind và evaluator chỉ mở gold sau checkpoint.

### Baseline P6 đã đóng băng

```text
question -> router/decomposer -> LLM logical planner -> hybrid grounding
         -> SQL generator -> safety/semantic validation -> bounded correction
```

### Biến thể Paper II / DIN-SQL được benchmark

```text
question -> deterministic decomposition -> hybrid semantic links + FK closure
         -> deterministic complexity + typed clause plan -> plan validator
         -> DIN-aware SQL generator -> safety/semantic validation -> bounded correction
```

Planner LLM DIN ban đầu không khả thi ở profile laptop một GPU layer: hai pilot lần lượt chạm
timeout 240 và 600 giây. Snapshot benchmark cuối thay bước này bằng clause planning xác định từ
semantic links/FK evidence, giữ validator và DIN-aware generation nhưng chỉ còn một model call.

## 3. Bằng chứng có thể tái lập

| Bằng chứng | Baseline P6 | Paper II / DIN-SQL |
|---|---:|---:|
| Evaluation ID | `olist-acceptance-60-p6-v1` | `olist-paper2-dinsql-60-a2bbdd8-v1-prefix-8` |
| Source commit | `1509faa78653` | `a2bbdd8681df` |
| Case đã đánh giá | 60 | Prefix 8, đã dừng |
| Kết quả đúng | 57/60 (95,00%) | 4/8 (50,00%) |
| Cùng prefix 8 case | 8/8 (100%) | 4/8 (50,00%) |
| Tiếng Anh trên prefix | 4/4 | 2/4 |
| Tiếng Việt trên prefix | 4/4 | 2/4 |
| Độ trễ P50 | 61,92 giây | 614,92 giây |
| Độ trễ P95 | 91,62 giây | 630,90 giây |
| Correction thử/cứu | 6/6 toàn suite | 0/0 trên prefix |
| Cận trên toàn suite | 57/60 đã đo | **không quá 56/60** |

Artifact:

- baseline: `evals/reports/olist-p6-60.json`;
- Paper II predictions: `evals/predictions/olist-paper2-dinsql-60-a2bbdd8-v1.jsonl`;
- Paper II prefix report: `evals/reports/olist-paper2-dinsql-60-a2bbdd8-v1.progress.json`;
- SHA-256 predictions: `f689a0ac261ce96bc543e3b5805ad71d280c6fd54914886c26ac7f10dcaec987`;
- SHA-256 prefix report: `b93b8eb34841e063f6b9e9502c4deba2f718feca130f5874af82041a98aae287`.

## 4. Bốn failure quyết định

### `olist_acc_002` — delivered bị nối với timestamp thay vì status

- Câu hỏi: `How many orders were delivered?`
- SQL sinh: `COUNT(*)` với `order_delivered_carrier_date IS NOT NULL`.
- Gold yêu cầu `order_status = 'delivered'`.
- Trạng thái: `VALIDATION_FAILED`, `RESULT_SHAPE_MISMATCH`.
- Nguyên nhân: semantic linker chọn cột delivery timestamp cho mention `delivered`; typed clause plan
  kế thừa evidence sai và không mã hóa cặp giá trị–cột status.

### `olist_acc_005` — semantic view và bảng vật lý tạo graph rời

- Câu hỏi: tổng doanh thu sản phẩm theo cents.
- Gold: `SUM(price_cents)` từ `olist_order_items_dataset`.
- Trạng thái: `GROUNDING_ERROR`, signal `JOIN_PATH_DISCONNECTED`.
- Nguyên nhân: metric được link tới view `order_item_totals.product_revenue_cents`, entity tới bảng
  products, nhưng join closure chỉ nối item–product và không có dependency edge tới view.

### `olist_acc_007` — generator không hoàn thành trong budget

- Câu hỏi: đếm buyer duy nhất theo `customer_unique_id`.
- Plan đã tìm được đúng cột identity nhưng thêm join orders không cần thiết.
- Trạng thái cuối sau một retry hạ tầng: `MODEL_ERROR`, `ReadTimeout` ở 600 giây.
- Nguyên nhân: DIN prompt/context và JSON grammar quá chậm với Qwen3-14B khi profile bắt buộc chỉ
  offload một GPU layer. Không được tăng layer hoặc nới ngưỡng trên laptop để cứu score.

### `olist_acc_008` — câu count bị biến thành dimension output

- Câu hỏi: `How many sellers are in the marketplace?`
- Trạng thái: `GROUNDING_ERROR`, signal `SCALAR_OUTPUT_GRAIN_MISMATCH`.
- Nguyên nhân: decomposer nhận `seller` là dimension nhưng không nhận seller-count là metric; plan
  vừa mang task aggregation vừa yêu cầu một dòng theo dimension.

## 5. Quyết định kỹ thuật

Không sửa tiếp bốn case trong cùng benchmark rồi resume, vì điều đó sẽ chọn kiến trúc theo gold/dev
prefix và phá vỡ tính độc lập của phép đo. Kết quả hiện tại phủ nhận giả thuyết rằng việc tích hợp
DIN-SQL này làm tăng Olist accuracy.

Các phần có thể giữ độc lập sau review: typed semantic-link contract, FK provenance, clause-plan
validator, metric evaluator, guarded runner và accuracy stop. Không bật `din_sql` làm mặc định cho
production/benchmark champion cho đến khi một vòng development mới giải quyết tổng quát các nhóm
lỗi dưới đây và được đánh giá bằng artifact/commit mới:

1. value-to-column linking cho enum/status, không suy từ timestamp gần nghĩa;
2. graph dependency cho semantic view hoặc chọn một owner vật lý duy nhất;
3. count-intent normalization tách entity khỏi output dimension;
4. prompt/context budget đủ nhỏ để một model call kết thúc ổn định dưới profile đã hiệu chuẩn;
5. deterministic tests trên case tổng hợp, sau đó mới chạy pilot và benchmark mới từ đầu.

Nếu vòng development mới vẫn không thắng baseline trên development gate độc lập, DIN-SQL phải được
giữ dưới feature flag hoặc loại khỏi runtime chính.

## 6. Hồ sơ an toàn và lý do không chạy Spider

Run dùng profile `olist-paper1-ultrasafe`: Qwen3-14B một GPU layer, batch size 1, sampling 0,5 giây,
unload từng case, cooldown 60 giây, VRAM stop 4 GiB, nhiệt stop 65°C, power stop 78 W và hard clock
cap Administrator 300–600 MHz. Generation và embedding không resident đồng thời.

Peak quan sát của run: **45,01 W**, **58°C**, **1.768 MiB VRAM**, **2,224 GiB RAM dùng**, swap 0;
server supervisor ghi clock peak không quá **600 MHz**. Không có resource breach. Sau accuracy stop,
mọi runner/model/Ollama process được dừng và graphics-clock lock được reset bằng quyền Administrator.

Spider không chạy vì Olist gate đã chứng minh cận trên 56/60, thấp hơn ngưỡng 57/60 mà người dùng
đặt trước. Chạy Spider lúc này vừa không thay đổi quyết định chọn kiến trúc, vừa tiêu tốn nhiều giờ
compute không cần thiết trên laptop.
