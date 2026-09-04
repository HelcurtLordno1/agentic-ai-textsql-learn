# So sánh kiến trúc Paper I / PRACTIQ với baseline Olist đã đóng băng

**Trạng thái thí nghiệm:** đã dừng theo tiêu chí ngắt vì accuracy được định trước

**Ngày:** 2026-09-03 (Asia/Bangkok)

**Quyết định:** **LOẠI biến thể Paper I tích hợp hiện tại khỏi vị trí kiến trúc tốt nhất cho Olist.**
Giữ question-reliability dưới dạng tính năng thử nghiệm, nhưng không thay thế baseline P6 đã đóng băng.

## 1. Kết luận điều hành

Baseline đã đóng băng hoàn thành Olist-60 với **57/60 kết quả đúng (95,00%)**. Kiến trúc mới được
dừng sau case 35 vì đã có năm lỗi ở mức kết quả. Ngay cả khi toàn bộ case 36--60 còn lại đều đúng,
điểm tối đa cuối cùng cũng chỉ là **55/60 (91,67%)**. Vì vậy, về mặt toán học, lần chạy này không thể
bằng hoặc vượt baseline.

Kết luận này không coi SQL thực thi thành công là SQL đúng. Prefix tại thời điểm dừng được đánh giá
offline bằng gold result đã qua review: **30/35 (85,71%)**. Trên cùng 35 case đầu, baseline đạt
**33/35 (94,29%)**, tức hồi quy theo cặp **3 case / 8,57 điểm phần trăm**.

Kiến trúc mới sửa hai lỗi baseline (`olist_acc_014`, `olist_acc_023`) nhưng tạo năm hồi quy mới
(`olist_acc_021`, `027`, `029`, `031`, `035`). Thay đổi ròng: **+2 lỗi được sửa, -5 hồi quy = giảm
3 case đúng**.

Theo thiết kế, thí nghiệm không hoàn thành sau tiêu chí dừng: không tuyên bố có điểm đủ 60 case, điểm
holdout hay `60/60 workflow completion`. Phát biểu có thể bảo vệ cho toàn suite là cận trên **không
quá 55/60**, vốn đã thấp hơn 57/60.

## 2. Các hệ thống được so sánh

Cả hai lần chạy đều dùng `olist-acceptance-60.jsonl` đã qua review, Olist SQLite do project tự build,
Qwen3-14B Q4_K_M local, seed xác định 42, runtime không nhìn gold, và evaluator chỉ mở gold sau khi
có prediction. Mã runtime không import evaluator hoặc gold benchmark.

### Baseline P6 đã đóng băng

```text
Câu hỏi
  -> router/decomposer
  -> logical planner một lượt
  -> truy xuất schema lai và đóng gói context
  -> một SQL candidate
  -> kiểm tra AST/read-only/ngữ nghĩa/kết quả
  -> correction có giới hạn khi đủ điều kiện
  -> kết quả có kiểu rõ ràng
```

Baseline không có quyết định `ANSWER / CLARIFY / CANNOT_ANSWER` mang tính thẩm quyền và nhận biết
schema trước khi sinh SQL. Nó dựa vào router, planning, grounding, validation và correction sẵn có.

### Biến thể lấy cảm hứng từ Paper I / PRACTIQ

```text
RawQuestion
  -> QuestionNormalizer không làm mất thông tin (VI/EN, lỗi gõ, alias không dấu)
  -> kiểm tra safety/unsupported ưu tiên luật xác định
  -> QuestionAnalyst nhận biết schema và glossary
  -> Interpretation(metric, dimensions, filters, grain, assumptions)
  -> AnswerabilityDecision mang tính thẩm quyền
       ANSWER          -> planner/grounding/generation/validation/correction
       CLARIFY         -> câu hỏi làm rõ có kiểu và 2--3 lựa chọn nghiệp vụ
       CANNOT_ANSWER   -> phản hồi có kiểu về bằng chứng còn thiếu
       SAFE_REJECT     -> từ chối theo policy với kiểu rõ ràng
```

Các phần tích hợp bổ sung:

- concept từ interpretation vẫn tồn tại sau chuẩn hóa scalar plan và được đưa vào retrieval;
- câu hỏi xác định về trạng thái Olist bỏ qua phân tích mơ hồ không cần thiết;
- mơ hồ chỉ liên quan cấu trúc vật lý có thể được thu gọn thành một cách hiểu nghiệp vụ;
- schema linking chấm điểm dimension khớp chính xác, aggregate measure thô và chủ sở hữu thực thể;
- semantic validation kiểm tra phân phối đầy đủ, status filter chính xác, scalar aggregate, grain của
  review row, danh tính khách hàng, giao hàng trễ, grain payment/item và quy tắc phá hòa;
- contract API/CLI/UI có thể trả câu hỏi làm rõ và tiếp tục conversation state có giới hạn;
- LLM local dùng batch size 1 có guard, GPU offload một layer, unload, cooldown, sensor liên tục và
  hard cap xung nhịp đồ họa.

Thiết kế tuân theo ranh giới sản phẩm hữu ích của PRACTIQ—quyết định có nên sinh SQL trước khi thực
hiện—nhưng không import mã PRACTIQ hoặc gold data vào runtime.

## 3. Bằng chứng có thể tái lập

| Bằng chứng | Baseline | Biến thể mới |
|---|---:|---:|
| Evaluation ID | `olist-acceptance-60-p6-v1` | `olist-paper1-r1-60-v3-stopped` |
| Số case đã đánh giá | 60 | Prefix 35 case đã dừng |
| Kết quả đúng | 57/60 (95,00%) | 30/35 (85,71%) |
| Cùng lát cắt 35 case đầu | 33/35 (94,29%) | 30/35 (85,71%) |
| Đúng ngay lượt đầu | 51/60 (85,00%) | 30/35 (85,71%) |
| Correction đã thử/đã cứu | 6/6 | 0/0 |
| Độ trễ P50 | 61,92 giây | 193,27 giây |
| Độ trễ P95 | 91,62 giây | 259,18 giây |
| Tiếng Anh | 28/30 (93,33%) | 17/17 (100%) trên prefix |
| Tiếng Việt | 29/30 (96,67%) | 13/18 (72,22%) trên prefix |
| Dev | 28/30 (93,33%) | 27/30 (90,00%) |
| Regression | 14/15 (93,33%) | 3/5 (60,00%) trên prefix |
| Holdout | 15/15 (100%) | Chưa chạy; không tuyên bố |
| Cận trên toàn suite | Đã đo 57/60 | **<=55/60**, vì 5 lỗi đã cố định trong mẫu số |

Độ trễ không phải phép A/B chỉ khác kiến trúc. Lần chạy mới an toàn dùng một GPU layer và hard cap
xung 300--600 MHz sau sự cố shutdown/power breach; baseline lịch sử dùng sáu GPU layer và báo peak
91,75 W. Độ trễ mới là bằng chứng vận hành hợp lệ cho profile an toàn, nhưng không phải ước lượng có
kiểm soát chỉ về overhead của PRACTIQ.

Artifact và định danh bất biến:

- báo cáo baseline: `evals/reports/olist-p6-60.json`;
- prefix prediction: `evals/predictions/olist-paper1-r1-60-v3.jsonl`;
- provenance/source hash: `evals/predictions/olist-paper1-r1-60-v3.provenance.json`;
- báo cáo prefix offline: `evals/reports/olist-paper1-r1-prefix35-v3.json`;
- SHA-256 prediction: `338498882dbde8b8bf91295cc2f5584a80f73cc9b26f98eddd4a6d23fda02e0a`;
- SHA-256 provenance: `650f372656c103b1ab0d959b0b82f0eebcafe34e031b2292ce3b14a83f85ad35`;
- SHA-256 báo cáo prefix: `7d857a4e683134c8c320cc765529a4cb0351ed06f8a06b18c9c7b4d4455712c7`.

## 4. Các lỗi chính xác của kiến trúc mới

### `olist_acc_021` — sai quan hệ vật lý, kết quả sai âm thầm

- Câu hỏi: `Có bao nhiêu sản phẩm thiếu danh mục?`
- Kỳ vọng: `610` sản phẩm trong `olist_products_dataset` có category null.
- SQL được sinh:

```sql
SELECT COUNT(*)
FROM product_category_name_translation
WHERE product_category_name IS NULL
```

- Thực tế: `0`; trạng thái `SUCCEEDED`.
- Nguyên nhân: bước thu gọn mơ hồ vật lý chấp nhận đúng ý nghĩa nghiệp vụ, nhưng grounding chọn bảng
  tra cứu bản dịch thay vì quần thể sản phẩm. Answerability và quyền sở hữu schema phải là hai
  contract riêng: chỉ được thu gọn lựa chọn bảng không quan trọng với người dùng nếu linker vẫn bảo
  đảm quần thể của metric.

### `olist_acc_027` — `MAX` hợp lệ bị luật ranking quá rộng từ chối

- Câu hỏi: giá trị lớn nhất của một dòng thanh toán, tính bằng cent.
- Kỳ vọng: `1366408`.
- SQL đúng về ngữ nghĩa:

```sql
SELECT MAX(payment_value_cents) AS max_payment_value_cents
FROM olist_order_payments_dataset
```

- Trạng thái: `VALIDATION_FAILED`, `SEMANTIC_MISMATCH`; không trả kết quả.
- Nguyên nhân: cách diễn đạt so sánh nhất tiếng Việt bị coi là yêu cầu xếp hạng dòng dù câu hỏi yêu
  cầu scalar maximum. Planner và validator chưa đồng bộ đầy đủ giữa các ngôn ngữ.

### `olist_acc_029` — ý tưởng đúng, validator báo sai scope cột dẫn xuất

- Câu hỏi: số item trung bình trên mỗi đơn hàng, làm tròn bốn chữ số thập phân.
- Kỳ vọng: `1.1417`.
- SQL được sinh:

```sql
SELECT ROUND(AVG(item_count), 4) AS avg_items_per_order
FROM (
  SELECT COUNT(*) AS item_count
  FROM olist_order_items_dataset
  GROUP BY order_id
)
```

- Trạng thái: `EXECUTION_ERROR`, `UNKNOWN_COLUMN`.
- Nguyên nhân: SQL diễn đạt đúng aggregate dẫn xuất, nhưng static schema validation không phân giải
  alias `item_count` của subquery. Semantic view `order_item_totals` cũng có thể tránh khoảng trống
  validation này.

### `olist_acc_031` — scalar maximum bị chuyển thành top-one theo nhóm

- Câu hỏi: số đơn hàng lớn nhất của một `customer_unique_id`.
- Kỳ vọng: `17`.
- SQL được sinh:

```sql
SELECT COUNT(*) AS order_count
FROM olist_orders_dataset
GROUP BY customer_id
ORDER BY order_count DESC
LIMIT 1
```

- Trạng thái: `VALIDATION_FAILED`, `SEMANTIC_MISMATCH`.
- Nguyên nhân: interpretation không ép contract danh tính/grain đã review (`customer_unique_id`,
  `customer_order_facts.order_count`) đủ mạnh. Lỗi cũng lặp lại khác biệt giữa `customer_id` theo
  phạm vi đơn hàng và `customer_unique_id` đại diện khách hàng thực.

### `olist_acc_035` — phép join khó bỏ sót bảng product

- Câu hỏi: năm danh mục sản phẩm tiếng Anh đứng đầu theo doanh thu item, với tie-break xác định.
- Các dòng kỳ vọng bắt đầu bằng `health_beauty`, `watches_gifts`, `bed_bath_table`, `sports_leisure`
  và `computers_accessories`.
- SQL join trực tiếp item với bảng bản dịch qua cột không tồn tại `oi.product_category_name`.
- Trạng thái: `EXECUTION_ERROR`, `UNKNOWN_COLUMN`.
- Nguyên nhân: grounding/generation bỏ cầu nối bắt buộc
  `order_items.product_id -> products.product_id -> translation.product_category_name`. Ưu tiên
  dimension khớp chính xác hiện tại không đủ cho join nhiều chặng.

## 5. Chuyển đổi theo cặp so với baseline

Cải thiện trên cùng prefix:

- `olist_acc_014`: phân phối đầy đủ của trạng thái đơn hàng không còn nhận nhầm `LIMIT 1`.
- `olist_acc_023`: các bang khách hàng khác nhau không còn thành các danh tính khách hàng khác nhau.

Hồi quy trên những case baseline làm đúng:

- `olist_acc_021`, `olist_acc_027`, `olist_acc_029`, `olist_acc_031`, `olist_acc_035`.

Không có case nào cả hai hệ thống cùng sai trong 35 case đầu. Kiến trúc mới thay đổi hành vi đáng kể,
nhưng cải thiện không bù được lỗi planner/linker/validator mới.

Lỗi thứ ba của baseline, `olist_acc_038`, nằm ngoài prefix. Nó từng pass diagnostic riêng sau bản sửa
status/timestamp, nhưng diagnostic đó không phải bằng chứng benchmark v3 và không được ghép vào lần
chạy đã dừng.

## 6. Hồ sơ an toàn và quyết định dừng

Lần chạy dùng profile `olist-paper1-ultrasafe`: Qwen3-14B một GPU layer, batch size 1, một model được
load, giám sát mỗi 0,5 giây, unload giữa các case, cooldown 60 giây, VRAM dưới 4 GiB, dưới 65 C, ngắt
ở 78 W và khóa xung Administrator 300--600 MHz đã xác minh. Generation và embedding không chạy cùng
lúc.

Pilot tiếp từ case 29 đạt peak 49,0 W, 59 C, 1.585 MiB VRAM, swap 0. Đoạn tiếp tới case 35 đạt peak
50,74 W, 59 C, 1.665 MiB VRAM, swap 0. Guard không vi phạm. Sau khi dừng vì accuracy, Ollama và mọi
runner được dừng; `nvidia-smi.exe -rgc` hoàn thành với mã thoát Administrator 0.

Logic dừng:

1. Tại 35 prediction, bốn lỗi terminal khiến cận trên theo status chỉ còn 56/60.
2. Đánh giá offline phát hiện lỗi thứ năm ẩn sau `SUCCEEDED` (`olist_acc_021`).
3. Cận trên thực là `30 đã đúng + 25 chưa chạy = 55/60`.
4. Chạy tiếp không thể bằng champion 57/60 và chỉ tốn thêm nhiều giờ compute, nên tiêu chí ngắt đã
   được thỏa mãn.

## 7. Vì sao ban đầu khả năng tăng accuracy có vẻ hợp lý

Kỳ vọng ban đầu hợp lý với tư cách một **giả thuyết**, nhưng mạnh hơn bằng chứng lúc đó.

### 7.1 PRACTIQ giải quyết ranh giới sản phẩm thực sự còn thiếu

Paper chính thức chỉ ra hạn chế của đánh giá text-to-SQL truyền thống: hầu hết dataset giả định câu
hỏi có một ý định rõ và trả lời được. PRACTIQ định nghĩa bốn nhóm mơ hồ, bốn nhóm không thể trả lời,
xây dựng khoảng 2.800 hội thoại và đánh giá hai task: phân loại category câu hỏi và dự đoán SQL có xét
làm rõ. Ranh giới `phân loại -> làm rõ/trợ giúp/từ chối -> SQL` nhắm trực tiếp vào SQL tự tin nhưng
không an toàn trên chat thực tế.

Điều đó gợi ý ba cải thiện đáng tin cậy:

1. từ chối câu hỏi không được dữ liệu hỗ trợ trước khi hallucinate bảng/cột;
2. giữ rõ metric, dimension, filter, grain và assumption cho planner;
3. hiểu nhất quán hơn chat command VI/EN, lỗi gõ, câu không dấu và lượt làm rõ tiếp theo.

Đây là cải thiện thực về reliability. Nhưng suy luận rằng intent tốt hơn chắc chắn làm execution
accuracy trên Olist sạch tăng là điều chưa được chứng minh.

### 7.2 Module mới khớp lỗi baseline đã biết

Baseline chỉ sai `014`, `023`, `038`; contract interpretation, xử lý status và semantic check mới
được thiết kế quanh các nhóm lỗi này. Chúng sửa `014`, `023` trong paired run và diagnostic riêng
từng pass `038`, khiến mục tiêu vượt 57/60 có vẻ khả thi.

Tuy nhiên, rerun nhắm mục tiêu là diagnostic phát triển, không phải mẫu không thiên lệch. Chúng đo
khả năng sửa lỗi đã biết nhưng không đo bao nhiêu case vốn đúng sẽ bị phá. Đây là selection bias:
chỉ test ba vị trí có upside không thể ước lượng thay đổi ròng trên 57 case còn lại.

### 7.3 Mô hình tư duy ban đầu coi analyst là tầng bổ sung an toàn

```text
interpretation tốt hơn -> pipeline SQL đã kiểm chứng nhận input tốt hơn -> accuracy bằng hoặc cao hơn
```

Nhưng implementation thực tế là:

```text
output analyst
  -> thay đổi concept và assumption
  -> thay đổi retrieval candidate và schema ownership
  -> thay đổi logical plan
  -> thay đổi SQL
  -> kích hoạt nhánh semantic-validator mới
  -> dùng chung deadline với correction
```

Analyst không phải guard thụ động. Khi mang tính thẩm quyền, nó thay đổi nhiều phân phối downstream
và có thể tạo lỗi mới ngay cả khi hiểu đúng ngôn ngữ tự nhiên.

### 7.4 Paper không chứng minh phép chuyển giao cụ thể này

PRACTIQ cho thấy phát hiện ambiguous/unanswerable và sinh SQL sau làm rõ là quan trọng và khó. Paper
không báo cáo rằng thêm một prompt call vào pipeline Olist local đã mạnh sẽ làm accuracy câu hỏi sạch
tăng đơn điệu. Phần giới hạn nói tác giả chưa fine-tune model mã nguồn mở bằng dữ liệu sinh ra do hạn
chế thời gian và để lại cho nghiên cứu tương lai. Framework/dataset là cơ sở cho mục tiêu reliability,
không phải bảo đảm plug-and-play cho tích hợp prompt-only Qwen3-14B.

## 8. Vì sao accuracy đo được lại giảm

### 8.1 Mục tiêu tối ưu và benchmark khác nhau

Olist-60 gồm câu hỏi sạch, answerable và kỳ vọng SQL. Nó không cộng điểm cho clarification đúng hoặc
refusal đúng. Khả năng bổ sung chính của PRACTIQ gần như không có upside trên phân phối này, nhưng
classification, interpretation, retrieval và validation mới vẫn tạo thêm bề mặt lỗi.

Kiến trúc mới tối ưu cho hỗn hợp task khác, trong khi gate chỉ đo lát cắt answerable-SQL cũ. Model có
thể giảm confident-wrong trên chat lộn xộn nhưng vẫn mất accuracy sạch. Cả hai có thể đồng thời đúng;
thí nghiệm này chỉ chứng minh trực tiếp điều thứ hai cho implementation hiện tại.

### 8.2 Baseline 95% gần như không có ngân sách hồi quy

Ở 57/60 chỉ có ba lỗi để sửa. Muốn đạt 58/60 phải có ít nhất một phục hồi ròng:

```text
2 lỗi baseline được sửa
- 5 case vốn đúng bị hồi quy
= giảm ròng 3 case đúng trong 35 case đầu
```

Ở mức trần này, heuristic sửa một case nhưng phá hai case đúng là không thể chấp nhận. Thay đổi phải
mang tính phẫu thuật và đơn điệu; các rule xuyên tầng mới không đạt hai đặc tính đó.

### 8.3 Lỗi khuếch đại qua nhiều giai đoạn

| Case | Tín hiệu analyst/plan | Điểm hỏng downstream | Hậu quả |
|---|---|---|---|
| `021` | Hiểu đúng “sản phẩm thiếu danh mục” | linker chọn bảng dịch làm quần thể | chạy được nhưng sai `0` thay vì `610` |
| `027` | Scalar `MAX(payment_value_cents)` đúng | rule superlative/ranking từ chối scalar maximum | false positive `SEMANTIC_MISMATCH` |
| `029` | Ý tưởng trung bình số item/đơn đúng | validator không phân giải alias `item_count` | sai `UNKNOWN_COLUMN`; không chọn semantic view |
| `031` | Analyst gọi đúng view và `customer_unique_id` | ownership phía sau quay về bảng thô | sai identity và grouped top-one |
| `035` | Intent doanh thu/danh mục Anh đúng | exact-dimension không đóng kín join | thiếu bảng products, dùng cột không tồn tại |

Trong nhiều case, cách hiểu nghiệp vụ của LLM đúng. Accuracy giảm vì thông tin bị làm yếu, ghi đè
hoặc validation sai giữa các contract. Nhiều reasoning hơn không bảo đảm ràng buộc schema vật lý còn
tồn tại tới generation.

### 8.4 Lượt gọi mới tiêu thụ ngân sách correction

| Case | Tổng độ trễ | Answerability | Correction |
|---|---:|---:|---|
| `027` | 193,2 giây | 103,9 giây | không chạy; `DEADLINE` |
| `029` | 153,5 giây | 84,3 giây | không chạy; `DEADLINE` |
| `031` | 143,5 giây | 78,9 giây | không chạy; `DEADLINE` |
| `035` | 174,8 giây | 101,4 giây | không chạy; `DEADLINE` |

Baseline thử sáu correction và cứu cả sáu. Answerability chiếm khoảng nửa hoặc hơn thời gian trong
các trace này, làm deadline chung hết đúng lúc cần repair. Kiến trúc thêm reasoning nhưng thực tế
loại bỏ recovery có giá trị cao trên case khó.

Không thể kết luận lượt gọi mới một mình gây mọi lỗi: baseline dùng sáu GPU layer, safe run dùng một
layer và cap 300--600 MHz, nên latency không phải A/B chỉ khác kiến trúc. Tuy vậy, `DEADLINE` trong
trace chứng minh cách phân bổ hiện tại không tương thích với correction dưới profile an toàn bắt buộc.

### 8.5 Heuristic cục bộ có tương tác không đơn điệu

- exact-dimension giúp lookup đơn giản nhưng ở `035` chọn dimension mà không bảo đảm join hoàn chỉnh;
- thu gọn mơ hồ vật lý tránh hỏi thừa nhưng ở `021` bỏ safety pause khi chưa chứng minh population;
- base-entity giúp count trực tiếp nhưng ở `029`, `031` đẩy semantic view đúng grain ra ngoài;
- superlative guard bắt `ORDER BY ... LIMIT 1` sai nhưng ở `027` từ chối scalar `MAX` hợp lệ.

Đây là lỗi tương tác, không chứng minh từng nguyên lý sai. Mỗi rule cần precondition có kiểu và
invariant test thay vì bonus điểm toàn cục hoặc keyword match.

### 8.6 Thành công workflow bị nhầm với kết quả đúng

`021` là `SUCCEEDED` vì SQL hợp lệ và chạy được. Chỉ so sánh result offline mới thấy đếm sai quan hệ.
Chỉ theo dõi status sẽ báo bốn thay vì năm lỗi và đánh giá cận trên sai thành 56/60. Execution success
là metric sức khỏe pipeline, không phải accuracy.

## 9. Phán quyết nhân quả

```text
mục tiêu PRACTIQ hữu ích
  + implementation kích hoạt trên suite toàn answerable
  + concept thẩm quyền thay đổi pipeline trưởng thành 95%
  + heuristic rộng thay invariant population/grain/join
  + LLM call bổ sung làm hết thời gian correction ở case khó
  = sửa hai lỗi dự kiến nhưng tạo năm hồi quy
```

Kết quả không biện minh cho “PRACTIQ làm giảm accuracy text-to-SQL”. Tuyên bố đúng là tích hợp
prompt-only, luôn bật hiện tại làm giảm accuracy Olist sạch dưới runtime Qwen3-14B an toàn. Thí nghiệm
chưa chấm phân phối ambiguous/unanswerable mà paper nhắm tới.

## 10. Các mối đe dọa đối với tính hợp lệ

- **Suite đã dừng:** chỉ đo case 1--35; 55/60 là cận trên, không phải điểm full run.
- **Nhiễu phần cứng:** GPU layer/xung khác nhau, tác động latency và cơ hội correction.
- **Tính ngẫu nhiên:** model/seed cố định không chứng minh output giống từng bit giữa mọi runtime.
- **Selection bias:** diagnostic lỗi đã biết không được ghép như quan sát holdout.
- **Metric mismatch:** Olist không đo clarification, false refusal, unanswerable hay confident-wrong.
- **Mẫu theo cặp nhỏ:** 35 case không hỗ trợ tuyên bố phổ quát cho mọi schema/ngôn ngữ/model.

## 11. Kiểm toán GitHub: commit chính xác của baseline

`origin` đúng repository `https://github.com/HelcurtLordno1/agentic-ai-textsql-learn.git`. Lệnh chỉ
đọc `git ls-remote origin refs/heads/main` ngày 2026-09-04 trả
`cebfeb1fd1499c0fcb7f88634b594e2bf9b5135e`, bằng `origin/main` và `HEAD`. Không fetch, checkout,
commit hay push.

| Ý nghĩa | Commit | Thời gian (UTC+07) | Bằng chứng |
|---|---|---|---|
| Revision code baseline | [`1509faa786534f36d33df34d4d5c4a9ed5fc1c54`](https://github.com/HelcurtLordno1/agentic-ai-textsql-learn/commit/1509faa786534f36d33df34d4d5c4a9ed5fc1c54) | 2026-08-14 17:03:45 | `feat: define laptop-stratified Gate P6 benchmark`; research plan xác định đây là revision baseline |
| Commit ghi/xác minh 57/60 | [`0972e4715f2aa8a64652c3b27d10c80f178bc162`](https://github.com/HelcurtLordno1/agentic-ai-textsql-learn/commit/0972e4715f2aa8a64652c3b27d10c80f178bc162) | 2026-08-14 22:27:54 | thêm `docs/evidence/p6_gate.md`, ghi Olist 57/60 và Spider 130/200 |
| Remote `main` hiện tại, không phải baseline sạch | [`cebfeb1fd1499c0fcb7f88634b594e2bf9b5135e`](https://github.com/HelcurtLordno1/agentic-ai-textsql-learn/commit/cebfeb1fd1499c0fcb7f88634b594e2bf9b5135e) | 2026-09-03 08:47:51 | đã thêm reliability workflow và hardware runbook |

Git xác nhận `0972e47` là con trực tiếp của `1509faa`; diff chỉ đổi tài liệu/evidence/ledger, không đổi
runtime. Trích dẫn chính xác là:

> **Revision hệ thống baseline:** `1509faa`; **commit bằng chứng:** `0972e47`; **Olist đã xác minh:**
> 57/60 (95,00%), ghi nhận ngày 2026-08-14.

Chỉ gọi `0972e47` là commit code sẽ làm mờ provenance; chỉ dùng `1509faa` sẽ bỏ nơi điểm được ghi.
`cebfeb1` không phải champion sạch vì đã chứa reliability workflow về sau.

## 12. Khuyến nghị kiến trúc và thí nghiệm đã điều chỉnh

1. Giữ P6 (`57/60`) làm champion; giữ `R1-M1` chưa verified.
2. Làm PRACTIQ gate có điều kiện: fast path xác định, rẻ cho câu sạch; chỉ gọi analyst khi có dấu hiệu
   mơ hồ/unsupported.
3. Biến ràng buộc `Interpretation` thành invariant bắt buộc: population owner, business identity,
   grain, scalar/ranking và join path đóng kín phải sống qua planning/linking hoặc fail closed.
4. Dành trước budget correction, tách budget từng stage thay vì deadline chung. Không nới giới hạn
   nhiệt, RAM, VRAM hay công suất để giải quyết latency.
5. Thay heuristic keyword/score toàn cục bằng predicate có kiểu; thêm test xác định cho năm cơ chế lỗi
   mà không import gold vào runtime.
6. Đánh giá độc lập:
   - Olist clean-answerable no-regression: fresh 60/60, ít nhất 57/60, tốt nhất từ 58/60;
   - PRACTIQ reliability: macro-F1 theo category, false-refusal, clarification success,
     unsupported-query recall và confident-wrong.
7. Dùng evaluation ID, source/config hash và prediction file mới sau mỗi đổi code; không ghép prefix
   v3 đã dừng vào implementation mới.

Mệnh đề cần kiểm tra là: reliability tăng trên chat lộn xộn **mà không** hy sinh champion sạch.

## 13. Ranh giới tuyên bố

- Đã chứng minh: v3 không thể vượt 55/60 và kém baseline 57/60.
- Đã đo: prefix mới 30/35 so với baseline theo cặp 33/35.
- Chưa đo: case 36--60, holdout mới hoặc full latency distribution v3.
- Không tuyên bố: Paper I nói chung giảm SQL accuracy hay clarification an toàn không có giá trị.
- Gate: biến thể hiện tại bị **LOẠI khỏi promotion**; không đánh dấu `R1-M1` là `VERIFIED`.

## 14. Kiểm tra repository sau khi dừng

Kiểm tra bắt buộc đã hoàn thành sau cập nhật báo cáo/ledger: Ruff pass, 227 file pass format check,
strict mypy hoàn thành, non-Ollama suite pass **221 test**, một test Ollama deselect. Cảnh báo duy nhất
là deprecation hiện có của Starlette/httpx test client. Không có benchmark/model local chạy khi kiểm
tra.

## 15. Nguồn nghiên cứu bên ngoài

- Dong và cộng sự, [PRACTIQ: A Practical Conversational Text-to-SQL Dataset with Ambiguous and
  Unanswerable Queries](https://aclanthology.org/2025.naacl-long.13/), NAACL 2025,
  DOI `10.18653/v1/2025.naacl-long.13`.
- Link commit GitHub tại Mục 11 là audit trail công khai cho revision baseline, evidence commit và
  remote `main`. Git object local và remote hash cũng được kiểm tra để không dùng timestamp của công
  cụ tìm kiếm làm provenance.
