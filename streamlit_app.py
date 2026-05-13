
import streamlit as st
import asyncio
import os
import html
import time
import threading
from queue import Queue, Empty
from datetime import datetime, timezone, timedelta
from tickers import TICKERS

GMT_PLUS_8 = timezone(timedelta(hours=8))

# --- Page Configuration ---
st.set_page_config(
    page_title="AgentInvest",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- App Styling ---
st.markdown("""
    <style>
        .stApp {
            background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
        }
        .hero-card {
            padding: 1rem 1.2rem;
            border-radius: 14px;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            box-shadow: 0 6px 20px rgba(15, 23, 42, 0.06);
            margin-bottom: 1rem;
        }
        .subtle-text {
            color: #475569;
            font-size: 0.95rem;
        }
        .generated-item {
            border: 1px solid #dbeafe;
            border-left: 4px solid #2563eb;
            border-radius: 8px;
            background: #f8fbff;
            padding: 0.6rem 0.8rem;
            margin-bottom: 0.5rem;
        }
        .status-chip {
            display: inline-block;
            padding: 0.25rem 0.6rem;
            border-radius: 999px;
            background: #e2e8f0;
            color: #0f172a;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .summary-preview-card {
            border: 1px solid #cbd5e1;
            border-left: 6px solid #1d4ed8;
            border-radius: 10px;
            background: #ffffff;
            padding: 1rem 1.1rem;
            margin-top: 0.3rem;
            box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
        }
        .keypoint-card {
            border: 1px solid #dbeafe;
            border-radius: 10px;
            background: #f8fbff;
            padding: 0.7rem 0.9rem;
            margin-bottom: 0.5rem;
            color: #0f172a;
        }
        .timeline-item {
            display: flex;
            align-items: flex-start;
            gap: 0.65rem;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            background: #ffffff;
            padding: 0.65rem 0.8rem;
            margin-bottom: 0.45rem;
            color: #0f172a;
        }
        .timeline-item.current {
            border-color: #93c5fd;
            background: #eff6ff;
            box-shadow: 0 4px 14px rgba(37, 99, 235, 0.12);
        }
        .timeline-dot {
            width: 1.4rem;
            height: 1.4rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            background: #dcfce7;
            color: #166534;
            font-size: 0.8rem;
            font-weight: 700;
            flex-shrink: 0;
        }
        .timeline-item.current .timeline-dot {
            background: #dbeafe;
            color: #1d4ed8;
        }
        .timeline-text {
            flex: 1;
            min-width: 0;
            line-height: 1.35;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: break-word;
        }
    </style>
""", unsafe_allow_html=True)

# --- Helper Functions ---
@st.cache_resource(show_spinner=False)
def get_agent_class():
    """Lazily import AgentInvest to keep initial page render responsive."""
    from agent import AgentInvest
    return AgentInvest


@st.cache_resource(show_spinner=False)
def warmup_agent_runtime() -> bool:
    """
    Preload heavy report runtime components once per app process.
    This reduces first-click latency when users start generation.
    """
    AgentInvest = get_agent_class()
    # Instantiate once so downstream imports/tool specs are warmed.
    AgentInvest(verbose_agent=False)
    return True

def run_report_worker(
    ticker: str,
    custom_instruction: str,
    progress_queue: Queue,
    stop_event: threading.Event,
) -> None:
    """Run report generation in a background thread."""

    def update_ui(payload: dict) -> None:
        progress_queue.put({"type": "progress", "payload": payload})

    try:
        update_ui({"message": "⚙️ Initializing research engine..."})
        AgentInvest = get_agent_class()
        agent = AgentInvest(verbose_agent=False)
        asyncio.run(
            agent.run(
                ticker=ticker,
                progress_callback=update_ui,
                custom_instruction=custom_instruction,
                stop_event=stop_event,
            )
        )
        if stop_event.is_set():
            progress_queue.put({"type": "stopped"})
        else:
            progress_queue.put(
                {
                    "type": "completed",
                    "pdf_path": f"generated_reports/{ticker}_AgentInvest_Report.pdf",
                    "md_path": f"generated_reports/{ticker}_AgentInvest_Report.md",
                }
            )
    except asyncio.CancelledError:
        progress_queue.put({"type": "stopped"})
    except Exception as exc:
        progress_queue.put(
            {"type": "error", "error": str(exc), "error_type": type(exc).__name__}
        )
    finally:
        progress_queue.put({"type": "finished"})

def initialize_session_state() -> None:
    defaults = {
        "report_generated": False,
        "pdf_path": "",
        "progress_log": [],
        "generated_data": {},
        "is_running": False,
        "run_status": "Idle",
        "custom_instruction_feedback": None,
        "last_selected_ticker": None,
        "worker_thread": None,
        "progress_queue": None,
        "stop_event": None,
        "run_error": None,
        "pending_error": None,
        "executive_summary_preview": "",
        "key_points": [],
        "report_md_path": "",
        "ppt_path": "",
        "ppt_ready": False,
        "ppt_error": None,
        "is_generating_ppt": False,
        "company_name": "",
        "pdf_in_progress": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def get_gmt8_timestamp() -> str:
    """Return current timestamp in GMT+8."""
    return datetime.now(GMT_PLUS_8).strftime("%Y-%m-%d %H:%M")

# --- Main Application ---
def main():
    initialize_session_state()
    warmup_ok = False
    try:
        warmup_ok = bool(warmup_agent_runtime())
    except Exception:
        warmup_ok = False

    def process_background_events() -> None:
        progress_queue = st.session_state.progress_queue
        if progress_queue is None:
            return

        while True:
            try:
                event = progress_queue.get_nowait()
            except Empty:
                break

            event_type = event.get("type")
            if event_type == "progress":
                payload = event.get("payload", {})
                message = payload.get("message", "")
                data = payload.get("data")
                st.session_state.progress_log.append(message)
                message_lower = message.lower()

                if "starting analysis" in message_lower:
                    st.session_state.run_status = "Building report"
                elif "generating content for each report section" in message_lower:
                    st.session_state.run_status = "Writing report"
                elif "executive summary extracted" in message_lower:
                    st.session_state.run_status = "Preparing highlights"
                elif "converting report to pdf" in message_lower:
                    st.session_state.run_status = "Preparing PDF"
                    st.session_state.pdf_in_progress = True
                elif "pdf report saved" in message_lower:
                    st.session_state.pdf_in_progress = False

                if "structure generated" in message and data:
                    st.session_state.generated_data["structure"] = data
                if "web search queries" in message and data:
                    st.session_state.generated_data["web_queries"] = data
                if "financial data queries" in message and data:
                    st.session_state.generated_data["financial_queries"] = data
                if "Custom instruction accepted and rewritten" in message:
                    st.session_state.custom_instruction_feedback = ("accepted", data or "")
                if "Custom instruction was ignored" in message:
                    st.session_state.custom_instruction_feedback = ("ignored", data or "")
                if "executive summary extracted" in message_lower and data:
                    st.session_state.executive_summary_preview = str(data).strip()
                if "key bullets extracted" in message_lower and data:
                    if isinstance(data, list):
                        st.session_state.key_points = [str(item).strip() for item in data if str(item).strip()]
                    else:
                        st.session_state.key_points = [str(data).strip()] if str(data).strip() else []
                if "identified company" in message_lower and data:
                    st.session_state.company_name = str(data).strip()
                if "using cached company name" in message_lower and data:
                    st.session_state.company_name = str(data).strip()
            elif event_type == "completed":
                st.session_state.report_generated = True
                st.session_state.run_status = "Completed"
                st.session_state.pdf_path = event.get("pdf_path", "")
                st.session_state.report_md_path = event.get("md_path", "")
                st.session_state.pdf_in_progress = False
                st.session_state.run_error = None
                st.session_state.pending_error = None
            elif event_type == "stopped":
                st.session_state.report_generated = False
                st.session_state.run_status = "Idle"
                st.session_state.run_error = None
                st.session_state.pending_error = None
                st.session_state.executive_summary_preview = ""
                st.session_state.key_points = []
                st.session_state.report_md_path = ""
                st.session_state.ppt_path = ""
                st.session_state.ppt_ready = False
                st.session_state.ppt_error = None
                st.session_state.is_generating_ppt = False
                st.session_state.company_name = ""
                st.session_state.pdf_in_progress = False
                st.session_state.progress_log.append("🛑 Report generation stopped by user.")
            elif event_type == "error":
                st.session_state.pending_error = (
                    f"{event.get('error_type', 'Error')}: {event.get('error', 'Unknown error')}"
                )
            elif event_type == "finished":
                st.session_state.is_running = False
                if st.session_state.pending_error:
                    st.session_state.report_generated = False
                    st.session_state.run_status = "Idle"
                    st.session_state.run_error = st.session_state.pending_error
                    st.session_state.pending_error = None

    process_background_events()

    st.markdown("""
    <div class="hero-card">
      <h2 style="margin:0; color:#0f172a;">AgentInvest Research Studio</h2>
      <p class="subtle-text" style="margin:0.5rem 0 0 0;">
        Built for investment teams to move from ticker selection to decision-ready materials quickly.
      </p>
      <ul style="margin:0.7rem 0 0 1.2rem; color:#334155; line-height:1.55;">
        <li><b>Investment-ready brief:</b> Generate a professional report with company context, structured analysis, and references.</li>
        <li><b>Live decision insights:</b> Review an executive summary and top highlights in the app before downloading files.</li>
        <li><b>Editable presentation export:</b> Create and download a <b>.pptx</b> deck (up to 10 slides) for internal edits and investment meetings.</li>
      </ul>
      <p style="margin:0.75rem 0 0 0; color:#1e293b; font-size:0.93rem;">
        <b>How to navigate:</b> Select a ticker in the sidebar, click <b>Generate Report</b>, follow the <b>Research Journey</b>,
        review the <b>Investment Snapshot</b>, then download the PDF and optional editable PowerPoint.
      </p>
    </div>
    """, unsafe_allow_html=True)

    st.sidebar.markdown("## Report Configuration")
    if not warmup_ok:
        st.sidebar.caption("Preparing report runtime components...")
    selected_ticker = st.sidebar.selectbox("Select a Stock Ticker:", TICKERS)
    custom_instruction_input = st.sidebar.text_area(
        "Optional Custom Instruction",
        placeholder=(
            "Example: Focus more on downside risk, valuation assumptions, and "
            "competitive moat sustainability."
        ),
        help=(
            "Optional guidance for report writing. Instructions are checked by an LLM. "
            "Irrelevant or unsafe instructions are automatically ignored."
        ),
        height=140,
    )
    presentation_style = st.sidebar.selectbox(
        "Presentation Style",
        ["Institutional Light", "Executive Dark", "Minimal Clean"],
        index=0,
        help="Choose the visual style for the editable PowerPoint deck.",
    )

    if st.session_state.is_running:
        if st.sidebar.button("Stop Report", type="secondary"):
            if st.session_state.stop_event is not None:
                st.session_state.stop_event.set()
                st.session_state.progress_log.append("🛑 Stop request received. Waiting for safe termination...")

    if st.session_state.last_selected_ticker is None:
        st.session_state.last_selected_ticker = selected_ticker
    elif (
        selected_ticker != st.session_state.last_selected_ticker
        and not st.session_state.is_running
    ):
        st.session_state.last_selected_ticker = selected_ticker
        st.session_state.run_status = "Idle"
        st.session_state.report_generated = False
        st.session_state.pdf_path = ""
        st.session_state.progress_log = []
        st.session_state.generated_data = {}
        st.session_state.custom_instruction_feedback = None
        st.session_state.run_error = None
        st.session_state.pending_error = None
        st.session_state.executive_summary_preview = ""
        st.session_state.key_points = []
        st.session_state.report_md_path = ""
        st.session_state.ppt_path = ""
        st.session_state.ppt_ready = False
        st.session_state.ppt_error = None
        st.session_state.is_generating_ppt = False
        st.session_state.company_name = ""
        st.session_state.pdf_in_progress = False

    generation_time = get_gmt8_timestamp()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Selected Ticker", selected_ticker)
    display_company = st.session_state.company_name or ("Detecting company..." if st.session_state.is_running else "Not started")
    m2.metric("Company", display_company)
    status_placeholder = m3.empty()
    status_placeholder.metric("Report Status", st.session_state.run_status)
    m4.metric("Timestamp (GMT+8)", generation_time)

    if st.session_state.custom_instruction_feedback:
        status, note = st.session_state.custom_instruction_feedback
        if status == "accepted":
            st.success(f"Custom instruction accepted and applied: {note}")
        elif status == "ignored":
            st.warning("Custom instruction was ignored.")
            if note:
                safe_note = html.escape(str(note), quote=True)
                st.markdown(
                    f"<span title=\"{safe_note}\">ℹ️ <b>Why ignored?</b> (hover)</span>",
                    unsafe_allow_html=True,
                )

    def render_dynamic_sections() -> None:
        structure_area, web_queries_area, financial_queries_area = st.tabs(
            ["Report Roadmap", "Market Signals", "Financial Highlights"]
        )

        with structure_area:
            st.markdown("### Storyline Outline")
            structure = st.session_state.generated_data.get("structure", [])
            if structure:
                for section in structure:
                    st.markdown(
                        f"<div class='generated-item'>{section}</div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("Your report storyline will appear once planning is completed.")

        with web_queries_area:
            st.markdown("### Market Research Focus")
            web_queries = st.session_state.generated_data.get("web_queries", [])
            for query in web_queries:
                st.markdown(f"<div class='generated-item'>{query}</div>", unsafe_allow_html=True)
            if not web_queries:
                st.caption("Market research themes will appear here.")

        with financial_queries_area:
            st.markdown("### Financial Analysis Focus")
            financial_queries = st.session_state.generated_data.get("financial_queries", [])
            for query in financial_queries:
                st.markdown(
                    f"<div class='generated-item'>{query['query']} ({query['ticker']})</div>",
                    unsafe_allow_html=True,
                )
            if not financial_queries:
                st.caption("Financial analysis themes will appear here.")

    def render_research_journey_panel() -> None:
        st.markdown("### AgentInvest Reasoning")
        if not st.session_state.progress_log:
            st.info("Choose your ticker and click `Generate Report` to begin.")
            return

        with st.expander("View Activity Timeline", expanded=True):
            for i, log in enumerate(st.session_state.progress_log):
                is_current = i == len(st.session_state.progress_log) - 1 and st.session_state.is_running
                item_class = "timeline-item current" if is_current else "timeline-item"
                safe_log = html.escape(str(log))
                st.markdown(
                    f"<div class='{item_class}'><span class='timeline-dot'>{'↻' if is_current else '✓'}</span><span class='timeline-text'>{safe_log}</span></div>",
                    unsafe_allow_html=True,
                )

    def render_investment_snapshot() -> None:
        has_summary = bool(st.session_state.executive_summary_preview.strip())
        has_points = bool(st.session_state.key_points)
        if not has_summary and not has_points and not st.session_state.report_generated:
            return

        st.markdown("### Investment Snapshot")
        left_col, right_col = st.columns([1.6, 1.0], gap="large")

        with left_col:
            st.markdown("#### Investment Brief")
            if has_summary:
                with st.container():
                    st.markdown(st.session_state.executive_summary_preview)
            else:
                st.info("Your investment brief will appear shortly.")

        with right_col:
            st.markdown("#### Decision Highlights")
            if has_points:
                for idx, point in enumerate(st.session_state.key_points[:5], start=1):
                    safe_point = html.escape(point)
                    st.markdown(
                        f"<div class='keypoint-card'><b>{idx}.</b> {safe_point}</div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.info("Top highlights will appear once extraction is complete.")

    if st.sidebar.button("Generate Report", type="primary", disabled=st.session_state.is_running):
        st.session_state.report_generated = False
        st.session_state.pdf_path = ""
        st.session_state.progress_log = []
        st.session_state.generated_data = {}
        st.session_state.is_running = True
        st.session_state.run_status = "Running"
        st.session_state.custom_instruction_feedback = None
        st.session_state.run_error = None
        st.session_state.pending_error = None
        st.session_state.executive_summary_preview = ""
        st.session_state.key_points = []
        st.session_state.report_md_path = ""
        st.session_state.ppt_path = ""
        st.session_state.ppt_ready = False
        st.session_state.ppt_error = None
        st.session_state.is_generating_ppt = False
        st.session_state.company_name = ""
        st.session_state.pdf_in_progress = False
        st.session_state.last_selected_ticker = selected_ticker
        st.session_state.progress_queue = Queue()
        st.session_state.stop_event = threading.Event()
        status_placeholder.metric("Run Status", st.session_state.run_status)
        worker = threading.Thread(
            target=run_report_worker,
            args=(
                selected_ticker,
                custom_instruction_input,
                st.session_state.progress_queue,
                st.session_state.stop_event,
            ),
            daemon=True,
        )
        st.session_state.worker_thread = worker
        worker.start()
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Presentation Export")
    st.sidebar.caption(
        "Create an editable investment meeting deck. Available after report generation is complete."
    )
    if st.session_state.ppt_error:
        st.sidebar.error(
            "Sorry, we could not generate your presentation this time. "
            "Please try again in a moment."
        )
        st.sidebar.caption(st.session_state.ppt_error)

    report_is_ready = st.session_state.report_generated and not st.session_state.is_running
    if st.sidebar.button(
        "Generate Presentation (PPTX)",
        type="primary",
        disabled=st.session_state.is_generating_ppt or not report_is_ready,
        help=None if report_is_ready else "Finish generating the report first.",
    ):
        report_md_path = st.session_state.report_md_path or f"generated_reports/{selected_ticker}_AgentInvest_Report.md"
        if not os.path.exists(report_md_path):
            st.session_state.ppt_error = "Markdown report was not found. Please regenerate the report first."
            st.session_state.ppt_ready = False
        else:
            st.session_state.is_generating_ppt = True
            st.session_state.ppt_error = None
            try:
                from ppt_export import build_professional_pptx
                AgentInvest = get_agent_class()

                with st.spinner("Generating professional presentation..."):
                    with open(report_md_path, "r", encoding="utf-8") as md_file:
                        report_markdown = md_file.read()
                    company_name = st.session_state.company_name or selected_ticker
                    visual_deck_spec = None
                    try:
                        planner_agent = AgentInvest(verbose_agent=False)
                        visual_deck_spec = asyncio.run(
                            planner_agent.generate_visual_deck_spec(
                                company_name=company_name,
                                ticker=selected_ticker,
                                report_markdown=report_markdown,
                                executive_summary=st.session_state.executive_summary_preview,
                                key_points=st.session_state.key_points[:5],
                            )
                        )
                    except Exception:
                        visual_deck_spec = None

                    output_ppt_path = f"generated_reports/{selected_ticker}_AgentInvest_Presentation.pptx"
                    build_professional_pptx(
                        report_markdown=report_markdown,
                        output_path=output_ppt_path,
                        company_name=company_name,
                        ticker=selected_ticker,
                        key_points=st.session_state.key_points[:5],
                        executive_summary=st.session_state.executive_summary_preview,
                        chartjs_src=os.getenv("CHARTJS_SRC", None),
                        visual_deck_spec=visual_deck_spec,
                        style_profile=presentation_style,
                    )
                    st.session_state.ppt_path = output_ppt_path
                    st.session_state.ppt_ready = True
            except ImportError:
                st.session_state.ppt_error = (
                    "PPT export dependency is missing. Please install `python-pptx` and retry."
                )
                st.session_state.ppt_ready = False
            except Exception as exc:
                st.session_state.ppt_error = f"PPT generation failed. Please retry. Details: {exc}"
                st.session_state.ppt_ready = False
            finally:
                st.session_state.is_generating_ppt = False

    if st.session_state.run_error and not st.session_state.is_running:
        st.error(f"Report generation failed: {st.session_state.run_error}")

    left_content_col, right_timeline_col = st.columns([2.1, 1.15], gap="large")
    with left_content_col:
        render_dynamic_sections()
        render_investment_snapshot()
    with right_timeline_col:
        render_research_journey_panel()

    if st.session_state.is_running and st.session_state.pdf_in_progress:
        st.info(
            "Your report narrative is ready. We are now generating the PDF and preparing downloads."
        )

    if st.session_state.report_generated and not st.session_state.is_running:
        st.markdown("---")
        st.success("Your report package is ready.")

        st.markdown("### Download Report")
        if os.path.exists(st.session_state.pdf_path):
            with open(st.session_state.pdf_path, "rb") as pdf_file:
                st.download_button(
                    label="Download Investment Report (PDF)",
                    data=pdf_file.read(),
                    file_name=os.path.basename(st.session_state.pdf_path),
                    mime="application/pdf",
                    type="primary",
                )
            file_size = os.path.getsize(st.session_state.pdf_path) / 1024
            st.caption(
                f"File size: {file_size:.1f} KB | Generated (GMT+8): {get_gmt8_timestamp()}"
            )
        else:
            st.error("Generated PDF file was not found.")

        if st.session_state.ppt_ready and st.session_state.ppt_path and os.path.exists(st.session_state.ppt_path):
            st.markdown("### Download Presentation")
            with open(st.session_state.ppt_path, "rb") as ppt_file:
                st.download_button(
                    label="Download Presentation (PPTX)",
                    data=ppt_file.read(),
                    file_name=os.path.basename(st.session_state.ppt_path),
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    type="primary",
                )
            ppt_size = os.path.getsize(st.session_state.ppt_path) / 1024
            st.caption(f"PPT size: {ppt_size:.1f} KB")
    elif st.session_state.report_generated and st.session_state.is_running:
        st.info("Finalizing report files...")

    if st.session_state.is_running:
        time.sleep(1)
        st.rerun()

if __name__ == "__main__":
    main()
