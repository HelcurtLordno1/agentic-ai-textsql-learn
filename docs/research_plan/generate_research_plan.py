#!/usr/bin/env python3
# ruff: noqa: E501, RUF001
"""Generate the post-P6 Text-to-SQL research plan as Markdown and standalone HTML.

The generator intentionally uses only the Python standard library. It reads no raw
benchmark data and copies no predictions or gold answers into the documentation.
Run it from any working directory:

    uv run python docs/research_plan/generate_research_plan.py
    uv run python docs/research_plan/generate_research_plan.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import html
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
MARKDOWN_PATH = SCRIPT_DIR / "research_plan.md"
HTML_PATH = SCRIPT_DIR / "research_plan.html"
SURVEY_CUTOFF = "2026-08-22"
PLAN_GENERATED_DATE = "2026-08-22"
PLAN_BASE_HEAD = "46a9c95cffa101f3198b44a49589a68c7fba08c4"


BASELINE = {
    "benchmark_commit": "1509faa786534f36d33df34d4d5c4a9ed5fc1c54",
    "gate_commit": "0972e4715f2aa8a64652c3b27d10c80f178bc162",
    "spider": {
        "score": "130/200",
        "accuracy": "65,00%",
        "holdout": "67/100",
        "valid": "199/200",
        "p50": "58,51 s",
        "p95": "85,29 s",
    },
    "olist": {
        "score": "57/60",
        "accuracy": "95,00%",
        "holdout": "15/15",
        "first_pass": "51/60",
        "p50": "61,92 s",
        "p95": "91,62 s",
    },
    "retrieval": {
        "table": "100,00%",
        "column": "99,65%",
        "schema": "99,75%",
        "join": "86,36%",
    },
}


SOURCES = [
    {
        "id": "spider",
        "name": "Spider",
        "url": "https://aclanthology.org/D18-1425/",
        "evidence": "10.181 câu hỏi, 200 CSDL, split cross-domain theo database.",
        "use": "Giữ làm benchmark generalization chính, nhưng không gọi subset-200 là leaderboard.",
    },
    {
        "id": "test-suite",
        "name": "Test-suite accuracy",
        "url": "https://aclanthology.org/2020.emnlp-main.29/",
        "evidence": "Single-database/ESM có false negative trung bình 2,5%, tệ nhất 8,1%.",
        "use": "Bổ sung TS hoặc mutation tests trước khi tối ưu theo score.",
    },
    {
        "id": "benchmark-audit",
        "name": "Cross-domain benchmark audit",
        "url": "https://aclanthology.org/2023.emnlp-main.99/",
        "evidence": (
            "Underspecification, assumptions và nhiều SQL tương đương có thể làm metric chuẩn "
            "đánh giá sai; manual re-evaluation còn đổi thứ hạng model."
        ),
        "use": (
            "Gắn nhãn ambiguity/uncertainty và review paired regressions; không tối ưu mù theo một gold SQL."
        ),
    },
    {
        "id": "ambiqt",
        "name": "AmbiQT",
        "url": "https://aclanthology.org/2023.emnlp-main.436/",
        "evidence": (
            "Hơn 3.000 câu có hai SQL hợp lý do lexical/structural ambiguity; LogicalBeam đa dạng "
            "logic top-k hiệu quả hơn token beam tới 2,5 lần."
        ),
        "use": (
            "Tách semantic interpretations trước candidate SQL; nếu hai interpretation đều hợp lý thì hỏi user."
        ),
    },
    {
        "id": "practiq",
        "name": "PRACTIQ",
        "url": "https://aclanthology.org/2025.naacl-long.13/",
        "evidence": (
            "Benchmark hội thoại cho câu ambiguous/unanswerable, dùng chu trình hỏi làm rõ rồi mới sinh SQL "
            "và giải thích kết quả."
        ),
        "use": (
            "Thêm answerability gate và clarification contract thay vì bắt hệ thống luôn phải đoán một SQL."
        ),
    },
    {
        "id": "know-unknown",
        "name": "Know What I Don't Know",
        "url": "https://aclanthology.org/2023.findings-acl.352/",
        "evidence": (
            "Phân loại sáu nhóm câu ambiguous/unanswerable và đề xuất Detecting-Then-Explaining thay vì "
            "luôn sinh một SQL có vẻ hợp lý."
        ),
        "use": "Huấn luyện/evaluate router trên counterfactual negatives và yêu cầu reason code có thể giải thích.",
    },
    {
        "id": "din-sql",
        "name": "DIN-SQL",
        "url": "https://arxiv.org/abs/2304.11015",
        "evidence": "Decomposition + self-correction báo 85,3% EX trên Spider test.",
        "use": "Mượn phân loại độ khó và plan theo clause; không mượn model GPT-4.",
    },
    {
        "id": "dail-sql",
        "name": "DAIL-SQL",
        "url": "https://arxiv.org/abs/2308.15363",
        "evidence": "Structural example selection đạt 86,6% EX Spider và chú trọng token efficiency.",
        "use": "Thử verified examples theo SQL skeleton sau khi có leakage audit.",
    },
    {
        "id": "cot",
        "name": "CoT-style prompting for Text-to-SQL",
        "url": "https://aclanthology.org/2023.emnlp-main.327/",
        "evidence": "Prompt reasoning chuyên biệt tăng 5,2 điểm tuyệt đối trên Spider dev.",
        "use": "Thiết kế plan ngắn theo clause; tránh reasoning dài gây error propagation.",
    },
    {
        "id": "dart-sql",
        "name": "DART-SQL",
        "url": "https://aclanthology.org/2024.findings-acl.120/",
        "evidence": "Database-content rewriting + execution refinement tăng trung bình 12,41% cho DAIL-SQL.",
        "use": "Ưu tiên value grounding và rewrite có kiểm soát cho filter/entity.",
    },
    {
        "id": "pet-sql",
        "name": "PET-SQL",
        "url": "https://arxiv.org/abs/2403.09732",
        "evidence": "Cell values + two-round refinement + cross-consistency báo 87,6% EX Spider.",
        "use": "Thử hai vòng chỉ cho case khó; không random cell values không giới hạn.",
    },
    {
        "id": "chess",
        "name": "CHESS",
        "url": "https://arxiv.org/abs/2405.16755",
        "evidence": "Schema selector báo khoảng +2 điểm, giảm token 5 lần; BIRD test 71,10%.",
        "use": "Học entity/value retrieval và unit-test verifier; schema pruning không phải bottleneck hiện tại.",
    },
    {
        "id": "chase-sql",
        "name": "CHASE-SQL",
        "url": "https://arxiv.org/abs/2410.01943",
        "evidence": "Multi-path generation + pairwise selector đạt 73,01% EX BIRD dev.",
        "use": "Adaptive best-of-3 trên case khó thay vì nhân compute cho mọi câu.",
    },
    {
        "id": "omnisql",
        "name": "OmniSQL / SynSQL-2.5M",
        "url": "https://www.vldb.org/pvldb/vol18/p4695-li.pdf",
        "evidence": (
            "OmniSQL-14B greedy: 81,4% TS Spider dev, 64,2% EX BIRD dev; "
            "synthetic data giúp OmniSQL-7B +4,3 điểm Spider dev và +8,8 BIRD dev."
        ),
        "use": "A/B model 7B rồi 14B; dùng external/robustness set vì model đã train với Spider/BIRD.",
    },
    {
        "id": "dr-spider",
        "name": "Dr.Spider",
        "url": "https://arxiv.org/abs/2301.08881",
        "evidence": "17 perturbations; model mạnh nhất vẫn giảm 14,0% tổng và 50,7% ở perturbation khó nhất.",
        "use": "Dùng làm diagnostic robustness, không trộn với accuracy Spider gốc.",
    },
    {
        "id": "bird",
        "name": "BIRD",
        "url": "https://arxiv.org/abs/2305.03111",
        "evidence": "12.751 cặp, 95 CSDL/33,4 GB; nhấn mạnh dirty values và external knowledge.",
        "use": "Chỉ Mini-Dev sau Spider; học cách chuẩn bị database descriptions và value index.",
    },
    {
        "id": "apel",
        "name": "APEL for non-programmers",
        "url": "https://aclanthology.org/2023.emnlp-main.312/",
        "evidence": (
            "Người không biết SQL chọn output trên input phân biệt candidate đạt cùng annotation accuracy "
            "75% như expert annotators và phát hiện lỗi annotation tinh vi."
        ),
        "use": (
            "Thiết kế feedback bằng result/assumption choice, không bắt user đọc SQL hay bấm đúng/sai mơ hồ."
        ),
    },
    {
        "id": "cosql",
        "name": "CoSQL",
        "url": "https://aclanthology.org/D19-1204/",
        "evidence": (
            "30k+ lượt hội thoại trên 200 DB gồm clarify ambiguity, báo unanswerable và diễn giải execution result."
        ),
        "use": "Định nghĩa dialog acts ANSWER/CLARIFY/CANNOT_ANSWER/REPHRASE cho UI không-code.",
    },
    {
        "id": "picard",
        "name": "PICARD",
        "url": "https://aclanthology.org/2021.emnlp-main.779/",
        "evidence": "Incremental parsing loại token không thể tạo chương trình SQL hợp lệ trong lúc decode.",
        "use": (
            "Giữ như phương án constrained decoding cho model fine-tuned; hiện invalid syntax không phải "
            "bottleneck nên không ưu tiên trước semantic verifier."
        ),
    },
    {
        "id": "spider2",
        "name": "Spider 2.0",
        "url": "https://openreview.net/forum?id=XmProj9cPs",
        "evidence": (
            "632 workflow thực tế, schema trung bình 812 cột, nhiều dialect và context từ docs/codebase; "
            "ICLR 2025 báo model mạnh vẫn có success rate thấp."
        ),
        "use": (
            "Dùng làm north-star enterprise sau khi SQLite single-query core ổn; không đưa ngay vào laptop gate."
        ),
    },
    {
        "id": "revisql",
        "name": "ReViSQL (2026 preprint)",
        "url": "https://arxiv.org/abs/2603.20004",
        "evidence": (
            "Audit sửa 61,1% subset BIRD Train; verified data tăng single-generation "
            "8,2–13,9 điểm trong cùng RLVR setup."
        ),
        "use": "Đặt data verification trước RL/LoRA; kết quả model lớn không chuyển trực tiếp sang laptop.",
    },
    {
        "id": "sql-of-thought",
        "name": "SQL-of-Thought",
        "url": "https://arxiv.org/abs/2509.00581",
        "evidence": (
            "Báo 91,59% EX Spider dev; mini ablation giảm ít nhất 5 điểm nếu bỏ plan và "
            "8–10 điểm nếu bỏ correction."
        ),
        "use": "Giữ taxonomy-guided repair, nhưng phải tái kiểm chứng bằng Qwen local và evaluator khóa.",
    },
    {
        "id": "bird-noise",
        "name": "BIRD noise audit",
        "url": "https://aclanthology.org/2024.acl-short.34/",
        "evidence": (
            "ACL 2024 tìm thấy noise ở question/gold SQL đủ để đổi thứ hạng giữa zero-shot "
            "và prompting methods sau correction."
        ),
        "use": "Thêm label uncertainty, gold review và benchmark-quality gate trước khi tin score.",
    },
    {
        "id": "metadata",
        "name": "Automatic Metadata Extraction",
        "url": "https://arxiv.org/abs/2505.19988",
        "evidence": (
            "Khảo sát profiling, query logs và SQL-to-text metadata; profiling-only từng đứng đầu "
            "BIRD theo thời điểm paper."
        ),
        "use": "Thiết kế bounded profiler + value/description evidence thay cho mô tả thủ công ad hoc.",
    },
    {
        "id": "solid-sql",
        "name": "Solid-SQL",
        "url": "https://aclanthology.org/2025.coling-main.654/",
        "evidence": (
            "Structural two-round example retrieval đạt 82,1% Spider, 58,9% BIRD và cải thiện "
            "trung bình 11,6% trên robustness variants."
        ),
        "use": "Kết hợp structure-aware examples với paraphrase robustness, nhưng khóa leakage theo DB.",
    },
]


EXPERIMENTS = [
    {
        "id": "R0",
        "priority": "P0",
        "lane": "Đo lường",
        "title": "Khóa baseline hiện tại và rerun revision mới",
        "why": (
            "Điểm 65%/95% thuộc generator v4/corrector v3 tại commit 1509faa; code hiện tại đã là "
            "generator v6/corrector v5 nên chưa có accuracy hợp lệ."
        ),
        "done": "P6 đã có manifest/hash/seed/model digest, 200/200 typed terminal và gold separation.",
        "world": "Test-suite accuracy cho thấy single denotation có thể đánh giá sai semantics.",
        "hypothesis": "Baseline v6 khóa lại sẽ phân biệt gain thật với regression do hardening/model variance.",
        "work": (
            "Tạo experiment ID mới; rerun Spider-200 và Olist-60 không đổi dữ liệu; thêm TS/mutation score; "
            "lưu aggregate + per-case delta ngoài Git theo policy."
        ),
        "metric": "Spider EX/TS; Olist result accuracy; paired per-case delta; p50/p95.",
        "promote": "200/200 hoàn tất, config/hash đầy đủ, safety 100%; đây là mốc B0, chưa đòi tăng điểm.",
        "kill": "Dừng nếu commit/model/index/prompt không khóa hoặc evaluator self-test không pass.",
        "effort": "2–3 ngày máy",
        "expected": "Đo lường, không hứa gain",
    },
    {
        "id": "R1",
        "priority": "P0",
        "lane": "Dữ liệu",
        "title": "Biến 70 lỗi Spider thành failure dataset có nhãn nguyên nhân",
        "why": (
            "68/70 lỗi là EXECUTION_MISMATCH; taxonomy runtime hiện không nói được sai join, aggregate, "
            "filter value, nesting, set operation hay output grain."
        ),
        "done": "Đã có difficulty/database slices; retrieval recall gần bão hòa; report giữ đủ denominator.",
        "world": "Dr.Spider dùng 17 perturbations; SQL-of-Thought dùng taxonomy logic để correction có mục tiêu.",
        "hypothesis": "Top 3 semantic causes sẽ bao phủ ít nhất 60% lỗi và quyết định đúng experiment kế tiếp.",
        "work": (
            "Offline-only: AST diff predicted/gold, result-shape diff, schema/value evidence, nhãn primary + "
            "secondary cause; review tay sample 20%; tạo dashboard error × complexity × DB."
        ),
        "metric": "Coverage nhãn 100%; agreement review ≥90%; top-cluster coverage; oracle recoverability.",
        "promote": "Mọi lỗi có evidence và một owner module; chọn R2–R6 theo dữ liệu, không theo cảm tính.",
        "kill": "Không dùng gold label trong runtime/prompt; artifact chi tiết tiếp tục gitignored.",
        "effort": "3–5 ngày",
        "expected": "Giảm rủi ro nghiên cứu sai hướng",
    },
    {
        "id": "R2",
        "priority": "P0",
        "lane": "Công nghệ lõi",
        "title": "Question contract: normalize, answerability và clarification",
        "why": (
            "User không-code sẽ hỏi thiếu chuẩn, nhiều nghĩa hoặc ngoài dữ liệu; đoán một SQL tạo "
            "answer sai nhưng có vẻ hợp lý."
        ),
        "done": (
            "Router đã có QUERY/CLARIFY/UNSUPPORTED/WRITE và hỗ trợ VI/EN, nhưng chưa có ambiguity "
            "confidence hay multi-turn contract."
        ),
        "world": (
            "AmbiQT, PRACTIQ, CoSQL và Know What I Don't Know đều yêu cầu biểu diễn nhiều "
            "interpretation hoặc hỏi làm rõ."
        ),
        "hypothesis": (
            "Tách interpretation trước SQL sẽ giảm confident-wrong và tăng task success cho câu "
            "paraphrase/ambiguous."
        ),
        "work": (
            "Canonicalize typo/VI-EN mix; tạo 1–3 interpretation có assumptions; classifier "
            "answerable/ambiguous/unanswerable; sinh một câu hỏi làm rõ với options không chứa jargon SQL."
        ),
        "metric": (
            "Routing macro-F1; ambiguity recall; clarification success; answer coverage; selective risk; "
            "paraphrase consistency."
        ),
        "promote": (
            "Ambiguity recall ≥85%, answerable false-refusal ≤3%, confident-wrong giảm ≥30% trên challenge set."
        ),
        "kill": "Clarify quá 15% câu answerable hoặc bắt user biết tên table/column.",
        "effort": "5–8 ngày",
        "expected": "Tăng reliability/user success; benchmark gốc có thể trung tính",
    },
    {
        "id": "R3",
        "priority": "P1",
        "lane": "Dữ liệu",
        "title": "Semantic catalog + bounded value/entity grounding",
        "why": (
            "Schema recall cao không đồng nghĩa hiểu business metric, enum, alias, date format, unit "
            "hay cell value—đặc biệt ở filter, identity và population."
        ),
        "done": "Safe Profiler L2-M2 và verified example store vẫn NOT_STARTED; catalog đã có type/FK/hash.",
        "world": "DART-SQL, PET-SQL, CHESS và BIRD đều cho thấy database content là tín hiệu quan trọng.",
        "hypothesis": (
            "Metric contracts cùng top/exact/rare-value retrieval đúng column giảm lỗi filter, "
            "identity, population và grain."
        ),
        "work": (
            "Profile allowlisted columns; metric/dimension registry; normalize aliases/units/time grain; "
            "value index có provenance và caps; ablate từng evidence type."
        ),
        "metric": "Value recall@k; metric-link F1; filter/grain slice EX; context tokens; privacy fixtures.",
        "promote": "≥+3 điểm trên slice value/filter và ≥+2 điểm overall; không leakage, không vượt budget.",
        "kill": "Value context làm overall giảm >1 điểm, context tăng >30% mà không gain, hoặc lộ value nhạy cảm.",
        "effort": "5–8 ngày",
        "expected": "+1 đến +4 điểm",
    },
    {
        "id": "R4",
        "priority": "P1",
        "lane": "Công nghệ lõi",
        "title": "Plan theo clause và query skeleton cho case medium/extra-hard",
        "why": "Medium chỉ 50,94%, extra-hard 36,36%; current plan chưa được đo bằng plan-quality oracle.",
        "done": "Planner v2 typed và generator v6 đã có scalar/ranking/owner/scope constraints.",
        "world": "CoT chuyên Text-to-SQL +5,2 điểm; DIN-SQL và SQL-of-Thought nhấn mạnh decomposition/plan.",
        "hypothesis": "Plan ngắn, kiểm được theo SELECT/FROM/WHERE/GROUP/HAVING/ORDER/set sẽ giảm lỗi cấu trúc.",
        "work": (
            "Tạo plan rubric từ R1; thêm SQL skeleton không chứa identifier gold; validate clause consistency; "
            "chỉ kích hoạt enhanced plan cho medium/hard classifier."
        ),
        "metric": "Clause F1 offline; EX theo difficulty; plan→SQL consistency; output tokens; latency.",
        "promote": "≥+5 điểm medium+hard aggregate, ≥+2 overall, easy regression ≤1 case.",
        "kill": "Reasoning dài tăng latency >25% hoặc tạo error propagation mà EX không tăng.",
        "effort": "5–7 ngày",
        "expected": "+2 đến +5 điểm",
    },
    {
        "id": "R5",
        "priority": "P1",
        "lane": "Dữ liệu",
        "title": "Verified few-shot retrieval theo structure, chống leakage",
        "why": "L6-M2 chưa làm; generator hiện không tận dụng kho ví dụ đã execute và review.",
        "done": "Có 60 Olist reviewed cases, Spider train và contract provenance; chưa có example store.",
        "world": "DAIL-SQL dùng skeleton similarity; PET-SQL dùng question-SQL retrieval; Solid-SQL dùng two-round ICL.",
        "hypothesis": "1–3 ví dụ cùng skeleton giúp small/local model ánh xạ intent→SQL tốt hơn prompt zero-shot.",
        "work": (
            "Chỉ ingest train/dev được phép; canonical AST skeleton; dedup question/schema/SQL; split theo DB và "
            "template; retrieve question + skeleton proxy; ablate 0/1/3 examples và order."
        ),
        "metric": "EX/TS; retrieval relevance; leakage audit 100%; prompt tokens; gain theo skeleton rarity.",
        "promote": "≥+3 điểm overall hoặc ≥+5 điểm rare-skeleton; không exact/paraphrase leakage.",
        "kill": "Gain mất trên database-disjoint set hoặc prompt >4096/token budget.",
        "effort": "6–9 ngày",
        "expected": "+2 đến +5 điểm",
    },
    {
        "id": "R6",
        "priority": "P1",
        "lane": "Công nghệ lõi",
        "title": "Adaptive best-of-3 với logic diversity và selector",
        "why": (
            "Một candidate deterministic bỏ lỡ pass@k; các biến thể token gần nhau không tạo "
            "semantic diversity hữu ích."
        ),
        "done": "Candidate budgets, policy, read-only executor và trace đã sẵn; laptop chỉ cho parallelism 1.",
        "world": (
            "AmbiQT LogicalBeam đa dạng logic; PET-SQL dùng cross-consistency; CHASE-SQL dùng "
            "multi-path reasoning và candidate selection."
        ),
        "hypothesis": "Sinh 3 candidate đa dạng chỉ ở case khó rồi chọn gold-blind sẽ chuyển pass@3 thành EX gain.",
        "work": (
            "Đo pass@3 oracle trước; diversify theo interpretation/plan chứ không chỉ seed; group result "
            "fingerprints; rank AST/evidence/invariants; chạy tuần tự chỉ cho hard/ambiguous cases."
        ),
        "metric": "pass@1/pass@3; selector accuracy; final EX; candidate diversity; calls/latency/energy.",
        "promote": "Oracle pass@3 ≥ baseline +8 điểm và selector thu ≥50% oracle gap; final +3 điểm overall.",
        "kill": "Pass@3 gap <5 điểm hoặc p95/calls >2× mà gain <3 điểm.",
        "effort": "7–10 ngày",
        "expected": "+3 đến +7 điểm, compute cao",
    },
    {
        "id": "R7",
        "priority": "P2",
        "lane": "Công nghệ lõi",
        "title": "Semantic verifier, calibrated repair và safe abstention",
        "why": "68 execution mismatches không phát sinh runtime error nên current corrector phần lớn không được gọi.",
        "done": "Đã có validator intent/shape/Olist invariants và bounded correction; recovery Olist P6 là 6/6.",
        "world": "CHESS dùng natural-language unit tests; DART-SQL dùng execution-guided refinement.",
        "hypothesis": (
            "Verifier theo cluster R1 có thể giảm confident-wrong nếu threshold ANSWER/REPAIR/"
            "CLARIFY/ABSTAIN được calibrate trên held-out data."
        ),
        "work": (
            "Mutation checks; NL↔SQL intent reconstruction; result invariants; verifier ensemble; "
            "calibrate decision thresholds, không dùng raw model self-confidence như probability."
        ),
        "metric": (
            "Detection AUROC/AUPRC; ECE/Brier; selective risk@coverage; repair recovery; "
            "correct→wrong; net EX."
        ),
        "promote": "Precision ≥90%, recall ≥35%, net +2 điểm, correct→wrong ≤1%.",
        "kill": "False-positive >5%, gold-derived signal lọt runtime, hoặc correction regression >gain.",
        "effort": "8–12 ngày",
        "expected": "+2 đến +5 điểm",
    },
    {
        "id": "R8",
        "priority": "P2",
        "lane": "Dữ liệu",
        "title": "Verified data flywheel + hard negatives; LoRA chỉ sau audit",
        "why": "Fine-tune sớm trên noisy/leaky data có thể làm benchmark đẹp nhưng generalization kém.",
        "done": (
            "Repo có run/feedback lineage, synthetic fixture và reviewed Olist; chưa có training "
            "corpus/versioned data card."
        ),
        "world": (
            "OmniSQL cho thấy synthetic scale; ReViSQL nhấn mạnh verified data; APEL cho phép "
            "non-programmers chọn output phân biệt thay vì đọc SQL."
        ),
        "hypothesis": "Dữ liệu sạch, diverse, DB-disjoint và có error pairs giúp 7B/14B tăng semantic reasoning.",
        "work": (
            "Capture question/clarification/outcome; APEL-style output/assumption choice; expert review "
            "queue; execute/dedup/leakage gates; LoRA 7B pilot chỉ sau data card."
        ),
        "metric": "Validity, dedup rate, coverage, reviewer acceptance; EX/TS external; robustness; forgetting.",
        "promote": "Data acceptance ≥95%; external DB-disjoint +3 điểm; không giảm Olist/robustness >1 điểm.",
        "kill": "Không đủ license/provenance, contamination audit fail, hoặc chỉ tăng train-like Spider slice.",
        "effort": "3–6 tuần",
        "expected": "+3 đến +10 điểm, rủi ro/cost cao",
    },
    {
        "id": "R9",
        "priority": "P2",
        "lane": "Đánh giá",
        "title": "Robustness + no-code user release ladder",
        "why": (
            "65% Spider chưa đo typo/paraphrase/ambiguity/unanswerable, task completion hoặc việc "
            "người không-code có hiểu answer/assumptions hay không."
        ),
        "done": "Gold-aware evaluator tách runtime; user đã lưu paper Dr.Spider; BIRD là optional roadmap.",
        "world": (
            "Dr.Spider/Solid-SQL đo perturbation; PRACTIQ/CoSQL đo clarification; Spider 2.0 "
            "mở rộng tới enterprise workflows."
        ),
        "hypothesis": "Một cải tiến thật phải giữ gain khi đổi cách diễn đạt và domain, không chỉ khớp Spider.",
        "work": (
            "Locked Dr.Spider-lite + PRACTIQ-like local set + fresh bilingual Olist; test 5–8 "
            "no-code users; Spider 2.0-lite chỉ sau core freeze."
        ),
        "metric": (
            "EX/TS; perturbation consistency; task success; clarification turns; answer comprehension; "
            "time-to-insight."
        ),
        "promote": "Gain cùng dấu external; no-code task success ≥85%; safety 100%; không che abstention.",
        "kill": "Không trộn dataset/metric thành một score; dừng nếu disk/compute vượt laptop budget.",
        "effort": "1–3 tuần máy",
        "expected": "Release proof, không trực tiếp hứa gain",
    },
    {
        "id": "R10",
        "priority": "P1",
        "lane": "Công nghệ lõi",
        "title": "A/B model chuyên Text-to-SQL: 7B trước 14B",
        "why": "Qwen3-14B là model tổng quát; specialist có thể tăng first-pass hoặc giảm latency.",
        "done": "Provider typed, digest pin, laptop governor và deterministic prompt contracts đã có.",
        "world": (
            "OmniSQL công bố model 7B/14B/32B từ SynSQL-2.5M; paper score không chuyển thẳng "
            "vì model đã train với Spider/BIRD."
        ),
        "hypothesis": "Specialist 7B có thể nằm trên Pareto frontier tốt hơn generalist 14B ở cùng evidence.",
        "work": (
            "Audit license/runtime; pilot 20; greedy one-candidate cùng context; 14B chỉ khi 7B "
            "có signal; chạy external robustness để kiểm train familiarity."
        ),
        "metric": "Paired EX/TS; first-pass; Dr.Spider slice; Olist; latency/W/RAM/VRAM.",
        "promote": "Spider +5 điểm hoặc accuracy ngang nhưng p95 giảm ≥25%; Olist mất tối đa 1 case.",
        "kill": "Không fit guarded profile, license không hợp hoặc gain chỉ tồn tại trên familiar set.",
        "effort": "3–6 ngày",
        "expected": "A/B đo được; không dùng paper score làm dự báo local",
    },
]


SCHEDULE = [
    ("Gate A", "Tuần 1", "R0", "Khóa B0 cho code hiện tại; snapshot provenance và evaluator."),
    ("Gate B", "Tuần 2", "R1", "Failure dataset 70 case; Pareto nguyên nhân và oracle study."),
    (
        "Gate C",
        "Tuần 3–4",
        "R2",
        "Answerability/ambiguity challenge set và clarification contract.",
    ),
    (
        "Gate D",
        "Tuần 4–6",
        "R3 hoặc R4",
        "Chọn đúng top failure cluster: value/metric hoặc structure.",
    ),
    ("Gate E", "Tuần 6", "R10", "A/B specialist 7B; chỉ thử 14B nếu pilot có signal."),
    ("Gate F", "Tuần 7", "R5", "Verified examples + leakage audit."),
    ("Gate G", "Tuần 8–9", "R6", "Adaptive pass@3 và selector; đo Pareto accuracy/latency."),
    ("Gate H", "Tuần 10–11", "R7", "Verifier calibrated; ANSWER/REPAIR/CLARIFY/ABSTAIN."),
    (
        "Gate I",
        "Tuần 12–14+",
        "R8/R9",
        "Chỉ train sau data audit; robustness, no-code UX và fresh release.",
    ),
]


BLUEPRINT_PHASES = [
    {
        "id": "B0",
        "stage": "Preserve",
        "period": "Tuần 0–1",
        "track": "shared",
        "title": "Đóng băng tài sản hiện tại",
        "objective": "Tạo baseline B0 đúng revision hiện tại trước mọi can thiệp.",
        "outputs": "Tag/manifest, Spider-200, Olist-60, TS/EX, latency, evidence fingerprint.",
        "gate": "Config/hashes đầy đủ; 100% workflow; không claim score v6 trước rerun.",
    },
    {
        "id": "B1",
        "stage": "Diagnose",
        "period": "Tuần 1–2",
        "track": "shared",
        "title": "Failure intelligence",
        "objective": "Biến 70 failures thành dataset causal, không chỉ error code runtime.",
        "outputs": "Taxonomy, AST/result diff, Pareto causes, owner module, oracle recoverability.",
        "gate": "100% labeled; review agreement ≥90%; top-3 causes bao phủ ≥60%.",
    },
    {
        "id": "U1",
        "stage": "Understand",
        "period": "Tuần 2–4",
        "track": "core",
        "title": "Question reliability contract",
        "objective": "Hiểu typo/paraphrase/ambiguity và biết khi nào phải hỏi hoặc từ chối đoán.",
        "outputs": "Interpretations, assumptions, answerability reason, clarification options, challenge set.",
        "gate": "Ambiguity recall ≥85%; false-refusal ≤3%; user không cần biết SQL jargon.",
    },
    {
        "id": "D1",
        "stage": "Prepare data",
        "period": "Tuần 3–4",
        "track": "data",
        "title": "Semantic context factory",
        "objective": "Chuẩn hóa metadata, descriptions, values và business semantics cho LLM.",
        "outputs": "Safe profile, value index, descriptions, aliases, lineage và quality dashboard.",
        "gate": "Value recall tăng; overall +2 điểm hoặc filter slice +3; zero leakage.",
    },
    {
        "id": "C1",
        "stage": "Improve core",
        "period": "Tuần 3–5",
        "track": "core",
        "title": "Specialist model + clause reasoning",
        "objective": "A/B SQL-specialized model và typed plan theo clause trên cùng evidence.",
        "outputs": "Specialist 7B/14B comparison, plan rubric, difficulty router, clause metrics.",
        "gate": "Spider +5 điểm hoặc latency -25% ở cùng accuracy; Olist giảm ≤1 case.",
    },
    {
        "id": "D2",
        "stage": "Teach from data",
        "period": "Tuần 5–7",
        "track": "data",
        "title": "Verified example memory",
        "objective": "Đưa 1–3 examples đúng structure vào prompt mà không làm leak benchmark.",
        "outputs": "Example store, AST skeleton index, dedup, DB-disjoint split, provenance.",
        "gate": "Overall +3 điểm hoặc rare-skeleton +5; leakage audit 100% pass.",
    },
    {
        "id": "C2",
        "stage": "Search & verify",
        "period": "Tuần 7–9",
        "track": "core",
        "title": "Adaptive candidate engine",
        "objective": "Easy đi fast path; hard sinh 3 paths và chọn bằng evidence gold-blind.",
        "outputs": "pass@3 oracle, diversity policy, result consensus, selector, semantic verifier.",
        "gate": "Final +3 điểm; selector thu ≥50% oracle gap; p95/calls không quá 2×.",
    },
    {
        "id": "D3",
        "stage": "Adapt model",
        "period": "Tuần 9–12+",
        "track": "data",
        "title": "Clean curriculum & hard negatives",
        "objective": "Chỉ LoRA sau khi corpus sạch, diverse, verified và contamination-safe.",
        "outputs": "Data card, synthetic SQL→question, hard negatives, LoRA-7B pilot.",
        "gate": "Data accept ≥95%; external DB-disjoint +3; không catastrophic forgetting.",
    },
    {
        "id": "B2",
        "stage": "Release",
        "period": "Sau freeze",
        "track": "shared",
        "title": "Champion integration & external proof",
        "objective": "Ghép chỉ các winner và chứng minh gain không phải overfit Spider-200.",
        "outputs": "Ablation ladder, fresh manifest/full Spider, Dr.Spider, Olist fresh holdout.",
        "gate": "Spider ≥70% rồi ≥75%; Olist ≥95%; safety 100%; gain cùng dấu external.",
    },
]


DATA_PIPELINE = [
    ("1. Inventory", "Nguồn, license, hash, dialect, ngôn ngữ, domain, split, reviewer."),
    ("2. Normalize", "Unicode/date/literal policy; SQLGlot parse; canonical AST và result shape."),
    ("3. Execute", "Read-only run, timeout/cap; loại query lỗi; lưu result hash ngoài Git."),
    (
        "4. Verify",
        "Question↔SQL semantic review; grain/join/filter/aggregate; reviewer confidence.",
    ),
    (
        "5. Deduplicate",
        "Exact text, paraphrase embedding, AST skeleton, result equivalence, template family.",
    ),
    (
        "6. Split",
        "Database-disjoint trước; sau đó template/semantic family; khóa tuning/validation/release.",
    ),
    (
        "7. Package",
        "Data card, provenance, version, quality metrics; raw/generated corpus gitignored.",
    ),
    (
        "8. Learn",
        "Feedback → outcome/assumption choice → expert review; không train trực tiếp từ thumbs.",
    ),
    (
        "9. Monitor",
        "Slice coverage, label drift, contamination scan và failure-to-training lineage.",
    ),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_snapshot() -> list[dict[str, str]]:
    files = [
        ("Master specification / ledger", PROJECT_ROOT / "realistic_project_creation_codex.md"),
        ("P6 benchmark dossier", PROJECT_ROOT / "benchmark_full.md"),
        ("P6 gate evidence", PROJECT_ROOT / "docs/evidence/p6_gate.md"),
        ("P3.1 retrieval evidence", PROJECT_ROOT / "docs/evidence/p3_1_gate.md"),
        ("P4 correction evidence", PROJECT_ROOT / "docs/evidence/p4_gate.md"),
        ("Post-P6 query recovery", PROJECT_ROOT / "docs/evidence/p6_3_query_recovery.md"),
        ("Project failure memory", PROJECT_ROOT / "all_failures_in_project.md"),
        ("Error analysis", PROJECT_ROOT / "docs/error_analysis.md"),
    ]
    snapshot = []
    for label, path in files:
        if not path.is_file():
            raise FileNotFoundError(f"Required evidence file not found: {path}")
        snapshot.append(
            {
                "label": label,
                "path": path.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": sha256(path),
            }
        )
    return snapshot


def source_url(source_id: str) -> str:
    return next(source["url"] for source in SOURCES if source["id"] == source_id)


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    def clean(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", "<br>")

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(clean(cell) for cell in row) + " |" for row in rows)
    return "\n".join(lines)


def render_markdown(snapshot: list[dict[str, str]], current_head: str) -> str:
    spider = BASELINE["spider"]
    olist = BASELINE["olist"]
    retrieval = BASELINE["retrieval"]
    source_rows = [
        [
            f"[{source['name']}]({source['url']})",
            source["evidence"],
            source["use"],
        ]
        for source in SOURCES
    ]
    experiment_rows = [
        [
            experiment["id"],
            experiment["priority"],
            experiment["lane"],
            experiment["title"],
            experiment["expected"],
            experiment["effort"],
            experiment["promote"],
        ]
        for experiment in EXPERIMENTS
    ]
    snapshot_rows = [
        [
            item["label"],
            f"[`{item['path']}`](../../{item['path']})",
            f"`{item['sha256']}`",
        ]
        for item in snapshot
    ]
    detail_sections = []
    for experiment in EXPERIMENTS:
        detail_sections.append(
            f"""### {experiment["id"]} — {experiment["title"]}

- **Vì sao bây giờ:** {experiment["why"]}
- **Project đã có:** {experiment["done"]}
- **Thế giới đã làm:** {experiment["world"]}
- **Giả thuyết:** {experiment["hypothesis"]}
- **Thiết kế thử nghiệm:** {experiment["work"]}
- **Metric chính:** {experiment["metric"]}
- **Promote:** {experiment["promote"]}
- **Kill/stop:** {experiment["kill"]}
- **Ước lượng:** {experiment["expected"]}; effort `{experiment["effort"]}`.
"""
        )
    detail_markdown = "\n".join(detail_sections)

    schedule_rows = [
        [gate, period, experiment, output] for gate, period, experiment, output in SCHEDULE
    ]
    data_rows = [[stage, contract] for stage, contract in DATA_PIPELINE]
    blueprint_rows = [
        [
            phase["id"],
            phase["track"],
            phase["period"],
            phase["title"],
            phase["outputs"],
            phase["gate"],
        ]
        for phase in BLUEPRINT_PHASES
    ]

    return f"""<!-- GENERATED FILE. Edit generate_research_plan.py, then regenerate. -->
# Kế hoạch nghiên cứu tăng accuracy — Agentic Text-to-SQL

> **Vai trò:** Data Scientist · **Trạng thái:** research plan, chưa triển khai experiment<br>
> **Survey cutoff:** {SURVEY_CUTOFF} · **Generated:** {PLAN_GENERATED_DATE}<br>
> **North star:** tăng Spider generalization có kiểm chứng; giữ Olist semantic quality và safety.

## 1. Kết luận điều hành

Project đã hoàn tất Gate P6 về engineering, nhưng chưa thể gọi là “đúng với mọi câu user hỏi”.
Schema retrieval cơ bản đã mạnh: Spider holdout có table recall@20 `{retrieval["table"]}` và
qualified column recall@20 `{retrieval["column"]}`. Tuy vậy, 68/70 lỗi Spider là
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
| Spider-200 | **{spider["score"]} = {spider["accuracy"]}** | holdout {spider["holdout"]}; valid {spider["valid"]} | p50 {spider["p50"]}; p95 {spider["p95"]} |
| Olist-60 | **{olist["score"]} = {olist["accuracy"]}** | holdout {olist["holdout"]}; first-pass {olist["first_pass"]} | p50 {olist["p50"]}; p95 {olist["p95"]} |

- Benchmark revision: `{BASELINE["benchmark_commit"]}`; gate completion: `{BASELINE["gate_commit"]}`.
- Checkout được chụp khi lập plan: `{current_head}`.
- Điểm 65%/95% **chỉ thuộc revision benchmark**, generator v4/corrector v3. Hardening v6/v5 hiện tại
  phải rerun trước khi nhận score mới.
- Full Spider-dev 1.034 chưa chạy; evaluator self-test 1.034/1.034 không phải model accuracy.
- Olist và Spider đo hai mục tiêu khác nhau, không lấy trung bình.

### Evidence fingerprint

{markdown_table(["Artifact", "Path", "SHA-256"], snapshot_rows)}

Fingerprint này bảo toàn *evidence aggregate*, không copy raw dataset, database, trace, prediction
hay gold data vào Git.

## 2.1 Blueprint path và target architecture

{markdown_table(["Gate", "Track", "Thời gian", "Mục tiêu", "Deliverable", "Decision gate"], blueprint_rows)}

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
| Schema macro holdout@20 `{retrieval["schema"]}` | Retrieval cơ bản gần bão hòa | Không tiếp tục vặn BM25/FAISS như ưu tiên số 1 |
| Join-edge recall `{retrieval["join"]}` | Join evidence còn khoảng trống | Phân tích failure join trước khi thay retriever |
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

{markdown_table(["ID", "P", "Workstream", "Experiment", "Expected", "Effort", "Gate promote"], experiment_rows)}

> Expected gain là **prior để xếp hàng**, không cộng dồn và không phải kết quả. Mỗi hàng chỉ được
> chuyển `PROPOSED → PILOT → EVALUATED → PROMOTED/REJECTED` khi có report tái lập.

## 5. Experiment cards

{detail_markdown}

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

{markdown_table(["Stage", "Contract"], data_rows)}

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

{markdown_table(["Gate", "Thời gian", "Experiment", "Deliverable"], schedule_rows)}

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

{markdown_table(["Nguồn chính", "Kết quả được báo cáo", "Áp dụng có chọn lọc"], source_rows)}

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
"""


def inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(
        r"\[([^]]+)]\((https?://[^)]+|[^)]+)\)",
        r'<a href="\2" target="_blank" rel="noreferrer">\1</a>',
        escaped,
    )
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def status_check(experiment_id: str) -> str:
    return (
        f'<label class="check"><input type="checkbox" data-exp="{experiment_id}"> '
        "Đã review với mentor</label>"
    )


def render_html(snapshot: list[dict[str, str]], current_head: str) -> str:
    spider = BASELINE["spider"]
    olist = BASELINE["olist"]
    retrieval = BASELINE["retrieval"]
    experiment_rows = []
    experiment_cards = []
    for experiment in EXPERIMENTS:
        lane_slug = {
            "Đo lường": "measurement",
            "Dữ liệu": "data",
            "Công nghệ lõi": "core",
            "Đánh giá": "evaluation",
        }[experiment["lane"]]
        experiment_rows.append(
            f"""<tr data-priority="{experiment["priority"]}" data-lane="{lane_slug}">
<td><a class="id" href="#{experiment["id"]}">{experiment["id"]}</a></td>
<td><span class="pill {experiment["priority"].lower()}">{experiment["priority"]}</span></td>
<td>{experiment["lane"]}</td><td>{experiment["title"]}</td>
<td>{experiment["expected"]}</td><td>{experiment["effort"]}</td></tr>"""
        )
        fields = [
            ("Vì sao bây giờ", experiment["why"]),
            ("Project đã có", experiment["done"]),
            ("Evidence thế giới", experiment["world"]),
            ("Hypothesis", experiment["hypothesis"]),
            ("Thiết kế", experiment["work"]),
            ("Metric", experiment["metric"]),
            ("Promote", experiment["promote"]),
            ("Kill", experiment["kill"]),
        ]
        field_html = "".join(
            f'<div class="field"><span>{label}</span><p>{inline(value)}</p></div>'
            for label, value in fields
        )
        experiment_cards.append(
            f"""<details class="experiment" id="{experiment["id"]}" data-lane="{lane_slug}">
<summary><span class="id">{experiment["id"]}</span><span class="pill {experiment["priority"].lower()}">{experiment["priority"]}</span>
<strong>{experiment["title"]}</strong><small>{experiment["expected"]} · {experiment["effort"]}</small></summary>
<div class="experiment-body">{field_html}{status_check(experiment["id"])}</div></details>"""
        )

    source_cards = "".join(
        f"""<article class="source"><div><span>{source["id"]}</span><a href="{source["url"]}" target="_blank" rel="noreferrer">{source["name"]} ↗</a></div>
<p><strong>Reported:</strong> {inline(source["evidence"])}</p><p><strong>Transfer:</strong> {inline(source["use"])}</p></article>"""
        for source in SOURCES
    )
    snapshot_rows = "".join(
        f"""<tr><td>{item["label"]}</td><td><a href="../../{item["path"]}">{item["path"]}</a></td>
<td><code title="{item["sha256"]}">{item["sha256"][:16]}…</code></td></tr>"""
        for item in snapshot
    )
    schedule_rows_html = []
    for gate, period, experiment, output in SCHEDULE:
        experiment_links = re.sub(
            r"R\d+",
            lambda match: f'<a href="#{match.group(0)}">{match.group(0)}</a>',
            experiment,
        )
        schedule_rows_html.append(
            f"<tr><td>{gate}</td><td>{period}</td><td>{experiment_links}</td><td>{output}</td></tr>"
        )
    schedule_html = "".join(schedule_rows_html)
    data_pipeline_html = "".join(
        f'<div class="pipeline-step"><b>{stage}</b><span>{contract}</span></div>'
        for stage, contract in DATA_PIPELINE
    )
    blueprint_phase_html = "".join(
        f"""<article class="phase {phase["track"]}" data-track="{phase["track"]}">
<div class="phase-top"><span class="phase-id">{phase["id"]}</span><small>{phase["period"]}</small></div>
<h3>{phase["title"]}</h3><p>{phase["objective"]}</p>
<dl><dt>Deliverable</dt><dd>{phase["outputs"]}</dd><dt>Decision gate</dt><dd>{phase["gate"]}</dd></dl>
<label class="phase-check"><input type="checkbox" data-phase="{phase["id"]}"> Gate complete</label></article>"""
        for phase in BLUEPRINT_PHASES
    )
    mentor_rows = "".join(
        f"""<tr data-lane="{lane_slug}"><td><span class="id">{experiment["id"]}</span><br><strong>{experiment["title"]}</strong></td>
<td>{inline(experiment["done"])}</td><td>{inline(experiment["why"])}</td>
<td>{inline(experiment["world"])}</td><td>{inline(experiment["work"])}</td>
<td><strong>{inline(experiment["metric"])}</strong><br><span class="gate-text">Gate: {inline(experiment["promote"])}</span></td></tr>"""
        for experiment in EXPERIMENTS
        for lane_slug in [
            {
                "Đo lường": "measurement",
                "Dữ liệu": "data",
                "Công nghệ lõi": "core",
                "Đánh giá": "evaluation",
            }[experiment["lane"]]
        ]
    )

    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Evidence-driven post-P6 research plan for local Agentic Text-to-SQL">
<title>Text-to-SQL Accuracy Research Plan</title>
<style>
:root{{--bg:#07111f;--panel:#0d1b2d;--panel2:#12243a;--text:#f1f5fb;--muted:#a8b9ce;--cyan:#54e3ee;--violet:#ad93ff;--green:#63e6ad;--amber:#ffd166;--red:#ff939b;--line:#304861;--shadow:0 18px 45px #02070f66;--hero:#1d2b4d;--code:#06101c}}
:root[data-theme="light"]{{--bg:#f5f7fb;--panel:#ffffff;--panel2:#eaf0f7;--text:#142033;--muted:#52647a;--cyan:#006a78;--violet:#6146c7;--green:#087b52;--amber:#8a5900;--red:#b42335;--line:#cbd6e3;--shadow:0 14px 34px #24364d18;--hero:#e9eefb;--code:#eaf1f7}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth;max-width:100%;overflow-x:clip}} body{{margin:0;max-width:100%;overflow-x:clip;background:radial-gradient(circle at 80% -10%,var(--hero) 0,transparent 32%),var(--bg);color:var(--text);font:16px/1.7 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
a{{color:var(--cyan);text-decoration-thickness:.08em;text-underline-offset:.18em}} a:hover{{text-decoration:underline}} a:focus-visible,button:focus-visible,input:focus-visible,summary:focus-visible{{outline:3px solid var(--amber);outline-offset:3px}} code{{font:13px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--cyan);background:var(--code);padding:.15rem .35rem;border-radius:5px;overflow-wrap:anywhere}}
.skip-link{{position:fixed;left:12px;top:-60px;z-index:50;padding:10px 14px;border-radius:8px;background:var(--text);color:var(--bg);font-weight:800}} .skip-link:focus{{top:12px}} .progress{{position:fixed;z-index:40;left:0;top:0;height:3px;width:0;background:linear-gradient(90deg,var(--violet),var(--cyan),var(--green))}}
.layout{{display:grid;grid-template-columns:245px minmax(0,1fr);min-height:100vh}} aside,main{{min-width:0;max-width:100%}} aside{{position:sticky;top:0;height:100vh;padding:26px 18px;border-right:1px solid var(--line);background:#07111fe8;backdrop-filter:blur(14px);overflow:auto}}
.brand{{display:flex;gap:10px;align-items:center;margin-bottom:18px}} .logo{{display:grid;place-items:center;width:38px;height:38px;border-radius:11px;background:linear-gradient(135deg,var(--violet),var(--cyan));color:#07111f;font-weight:900}} .brand b{{line-height:1.2}} .brand small{{display:block;color:var(--muted);font-weight:500}} .side-actions{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin:0 0 18px}} .side-actions button{{min-width:0;font-size:12px;padding:7px 8px}}
nav a{{display:block;padding:8px 11px;margin:3px 0;color:var(--muted);border-radius:8px}} nav a:hover,nav a.active{{color:var(--text);background:#172a42;text-decoration:none}} .side-note{{margin-top:24px;padding:12px;border:1px solid var(--line);border-radius:10px;color:var(--muted);font-size:12px}}
main{{width:min(1280px,100%);padding:46px clamp(24px,4vw,68px) 100px}} body.reading main{{width:min(980px,100%)}} section{{scroll-margin-top:24px;margin-bottom:76px}} .eyebrow{{color:var(--cyan);text-transform:uppercase;letter-spacing:.17em;font-size:12px;font-weight:800}} h1{{max-width:980px;margin:.3rem 0 1rem;font-size:clamp(42px,5.2vw,66px);line-height:1.06;letter-spacing:-.04em}} h2{{margin:0 0 18px;font-size:clamp(28px,3vw,34px);letter-spacing:-.025em}} h3{{margin:24px 0 10px}} p,li{{max-width:78ch}} .lead{{max-width:76ch;color:var(--muted);font-size:18px}} .notice{{padding:16px 18px;border:1px solid var(--violet);border-left:4px solid var(--violet);border-radius:10px;background:var(--panel);color:var(--text)}}
.kpis{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin:30px 0}} .kpi{{padding:19px;border:1px solid var(--line);border-radius:14px;background:linear-gradient(145deg,#10233a,#0b1828);box-shadow:var(--shadow)}} .kpi span{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}} .kpi b{{display:block;font-size:28px;margin-top:5px}} .kpi small{{color:var(--muted)}}
.target{{display:grid;grid-template-columns:150px 1fr 80px;align-items:center;gap:12px;margin:12px 0}} .bar{{height:14px;background:#192b42;border-radius:999px;overflow:hidden}} .bar i{{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--violet),var(--cyan))}} .bar.green i{{background:linear-gradient(90deg,#2fb47c,var(--green))}}
.grid2{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}} .card{{padding:20px;border:1px solid var(--line);border-radius:14px;background:var(--panel)}} .card h3{{margin-top:0}} .card p:last-child{{margin-bottom:0}} .muted{{color:var(--muted)}} .outcomes{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}} .outcome{{padding:17px;border:1px solid var(--line);border-radius:13px;background:var(--panel)}} .outcome b{{display:block;color:var(--cyan);margin-bottom:6px}} .outcome small{{display:block;color:var(--muted);margin-top:7px}} .formula{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}} .formula div{{padding:14px;border:1px dashed var(--line);border-radius:10px;background:var(--panel)}}
.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:12px;background:var(--panel)}} table{{border-collapse:collapse;width:100%;min-width:760px}} th,td{{padding:12px 14px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}} th{{position:sticky;top:0;background:#12243a;color:#b9c8da;font-size:12px;text-transform:uppercase;letter-spacing:.06em}} tr:last-child td{{border-bottom:0}} tbody tr:hover{{background:#11243a}} .id{{font:800 13px ui-monospace,SFMono-Regular,monospace;color:var(--cyan)}}
.pill{{display:inline-flex;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:800}} .p0{{background:#4b1d31;color:#ffabb2}} .p1{{background:#483a17;color:#ffd978}} .p2{{background:#183b34;color:#7ce3b4}}
.filters{{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 14px}} button{{border:1px solid var(--line);border-radius:999px;background:#102139;color:var(--muted);padding:7px 12px;cursor:pointer}} button:hover,button.selected{{border-color:var(--cyan);color:var(--text);background:#12344b}} input[type=search]{{min-width:240px;border:1px solid var(--line);border-radius:999px;background:#091625;color:var(--text);padding:8px 14px;outline:none}} input[type=search]:focus{{border-color:var(--cyan)}}
.experiment{{margin:10px 0;border:1px solid var(--line);border-radius:12px;background:var(--panel);overflow:hidden}} .experiment summary{{display:grid;grid-template-columns:38px 38px minmax(0,1fr) auto;gap:10px;align-items:center;padding:15px 18px;cursor:pointer}} .experiment summary:hover{{background:#11243a}} .experiment summary small{{color:var(--muted)}} .experiment-body{{padding:3px 18px 18px;border-top:1px solid var(--line);display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 20px}} .field{{border-bottom:1px dashed #273d57;padding:11px 0}} .field span{{color:var(--cyan);font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.05em}} .field p{{margin:3px 0}} .check{{grid-column:1/-1;color:var(--muted);padding-top:8px}} .check input{{accent-color:var(--green)}}
.pipeline{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}} .pipeline-step{{padding:15px;border:1px solid var(--line);border-top:3px solid var(--cyan);border-radius:10px;background:var(--panel)}} .pipeline-step b,.pipeline-step span{{display:block}} .pipeline-step span{{margin-top:5px;color:var(--muted);font-size:13px}}
.source-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}} .source{{padding:16px;border:1px solid var(--line);border-radius:12px;background:var(--panel)}} .source>div{{display:flex;align-items:center;gap:10px}} .source>div span{{font:11px ui-monospace,monospace;color:var(--violet)}} .source>div a{{font-weight:800}} .source p{{margin:8px 0 0;color:#b8c7da;font-size:13px}}
.blueprint-map{{position:relative;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}} .blueprint-map:before{{content:"";position:absolute;left:3%;right:3%;top:28px;height:2px;background:linear-gradient(90deg,var(--violet),var(--cyan),var(--green));opacity:.45}} .phase{{position:relative;padding:17px;border:1px solid var(--line);border-radius:14px;background:#0d1b2df2;box-shadow:var(--shadow)}} .phase.shared{{border-top:3px solid var(--violet)}} .phase.data{{border-top:3px solid var(--green)}} .phase.core{{border-top:3px solid var(--cyan)}} .phase-top{{display:flex;justify-content:space-between;align-items:center}} .phase-id{{display:grid;place-items:center;width:34px;height:34px;border-radius:50%;background:#162942;font:800 12px ui-monospace,monospace;color:var(--text)}} .phase-top small{{color:var(--muted)}} .phase h3{{margin:12px 0 6px;font-size:17px}} .phase p{{color:#c1cede;min-height:48px}} .phase dl{{margin:0}} .phase dt{{margin-top:9px;color:var(--cyan);font-size:10px;text-transform:uppercase;letter-spacing:.08em;font-weight:800}} .phase dd{{margin:2px 0;color:var(--muted);font-size:12px}} .phase-check{{display:block;margin-top:12px;padding-top:10px;border-top:1px dashed var(--line);color:var(--muted);font-size:12px}} .phase-check input{{accent-color:var(--green)}}
.legend{{display:flex;flex-wrap:wrap;gap:9px;margin:12px 0 18px}} .legend span{{padding:4px 9px;border-radius:999px;background:#101e31;color:var(--muted);font-size:11px}} .legend i{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}} .legend .shared i{{background:var(--violet)}} .legend .data i{{background:var(--green)}} .legend .core i{{background:var(--cyan)}}
.architecture-shell{{border:1px solid var(--line);border-radius:16px;background:#091625;padding:18px}} .architecture-tabs{{display:flex;gap:8px;margin-bottom:16px}} .architecture{{display:none}} .architecture.active{{display:block}} .plane{{padding:16px;border:1px solid var(--line);border-radius:12px;background:#0d1b2d;margin:11px 0}} .plane-title{{display:flex;justify-content:space-between;gap:12px;margin-bottom:12px}} .plane-title b{{font-size:13px;text-transform:uppercase;letter-spacing:.08em}} .plane-title span{{color:var(--muted);font-size:12px}} .flow{{display:flex;align-items:stretch;gap:7px;overflow:auto;padding-bottom:4px}} .node{{min-width:126px;flex:1;padding:12px;border:1px solid #2a405a;border-radius:10px;background:#10233a}} .node b,.node small{{display:block}} .node b{{font-size:12px}} .node small{{margin-top:4px;color:var(--muted);line-height:1.35}} .arrow{{display:grid;place-items:center;color:var(--cyan);font-weight:900}} .node.add{{border-color:#267d65;background:#0e2d29}} .node.keep{{border-color:#354d69}} .node.measure{{border-color:#735f2f;background:#2a2414}} .gold-wall{{padding:8px 12px;border:1px dashed var(--red);border-radius:8px;color:#ffb8be;text-align:center;font-size:12px}}
.score-control{{display:grid;grid-template-columns:180px 1fr 250px;gap:18px;align-items:center;padding:18px;border:1px solid var(--line);border-radius:14px;background:var(--panel)}} .score-control input{{width:100%;accent-color:var(--cyan)}} .score-number{{font-size:34px;font-weight:900;color:var(--cyan)}} .score-output{{padding:12px;border-radius:10px;background:#091625}} .score-output b{{font-size:20px;color:var(--green)}}
.mentor-table{{font-size:13px}} .mentor-table table{{min-width:1450px}} .mentor-table th:first-child,.mentor-table td:first-child{{position:sticky;left:0;background:#10233a;z-index:2;min-width:190px}} .mentor-table td{{max-width:280px}} .gate-text{{display:block;margin-top:8px;color:var(--green)}}
.operating-loop{{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;align-items:stretch}} .loop-step{{padding:13px;border:1px solid var(--line);border-radius:10px;background:var(--panel);font-size:12px}} .loop-step b{{display:block;color:var(--cyan);margin-bottom:4px}} .loop-step:not(:last-child):after{{content:"→";float:right;color:var(--violet);font-size:17px}}
.decision{{border-left:3px solid var(--green)}} .warning{{border-left:3px solid var(--amber)}} footer{{color:var(--muted);border-top:1px solid var(--line);padding-top:20px}}
:root[data-theme="light"] aside{{background:#f5f7fbef}} :root[data-theme="light"] nav a:hover,:root[data-theme="light"] nav a.active,:root[data-theme="light"] tbody tr:hover,:root[data-theme="light"] .experiment summary:hover{{background:var(--panel2)}} :root[data-theme="light"] .kpi,:root[data-theme="light"] .phase{{background:var(--panel)}} :root[data-theme="light"] th,:root[data-theme="light"] .mentor-table th:first-child,:root[data-theme="light"] .mentor-table td:first-child{{background:var(--panel2);color:var(--text)}} :root[data-theme="light"] button,:root[data-theme="light"] input[type=search],:root[data-theme="light"] .architecture-shell,:root[data-theme="light"] .score-output{{background:var(--panel);color:var(--text)}} :root[data-theme="light"] .plane,:root[data-theme="light"] .node,:root[data-theme="light"] .legend span{{background:var(--panel)}} :root[data-theme="light"] .node.add{{background:#e4f7ef}} :root[data-theme="light"] .node.measure{{background:#fff5d9}} :root[data-theme="light"] .source p,:root[data-theme="light"] .phase p{{color:var(--muted)}}
@media(max-width:1050px){{.blueprint-map{{grid-template-columns:repeat(2,minmax(0,1fr))}} .operating-loop{{grid-template-columns:repeat(3,minmax(0,1fr))}} .outcomes{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media(max-width:900px){{.layout{{display:block}} aside{{position:relative;height:auto;border-right:0;border-bottom:1px solid var(--line)}} nav{{display:flex;max-width:100%;overflow-x:auto;overscroll-behavior-inline:contain}} nav a{{flex:0 0 auto;white-space:nowrap}} main{{padding-top:30px}} .kpis,.pipeline{{grid-template-columns:repeat(2,minmax(0,1fr))}} .source-grid{{grid-template-columns:1fr}} .score-control{{grid-template-columns:1fr}}}}
@media(max-width:600px){{.kpis,.grid2,.pipeline,.experiment-body,.blueprint-map,.operating-loop,.outcomes,.formula{{grid-template-columns:1fr}} .experiment summary{{grid-template-columns:34px 34px minmax(0,1fr)}} .experiment summary small{{grid-column:3}} .target{{grid-template-columns:100px minmax(0,1fr) 60px}} .eyebrow,h1,h2{{overflow-wrap:anywhere}} h1{{font-size:39px}} .blueprint-map:before{{display:none}} main{{padding-inline:18px}}}}
@media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}} *,*::before,*::after{{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}}}
@media print{{aside,.filters,.check{{display:none!important}} .layout{{display:block}} body{{background:white;color:#111}} main{{width:100%;padding:0}} .card,.kpi,.experiment,.source,.table-wrap{{background:white;color:#111;box-shadow:none;break-inside:avoid}} .muted,.lead,.field p,.source p{{color:#333}} details{{break-inside:avoid}} details>*{{display:block!important}} a{{color:#0645ad}}}}
</style>
</head>
<body>
<a class="skip-link" href="#content">Bỏ qua menu, tới nội dung</a><div class="progress" aria-hidden="true"></div>
<div class="layout">
<aside><div class="brand"><div class="logo">SQL</div><b>Accuracy Lab<small>Post-P6 research plan</small></b></div>
<div class="side-actions"><button type="button" id="theme-toggle" aria-label="Đổi giao diện sáng tối">☀︎ Sáng</button><button type="button" id="reading-toggle" aria-pressed="false">⌁ Dễ đọc</button></div>
<nav aria-label="Mục lục research plan">{"".join(f'<a href="#{anchor}">{label}</a>' for anchor, label in [("overview", "Mission"), ("baseline", "Baseline"), ("blueprint", "Blueprint path"), ("architecture", "Architecture"), ("diagnosis", "Chẩn đoán"), ("user-contract", "User contract"), ("mentor-sheet", "Mentor sheet"), ("roadmap", "Experiments"), ("data", "Data factory"), ("evaluation", "Evaluation"), ("schedule", "Gates"), ("survey", "Sources"), ("next", "Bước tiếp")])}</nav>
<div class="side-note">Survey cutoff<br><b>{SURVEY_CUTOFF}</b><br><br>Generated<br><b>{PLAN_GENERATED_DATE}</b></div></aside>
<main id="content" tabindex="-1">
<section id="overview"><div class="eyebrow">Evidence-driven research & product blueprint</div><h1>Từ “sinh được SQL” đến câu trả lời đáng tin cho mọi kiểu người dùng.</h1>
<p class="lead">Blueprint sau Gate P6 kết nối bốn năng lực: hiểu câu hỏi đời thực, thu thập semantic evidence, sinh/xác minh SQL có giới hạn và trình bày kết quả để người không biết code vẫn kiểm soát được assumptions. Benchmark tăng là mục tiêu; confident-wrong giảm mới là điều kiện để dùng thật.</p>
<div class="kpis"><div class="kpi"><span>Spider-200 historical</span><b>{spider["accuracy"]}</b><small>{spider["score"]} · 20 DB</small></div><div class="kpi"><span>Olist-60 historical</span><b>{olist["accuracy"]}</b><small>{olist["score"]} · bilingual</small></div><div class="kpi"><span>Schema recall@20</span><b>{retrieval["schema"]}</b><small>holdout, qualified</small></div><div class="kpi"><span>Semantic mismatch</span><b>68/70</b><small>Spider failures</small></div></div>
<div class="notice"><b>North star gần:</b> Spider ≥70% (+10 case) trên locked-200, Olist ≥95%, safety 100%. <b>North star research:</b> 75% trên fresh/full release sau freeze. Điểm paper là evidence định hướng, không phải lời hứa cho Qwen local.</div>
<h3>Score gap planner</h3><div class="score-control"><div><span class="muted">Target Spider-200</span><div><span id="target-score" class="score-number">70</span>%</div></div><input id="score-slider" type="range" min="65" max="85" value="70" step="1" aria-label="Target Spider accuracy"><div class="score-output">Cần phục hồi ròng <b id="cases-needed">10 case</b><br><span class="muted" id="target-note">mốc improvement gate tối thiểu</span></div></div></section>

<section id="baseline"><div class="eyebrow">01 · Baseline freeze</div><h2>Kết quả hiện tại đã được định danh</h2>
<div class="grid2"><div class="card decision"><h3>Spider generalization</h3><p><b>{spider["score"]} = {spider["accuracy"]}</b><br>Holdout {spider["holdout"]} · valid {spider["valid"]}<br>p50/p95 {spider["p50"]} / {spider["p95"]}</p></div><div class="card decision"><h3>Olist application</h3><p><b>{olist["score"]} = {olist["accuracy"]}</b><br>Holdout {olist["holdout"]} · first-pass {olist["first_pass"]}<br>p50/p95 {olist["p50"]} / {olist["p95"]}</p></div></div>
<p class="notice warning"><b>Claim boundary:</b> các score thuộc commit <code>{BASELINE["benchmark_commit"][:12]}</code>, generator v4/corrector v3. Checkout được chụp khi lập plan <code>{current_head[:12]}</code> đã harden v6/v5 và chưa được nhận lại score.</p>
<h3>Evidence fingerprints</h3><div class="table-wrap"><table><thead><tr><th>Artifact</th><th>Path</th><th>SHA-256</th></tr></thead><tbody>{snapshot_rows}</tbody></table></div></section>

<section id="blueprint"><div class="eyebrow">02 · End-to-end blueprint</div><h2>Một đường đi từ hiện trạng đến score mới</h2>
<p class="lead">Tám gates dưới đây là dependency path, không phải backlog tùy ý. Shared gates khóa đo lường; Data track chuẩn bị evidence/supervision; Core track thay đổi inference. Tại mỗi gate chỉ một independent variable được phép đổi.</p>
<div class="legend"><span class="shared"><i></i>Shared evidence gate</span><span class="data"><i></i>LLM Data Factory</span><span class="core"><i></i>Core Accuracy Engine</span></div>
<div class="blueprint-map">{blueprint_phase_html}</div>
<h3>Research operating loop</h3><div class="operating-loop"><div class="loop-step"><b>1 · Observe</b>Baseline + failures</div><div class="loop-step"><b>2 · Explain</b>Causal taxonomy</div><div class="loop-step"><b>3 · Hypothesize</b>Paper + local evidence</div><div class="loop-step"><b>4 · Experiment</b>One variable</div><div class="loop-step"><b>5 · Decide</b>Promote / reject</div><div class="loop-step"><b>6 · Learn</b>Failure → data asset</div></div></section>

<section id="architecture"><div class="eyebrow">03 · Architecture evolution</div><h2>Giữ phần đã mạnh, thêm đúng nơi đang mất accuracy</h2>
<div class="architecture-shell"><div class="architecture-tabs"><button class="arch-button selected" data-arch="current">Current state</button><button class="arch-button" data-arch="target">Target blueprint</button></div>
<div class="architecture active" id="arch-current"><div class="plane"><div class="plane-title"><b>Online inference hiện tại</b><span>Điểm mạnh: typed, bounded, safe · Điểm yếu: semantic mismatch</span></div><div class="flow"><div class="node keep"><b>Question</b><small>VI / EN</small></div><div class="arrow">→</div><div class="node keep"><b>Planner v2</b><small>Logical plan</small></div><div class="arrow">→</div><div class="node keep"><b>Schema retrieval</b><small>BM25 + BGE + FK<br>99,65% column recall</small></div><div class="arrow">→</div><div class="node measure"><b>1 candidate</b><small>Qwen3-14B<br>semantic bottleneck</small></div><div class="arrow">→</div><div class="node keep"><b>Policy + execute</b><small>99,5% valid</small></div><div class="arrow">→</div><div class="node measure"><b>Correction</b><small>Chủ yếu lỗi được detect</small></div></div></div>
<div class="plane"><div class="plane-title"><b>Offline data/evaluation hiện tại</b><span>Có provenance nhưng chưa thành learning loop</span></div><div class="flow"><div class="node keep"><b>Catalog/index</b><small>Schema + FK</small></div><div class="arrow">→</div><div class="node keep"><b>Olist contracts</b><small>Glossary + invariants</small></div><div class="arrow">→</div><div class="node measure"><b>Benchmark reports</b><small>70 failures chưa có causal labels</small></div><div class="arrow">→</div><div class="node measure"><b>No feedback asset</b><small>Example store / profiler / training corpus chưa có</small></div></div></div></div>
<div class="architecture" id="arch-target"><div class="plane"><div class="plane-title"><b>Target · Question Reliability</b><span>Không ép mọi câu thành SQL</span></div><div class="flow"><div class="node keep"><b>Raw question</b><small>VI / EN / mixed</small></div><div class="arrow">→</div><div class="node add"><b>Normalizer</b><small>Typo · alias · time</small></div><div class="arrow">→</div><div class="node add"><b>Interpretations</b><small>Intent + assumptions</small></div><div class="arrow">→</div><div class="node add"><b>Answerability</b><small>Answer / clarify / cannot</small></div><div class="arrow">→</div><div class="node add"><b>Clarification</b><small>Business options, no SQL jargon</small></div></div></div><div class="plane"><div class="plane-title"><b>Target · Core Accuracy Engine</b><span>Adaptive theo độ khó, verifier gold-blind</span></div><div class="flow"><div class="node keep"><b>Resolved intent</b><small>metric · dimensions</small></div><div class="arrow">→</div><div class="node add"><b>Complexity router</b><small>Easy fast path<br>Hard research path</small></div><div class="arrow">→</div><div class="node add"><b>Clause plan</b><small>Intent + SQL skeleton</small></div><div class="arrow">→</div><div class="node add"><b>Context assembler</b><small>Schema + values + descriptions + examples</small></div><div class="arrow">→</div><div class="node add"><b>Candidate engine</b><small>1 easy / best-of-3 hard</small></div><div class="arrow">→</div><div class="node add"><b>Verifier/selector</b><small>AST + intent + consensus + invariants</small></div><div class="arrow">→</div><div class="node keep"><b>Safe execution</b><small>Repair / abstain / answer</small></div></div></div>
<div class="plane"><div class="plane-title"><b>Target · LLM Data Factory</b><span>Data lineage đi xuyên từ raw evidence tới experiment</span></div><div class="flow"><div class="node add"><b>Profile & metadata</b><small>Values, aliases, descriptions</small></div><div class="arrow">→</div><div class="node add"><b>Failure intelligence</b><small>Causal labels + hard negatives</small></div><div class="arrow">→</div><div class="node add"><b>Quality gates</b><small>Execute, review, dedup, leakage</small></div><div class="arrow">→</div><div class="node add"><b>Example memory</b><small>Verified ICL</small></div><div class="arrow">→</div><div class="node add"><b>Reviewed feedback</b><small>Output choice + assumptions</small></div><div class="arrow">→</div><div class="node add"><b>Adaptation</b><small>LoRA only after proof</small></div></div></div><div class="plane"><div class="plane-title"><b>Target · Product Trust</b><span>Câu trả lời trước, evidence theo progressive disclosure</span></div><div class="flow"><div class="node add"><b>Answer card</b><small>Result + unit + scope</small></div><div class="arrow">→</div><div class="node add"><b>Assumptions</b><small>Metric · filter · time grain</small></div><div class="arrow">→</div><div class="node add"><b>Calibrated state</b><small>Validated / uncertain</small></div><div class="arrow">→</div><div class="node add"><b>Advanced</b><small>SQL · schema · trace</small></div><div class="arrow">→</div><div class="node add"><b>Useful feedback</b><small>Intent/outcome, not raw thumbs</small></div></div></div><div class="gold-wall">GOLD FIREWALL · Gold SQL/result chỉ ở evaluator sau final stop, không đi ngược vào runtime</div></div></div>
<div class="grid2" style="margin-top:16px"><div class="card decision"><h3>Giữ nguyên</h3><p>Typed contracts, SQLGlot policy, read-only executor, bounded budgets, trace/provenance, hybrid schema retrieval và Olist semantic invariants.</p></div><div class="card warning"><h3>Phải bổ sung</h3><p>Answerability/clarification, failure intelligence, semantic/value evidence, verified examples, logic diversity, calibrated verifier và reviewed-data flywheel.</p></div></div></section>

<section id="diagnosis"><div class="eyebrow">04 · Diagnostic</div><h2>Bottleneck nằm ở semantics</h2>
<div class="grid2"><div class="card"><h3>Retrieval gần bão hòa</h3><div class="target"><span>Table</span><div class="bar"><i style="width:100%"></i></div><b>{retrieval["table"]}</b></div><div class="target"><span>Column</span><div class="bar"><i style="width:99.65%"></i></div><b>{retrieval["column"]}</b></div><div class="target"><span>Join edge</span><div class="bar"><i style="width:86.36%"></i></div><b>{retrieval["join"]}</b></div></div><div class="card"><h3>Difficulty gap</h3><div class="target"><span>Easy</span><div class="bar green"><i style="width:77.57%"></i></div><b>77,57%</b></div><div class="target"><span>Medium</span><div class="bar green"><i style="width:50.94%"></i></div><b>50,94%</b></div><div class="target"><span>Extra-hard</span><div class="bar green"><i style="width:36.36%"></i></div><b>36,36%</b></div></div></div>
<p class="lead">Kết luận: không tiếp tục tuning BM25/FAISS mù. Trước hết phải biết 68 mismatch sai ở join, aggregate, filter/value, nesting, set operation hay result grain.</p></section>

<section id="user-contract"><div class="eyebrow">05 · User reliability contract</div><h2>Không phải câu nào cũng nên bị ép thành SQL</h2><p class="lead">Một sản phẩm đáng tin tối ưu outcome của người dùng, không tối ưu số lần model chịu trả lời. Mỗi request phải kết thúc có ích và giải thích được.</p>
<div class="outcomes"><article class="outcome"><b>ANSWER</b>Kết quả trước, kèm metric, time grain, filters và assumptions.<small>Chỉ khi evidence + SQL + result validation đủ.</small></article><article class="outcome"><b>CLARIFY</b>Một câu hỏi ngắn cùng 2–3 lựa chọn nghiệp vụ.<small>Không bắt user biết table hay column.</small></article><article class="outcome"><b>CANNOT ANSWER</b>Nêu fact/relationship nào không có và gợi ý câu thay thế.<small>Không bịa proxy metric.</small></article><article class="outcome"><b>SAFE REJECT</b>Giải thích read-only/safety boundary và lựa chọn hợp lệ.<small>Không nới policy để tăng completion.</small></article></div>
<h3>Challenge matrix bắt buộc</h3><div class="table-wrap"><table><thead><tr><th>Family</th><th>Ví dụ</th><th>Behavior đúng</th></tr></thead><tbody><tr><td>Paraphrase</td><td>Đồng nghĩa, văn nói, thêm “giải thích”</td><td>Cùng interpretation + result fingerprint</td></tr><tr><td>Noisy input</td><td>Typo, thiếu dấu, VI/EN mix</td><td>Normalize có trace, không đổi metric</td></tr><tr><td>Ambiguity</td><td>“doanh thu”, “gần đây”, hai join paths</td><td>Glossary hoặc clarification options</td></tr><tr><td>Unanswerable</td><td>Return/refund khi DB thiếu facts</td><td>CANNOT_ANSWER + missing evidence</td></tr><tr><td>Long-tail SQL</td><td>Ratio, cohort, nested, set operation</td><td>Enhanced plan/candidate path có budget</td></tr></tbody></table></div>
<h3>Hai scorecard, không trộn</h3><div class="formula"><div><b>Research</b><br>EX · TS · paired delta · robustness slices</div><div><b>Risk–coverage</b><br>wrong answers / answered requests, báo cùng coverage</div><div><b>Product</b><br>clarification success · false-refusal · comprehension · time-to-insight</div></div><p class="notice"><b>Confidence rule:</b> self-confidence của model không phải probability. Chỉ hiện phần trăm sau calibration held-out và phải báo ECE/Brier; trước đó dùng nhãn “validated”, “uncertain” hoặc “needs clarification”.</p></section>

<section id="mentor-sheet"><div class="eyebrow">06 · Mentor planning sheet</div><h2>Mỗi mục đi trọn vòng: hiện trạng → survey → áp dụng → đo lại</h2>
<p class="lead">Đây là sheet chính để follow với mentor. Mỗi hàng có bằng chứng hiện tại, research precedent, thay đổi đề xuất và decision gate; không có mục “nghiên cứu chung chung”.</p>
<div class="filters"><button class="mentor-filter selected" data-mentor="all">Tất cả</button><button class="mentor-filter" data-mentor="data">Data preparation</button><button class="mentor-filter" data-mentor="core">Core accuracy</button><button class="mentor-filter" data-mentor="measurement">Baseline</button><button class="mentor-filter" data-mentor="evaluation">Evaluation</button></div>
<div class="table-wrap mentor-table"><table id="mentor-table"><thead><tr><th>Mục / owner</th><th>Đã làm được gì</th><th>Score & vấn đề hiện tại</th><th>Thế giới đã làm gì</th><th>Áp dụng vào project</th><th>Đánh giá lại / decision gate</th></tr></thead><tbody>{mentor_rows}</tbody></table></div></section>

<section id="roadmap"><div class="eyebrow">07 · Experiment portfolio</div><h2>Roadmap ưu tiên theo khả năng tạo score và trust</h2>
<div class="filters"><button class="selected" data-filter="all">Tất cả</button><button data-filter="P0">P0</button><button data-filter="P1">P1</button><button data-filter="P2">P2</button><button data-filter="data">Dữ liệu</button><button data-filter="core">Công nghệ lõi</button><input id="search" type="search" placeholder="Tìm experiment…"></div>
<div class="table-wrap"><table id="experiment-table"><thead><tr><th>ID</th><th>P</th><th>Workstream</th><th>Experiment</th><th>Expected prior</th><th>Effort</th></tr></thead><tbody>{"".join(experiment_rows)}</tbody></table></div><p class="muted">Expected là prior để xếp hàng, không cộng dồn. Promote/kill nằm trong từng card bên dưới.</p></section>

<section id="experiments"><div class="eyebrow">08 · Scientific cards</div><h2>Mỗi bước có hypothesis, control và kill criterion</h2>{"".join(experiment_cards)}</section>

<section id="data"><div class="eyebrow">09 · LLM Data Factory</div><h2>Dữ liệu tốt trước fine-tuning</h2>
<p class="lead">Workstream dữ liệu không phải “gom thêm samples”. Nó là quy trình biến schema, values, examples và failures thành supervision sạch, có lineage và không leakage.</p><div class="pipeline">{data_pipeline_html}</div>
<div class="grid2" style="margin-top:16px"><div class="card"><h3>Existing strengths</h3><p>Olist 60 reviewed cases; glossary/invariants; Spider manifests; deterministic evaluator; gold separation; synthetic fixture và local feedback store.</p></div><div class="card warning"><h3>Gaps cần lấp</h3><p>Failure semantic labels; user-query challenge set; Safe Profiler/value index; verified example store; reviewed feedback queue; data card/dedup pipeline và fresh holdout.</p></div></div>
<h3>Data quality dashboard tối thiểu</h3><div class="table-wrap"><table><thead><tr><th>Dimension</th><th>Metrics</th><th>Gate</th></tr></thead><tbody><tr><td>Validity</td><td>parse/execute/timeout/result degeneracy</td><td>≥99% execute với accepted corpus</td></tr><tr><td>Semantics</td><td>review accept; clause/grain/join/filter</td><td>≥95% accepted</td></tr><tr><td>Diversity</td><td>domain/schema/template/operator/language</td><td>Không cluster nào độc chiếm vô lý</td></tr><tr><td>Leakage</td><td>text + AST + result + embedding near-dup</td><td>0 overlap với locked/fresh set</td></tr><tr><td>Lineage</td><td>source→transform→review→version→experiment</td><td>100% rows truy vết được</td></tr></tbody></table></div></section>

<section id="evaluation"><div class="eyebrow">10 · Evaluation contract</div><h2>Score chỉ có nghĩa khi split và control còn nguyên</h2>
<div class="grid2"><div class="card"><h3>Dataset ladder</h3><ol><li>Development: regression-100 + labeled failures.</li><li>Historical validation: old holdout-100; không còn untouched.</li><li>Fresh validation: khóa từ Spider còn lại.</li><li>Release: full-1.034/external, chạy sau freeze.</li><li>Olist: report riêng + fresh bilingual holdout.</li><li>User challenge: typo/paraphrase/ambiguity/unanswerable.</li></ol></div><div class="card"><h3>Statistical + product report</h3><ul><li>n/N + wrong→right/right→wrong.</li><li>McNemar exact + bootstrap 95% CI.</li><li>Slices difficulty/DB/error/language/noise.</li><li>Risk–coverage + ECE/Brier khi calibrated.</li><li>Clarification success + false-refusal.</li><li>Calls/tokens/p50/p95/resource.</li></ul></div></div>
<p class="notice"><b>Promote default:</b> locked-200 tăng ít nhất 10 correct (+5 điểm), Olist ≥95%, safety 100%, gain cùng dấu trên fresh set; đồng thời confident-wrong giảm và answerable false-refusal không vượt 3%. Nếu sampling, lặp ba seed.</p></section>

<section id="schedule"><div class="eyebrow">11 · 14-week gates</div><h2>Một gate tại một thời điểm</h2><div class="table-wrap"><table><thead><tr><th>Gate</th><th>Thời gian</th><th>ID</th><th>Deliverable</th></tr></thead><tbody>{schedule_html}</tbody></table></div><p class="muted">Gate D chọn R3 hoặc R4 theo Pareto từ R1; không triển khai cả hai cùng lúc.</p></section>

<section id="survey"><div class="eyebrow">12 · Evidence library</div><h2>Ý tưởng đã có bằng chứng, nhưng phải transfer có kiểm soát</h2><div class="source-grid">{source_cards}</div>
<div class="notice warning" style="margin-top:16px"><b>Caveat:</b> EX ≠ TS; dev ≠ test; Spider ≠ BIRD; 7B/14B ≠ GPT-4/Claude. OmniSQL đã train với Spider/BIRD. ReViSQL là preprint 2026 và dùng compute lớn. Chỉ mechanism được mang vào hypothesis.</div></section>

<section id="next"><div class="eyebrow">13 · Immediate action</div><h2>Chưa sửa thuật toán. Làm R0 rồi R1.</h2><div class="card decision"><h3>Definition of ready</h3><p>Rerun code v6/v5 thành baseline B0 với provenance khóa; sau đó phân nhãn failures và user-query challenges. R2 đóng contract answerability/clarification; Pareto nguyên nhân mới quyết định R3, R4 hay model A/B R10 là accuracy intervention đầu tiên.</p></div>
<h3>Không ưu tiên lúc này</h3><ol><li>Thêm agent/refactor workflow khi chưa có causal evidence.</li><li>Tăng top-k/đổi embedding khi column recall đã 99,65%.</li><li>Fine-tune trước data audit và contamination scan.</li><li>Best-of-8/16 cho mọi câu trên laptop.</li><li>Nội suy 200 case thành full Spider hoặc trộn Olist/Spider.</li></ol></section>

<footer>Generated by <code>docs/research_plan/generate_research_plan.py</code> · <a href="research_plan.md">Mở bản Markdown</a> · Survey cutoff {SURVEY_CUTOFF}</footer>
</main></div>
<script>
const filterButtons=[...document.querySelectorAll('[data-filter]')];const rows=[...document.querySelectorAll('#experiment-table tbody tr')];const search=document.querySelector('#search');let active='all';function applyFilter(){{const q=search.value.toLowerCase();rows.forEach(row=>{{const matchesFilter=active==='all'||row.dataset.priority===active||row.dataset.lane===active;row.hidden=!(matchesFilter&&row.textContent.toLowerCase().includes(q));}})}}filterButtons.forEach(button=>button.addEventListener('click',()=>{{filterButtons.forEach(item=>item.classList.remove('selected'));button.classList.add('selected');active=button.dataset.filter;applyFilter();}}));search.addEventListener('input',applyFilter);
document.querySelectorAll('input[data-exp]').forEach(box=>{{const key='research-plan-'+box.dataset.exp;box.checked=localStorage.getItem(key)==='1';box.addEventListener('change',()=>localStorage.setItem(key,box.checked?'1':'0'));}});
document.querySelectorAll('input[data-phase]').forEach(box=>{{const key='blueprint-phase-'+box.dataset.phase;box.checked=localStorage.getItem(key)==='1';box.addEventListener('change',()=>localStorage.setItem(key,box.checked?'1':'0'));}});
const archButtons=[...document.querySelectorAll('[data-arch]')];archButtons.forEach(button=>button.addEventListener('click',()=>{{archButtons.forEach(item=>item.classList.remove('selected'));document.querySelectorAll('.architecture').forEach(item=>item.classList.remove('active'));button.classList.add('selected');document.querySelector('#arch-'+button.dataset.arch).classList.add('active');}}));
const mentorButtons=[...document.querySelectorAll('[data-mentor]')];const mentorRows=[...document.querySelectorAll('#mentor-table tbody tr')];mentorButtons.forEach(button=>button.addEventListener('click',()=>{{mentorButtons.forEach(item=>item.classList.remove('selected'));button.classList.add('selected');mentorRows.forEach(row=>row.hidden=!(button.dataset.mentor==='all'||row.dataset.lane===button.dataset.mentor));}}));
const scoreSlider=document.querySelector('#score-slider');function updateTarget(){{const target=Number(scoreSlider.value);const cases=Math.max(0,Math.round(target*2)-130);document.querySelector('#target-score').textContent=target;document.querySelector('#cases-needed').textContent=cases+' case';document.querySelector('#target-note').textContent=target===70?'mốc improvement gate tối thiểu':target===75?'mốc research kế tiếp':'không phải các gain cộng dồn';}}scoreSlider.addEventListener('input',updateTarget);updateTarget();
const navLinks=[...document.querySelectorAll('nav a')];const sections=[...document.querySelectorAll('main section')];const observer=new IntersectionObserver(entries=>{{entries.forEach(entry=>{{if(entry.isIntersecting){{navLinks.forEach(link=>link.classList.toggle('active',link.getAttribute('href')==='#'+entry.target.id));}}}})}},{{rootMargin:'-20% 0px -70% 0px'}});sections.forEach(section=>observer.observe(section));
const root=document.documentElement;const themeButton=document.querySelector('#theme-toggle');const requestedTheme=new URLSearchParams(location.search).get('theme');const savedTheme=localStorage.getItem('research-plan-theme');if(requestedTheme==='light'||requestedTheme==='dark')root.dataset.theme=requestedTheme;else if(savedTheme)root.dataset.theme=savedTheme;function syncTheme(){{const light=root.dataset.theme==='light';themeButton.textContent=light?'◐ Tối':'☀︎ Sáng';themeButton.setAttribute('aria-pressed',String(light));}}themeButton.addEventListener('click',()=>{{root.dataset.theme=root.dataset.theme==='light'?'dark':'light';localStorage.setItem('research-plan-theme',root.dataset.theme);syncTheme();}});syncTheme();
const readingButton=document.querySelector('#reading-toggle');const reading=localStorage.getItem('research-plan-reading')==='1';document.body.classList.toggle('reading',reading);readingButton.setAttribute('aria-pressed',String(reading));readingButton.addEventListener('click',()=>{{const active=document.body.classList.toggle('reading');readingButton.setAttribute('aria-pressed',String(active));localStorage.setItem('research-plan-reading',active?'1':'0');}});
const progress=document.querySelector('.progress');function updateProgress(){{const max=document.documentElement.scrollHeight-window.innerHeight;progress.style.width=(max>0?window.scrollY/max*100:0)+'%';}}document.addEventListener('scroll',updateProgress,{{passive:true}});updateProgress();
</script>
</body></html>
"""


def write_or_check(path: Path, content: str, check: bool) -> bool:
    normalized = content.rstrip() + "\n"
    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != normalized:
            print(f"OUTDATED: {path.relative_to(PROJECT_ROOT)}", file=sys.stderr)
            return False
        print(f"OK: {path.relative_to(PROJECT_ROOT)}")
        return True
    path.write_text(normalized, encoding="utf-8")
    print(f"WROTE: {path.relative_to(PROJECT_ROOT)}")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated Markdown or HTML differs from the checked-in output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot = evidence_snapshot()
    markdown = render_markdown(snapshot, PLAN_BASE_HEAD)
    html_document = render_html(snapshot, PLAN_BASE_HEAD)
    results = [
        write_or_check(MARKDOWN_PATH, markdown, args.check),
        write_or_check(HTML_PATH, html_document, args.check),
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
