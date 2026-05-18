
import base64
import re
import urllib.parse
import streamlit as st
import asyncio
import os
import html
import time
import threading
from queue import Queue, Empty
from datetime import datetime, timezone, timedelta
from tickers import TICKERS
from report_viewer import load_report_markdown, build_report_viewer_html

GMT_PLUS_8 = timezone(timedelta(hours=8))
REPORT_TYPE_OPTIONS = {
    "Investment Report": "investment",
    "Credit Analysis Report": "credit",
}
REPORT_TYPE_LABELS = {value: key for key, value in REPORT_TYPE_OPTIONS.items()}

# --- Page Configuration ---
st.set_page_config(
    page_title="AnalystIQ",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- App Styling ---
st.markdown("""
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-canvas: #f3f6fc;
            --bg-page: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
            --surface-primary: #ffffff;
            --surface-secondary: #f8fbff;
            --surface-muted: #f1f5f9;
            --surface-accent: #eff6ff;
            --border-subtle: #dbe3ef;
            --border-strong: #cbd5e1;
            --text-primary: #0f172a;
            --text-secondary: #334155;
            --text-muted: #64748b;
            --accent-primary: #2563eb; /* Slightly darker blue */
            --accent-primary-dark: #1d4ed8;
            --accent-primary-soft: #dbeafe;
            --success-soft: #dcfce7;
            --success-text: #166534;
            --radius-xs: 8px;
            --radius-sm: 10px;
            --radius-md: 14px;
            --radius-lg: 18px;
            --space-1: 0.3rem;
            --space-2: 0.55rem;
            --space-3: 0.8rem;
            --space-4: 1rem;
            --space-5: 1.25rem;
            --space-6: 1.6rem;
            --space-7: 2rem;
            --shadow-soft: 0 8px 24px rgba(15, 23, 42, 0.06);
            --shadow-medium: 0 14px 38px rgba(15, 23, 42, 0.1);
            --shadow-focus: 0 0 0 3px rgba(37, 99, 235, 0.2);
            --font-family: 'IBM Plex Sans', sans-serif;
        }

        body {
            font-family: var(--font-family);
        }

        .stApp {
            background: var(--bg-page);
            color: var(--text-primary);
            font-family: var(--font-family);
        }
        .stMainBlockContainer {
            max-width: 1360px;
            padding-top: 1.15rem;
            padding-bottom: 2.35rem;
        }
        h1, h2, h3, h4 {
            font-family: var(--font-family);
            color: var(--text-primary);
            letter-spacing: -0.01em;
        }
        h2 {
            font-size: 1.65rem; /* Slightly larger */
            font-weight: 700;
            line-height: 1.25;
            margin-bottom: var(--space-2);
        }
        h3 {
            font-size: 1.15rem; /* Slightly larger */
            font-weight: 600; /* Slightly lighter */
            line-height: 1.35;
            margin-top: var(--space-5);
            margin-bottom: var(--space-3);
        }
        p, li, .stMarkdown, .stCaption {
            font-family: var(--font-family);
            color: var(--text-secondary);
            line-height: 1.6; /* Increased line height */
            font-size: 0.96rem; /* Slightly smaller for body text */
        }
        .stCaption {
            color: var(--text-muted);
            font-size: 0.88rem; /* Slightly smaller */
        }
        .hero-card {
            padding: var(--space-6) var(--space-6);
            border-radius: var(--radius-lg);
            background: linear-gradient(160deg, #ffffff 0%, #f8fbff 100%);
            border: 1px solid var(--border-subtle);
            box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08);
            margin-bottom: var(--space-6);
        }
        .hero-kicker {
            display: inline-flex;
            align-items: center;
            padding: 0.26rem 0.65rem;
            border-radius: 999px;
            background: var(--surface-accent);
            color: #1d4ed8;
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            text-transform: uppercase;
            margin-bottom: 0.55rem;
        }
        .subtle-text {
            color: var(--text-muted);
            font-size: 0.98rem;
            max-width: 74ch;
        }
        .hero-list {
            margin: var(--space-4) 0 0 1.15rem;
            color: var(--text-secondary);
            line-height: 1.6;
        }
        .hero-footnote {
            margin-top: var(--space-4);
            padding-top: var(--space-3);
            border-top: 1px solid #e2e8f0;
            font-size: 0.92rem;
            color: var(--text-secondary);
        }
        .kpi-intro {
            margin: 0.15rem 0 0.4rem 0;
            color: var(--text-muted);
            font-size: 0.9rem;
        }
        .generated-item {
            border: 1px solid var(--border-subtle);
            border-left: 4px solid var(--accent-primary);
            border-radius: var(--radius-sm);
            background: var(--surface-secondary);
            padding: 0.68rem 0.9rem;
            margin-bottom: var(--space-2);
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        .status-chip {
            display: inline-block;
            padding: 0.28rem 0.66rem;
            border-radius: 999px;
            background: var(--surface-muted);
            color: var(--text-secondary);
            font-size: 0.77rem;
            font-weight: 700;
            letter-spacing: 0.01em;
        }
        .summary-preview-card {
            border: 1px solid var(--border-strong);
            border-left: 5px solid var(--accent-primary);
            border-radius: var(--radius-md);
            background: var(--surface-primary);
            padding: var(--space-5);
            margin-top: var(--space-1);
            box-shadow: var(--shadow-soft);
        }
        .highlights-card {
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
            padding: var(--space-4);
            box-shadow: var(--shadow-soft);
        }
        .keypoint-card {
            border: 1px solid #dbeafe;
            border-radius: var(--radius-sm);
            background: var(--surface-secondary);
            padding: 0.72rem 0.9rem;
            margin-bottom: var(--space-2);
            color: var(--text-primary);
        }
        .timeline-panel {
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            background: var(--surface-primary);
            padding: var(--space-5);
            box-shadow: var(--shadow-soft);
        }
        .timeline-item {
            display: flex;
            align-items: flex-start;
            gap: var(--space-2);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-sm);
            background: var(--surface-primary);
            padding: 0.68rem 0.82rem;
            margin-bottom: 0.42rem;
            color: var(--text-primary);
            transition: all 0.2s ease;
        }
        .timeline-item.current {
            border-color: #93c5fd;
            background: var(--surface-accent);
            box-shadow: 0 6px 18px rgba(37, 99, 235, 0.14);
        }
        .timeline-dot {
            width: 1.4rem;
            height: 1.4rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            background: var(--success-soft);
            color: var(--success-text);
            font-size: 0.8rem;
            font-weight: 700;
            flex-shrink: 0;
        }
        .timeline-item.current .timeline-dot {
            background: var(--accent-primary-soft);
            color: #1d4ed8;
        }
        .timeline-text {
            flex: 1;
            min-width: 0;
            line-height: 1.4;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: break-word;
        }
        .snapshot-citation-link {
            position: relative;
            font-weight: 600;
            color: var(--accent-primary);
            text-decoration: none;
            border-bottom: 1px dashed rgba(37, 99, 235, 0.55);
        }
        .snapshot-citation-link:hover {
            color: var(--accent-primary-dark);
            border-bottom-color: var(--accent-primary-dark);
        }
        .snapshot-citation-link::after {
            content: attr(data-preview);
            position: absolute;
            left: 50%;
            transform: translateX(-50%);
            bottom: calc(100% + 0.3rem);
            min-width: 220px;
            max-width: 380px;
            padding: 0.45rem 0.55rem;
            border-radius: var(--radius-sm);
            background: #0f172a;
            color: #f8fafc;
            border: 1px solid var(--border-strong);
            font-size: 0.75rem;
            line-height: 1.35;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.15s ease, visibility 0.15s ease;
            pointer-events: none;
            z-index: 25;
            white-space: normal;
            word-break: break-word;
            box-shadow: var(--shadow-medium);
        }
        .snapshot-citation-link:hover::after {
            opacity: 1;
            visibility: visible;
        }

        .report-viewer-modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background-color: rgba(0, 0, 0, 0.7);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }

        .report-viewer-modal-content {
            background: var(--surface-primary);
            border-radius: var(--radius-lg);
            width: 90%;
            height: 90%;
            display: flex;
            flex-direction: column;
            position: relative;
            overflow: hidden;
        }

        .report-viewer-modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: var(--space-4) var(--space-5);
            border-bottom: 1px solid var(--border-subtle);
        }

        .report-viewer-modal-body {
            flex-grow: 1;
            overflow-y: auto;
            padding: var(--space-4) var(--space-5);
        }

        .report-viewer-close-button {
            background: none;
            border: none;
            font-size: 1.5rem;
            cursor: pointer;
            color: var(--text-muted);
        }

        .report-viewer-close-button:hover {
            color: var(--text-primary);
        }
        .section-shell {
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            background: var(--surface-primary);
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
            padding: var(--space-5) var(--space-6);
            margin-bottom: var(--space-5);
        }
        .snapshot-shell {
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            background: var(--surface-primary);
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
            padding: var(--space-5) var(--space-6);
            margin-top: var(--space-4);
        }
        .download-shell {
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            background: var(--surface-primary);
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
            padding: var(--space-6);
            margin-top: var(--space-4);
        }
        .download-heading {
            margin-top: 0;
            margin-bottom: var(--space-1);
        }
        [data-testid="stMetric"] {
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            background: linear-gradient(180deg, #ffffff 0%, #f9fbff 100%);
            box-shadow: var(--shadow-soft);
            padding: 0.8rem 0.95rem;
            min-height: 7rem;
        }
        [data-testid="stMetricLabel"] {
            color: var(--text-muted);
            font-weight: 600;
            letter-spacing: 0.01em;
        }
        [data-testid="stMetricValue"] {
            color: var(--text-primary);
            font-size: 1.12rem;
            font-weight: 700;
            line-height: 1.22;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.25rem;
            background: #eef2ff;
            border-radius: 12px;
            padding: 0.25rem;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 9px;
            color: var(--text-secondary);
            font-weight: 600;
            letter-spacing: 0.01em;
            padding: 0.35rem 0.7rem;
        }
        .stTabs [aria-selected="true"] {
            background: #ffffff;
            color: #1e3a8a;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.07);
        }
        .stButton > button,
        .stDownloadButton > button {
            border-radius: 10px;
            border: 1px solid var(--accent-primary);
            font-weight: 600;
            letter-spacing: 0.01em;
            transition: all 0.2s ease;
            color: var(--accent-primary);
            background: transparent;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: var(--accent-primary-dark);
            color: var(--accent-primary-dark);
        }
        .stButton > button[kind="primary"],
        .stDownloadButton > button[kind="primary"] {
            background: linear-gradient(135deg, var(--accent-primary) 0%, var(--accent-primary-dark) 100%);
            border: 1px solid var(--accent-primary-dark);
            box-shadow: 0 8px 20px rgba(37, 99, 235, 0.25);
            color: #ffffff !important;
        }
        .stButton > button[kind="primary"] *,
        .stDownloadButton > button[kind="primary"] * {
            color: #ffffff !important;
        }
        .stButton > button[kind="primary"]:hover,
        .stDownloadButton > button[kind="primary"]:hover {
            filter: brightness(1.03);
            transform: translateY(-1px);
        }
        .stButton > button:focus-visible,
        .stDownloadButton > button:focus-visible {
            box-shadow: var(--shadow-focus);
            outline: none;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
            border-right: 1px solid var(--border-subtle);
        }
        [data-testid="stSidebar"] .stSelectbox,
        [data-testid="stSidebar"] .stTextArea {
            margin-bottom: 0.32rem;
        }
        .status-metric-card {
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            background: linear-gradient(180deg, #ffffff 0%, #f9fbff 100%);
            box-shadow: 0 6px 20px rgba(15, 23, 42, 0.06);
            padding: 0.8rem 0.95rem;
            min-height: 7rem;
            display: flex;
            flex-direction: column;
            justify-content: flex-start;
        }
        .immersive-view-shell {
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-lg);
            background: var(--surface-primary);
            box-shadow: 0 16px 36px rgba(15, 23, 42, 0.1);
            padding: var(--space-5);
            margin-top: var(--space-4);
            margin-bottom: var(--space-5);
        }
        .immersive-view-sub {
            color: var(--text-muted);
            margin-top: -0.25rem;
            margin-bottom: var(--space-3);
        }
        .status-metric-label {
            color: var(--text-muted);
            font-weight: 600;
            letter-spacing: 0.01em;
            font-size: 0.87rem;
            margin-bottom: 0.5rem;
        }
        .status-metric-value {
            color: var(--text-primary);
            font-size: 1.12rem;
            font-weight: 700;
            line-height: 1.22;
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
        }
        .status-spinner {
            width: 0.9rem;
            height: 0.9rem;
            border-radius: 999px;
            border: 2px solid rgba(37, 99, 235, 0.22);
            border-top-color: #2563eb;
            animation: status-spin 0.85s linear infinite;
            flex-shrink: 0;
        }
        @keyframes status-spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
    </style>
""", unsafe_allow_html=True)

# --- Helper Functions ---

# --- Helper Functions ---
@st.cache_resource(show_spinner=False)
def get_agent_class():
    """Lazily import AnalystIQ to keep initial page render responsive."""
    from agent import AnalystIQ
    return AnalystIQ


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
    report_type: str,
    custom_instruction: str,
    progress_queue: Queue,
    stop_event: threading.Event,
) -> None:
    """Run report generation in a background thread."""

    def update_ui(payload: dict) -> None:
        progress_queue.put({"type": "progress", "payload": payload})

    try:
        report_label = REPORT_TYPE_LABELS.get(report_type, "Investment Report")
        update_ui({"message": f"⚙️ Initializing {report_label} engine..."})
        AgentInvest = get_agent_class()
        agent = AgentInvest(verbose_agent=False)
        asyncio.run(
            agent.run(
                ticker=ticker,
                report_type=report_type,
                progress_callback=update_ui,
                custom_instruction=custom_instruction,
                stop_event=stop_event,
            )
        )
        report_slug = "CreditAnalysis" if report_type == "credit" else "AnalystIQ"
        if stop_event.is_set():
            progress_queue.put({"type": "stopped"})
        else:
            progress_queue.put(
                {
                    "type": "completed",
                    "report_type": report_type,
                    "pdf_path": f"generated_reports/{ticker}_{report_slug}_Report.pdf",
                    "md_path": f"generated_reports/{ticker}_{report_slug}_Report.md",
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
        "opening_section_preview": "",
        "key_points": [],
        "report_md_path": "",
        "ppt_path": "",
        "ppt_ready": False,
        "ppt_error": None,
        "is_generating_ppt": False,
        "company_name": "",
        "pdf_in_progress": False,
        "selected_report_type": "investment",
        "last_selected_report_type": None,
        "is_report_viewer_open": False,
        "report_view_ready": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def get_gmt8_timestamp() -> str:
    """Return current timestamp in GMT+8."""
    return datetime.now(GMT_PLUS_8).strftime("%Y-%m-%d %H:%M")


def _build_reference_map(markdown_text: str) -> dict[str, dict[str, str]]:
    refs: dict[str, dict[str, str]] = {}
    pattern = r"\*\*\[(\d+)\]\*\*\s*(?:\((.*?)\))?\s*\[link\]\((https?://[^)]+)\)"
    for number, title, url in re.findall(pattern, markdown_text):
        parsed = urllib.parse.urlparse(url.strip())
        domain = parsed.netloc.removeprefix("www.")
        refs[number] = {
            "url": url.strip(),
            "title": (title or url).strip(),
            "domain": domain,
        }
    return refs


def _decorate_snapshot_citations(snapshot_markdown: str, report_markdown: str) -> str:
    if not snapshot_markdown.strip():
        return snapshot_markdown
    references = _build_reference_map(report_markdown)
    if not references:
        return snapshot_markdown

    def _replace(match: re.Match[str]) -> str:
        ref_num = match.group(1)
        ref_data = references.get(ref_num)
        if not ref_data:
            return match.group(0)
        title = html.escape(ref_data["title"])
        domain = html.escape(ref_data.get("domain", ""))
        preview = f"{title} ({domain})" if domain else title
        preview_attr = html.escape(preview, quote=True)
        url = html.escape(ref_data["url"], quote=True)
        return (
            f'<a href="{url}" class="snapshot-citation-link" '
            f'data-preview="{preview_attr}" target="_blank" rel="noopener noreferrer">[{ref_num}]</a>'
        )

    return re.sub(r"\[(\d+)\]", _replace, snapshot_markdown)

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
                if "opening section extracted" in message_lower and data:
                    st.session_state.opening_section_preview = str(data).strip()
                if "key bullets extracted" in message_lower and data:
                    if isinstance(data, list):
                        st.session_state.key_points = [str(item).strip() for item in data if str(item).strip()]
                    else:
                        st.session_state.key_points = [str(data).strip()] if str(data).strip() else []
                if "markdown report saved" in message_lower:
                    md_path = str(data).strip() if data else ""
                    if md_path:
                        st.session_state.report_md_path = md_path
                    if st.session_state.report_md_path and os.path.exists(st.session_state.report_md_path):
                        st.session_state.report_view_ready = True
                if "identified company" in message_lower and data:
                    st.session_state.company_name = str(data).strip()
                if "using cached company name" in message_lower and data:
                    st.session_state.company_name = str(data).strip()
            elif event_type == "completed":
                st.session_state.report_generated = True
                st.session_state.run_status = "Completed"
                st.session_state.selected_report_type = event.get("report_type", st.session_state.selected_report_type)
                st.session_state.pdf_path = event.get("pdf_path", "")
                st.session_state.report_md_path = event.get("md_path", "")
                st.session_state.report_view_ready = bool(
                    st.session_state.report_md_path and os.path.exists(st.session_state.report_md_path)
                )
                st.session_state.pdf_in_progress = False
                st.session_state.run_error = None
                st.session_state.pending_error = None
            elif event_type == "stopped":
                st.session_state.report_generated = False
                st.session_state.run_status = "Idle"
                st.session_state.run_error = None
                st.session_state.pending_error = None
                st.session_state.opening_section_preview = ""
                st.session_state.executive_summary_preview = ""
                st.session_state.key_points = []
                st.session_state.report_md_path = ""
                st.session_state.report_view_ready = False
                st.session_state.ppt_path = ""
                st.session_state.ppt_ready = False
                st.session_state.ppt_error = None
                st.session_state.is_generating_ppt = False
                st.session_state.company_name = ""
                st.session_state.pdf_in_progress = False
                st.session_state.is_report_viewer_open = False
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
      <span class="hero-kicker">Institutional workflow</span>
      <h2 style="margin:0;">AnalystIQ Studio</h2>
      <p class="subtle-text" style="margin:0.4rem 0 0 0;">
        Built for analyst teams to move from ticker selection to decision-ready materials across investment and credit workflows.
      </p>
      <ul class="hero-list">
        <li><b>Dual report modes:</b> Generate either an <b>Investment Report</b> or a <b>Credit Analysis Report</b> for the selected company.</li>
        <li><b>Decision-ready insights:</b> Review executive summary and key highlights in-app before exporting deliverables.</li>
        <li><b>Editable presentation export:</b> Create and download a <b>.pptx</b> deck (up to 10 slides) for internal review meetings.</li>
      </ul>
      <p class="hero-footnote">
        <b>How to navigate:</b> Select a ticker and report type in the sidebar, click <b>Generate Report</b>, follow the <b>Research Journey</b>,
        review the <b>Report Snapshot</b>, then download the PDF and optional editable PowerPoint.
      </p>
    </div>
    """, unsafe_allow_html=True)

    st.sidebar.markdown("<h2 style='margin-bottom:0;'>AnalystIQ Studio</h2>", unsafe_allow_html=True)
    st.sidebar.markdown("""<p style='font-size:0.9rem; color:var(--text-muted); margin-bottom: 1.5rem;'>Generate comprehensive investment reports.</p>""", unsafe_allow_html=True)

    st.sidebar.markdown("### Report Configuration")
    with st.sidebar.container(border=True):
        st.markdown("**Ticker Selection**")
        if not warmup_ok:
            st.caption("Preparing report runtime components...")
        selected_ticker = st.selectbox("Select a Stock Ticker:", TICKERS, label_visibility="collapsed")
        report_type_label = st.selectbox(
            "Report Type",
            list(REPORT_TYPE_OPTIONS.keys()),
            index=0,
            help="Choose between investment and credit analysis report generation modes.",
        )
        selected_report_type = REPORT_TYPE_OPTIONS[report_type_label]
    
    st.sidebar.markdown("### Customization")
    with st.sidebar.expander("Advanced Options", expanded=True):
        custom_instruction_input = st.text_area(
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
        st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True) # Add spacing
        presentation_style = st.selectbox(
            "Presentation Style",
            ["Institutional Light", "Executive Dark", "Minimal Clean"],
            index=0,
            help="Choose the visual style for the editable PowerPoint deck.",
        )

    if st.session_state.is_running:
        with st.sidebar.container(border=True):
            st.markdown("**Report Generation Status**")
            st.info("Report generation is running...")
            if st.sidebar.button("Stop Report", type="secondary"):
                if st.session_state.stop_event is not None:
                    st.session_state.stop_event.set()
                    st.session_state.progress_log.append("🛑 Stop request received. Waiting for safe termination...")
            st.progress(min(1.0, len(st.session_state.progress_log) / 20)) # Assuming max 20 steps for progress bar

    if st.session_state.last_selected_ticker is None:
        st.session_state.last_selected_ticker = selected_ticker
    if st.session_state.last_selected_report_type is None:
        st.session_state.last_selected_report_type = selected_report_type
    elif (
        (
            selected_ticker != st.session_state.last_selected_ticker
            or selected_report_type != st.session_state.last_selected_report_type
        )
        and not st.session_state.is_running
    ):
        st.session_state.last_selected_ticker = selected_ticker
        st.session_state.last_selected_report_type = selected_report_type
        st.session_state.selected_report_type = selected_report_type
        st.session_state.run_status = "Idle"
        st.session_state.report_generated = False
        st.session_state.pdf_path = ""
        st.session_state.progress_log = []
        st.session_state.generated_data = {}
        st.session_state.custom_instruction_feedback = None
        st.session_state.run_error = None
        st.session_state.pending_error = None
        st.session_state.opening_section_preview = ""
        st.session_state.executive_summary_preview = ""
        st.session_state.key_points = []
        st.session_state.report_md_path = ""
        st.session_state.report_view_ready = False
        st.session_state.ppt_path = ""
        st.session_state.ppt_ready = False
        st.session_state.ppt_error = None
        st.session_state.is_generating_ppt = False
        st.session_state.company_name = ""
        st.session_state.pdf_in_progress = False
        st.session_state.is_report_viewer_open = False

    generation_time = get_gmt8_timestamp()
    st.markdown("<p class='kpi-intro'>Live run diagnostics and generation status</p>", unsafe_allow_html=True)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Selected Ticker", selected_ticker)
    if st.session_state.company_name:
        company_words = st.session_state.company_name.split()
        display_company = " ".join(company_words[:2])
    else:
        display_company = "Detecting company..." if st.session_state.is_running else "Not started"
    m2.metric("Company", display_company)
    with m3:
        status_placeholder = st.empty()

    def render_status_metric() -> None:
        status_value = html.escape(st.session_state.run_status)
        spinner_html = "<span class='status-spinner' aria-hidden='true'></span>" if st.session_state.is_running else ""
        status_placeholder.markdown(
            (
                "<div class='status-metric-card'>"
                "<div class='status-metric-label'>Report Status</div>"
                f"<div class='status-metric-value'>{spinner_html}<span>{status_value}</span></div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

    render_status_metric()
    m4.metric("Report Type", REPORT_TYPE_LABELS.get(selected_report_type, "Investment Report"))

    if st.session_state.custom_instruction_feedback:
            status, note = st.session_state.custom_instruction_feedback
            if status == "accepted":
                st.sidebar.success(f"Instruction accepted: {note}")
            elif status == "ignored":
                st.sidebar.warning(f"Instruction ignored: {note}. Reason: The instruction was deemed irrelevant or unsafe by the LLM.")

    def render_dynamic_sections() -> None:
        st.markdown("<div class='section-shell'>", unsafe_allow_html=True)
        snapshot_ready = bool(st.session_state.opening_section_preview.strip()) or bool(st.session_state.key_points)
        with st.expander("Storyline Outline", expanded=not snapshot_ready):
            structure = st.session_state.generated_data.get("structure", [])
            if structure:
                for section in structure:
                    st.markdown(
                        f"<div class='generated-item'>{section}</div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("Your report storyline will appear once planning is completed.")

        with st.expander("Market Research Focus", expanded=not snapshot_ready):
            web_queries = st.session_state.generated_data.get("web_queries", [])
            for query in web_queries:
                st.markdown(f"<div class='generated-item'>{query}</div>", unsafe_allow_html=True)
            if not web_queries:
                st.caption("Market research themes will appear here.")

        with st.expander("Financial Analysis Focus", expanded=not snapshot_ready):
            financial_queries = st.session_state.generated_data.get("financial_queries", [])
            for query in financial_queries:
                st.markdown(
                    f"<div class='generated-item'>{query['query']} ({query['ticker']})</div>",
                    unsafe_allow_html=True,
                )
            if not financial_queries:
                st.caption("Financial analysis themes will appear here.")
        st.markdown("</div>", unsafe_allow_html=True)

    def render_research_journey_panel() -> None:
        st.markdown("<div class='timeline-panel'>", unsafe_allow_html=True)
        st.markdown("### AnalystIQ Reasoning")

        can_view_report = (
            st.session_state.report_view_ready
            and bool(st.session_state.report_md_path)
            and os.path.exists(st.session_state.report_md_path)
        )
        viewer_col1, viewer_col2 = st.columns(2)
        with viewer_col1:
            if st.button(
                "View Report",
                type="primary" if can_view_report else "secondary",
                disabled=not can_view_report,
                help=None if can_view_report else "Generate and complete the report first.",
                key="view_report_button"
            ):
                st.session_state.is_report_viewer_open = True
        with viewer_col2:
            if st.button(
                "Close Viewer",
                type="secondary",
                disabled=not st.session_state.is_report_viewer_open,
                key="close_report_button"
            ):
                st.session_state.is_report_viewer_open = False

        if not st.session_state.progress_log:
            st.info("Choose your ticker and click `Generate Report` to begin.")
            st.markdown("</div>", unsafe_allow_html=True)
            return

        with st.expander("View Activity Timeline", expanded=True):
            with st.container(height=360, border=False):
                for i, log in enumerate(st.session_state.progress_log):
                    is_current = i == len(st.session_state.progress_log) - 1 and st.session_state.is_running
                    item_class = "timeline-item current" if is_current else "timeline-item"
                    safe_log = html.escape(str(log))
                    icon = "🚀" if "starting analysis" in safe_log.lower() else \
                           "📝" if "generating content" in safe_log.lower() else \
                           "📄" if "executive summary extracted" in safe_log.lower() else \
                           "📊" if "financial data queried" in safe_log.lower() else \
                           "🌐" if "web search queries" in safe_log.lower() else \
                           "✅" if "pdf report saved" in safe_log.lower() else \
                           "🛑" if "stop request received" in safe_log.lower() else \
                           "⚙️" if "initializing research engine" in safe_log.lower() else \
                           "🧠" if "analyzing market trends" in safe_log.lower() else \
                           "✍️" if "writing report" in safe_log.lower() else \
                           "✨" if "preparing highlights" in safe_log.lower() else \
                           "📦" if "converting report to pdf" in safe_log.lower() else \
                           "⏳" if is_current else "✔️"
                    st.markdown(
                        f"<div class='{item_class}'><span class='timeline-dot'>{icon}</span><span class='timeline-text'>{safe_log}</span></div>",
                        unsafe_allow_html=True,
                    )
        st.markdown("</div>", unsafe_allow_html=True)

    def render_investment_snapshot() -> None:
        has_summary = bool(st.session_state.opening_section_preview.strip())
        has_points = bool(st.session_state.key_points)
        if not has_summary and not has_points and not st.session_state.report_generated:
            return

        st.markdown("<div class='snapshot-shell'>", unsafe_allow_html=True)
        st.markdown("### Investment Snapshot")
        col1, col2 = st.columns([0.6, 0.4])

        with col1:
            with st.container(border=True):
                st.markdown("**Investment Brief**")
                if has_summary:
                    report_markdown = load_report_markdown(st.session_state.report_md_path)
                    decorated_brief = _decorate_snapshot_citations(
                        st.session_state.opening_section_preview,
                        report_markdown,
                    )
                    st.markdown(decorated_brief, unsafe_allow_html=True)
                else:
                    st.info("Your investment brief will appear shortly.")

        with col2:
            with st.container(border=True):
                st.markdown("**Decision Highlights**")
                if has_points:
                    for idx, point in enumerate(st.session_state.key_points[:5], start=1):
                        safe_point = html.escape(point)
                        st.markdown(
                            f"<div class='keypoint-card'><b>{idx}.</b> {safe_point}</div>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.info("Top highlights will appear once extraction is complete.")
        st.markdown("</div>", unsafe_allow_html=True)

    def render_report_viewer_modal() -> None:
        if not st.session_state.is_report_viewer_open:
            return

        report_markdown = load_report_markdown(st.session_state.report_md_path)
        if not report_markdown:
            st.warning("Report markdown could not be loaded for rendering.")
            return

        report_label = REPORT_TYPE_LABELS.get(st.session_state.selected_report_type, "Report")
        viewer_html = build_report_viewer_html(report_markdown, report_label=report_label)
        html_bytes = viewer_html.encode("utf-8")
        data_uri = "data:text/html;base64," + base64.b64encode(html_bytes).decode("ascii")

        st.markdown("<div class='immersive-view-shell'>", unsafe_allow_html=True)
        header_col, action_col = st.columns([0.82, 0.18])
        with header_col:
            st.markdown("### Report Viewer")
            st.markdown(
                f"<p class='immersive-view-sub'>{report_label} | premium reading mode</p>",
                unsafe_allow_html=True,
            )
        with action_col:
            st.markdown("<div style='height:0.8rem;'></div>", unsafe_allow_html=True)
            if st.button("Exit Viewer", key="close_full_report_viewer_btn", type="secondary"):
                st.session_state.is_report_viewer_open = False
                st.rerun()

        st.iframe(data_uri, height=1020)
        st.markdown("</div>", unsafe_allow_html=True)


    if st.sidebar.button("Generate Report", type="primary", disabled=st.session_state.is_running):
        report_label = REPORT_TYPE_LABELS.get(selected_report_type, "Investment Report")
        with st.spinner(f"Generating {report_label.lower()}..."):
            st.session_state.report_generated = False
        st.session_state.pdf_path = ""
        st.session_state.progress_log = []
        st.session_state.generated_data = {}
        st.session_state.is_running = True
        st.session_state.run_status = "Running"
        st.session_state.custom_instruction_feedback = None
        st.session_state.run_error = None
        st.session_state.pending_error = None
        st.session_state.opening_section_preview = ""
        st.session_state.executive_summary_preview = ""
        st.session_state.key_points = []
        st.session_state.report_md_path = ""
        st.session_state.report_view_ready = False
        st.session_state.ppt_path = ""
        st.session_state.ppt_ready = False
        st.session_state.ppt_error = None
        st.session_state.is_generating_ppt = False
        st.session_state.company_name = ""
        st.session_state.pdf_in_progress = False
        st.session_state.is_report_viewer_open = False
        st.session_state.last_selected_ticker = selected_ticker
        st.session_state.selected_report_type = selected_report_type
        st.session_state.last_selected_report_type = selected_report_type
        st.session_state.progress_queue = Queue()
        st.session_state.stop_event = threading.Event()
        render_status_metric()
        worker = threading.Thread(
            target=run_report_worker,
            args=(
                selected_ticker,
                selected_report_type,
                custom_instruction_input,
                st.session_state.progress_queue,
                st.session_state.stop_event,
            ),
            daemon=True,
        )
        st.session_state.worker_thread = worker
        worker.start()
        st.rerun()

    report_download_ready = (
        st.session_state.report_generated
        and not st.session_state.is_running
        and bool(st.session_state.pdf_path)
        and os.path.exists(st.session_state.pdf_path)
    )
    report_download_data = b""
    report_download_name = "Credit_Analysis_Report.pdf" if st.session_state.selected_report_type == "credit" else "Investment_Report.pdf"
    report_size_text = ""
    if report_download_ready:
        report_download_name = os.path.basename(st.session_state.pdf_path)
        with open(st.session_state.pdf_path, "rb") as pdf_file:
            report_download_data = pdf_file.read()
        report_size = os.path.getsize(st.session_state.pdf_path) / 1024
        report_size_text = f"PDF size: {report_size:.1f} KB"

    st.markdown("</div>", unsafe_allow_html=True)

    # Moved download buttons to main content area
    st.markdown("<div class='download-shell'>", unsafe_allow_html=True)
    st.markdown("<h2 class='download-heading' style='margin-bottom: 0.75rem;'>Download Report & Presentation</h2>", unsafe_allow_html=True)
    download_col1, download_col2 = st.columns(2)

    with download_col1:
        report_download_ready = (
            st.session_state.report_generated
            and not st.session_state.is_running
            and bool(st.session_state.pdf_path)
            and os.path.exists(st.session_state.pdf_path)
        )
        report_download_data = b""
        report_download_name = "Credit_Analysis_Report.pdf" if st.session_state.selected_report_type == "credit" else "Investment_Report.pdf"
        report_size_text = ""
        if report_download_ready:
            report_download_name = os.path.basename(st.session_state.pdf_path)
            with open(st.session_state.pdf_path, "rb") as pdf_file:
                report_download_data = pdf_file.read()
            report_size = os.path.getsize(st.session_state.pdf_path) / 1024
            report_size_text = f"PDF size: {report_size:.1f} KB"

        st.download_button(
            label="Download Report (PDF)",
            data=report_download_data,
            file_name=report_download_name,
            mime="application/pdf",
            type="primary",
            disabled=not report_download_ready,
            help=None if report_download_ready else "Generate and complete the report first.",
        )
        if report_download_ready:
            st.caption(f"{report_size_text} | Generated (GMT+8): {get_gmt8_timestamp()}")

    with download_col2:
        st.markdown("### Presentation Export")
        st.caption(
            "Create an editable presentation deck. Available after report generation is complete."
        )
        if st.session_state.ppt_error:
            st.error(
                "Sorry, we could not generate your presentation this time. "
                "Please try again in a moment."
            )
            st.caption(st.session_state.ppt_error)

        report_is_ready = st.session_state.report_generated and not st.session_state.is_running
        if st.button(
            "Generate Presentation (PPTX)",
            type="primary",
            disabled=st.session_state.is_generating_ppt or not report_is_ready,
            help=None if report_is_ready else "Finish generating the report first.",
        ):
            report_slug = "CreditAnalysis" if st.session_state.selected_report_type == "credit" else "AnalystIQ"
            report_md_path = st.session_state.report_md_path or f"generated_reports/{selected_ticker}_{report_slug}_Report.md"
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

                        output_ppt_path = f"generated_reports/{selected_ticker}_AnalystIQ_Presentation.pptx"
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

        ppt_download_ready = (
            st.session_state.ppt_ready
            and bool(st.session_state.ppt_path)
            and os.path.exists(st.session_state.ppt_path)
        )
        ppt_download_data = b""
        ppt_download_name = "Investment_Presentation.pptx"
        ppt_size_text = ""
        if ppt_download_ready:
            ppt_download_name = os.path.basename(st.session_state.ppt_path)
            with open(st.session_state.ppt_path, "rb") as ppt_file:
                ppt_download_data = ppt_file.read()
            ppt_size = os.path.getsize(st.session_state.ppt_path) / 1024
            ppt_size_text = f"PPT size: {ppt_size:.1f} KB"

        st.download_button(
            label="Download Presentation (PPTX)",
            data=ppt_download_data,
            file_name=ppt_download_name,
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            type="primary",
            disabled=not ppt_download_ready,
            help=None if ppt_download_ready else "Generate the presentation first.",
        )
        if ppt_download_ready:
            st.caption(ppt_size_text)
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.run_error and not st.session_state.is_running:
        st.error(f"Report generation failed: {st.session_state.run_error}")

    if st.session_state.is_report_viewer_open:
        render_report_viewer_modal()
    else:
        left_content_col, right_timeline_col = st.columns([2.2, 1.1], gap="large")
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
        st.success("Your report package is ready.")
    elif st.session_state.report_generated and st.session_state.is_running:
        st.info("Finalizing report files...")

    if st.session_state.is_running:
        time.sleep(1)
        st.rerun()

    if st.session_state.is_report_viewer_open:
        st.info("Report viewer is open in immersive mode. Click `Exit Viewer` to return to the studio layout.")

if __name__ == "__main__":
    main()
