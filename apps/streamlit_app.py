"""Local AI Data Observatory — Streamlit calls only the FastAPI boundary."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import httpx
import streamlit as st
from ui_client import LocalAPIClient

st.set_page_config(
    page_title="Local SQL Observatory",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
:root { --ink:#EAF2FF; --muted:#91A4BF; --panel:#101A2D; --line:#263754;
        --violet:#8B5CF6; --cyan:#22D3EE; --emerald:#34D399; --amber:#FBBF24; }
.stApp { background: radial-gradient(circle at 80% -10%, #1E1B4B 0%, #08111F 35%, #060C16 100%); }
[data-testid="stSidebar"] { background:linear-gradient(180deg,#0B1424 0%,#07101D 100%);
  border-right:1px solid var(--line); resize:horizontal; overflow:auto; min-width:260px; max-width:440px; }
[data-testid="stHeader"] { background:transparent; }
.block-container { padding-top:1.3rem; max-width:1500px; }
h1,h2,h3 { letter-spacing:-.025em; color:var(--ink); }
.observatory-hero { padding:1.5rem 1.7rem; border:1px solid #334466; border-radius:22px;
 background:linear-gradient(120deg,rgba(139,92,246,.18),rgba(34,211,238,.08)); margin-bottom:1rem; }
.eyebrow { color:var(--cyan); font-size:.74rem; font-weight:800; letter-spacing:.16em; text-transform:uppercase; }
.hero-title { font-size:2.1rem; line-height:1.08; margin:.35rem 0; color:#F8FAFC; font-weight:800; }
.hero-copy { color:#A8B6CC; max-width:780px; }
.status-pill { display:inline-flex; gap:.4rem; align-items:center; padding:.3rem .65rem;
 border:1px solid #31506B; background:#0C2130; border-radius:999px; color:#A5F3FC; font-size:.78rem; }
.metric-card { padding:1rem 1.1rem; background:rgba(16,26,45,.88); border:1px solid var(--line);
 border-radius:16px; min-height:105px; }
.metric-label { color:var(--muted); font-size:.75rem; text-transform:uppercase; letter-spacing:.08em; }
.metric-value { color:#F8FAFC; font-weight:800; font-size:1.4rem; margin-top:.35rem; }
.layer-card { padding:.8rem 1rem; margin:.35rem 0; border-left:3px solid var(--cyan);
 background:#0E192A; border-radius:0 12px 12px 0; }
.safe { border-color:var(--emerald)!important; }.corrected { border-color:var(--amber)!important; }
.blocked { border-color:#FB7185!important; }
.tiny { color:var(--muted); font-size:.78rem; }
.sortable-component { background:transparent!important; padding:0!important; }
.sortable-container { background:#0D1728!important; border:1px solid #2C3D5B!important; border-radius:14px!important; }
.sortable-container-header { color:#A5F3FC!important; background:#13233A!important; padding:.65rem!important; }
.sortable-item { background:#17243A!important; color:#DCE8F8!important; border:1px solid #31435F!important;
 border-radius:10px!important; margin:.45rem!important; padding:.65rem!important; cursor:grab!important; }
.sortable-item:hover { border-color:#8B5CF6!important; transform:translateY(-1px); }
div[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:14px; overflow:hidden; }
.stButton>button { border-radius:11px; border:1px solid #40577A; font-weight:700; }
.stButton>button[kind="primary"] { background:linear-gradient(90deg,#7C3AED,#2563EB); border:none; }
code { font-size:.86rem!important; }
@media (max-width:800px){ .hero-title{font-size:1.55rem}.block-container{padding:.8rem}.observatory-hero{padding:1rem} }
</style>
"""
SORTABLE_CSS = """
.sortable-component { background:transparent!important; padding:0!important; }
.sortable-container { background:#0D1728!important; border:1px solid #2C3D5B!important;
  border-radius:14px!important; }
.sortable-container-header { color:#A5F3FC!important; background:#13233A!important;
  padding:.65rem!important; }
.sortable-item { background:#17243A!important; color:#DCE8F8!important;
  border:1px solid #31435F!important; border-radius:10px!important; margin:.45rem!important;
  padding:.65rem!important; cursor:grab!important; transition:transform .14s ease,border-color .14s ease; }
.sortable-item:hover { border-color:#8B5CF6!important; transform:translateY(-1px); }
"""
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_resource
def api_client() -> LocalAPIClient:
    return LocalAPIClient()


client = api_client()


@st.cache_data(ttl=5, show_spinner=False)
def cached_health() -> dict[str, Any]:
    return client.health()


@st.cache_data(ttl=10, show_spinner=False)
def cached_catalogs() -> list[dict[str, Any]]:
    return client.catalogs()


@st.cache_data(ttl=30, show_spinner=False)
def cached_reports() -> list[dict[str, Any]]:
    return client.reports()


EXAMPLES = [
    "Top 5 danh mục theo doanh thu sản phẩm, tách phí vận chuyển",
    "Có bao nhiêu khách hàng quay lại theo customer_unique_id?",
    "What is the average review score rounded to 6 decimal places?",
    "Bang nào có nhiều đơn hàng nhất?",
    "Show monthly canceled order counts",
]


def hero(kicker: str, title: str, copy: str) -> None:
    st.markdown(
        f'<section class="observatory-hero"><div class="eyebrow">{kicker}</div>'
        f'<div class="hero-title">{title}</div><div class="hero-copy">{copy}</div></section>',
        unsafe_allow_html=True,
    )


def api_error(exc: Exception) -> None:
    message = "API is unavailable. Start it with `uv run text2sql serve`."
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            message = str(exc.response.json().get("detail", message))
        except ValueError:
            pass
    st.error(message, icon="🚦")


def metric(label: str, value: str, accent: str = "") -> None:
    st.markdown(
        f'<div class="metric-card {accent}"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div></div>',
        unsafe_allow_html=True,
    )


def horizontal_bars(records: list[dict[str, Any]], label: str, value: str) -> None:
    numeric = [
        (record, float(record[value]))
        for record in records
        if isinstance(record.get(value), int | float)
    ]
    if not numeric:
        st.info("This result has no numeric measure to visualize.")
        return
    peak = max(abs(number) for _, number in numeric) or 1.0
    for record, number in sorted(numeric, key=lambda item: item[1], reverse=True):
        display = f"{number:,.0f}" if number.is_integer() else f"{number:,.2f}"
        st.progress(
            min(abs(number) / peak, 1.0),
            text=f"{record.get(label, '—')} · {display}",
        )


def render_result(run: dict[str, Any]) -> None:
    result = run.get("result") or {}
    status = str(result.get("status", run["status"]))
    corrected = bool((result.get("correction") or {}).get("recovered"))
    rows = result.get("result_rows", [])
    columns = result.get("result_columns", [])
    latency = float((result.get("latency_ms") or {}).get("total", 0)) / 1000
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric(
            "Final status",
            "Corrected" if corrected else status,
            "corrected" if corrected else "safe",
        )
    with c2:
        metric("Total latency", f"{latency:.2f}s")
    with c3:
        metric("Rows", str(len(rows)))
    with c4:
        calls = int((result.get("correction") or {}).get("llm_calls", 0))
        metric("Repair calls", str(calls))

    if status == "SUCCEEDED":
        table, chart, sql, trust = st.tabs(["Result", "Visualization", "SQL", "Trust & evidence"])
        frame = [dict(zip(columns, row, strict=True)) for row in rows]
        with table:
            if len(rows) == len(columns) == 1:
                st.metric(columns[0], rows[0][0])
            else:
                st.dataframe(frame, width="stretch", hide_index=True)
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow(columns)
            writer.writerows(rows)
            st.download_button(
                "Download preview CSV",
                csv_buffer.getvalue().encode("utf-8"),
                f"{run['run_id']}-preview.csv",
                "text/csv",
            )
        with chart:
            if len(columns) == 2 and len(rows) > 1:
                horizontal_bars(frame, columns[0], columns[1])
            else:
                st.info("This result shape is best represented as a table or KPI.")
        with sql:
            candidate = result.get("candidate") or {}
            st.code(candidate.get("normalized_sql", "No SQL candidate"), language="sql")
            st.caption(
                "Read-only policy verified · Copy is allowed · Browser execution is disabled"
            )
        with trust:
            st.subheader("Logical plan")
            st.json(result.get("plan") or {})
            st.subheader("Schema evidence")
            schema = result.get("schema_context") or {}
            st.code(schema.get("rendered_context", "Full catalog mode"), language="text")
            if result.get("correction"):
                st.subheader("Correction outcome")
                st.json(result["correction"])
    else:
        message = result.get("safe_message") or "The workflow stopped with a typed safe status."
        if status in {"WRITE_BLOCKED", "POLICY_BLOCKED"}:
            st.warning(f"🛡️ {message}")
        elif status == "CLARIFY":
            st.info(message)
        else:
            st.error(message)

    st.subheader("Was this answer useful?")
    st.caption("Feedback stays on this machine and is linked to the immutable run ID.")
    with st.form(f"feedback-{run['run_id']}"):
        rating_label = st.radio(
            "Verdict",
            ["Correct", "Incorrect"],
            horizontal=True,
            key=f"rating-{run['run_id']}",
        )
        categories = st.multiselect(
            "Failure categories (for incorrect answers)",
            [
                "WRONG_RESULT",
                "WRONG_SHAPE",
                "WRONG_METRIC",
                "WRONG_FILTER",
                "WRONG_JOIN",
                "MISSING_DATA",
                "TOO_SLOW",
                "UNSAFE_OR_UNEXPECTED",
                "OTHER",
            ],
            disabled=rating_label == "Correct",
        )
        note = st.text_input("Optional note", max_chars=2000)
        save_feedback = st.form_submit_button("Save local feedback")
    if save_feedback:
        try:
            client.feedback(
                run["run_id"],
                "CORRECT" if rating_label == "Correct" else "INCORRECT",
                [] if rating_label == "Correct" else categories,
                note or None,
            )
            st.success("Feedback saved locally.")
        except httpx.HTTPError as exc:
            api_error(exc)


@st.fragment(run_every=1.0 if st.session_state.get("active_run_id") else None)
def active_run_panel() -> None:
    run_id = st.session_state.get("active_run_id")
    if run_id:
        try:
            run = client.run(str(run_id))
        except httpx.HTTPError as exc:
            api_error(exc)
            return
        if run["status"] not in {"COMPLETED", "FAILED"}:
            st.info(
                f"Run `{str(run_id)[:8]}` is {str(run['status']).lower()}. "
                "You may inspect another workspace while it continues in the background."
            )
            return
        st.session_state["active_run"] = run
        st.session_state.pop("active_run_id", None)
        st.rerun()
    if run := st.session_state.get("active_run"):
        st.divider()
        render_result(run)


def query_studio() -> None:
    hero(
        "Query Studio",
        "Ask the data. Inspect the reasoning.",
        "A local, read-only workspace for bilingual questions with grounded evidence and bounded correction.",
    )
    try:
        health = cached_health()
        catalogs = cached_catalogs()
    except httpx.HTTPError as exc:
        api_error(exc)
        return
    st.markdown(
        f'<span class="status-pill">● API ready · {health["registered_catalogs"]} catalog(s)</span>',
        unsafe_allow_html=True,
    )
    if not catalogs:
        st.info("Register the canonical Olist database to begin.")
        if st.button("Register Olist", type="primary"):
            try:
                client.ingest("olist")
                cached_health.clear()
                cached_catalogs.clear()
                st.rerun()
            except httpx.HTTPError as exc:
                api_error(exc)
        return

    left, right = st.columns([1.9, 1], gap="large")
    with right:
        st.subheader("Drag to prioritize")
        st.caption(
            "Keyboard users get an instant selector. Enable the optional drag organizer when needed."
        )
        ordered = EXAMPLES
        if st.toggle("Enable drag organizer", value=False, key="enable-drag"):
            from streamlit_sortables import sort_items

            ordered = sort_items(
                EXAMPLES,
                direction="vertical",
                custom_style=SORTABLE_CSS,
                key="query-starters",
            )
        starter = st.selectbox("Use a starter", ["Write my own", *ordered])
    with left:
        with st.form("query-form"):
            db_id = st.selectbox("Database", [item["db_id"] for item in catalogs])
            default = "" if starter == "Write my own" else starter
            question = st.text_area(
                "Question",
                value=default,
                height=145,
                placeholder="Ví dụ: Top 5 danh mục theo doanh thu sản phẩm...",
            )
            with st.expander("Advanced controls"):
                correction = st.toggle(
                    "Enable bounded correction",
                    value=False,
                    help="At most one repair call; every candidate re-enters the full safety gate.",
                )
                st.caption(
                    "Correction remains opt-in after Gate P4 because local model runs can vary."
                )
            submitted = st.form_submit_button("Run query", type="primary", width="stretch")
        if submitted:
            try:
                accepted = client.submit(db_id, question, correction)
                run_id = accepted["run_id"]
                st.session_state["active_run_id"] = run_id
                st.session_state.pop("active_run", None)
                st.rerun()
            except (httpx.HTTPError, ValueError) as exc:
                api_error(exc)
    active_run_panel()


def run_inspector() -> None:
    hero(
        "Run Inspector",
        "Six layers, one auditable story.",
        "Replay planning, grounding, SQL generation, validation, correction, and presentation.",
    )
    try:
        runs = client.runs()
    except httpx.HTTPError as exc:
        api_error(exc)
        return
    if not runs:
        st.info("No persisted runs yet.")
        return
    labels = {f"{item['question'][:70]} · {item['run_id'][:8]}": item for item in runs}
    selected = labels[st.selectbox("Run", list(labels))]
    try:
        selected = client.run(selected["run_id"])
        events = client.events(selected["run_id"])
    except httpx.HTTPError as exc:
        api_error(exc)
        return
    for event in events:
        state = event.get("details", {}).get("state", "COMPLETED")
        st.markdown(
            f'<div class="layer-card"><b>Layer {event["layer"]} · {event["event"]}</b>'
            f'<div class="tiny">{state} · {event["elapsed_ms"]:.2f} ms</div></div>',
            unsafe_allow_html=True,
        )
    if selected.get("result"):
        render_result(selected)
        with st.expander("Sanitized trace JSON"):
            st.json(events)
            st.download_button(
                "Download trace",
                json.dumps(events, ensure_ascii=False, indent=2),
                f"{selected['run_id']}-trace.json",
                "application/json",
            )


def history() -> None:
    hero(
        "History",
        "Your local run ledger.",
        "Search, reopen, and compare reproducible runs after an application restart.",
    )
    search = st.text_input("Search questions", placeholder="revenue, delivery, customer…")
    try:
        runs = client.runs(search or None)
    except httpx.HTTPError as exc:
        api_error(exc)
        return
    st.caption(f"{len(runs)} run(s) · lightweight summaries loaded")
    for run in runs:
        with st.expander(f"{run['question']} · {run['status']}"):
            a, b, c = st.columns(3)
            a.code(run["run_id"])
            b.write(run["db_id"])
            c.write(run["updated_at"][:19])
    if runs:
        labels = {f"{item['question'][:70]} · {item['run_id'][:8]}": item for item in runs}
        detail_label = st.selectbox("Open one run", ["None", *labels], key="history-detail")
        if detail_label != "None":
            try:
                detail = client.run(labels[detail_label]["run_id"])
            except httpx.HTTPError as exc:
                api_error(exc)
                return
            result = detail.get("result") or {}
            st.code((result.get("candidate") or {}).get("normalized_sql", "No SQL"), language="sql")


def benchmark_lab() -> None:
    hero(
        "Benchmark Lab",
        "Metrics with boundaries.",
        "Olist application fitness and cross-domain benchmarks stay explicitly separated.",
    )
    try:
        reports = cached_reports()
    except httpx.HTTPError as exc:
        api_error(exc)
        return
    olist, generalization = st.tabs(["Olist acceptance", "Generalization"])
    with olist:
        selected = [
            item for item in reports if "olist" in str(item.get("evaluation_id", "")).lower()
        ]
        for item in selected:
            count = item.get("case_count") or 0
            accuracy = item.get("result_accuracy")
            value = "n/a" if accuracy is None else f"{float(accuracy) * 100:.2f}% · n={count}"
            metric(str(item.get("evaluation_id")), value)
        if not selected:
            st.info("Run the Olist acceptance command to populate this page.")
    with generalization:
        spider = [
            item for item in reports if "spider" in str(item.get("evaluation_id", "")).lower()
        ]
        if not spider:
            st.info("Run the guarded Spider release benchmark to populate Gate P6 evidence.")
        else:
            labels = {
                f"{item.get('evaluation_id')} · n={item.get('case_count')}": item for item in spider
            }
            selected_label = st.selectbox("Release report", list(labels), key="spider-report")
            selected = labels[selected_label]
            try:
                report = client.report(str(selected["report_id"]))
            except httpx.HTTPError as exc:
                api_error(exc)
                return
            accuracy = float(report.get("result_accuracy") or 0)
            completion = float(report.get("workflow_completion_rate") or 0)
            latency = report.get("latency_ms") or {}
            a, b, c, d = st.columns(4)
            with a:
                metric("Execution accuracy", f"{accuracy * 100:.2f}%")
            with b:
                metric("Workflow completion", f"{completion * 100:.2f}%")
            with c:
                metric("P50", f"{float(latency.get('p50', 0)) / 1000:.1f}s")
            with d:
                metric("P95", f"{float(latency.get('p95', 0)) / 1000:.1f}s")
            st.caption(
                "Cross-domain Spider execution is never blended with Olist application fitness."
            )
            categories = report.get("failure_categories") or {}
            complexity = report.get("by_complexity") or {}
            partitions = report.get("by_partition") or {}
            failures, slices, partition_view, provenance = st.tabs(
                [
                    "Failure taxonomy",
                    "Complexity slices",
                    "Regression vs holdout",
                    "Manifest & provenance",
                ]
            )
            with failures:
                if categories:
                    frame = [{"category": key, "count": value} for key, value in categories.items()]
                    horizontal_bars(frame, "category", "count")
                else:
                    st.success("No failures in this report.")
            with slices:
                st.dataframe(
                    [{"complexity": key, **value} for key, value in complexity.items()],
                    width="stretch",
                    hide_index=True,
                )
            with partition_view:
                st.dataframe(
                    [{"partition": key, **value} for key, value in partitions.items()],
                    width="stretch",
                    hide_index=True,
                )
            with provenance:
                st.json(
                    {
                        "manifest": report.get("manifest"),
                        "provenance": report.get("provenance"),
                        "limitations": report.get("limitations"),
                    }
                )


def system_center() -> None:
    hero(
        "System Center",
        "Local-first readiness.",
        "Inspect registered data, pinned models, safety defaults, and service health without exposing secrets.",
    )
    try:
        health = cached_health()
        models = client.models()
        catalogs = cached_catalogs()
    except httpx.HTTPError as exc:
        api_error(exc)
        return
    a, b, c = st.columns(3)
    with a:
        metric("API", str(health["status"]).upper(), "safe")
    with b:
        metric("Generation", str(models["generation"]))
    with c:
        metric("Correction default", "OFF")
    st.subheader("Registered catalogs")
    for catalog in catalogs:
        st.markdown(
            f"**{catalog['db_id']}** · {len(catalog['tables'])} objects · `{catalog['catalog_hash'][:12]}`"
        )
    st.subheader("Safety posture")
    st.success("Read-only SQLite URI · query_only · authorizer · timeout · row/byte caps")


with st.sidebar:
    st.markdown("## ◈ SQL Observatory")
    st.caption("Local · Free · Evidence-driven")
    page = st.radio(
        "Workspace",
        ["Query Studio", "Run Inspector", "History", "Benchmark Lab", "System Center"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("Drag the sidebar edge to resize · Data never leaves the local runtime")

{
    "Query Studio": query_studio,
    "Run Inspector": run_inspector,
    "History": history,
    "Benchmark Lab": benchmark_lab,
    "System Center": system_center,
}[page]()
