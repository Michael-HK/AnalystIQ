
import streamlit as st
import asyncio
import os
import html
import time
import threading
from queue import Queue, Empty
from datetime import datetime
from tickers import TICKERS

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
    </style>
""", unsafe_allow_html=True)

# --- Helper Functions ---
def get_agent_class():
    """Lazily import AgentInvest to keep initial page render responsive."""
    from agent import AgentInvest
    return AgentInvest

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
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# --- Main Application ---
def main():
    initialize_session_state()

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
            elif event_type == "completed":
                st.session_state.report_generated = True
                st.session_state.run_status = "Completed"
                st.session_state.pdf_path = event.get("pdf_path", "")
                st.session_state.run_error = None
                st.session_state.pending_error = None
            elif event_type == "stopped":
                st.session_state.report_generated = False
                st.session_state.run_status = "Idle"
                st.session_state.run_error = None
                st.session_state.pending_error = None
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
        Generate institution-style investment reports with automated data collection,
        structured analysis, and publication-ready PDF output.
      </p>
    </div>
    """, unsafe_allow_html=True)

    st.sidebar.markdown("## Report Configuration")
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

    generation_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    m1, m2, m3 = st.columns(3)
    m1.metric("Selected Ticker", selected_ticker)
    status_placeholder = m2.empty()
    status_placeholder.metric("Run Status", st.session_state.run_status)
    m3.metric("Timestamp", generation_time)

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

    structure_area, web_queries_area, financial_queries_area = st.tabs(
        ["Report Structure", "Web Queries", "Financial Queries"]
    )
    progress_area = st.container()
    structure_placeholder = structure_area.empty()
    web_queries_placeholder = web_queries_area.empty()
    financial_queries_placeholder = financial_queries_area.empty()
    progress_placeholder = progress_area.empty()

    def render_dynamic_sections() -> None:
        with progress_placeholder.container():
            st.markdown("### Workflow Progress")
            if not st.session_state.progress_log:
                st.info("Configure options in the sidebar and click `Generate Report` to begin.")
            else:
                with st.expander("View Step-by-Step Logs", expanded=True):
                    for i, log in enumerate(st.session_state.progress_log):
                        if i == len(st.session_state.progress_log) - 1 and st.session_state.is_running:
                            st.warning(f"🔄 {log}")
                        else:
                            st.success(f"✅ {log}")

        with structure_placeholder.container():
            st.markdown("### Generated Report Structure")
            structure = st.session_state.generated_data.get("structure", [])
            if structure:
                for section in structure:
                    st.markdown(
                        f"<div class='generated-item'>{section}</div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("Structure will appear once generation reaches planning stage.")

        with web_queries_placeholder.container():
            st.markdown("### Generated Web Queries")
            web_queries = st.session_state.generated_data.get("web_queries", [])
            for query in web_queries:
                st.markdown(f"<div class='generated-item'>{query}</div>", unsafe_allow_html=True)
            if not web_queries:
                st.caption("Web search queries will appear here.")

        with financial_queries_placeholder.container():
            st.markdown("### Generated Financial Queries")
            financial_queries = st.session_state.generated_data.get("financial_queries", [])
            for query in financial_queries:
                st.markdown(
                    f"<div class='generated-item'>{query['query']} ({query['ticker']})</div>",
                    unsafe_allow_html=True,
                )
            if not financial_queries:
                st.caption("Financial queries will appear here.")

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

    if st.session_state.run_error and not st.session_state.is_running:
        st.error(f"Report generation failed: {st.session_state.run_error}")

    render_dynamic_sections()

    if st.session_state.report_generated and not st.session_state.is_running:
        st.markdown("---")
        st.success("Report generation complete.")
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
                f"File size: {file_size:.1f} KB | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
        else:
            st.error("Generated PDF file was not found.")
    elif st.session_state.report_generated and st.session_state.is_running:
        st.info("Finalizing report files...")

    if st.session_state.is_running:
        time.sleep(1)
        st.rerun()

if __name__ == "__main__":
    main()
