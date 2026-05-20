import asyncio
import html
import json
import os
import re
import threading
import urllib.parse
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent import AnalystIQ
from cache_manager import _create_redis_client
from ppt_export import build_professional_pptx
from report_viewer import build_report_viewer_html, load_report_markdown
from tickers import TICKERS
from utils import convert_report_to_pdf

REPORT_TYPE_OPTIONS = {
    "Investment Report": "investment",
    "Credit Analysis Report": "credit",
}

PRESENTATION_STYLES = [
    "Institutional Light",
    "Executive Dark",
    "Minimal Clean",
]
CREDIT_RATING_AGENCIES = ["Moody's", "Fitch", "S&P", "MSCI ESG"]

ARTIFACTS_DIR = Path(__file__).resolve().parent / "generated_reports"
FRONTEND_DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def infer_phase(message: str) -> str:
    lowered = message.lower()
    if "custom instruction" in lowered:
        return "instruction"
    if "report structure" in lowered:
        return "planning"
    if "gathering context" in lowered or "query" in lowered:
        return "research"
    if "section" in lowered:
        return "composition"
    if "executive summary" in lowered or "opening section" in lowered:
        return "synthesis"
    if "pdf" in lowered:
        return "export"
    if "error" in lowered or "failed" in lowered:
        return "error"
    return "status"


def report_slug(report_type: str) -> str:
    return "CreditAnalysis" if report_type == "credit" else "AnalystIQ"


def extract_reference_links(markdown_text: str) -> Dict[str, Dict[str, str]]:
    links: Dict[str, Dict[str, str]] = {}
    if not markdown_text:
        return links
    pattern = r"\*\*\[(\d+)\]\*\*\s*(?:\((.*?)\))?\s*\[link\]\((https?://[^)]+)\)"
    for number, title, url in re.findall(pattern, markdown_text):
        parsed = urllib.parse.urlparse(url.strip())
        domain = parsed.netloc.removeprefix("www.")
        links[number] = {
            "url": url.strip(),
            "title": (title or url).strip(),
            "domain": domain,
        }
    return links


class ReportJobRequest(BaseModel):
    ticker: str
    report_type: str = "investment"
    custom_instruction: Optional[str] = None
    pipeline: str = Field(default="v1", pattern="^(v1|v3)$")
    presentation_style: str = "Institutional Light"


CREDIT_RATING_YEAR_SPAN = 15


def _credit_year_options() -> Dict[str, Any]:
    current_year = datetime.now().year
    year_options = list(range(current_year, current_year - CREDIT_RATING_YEAR_SPAN, -1))
    return {
        "year_options": year_options,
        "default_start_year": current_year,
        "default_end_year": current_year,
    }


def _normalize_credit_year_range(
    start_year: Optional[int], end_year: Optional[int]
) -> tuple[int, int]:
    current_year = datetime.now().year
    min_year = current_year - CREDIT_RATING_YEAR_SPAN + 1
    focus_start = int(start_year or current_year)
    focus_end = int(end_year or focus_start)
    focus_start = max(min_year, min(current_year, focus_start))
    focus_end = max(min_year, min(current_year, focus_end))
    if focus_end < focus_start:
        focus_end = focus_start
    return focus_start, focus_end


def _credit_period_label(start_year: int, end_year: int) -> str:
    if start_year == end_year:
        return str(start_year)
    return f"{start_year}-{end_year}"


class CreditRatingJobRequest(BaseModel):
    ticker: str
    agencies: List[str] = Field(default_factory=lambda: CREDIT_RATING_AGENCIES[:3])
    start_year: Optional[int] = None
    end_year: Optional[int] = None


class JobCancelResponse(BaseModel):
    job_id: str
    status: str


@dataclass
class JobState:
    job_id: str
    ticker: str
    report_type: str
    custom_instruction: Optional[str]
    pipeline: str
    presentation_style: str
    status: str = "queued"
    phase: str = "queued"
    progress: int = 0
    created_at: str = field(default_factory=utc_iso)
    started_at: Optional[str] = None
    updated_at: str = field(default_factory=utc_iso)
    completed_at: Optional[str] = None
    error: Optional[str] = None
    company_name: Optional[str] = None
    final_report: Optional[str] = None
    opening_section_preview: Optional[str] = None
    executive_summary_preview: Optional[str] = None
    key_points: List[str] = field(default_factory=list)
    generated_data: Dict[str, Any] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    report_md_path: Optional[str] = None
    pdf_path: Optional[str] = None
    ppt_path: Optional[str] = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    event_queue: "Queue[Dict[str, Any]]" = field(default_factory=Queue)
    worker_thread: Optional[threading.Thread] = None

    def to_dict(self) -> Dict[str, Any]:
        reference_links: Dict[str, Dict[str, str]] = {}
        if self.report_md_path and os.path.exists(self.report_md_path):
            try:
                report_markdown = load_report_markdown(self.report_md_path)
                reference_links = extract_reference_links(report_markdown)
            except Exception:
                reference_links = {}
        return {
            "job_id": self.job_id,
            "ticker": self.ticker,
            "report_type": self.report_type,
            "custom_instruction": self.custom_instruction,
            "pipeline": self.pipeline,
            "presentation_style": self.presentation_style,
            "status": self.status,
            "phase": self.phase,
            "progress": self.progress,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "company_name": self.company_name,
            "opening_section_preview": self.opening_section_preview,
            "executive_summary_preview": self.executive_summary_preview,
            "key_points": self.key_points,
            "generated_data": self.generated_data,
            "reference_links": reference_links,
            "artifacts": {
                "markdown_ready": bool(self.report_md_path and os.path.exists(self.report_md_path)),
                "pdf_ready": bool(self.pdf_path and os.path.exists(self.pdf_path)),
                "ppt_ready": bool(self.ppt_path and os.path.exists(self.ppt_path)),
                "report_md_path": self.report_md_path,
                "pdf_path": self.pdf_path,
                "ppt_path": self.ppt_path,
            },
            "log_count": len(self.logs),
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, JobState] = {}
        self._lock = threading.Lock()

    def create(self, payload: ReportJobRequest) -> JobState:
        normalized_report_type = payload.report_type.lower().strip()
        if normalized_report_type not in ("investment", "credit"):
            raise HTTPException(status_code=400, detail="report_type must be 'investment' or 'credit'.")
        if payload.ticker not in TICKERS:
            raise HTTPException(status_code=400, detail="Unsupported ticker symbol.")
        if payload.presentation_style not in PRESENTATION_STYLES:
            raise HTTPException(status_code=400, detail="Unsupported presentation style.")

        job = JobState(
            job_id=str(uuid.uuid4()),
            ticker=payload.ticker,
            report_type=normalized_report_type,
            custom_instruction=(payload.custom_instruction or "").strip() or None,
            pipeline=payload.pipeline,
            presentation_style=payload.presentation_style,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> JobState:
        with self._lock:
            if job_id not in self._jobs:
                raise HTTPException(status_code=404, detail="Job not found.")
            return self._jobs[job_id]

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda item: item.created_at, reverse=True)
        return [job.to_dict() for job in jobs]


@dataclass
class CreditRatingJobState:
    job_id: str
    ticker: str
    agencies: List[str]
    start_year: int = 0
    end_year: int = 0
    status: str = "queued"
    phase: str = "queued"
    progress: int = 0
    created_at: str = field(default_factory=utc_iso)
    started_at: Optional[str] = None
    updated_at: str = field(default_factory=utc_iso)
    completed_at: Optional[str] = None
    error: Optional[str] = None
    company_name: Optional[str] = None
    logs: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    generated_data: Dict[str, Any] = field(default_factory=dict)
    reference_links: Dict[str, Dict[str, str]] = field(default_factory=dict)
    doc_path: Optional[str] = None
    pdf_path: Optional[str] = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    event_queue: "Queue[Dict[str, Any]]" = field(default_factory=Queue)
    worker_thread: Optional[threading.Thread] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "ticker": self.ticker,
            "agencies": self.agencies,
            "start_year": self.start_year,
            "end_year": self.end_year,
            "period_label": _credit_period_label(self.start_year, self.end_year),
            "status": self.status,
            "phase": self.phase,
            "progress": self.progress,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "company_name": self.company_name,
            "generated_data": self.generated_data,
            "reference_links": self.reference_links,
            "artifacts": {
                "doc_ready": bool(self.doc_path and os.path.exists(self.doc_path)),
                "pdf_ready": bool(self.pdf_path and os.path.exists(self.pdf_path)),
                "doc_path": self.doc_path,
                "pdf_path": self.pdf_path,
            },
            "log_count": len(self.logs),
        }


class CreditRatingJobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, CreditRatingJobState] = {}
        self._lock = threading.Lock()

    def create(self, payload: CreditRatingJobRequest) -> CreditRatingJobState:
        if payload.ticker not in TICKERS:
            raise HTTPException(status_code=400, detail="Unsupported ticker symbol.")
        agencies = [item for item in payload.agencies if item in CREDIT_RATING_AGENCIES]
        if not agencies:
            raise HTTPException(status_code=400, detail="At least one supported agency must be selected.")
        start_year, end_year = _normalize_credit_year_range(payload.start_year, payload.end_year)
        job = CreditRatingJobState(
            job_id=str(uuid.uuid4()),
            ticker=payload.ticker,
            agencies=agencies,
            start_year=start_year,
            end_year=end_year,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> CreditRatingJobState:
        with self._lock:
            if job_id not in self._jobs:
                raise HTTPException(status_code=404, detail="Credit rating job not found.")
            return self._jobs[job_id]

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda item: item.created_at, reverse=True)
        return [job.to_dict() for job in jobs]


store = JobStore()
credit_store = CreditRatingJobStore()
router = APIRouter()
app = FastAPI(title="AnalystIQ API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _append_event(job: JobState, event_type: str, payload: Dict[str, Any]) -> None:
    event = {
        "id": len(job.events),
        "type": event_type,
        "timestamp": utc_iso(),
        "payload": payload,
    }
    job.events.append(event)
    job.event_queue.put(event)
    job.updated_at = utc_iso()


def _append_credit_event(job: CreditRatingJobState, event_type: str, payload: Dict[str, Any]) -> None:
    event = {
        "id": len(job.events),
        "type": event_type,
        "timestamp": utc_iso(),
        "payload": payload,
    }
    job.events.append(event)
    job.event_queue.put(event)
    job.updated_at = utc_iso()


def _parse_markdown_table(table_markdown: str) -> Dict[str, Any]:
    lines = [
        line.strip()
        for line in (table_markdown or "").splitlines()
        if line.strip() and "|" in line
    ]
    if len(lines) < 2:
        return {"headers": [], "rows": []}

    def _parse_line(line: str) -> List[str]:
        return [cell.strip() for cell in line.strip("|").split("|") if cell.strip()]

    headers = _parse_line(lines[0])
    rows: List[List[str]] = []
    for line in lines[1:]:
        if re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?", line):
            continue
        parsed = _parse_line(line)
        if parsed:
            rows.append(parsed)
    return {"headers": headers, "rows": rows}


def _render_export_citations(text: str, reference_links: Dict[str, Dict[str, str]]) -> str:
    escaped = html.escape(text or "")

    def _replace(match: re.Match[str]) -> str:
        number = match.group(1)
        source = reference_links.get(number)
        if not source or not source.get("url"):
            return f"[{number}]"
        url = html.escape(source["url"], quote=True)
        return f'<a href="{url}">[{number}]</a>'

    with_links = re.sub(r"\[(\d+)\]", _replace, escaped)
    return with_links.replace("\n", "<br/>")


def _table_markdown_to_html(
    table_markdown: str,
    reference_links: Dict[str, Dict[str, str]],
) -> str:
    parsed = _parse_markdown_table(_strip_source_document_table_row(table_markdown))
    if not parsed["headers"]:
        return "<p>Matrix output unavailable.</p>"

    header_html = "".join(
        f'<th style="border:1px solid #cbd5e1;padding:8px;text-align:left;background:#f8fafc;">'
        f"{html.escape(header)}</th>"
        for header in parsed["headers"]
    )
    body_html = []
    for row in parsed["rows"]:
        if row and "source document" in str(row[0]).lower():
            continue
        cells = "".join(
            (
                '<td style="border:1px solid #cbd5e1;padding:8px;vertical-align:top;">'
                f"{_render_export_citations(cell, reference_links)}</td>"
            )
            for cell in row
        )
        body_html.append(f"<tr>{cells}</tr>")

    return (
        '<table style="border-collapse:collapse;width:100%;margin-top:8px;font-size:11pt;">'
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{''.join(body_html)}</tbody>"
        "</table>"
    )


def _strip_source_document_table_row(table_markdown: str) -> str:
    filtered_lines: List[str] = []
    for line in (table_markdown or "").splitlines():
        stripped = line.strip()
        if "|" in stripped:
            cells = [cell.strip() for cell in stripped.strip("|").split("|") if cell.strip()]
            if cells and "source document" in cells[0].lower():
                continue
        filtered_lines.append(line)
    return "\n".join(filtered_lines).strip()


def _write_credit_workspace_artifacts(job: CreditRatingJobState) -> None:
    paragraphs = job.generated_data.get("comparison_paragraphs", [])
    table_markdown = _strip_source_document_table_row(job.generated_data.get("comparison_table_markdown", ""))
    if not paragraphs and not table_markdown:
        return

    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    period_suffix = (
        f"_{job.start_year}"
        if job.start_year == job.end_year
        else f"_{job.start_year}_{job.end_year}"
    )
    doc_path = ARTIFACTS_DIR / f"{job.ticker}_CreditRatingWorkspace{period_suffix}.doc"
    pdf_path = ARTIFACTS_DIR / f"{job.ticker}_CreditRatingWorkspace{period_suffix}.pdf"
    company_name = job.company_name or job.ticker

    period_label = _credit_period_label(job.start_year, job.end_year)
    markdown_text = _build_credit_workspace_markdown(
        company_name=company_name,
        ticker=job.ticker,
        period_label=period_label,
        paragraphs=paragraphs,
        table_markdown=table_markdown,
        reference_links=job.reference_links,
    )

    with open(doc_path, "w", encoding="utf-8") as file:
        file.write(
            _build_credit_workspace_doc_html(
                company_name=company_name,
                ticker=job.ticker,
                period_label=period_label,
                paragraphs=paragraphs,
                table_markdown=table_markdown,
                reference_links=job.reference_links,
            )
        )
    job.doc_path = str(doc_path)

    try:
        pdf_success = asyncio.run(
            convert_report_to_pdf(
                markdown_text,
                str(pdf_path),
                company_name=company_name,
                report_title="Credit Rating Workspace Brief",
            )
        )
        if pdf_success and os.path.exists(pdf_path):
            job.pdf_path = str(pdf_path)
    except Exception:
        # Word export remains available even when PDF conversion fails.
        pass


def _build_credit_reference_links(cited_sources: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    links: Dict[str, Dict[str, str]] = {}
    for key, source in cited_sources.items():
        url = str((source or {}).get("url", "")).strip()
        if not url:
            continue
        title = str((source or {}).get("title", "")).strip() or url
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.removeprefix("www.")
        links[str(key)] = {
            "url": url,
            "title": title,
            "domain": domain,
        }
    return links


def _build_credit_workspace_markdown(
    *,
    company_name: str,
    ticker: str,
    period_label: str,
    paragraphs: List[str],
    table_markdown: str,
    reference_links: Dict[str, Dict[str, str]],
) -> str:
    lines: List[str] = [
        f"# Credit Rating Workspace Brief - {company_name} ({ticker})",
        f"**Rating focus period:** {period_label}",
        "",
        "## Comparison Narrative",
        "",
    ]
    if paragraphs:
        lines.extend(paragraphs)
        lines.append("")
    else:
        lines.extend(["Narrative was unavailable.", ""])

    lines.extend(["## Comparison Matrix", ""])
    lines.append(table_markdown.strip() if table_markdown.strip() else "_Matrix output unavailable._")
    lines.append("")

    if reference_links:
        lines.extend(["## References", ""])
        for key in sorted(reference_links.keys(), key=lambda item: int(item) if str(item).isdigit() else 10**9):
            source = reference_links[key]
            url = source.get("url", "")
            title = source.get("title", "") or url
            lines.append(f"**[{key}]** ({title}) [link]({url})")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _build_credit_workspace_doc_html(
    *,
    company_name: str,
    ticker: str,
    period_label: str,
    paragraphs: List[str],
    table_markdown: str,
    reference_links: Dict[str, Dict[str, str]],
) -> str:
    paragraph_html = "".join(
        f"<p style='margin:0 0 10px 0;line-height:1.5;'>{_render_export_citations(paragraph, reference_links)}</p>"
        for paragraph in paragraphs
        if paragraph.strip()
    ) or "<p>Narrative was unavailable.</p>"

    references_html = ""
    if reference_links:
        refs = []
        for key in sorted(reference_links.keys(), key=lambda item: int(item) if str(item).isdigit() else 10**9):
            source = reference_links[key]
            url = html.escape(source.get("url", ""))
            title = html.escape(source.get("title", "") or source.get("url", ""))
            refs.append(f"<li><strong>[{key}]</strong> ({title}) <a href='{url}'>{url}</a></li>")
        references_html = "<h2>References</h2><ul>" + "".join(refs) + "</ul>"

    table_html = _table_markdown_to_html(table_markdown, reference_links)
    return (
        "<html xmlns:o='urn:schemas-microsoft-com:office:office' "
        "xmlns:w='urn:schemas-microsoft-com:office:word' "
        "xmlns='http://www.w3.org/TR/REC-html40'>"
        "<head><meta charset='utf-8'>"
        "<style>"
        "body{font-family:Calibri,Arial,sans-serif;font-size:11pt;color:#0f172a;}"
        "h1{font-size:18pt;} h2{font-size:13pt;margin-top:18px;}"
        "table{border-collapse:collapse;}"
        "</style></head><body>"
        f"<h1>Credit Rating Workspace Brief - {html.escape(company_name)} ({html.escape(ticker)})</h1>"
        f"<p><strong>Rating focus period:</strong> {html.escape(period_label)}</p>"
        "<h2>Comparison Narrative</h2>"
        f"{paragraph_html}"
        "<h2>Comparison Matrix</h2>"
        f"{table_html}"
        f"{references_html}"
        "</body></html>"
    )


def _job_worker(job: JobState) -> None:
    job.status = "running"
    job.phase = "initializing"
    job.started_at = utc_iso()
    _append_event(job, "status", {"message": "Job started."})
    agent = AnalystIQ()

    def progress_callback(update: Any) -> None:
        if not isinstance(update, dict):
            return
        message = str(update.get("message", "")).strip() or "Status update"
        data = update.get("data")
        phase = infer_phase(message)
        job.phase = phase
        job.progress = min(95, job.progress + 2)
        log_entry = {
            "timestamp": utc_iso(),
            "phase": phase,
            "message": message,
            "data": data,
        }
        job.logs.append(log_entry)
        if isinstance(data, list):
            lowered_msg = message.lower()
            # Report structure
            if "report structure" in lowered_msg or "report outline" in lowered_msg or "storyline outline" in lowered_msg:
                job.generated_data["structure"] = [str(item) for item in data]
            # Web queries
            elif "web search queries" in lowered_msg or "web queries" in lowered_msg:
                job.generated_data["web_queries"] = [str(item) for item in data]
            # Financial queries
            elif "financial data queries" in lowered_msg or "financial queries" in lowered_msg:
                job.generated_data["financial_queries"] = data
            elif "key points" in lowered_msg or "key bullets" in lowered_msg:
                job.key_points = [str(point) for point in data][:5]
            # Shape-based fallback in case message wording changes
            elif data and all(isinstance(item, dict) for item in data):
                job.generated_data["financial_queries"] = data
            elif data and all(isinstance(item, str) for item in data):
                if "structure" not in job.generated_data:
                    job.generated_data["structure"] = data
                else:
                    job.generated_data["web_queries"] = data
        if isinstance(data, str):
            lowered = message.lower()
            if "opening section preview" in lowered or "opening section extracted" in lowered:
                job.opening_section_preview = data
            elif "executive summary preview" in lowered:
                job.executive_summary_preview = data
            elif "report markdown path" in lowered:
                job.report_md_path = data
            elif "pdf report saved" in lowered:
                job.pdf_path = data
            elif (
                "company name inferred" in lowered
                or "identified company" in lowered
                or "cached company name" in lowered
            ):
                job.company_name = data
            if data.strip().lower().endswith(".md"):
                job.report_md_path = data.strip()
            if data.strip().lower().endswith(".pdf"):
                job.pdf_path = data.strip()
        # Some progress lines include company name in the message itself.
        lowered_message = message.lower()
        if "identified company" in lowered_message and ":" in message:
            parsed_company = message.split(":", 1)[1].strip()
            if parsed_company:
                job.company_name = parsed_company
        elif "cached company name" in lowered_message and isinstance(data, str) and data.strip():
            job.company_name = data.strip()

        _append_event(job, "progress", log_entry)

    try:
        if job.pipeline == "v3":
            report = asyncio.run(
                agent.run_v3(
                    ticker=job.ticker,
                    progress_callback=progress_callback,
                    custom_instruction=job.custom_instruction,
                )
            )
            default_md = ARTIFACTS_DIR / f"{job.ticker}_AnalystIQ_Report_v3.md"
            default_pdf = ARTIFACTS_DIR / f"{job.ticker}_AnalystIQ_Report_v3.pdf"
        else:
            report = asyncio.run(
                agent.run(
                    ticker=job.ticker,
                    report_type=job.report_type,
                    progress_callback=progress_callback,
                    custom_instruction=job.custom_instruction,
                    stop_event=job.stop_event,
                )
            )
            slug = report_slug(job.report_type)
            default_md = ARTIFACTS_DIR / f"{job.ticker}_{slug}_Report.md"
            default_pdf = ARTIFACTS_DIR / f"{job.ticker}_{slug}_Report.pdf"

        if job.report_md_path is None and default_md.exists():
            job.report_md_path = str(default_md)
        if job.pdf_path is None and default_pdf.exists():
            job.pdf_path = str(default_pdf)

        job.final_report = report
        if job.stop_event.is_set():
            job.status = "cancelled"
            job.phase = "cancelled"
            _append_event(job, "status", {"message": "Job cancelled by user."})
        elif report:
            job.status = "completed"
            job.phase = "completed"
            job.progress = 100
            _append_event(job, "status", {"message": "Report generation completed."})
        else:
            job.status = "failed"
            job.phase = "error"
            job.error = "Agent returned no report content."
            _append_event(job, "error", {"message": job.error})
    except asyncio.CancelledError:
        job.status = "cancelled"
        job.phase = "cancelled"
        job.error = "Report generation cancelled by user."
        _append_event(job, "status", {"message": job.error})
    except Exception as exc:  # pragma: no cover
        detail = str(exc)
        # Tenacity wraps provider failures in RetryError; surface root cause.
        last_attempt = getattr(exc, "last_attempt", None)
        if last_attempt is not None:
            try:
                root = last_attempt.exception()
            except Exception:
                root = None
            if root is not None:
                detail = f"{type(root).__name__}: {root}"
        job.status = "failed"
        job.phase = "error"
        job.error = detail
        _append_event(job, "error", {"message": detail})
    finally:
        job.completed_at = utc_iso()
        job.updated_at = utc_iso()
        _append_event(job, "final", {"status": job.status})


def _credit_job_worker(job: CreditRatingJobState) -> None:
    job.status = "running"
    job.phase = "initializing"
    job.started_at = utc_iso()
    _append_credit_event(job, "status", {"message": "Credit rating job started."})
    agent = AnalystIQ()

    def progress_callback(update: Any) -> None:
        if not isinstance(update, dict):
            return
        message = str(update.get("message", "")).strip() or "Status update"
        data = update.get("data")
        phase = infer_phase(message)
        job.phase = phase
        job.progress = min(95, job.progress + 4)
        log_entry = {
            "timestamp": utc_iso(),
            "phase": phase,
            "message": message,
            "data": data,
        }
        job.logs.append(log_entry)
        lowered_message = message.lower()
        if isinstance(data, str) and (
            "identified company" in lowered_message or "company name" in lowered_message
        ):
            job.company_name = data
        if isinstance(data, list) and ("web search queries" in lowered_message or "queries" in lowered_message):
            job.generated_data["web_queries"] = [str(item) for item in data]
        _append_credit_event(job, "progress", log_entry)

    try:
        result = asyncio.run(
            agent.run_credit_rating_workspace(
                ticker=job.ticker,
                agencies=job.agencies,
                start_year=job.start_year,
                end_year=job.end_year,
                progress_callback=progress_callback,
                stop_event=job.stop_event,
            )
        )
        if job.stop_event.is_set():
            job.status = "cancelled"
            job.phase = "cancelled"
            _append_credit_event(job, "status", {"message": "Credit rating job cancelled by user."})
        elif result:
            job.company_name = result.get("company_name") or job.company_name
            job.generated_data = {
                "agencies": result.get("agencies", job.agencies),
                "web_queries": result.get("web_queries", []),
                "comparison_paragraphs": result.get("comparison_paragraphs", []),
                "comparison_table_markdown": result.get("comparison_table_markdown", ""),
            }
            job.reference_links = _build_credit_reference_links(result.get("cited_source_map", {}))
            job.generated_data["comparison_table_markdown"] = _strip_source_document_table_row(
                job.generated_data.get("comparison_table_markdown", "")
            )
            _write_credit_workspace_artifacts(job)
            if job.doc_path:
                _append_credit_event(job, "artifact", {"type": "doc", "path": job.doc_path})
            if job.pdf_path:
                _append_credit_event(job, "artifact", {"type": "pdf", "path": job.pdf_path})
            job.status = "completed"
            job.phase = "completed"
            job.progress = 100
            _append_credit_event(job, "status", {"message": "Credit rating workspace generation completed."})
        else:
            job.status = "failed"
            job.phase = "error"
            job.error = "Agent returned no credit workspace content."
            _append_credit_event(job, "error", {"message": job.error})
    except asyncio.CancelledError:
        job.status = "cancelled"
        job.phase = "cancelled"
        job.error = "Credit rating workspace generation cancelled by user."
        _append_credit_event(job, "status", {"message": job.error})
    except Exception as exc:  # pragma: no cover
        job.status = "failed"
        job.phase = "error"
        job.error = str(exc)
        _append_credit_event(job, "error", {"message": job.error})
    finally:
        job.completed_at = utc_iso()
        job.updated_at = utc_iso()
        _append_credit_event(job, "final", {"status": job.status})


def _sse_encode(event: Dict[str, Any]) -> str:
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"


@app.get("/health")
def health() -> Dict[str, Any]:
    cache_enabled = False
    if os.getenv("REDIS_URL") or os.getenv("REDIS_HOST"):
        try:
            redis_client = _create_redis_client()
            redis_client.ping()
            cache_enabled = True
        except Exception:
            cache_enabled = False
    return {"status": "ok", "cache_enabled": cache_enabled}


@router.get("/reports/options")
def report_options() -> Dict[str, Any]:
    return {
        "tickers": TICKERS,
        "report_type_options": REPORT_TYPE_OPTIONS,
        "presentation_styles": PRESENTATION_STYLES,
    }


@router.get("/credit-rating/options")
def credit_rating_options() -> Dict[str, Any]:
    return {
        "tickers": TICKERS,
        "agencies": CREDIT_RATING_AGENCIES,
        **_credit_year_options(),
    }


@router.get("/credit-rating/jobs")
def list_credit_jobs() -> List[Dict[str, Any]]:
    return credit_store.list()


@router.post("/credit-rating/jobs")
def create_credit_job(payload: CreditRatingJobRequest) -> Dict[str, Any]:
    job = credit_store.create(payload)
    worker = threading.Thread(target=_credit_job_worker, args=(job,), daemon=True)
    job.worker_thread = worker
    worker.start()
    return job.to_dict()


@router.get("/credit-rating/jobs/{job_id}")
def get_credit_job(job_id: str) -> Dict[str, Any]:
    return credit_store.get(job_id).to_dict()


@router.get("/credit-rating/jobs/{job_id}/events")
async def stream_credit_job_events(job_id: str, request: Request, from_event_id: int = 0) -> StreamingResponse:
    job = credit_store.get(job_id)
    last_event_id_header = request.headers.get("last-event-id")
    if last_event_id_header is not None:
        try:
            from_event_id = max(from_event_id, int(last_event_id_header) + 1)
        except ValueError:
            pass

    async def _generator():
        for event in job.events:
            if event["id"] >= from_event_id:
                yield _sse_encode(event)
        while True:
            if job.status in ("completed", "failed", "cancelled") and job.event_queue.empty():
                break
            try:
                event = job.event_queue.get_nowait()
                if event["id"] >= from_event_id:
                    yield _sse_encode(event)
            except Empty:
                await asyncio.sleep(0.5)

    return StreamingResponse(_generator(), media_type="text/event-stream")


@router.post("/credit-rating/jobs/{job_id}/cancel", response_model=JobCancelResponse)
def cancel_credit_job(job_id: str) -> JobCancelResponse:
    job = credit_store.get(job_id)
    if job.status not in ("running", "queued"):
        return JobCancelResponse(job_id=job_id, status=job.status)
    job.stop_event.set()
    return JobCancelResponse(job_id=job_id, status="cancelling")


@router.get("/credit-rating/jobs/{job_id}/artifacts/{artifact_type}")
def download_credit_artifact(job_id: str, artifact_type: str) -> FileResponse:
    job = credit_store.get(job_id)
    if artifact_type not in ("doc", "pdf"):
        raise HTTPException(status_code=404, detail="Unsupported artifact type.")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Export is available after generation completes.")
    _write_credit_workspace_artifacts(job)
    path_lookup = {
        "doc": job.doc_path,
        "pdf": job.pdf_path,
    }
    file_path = path_lookup[artifact_type]
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Artifact not found.")
    media_types = {
        "doc": "application/msword",
        "pdf": "application/pdf",
    }
    return FileResponse(file_path, media_type=media_types[artifact_type], filename=os.path.basename(file_path))


@router.get("/reports/jobs")
def list_jobs() -> List[Dict[str, Any]]:
    return store.list()


@router.post("/reports/jobs")
def create_job(payload: ReportJobRequest) -> Dict[str, Any]:
    job = store.create(payload)
    worker = threading.Thread(target=_job_worker, args=(job,), daemon=True)
    job.worker_thread = worker
    worker.start()
    return job.to_dict()


@router.get("/reports/jobs/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    return store.get(job_id).to_dict()


@router.get("/reports/jobs/{job_id}/events")
async def stream_job_events(job_id: str, request: Request, from_event_id: int = 0) -> StreamingResponse:
    job = store.get(job_id)
    last_event_id_header = request.headers.get("last-event-id")
    if last_event_id_header is not None:
        try:
            from_event_id = max(from_event_id, int(last_event_id_header) + 1)
        except ValueError:
            pass

    async def _generator():
        for event in job.events:
            if event["id"] >= from_event_id:
                yield _sse_encode(event)
        while True:
            if job.status in ("completed", "failed", "cancelled") and job.event_queue.empty():
                break
            try:
                event = job.event_queue.get_nowait()
                if event["id"] >= from_event_id:
                    yield _sse_encode(event)
            except Empty:
                await asyncio.sleep(0.5)

    return StreamingResponse(_generator(), media_type="text/event-stream")


@router.post("/reports/jobs/{job_id}/cancel", response_model=JobCancelResponse)
def cancel_job(job_id: str) -> JobCancelResponse:
    job = store.get(job_id)
    if job.status not in ("running", "queued"):
        return JobCancelResponse(job_id=job_id, status=job.status)
    job.stop_event.set()
    return JobCancelResponse(job_id=job_id, status="cancelling")


@router.post("/reports/jobs/{job_id}/pptx")
def build_pptx(job_id: str) -> Dict[str, Any]:
    job = store.get(job_id)
    if not job.report_md_path or not os.path.exists(job.report_md_path):
        raise HTTPException(status_code=400, detail="Markdown report not available.")
    report_markdown = load_report_markdown(job.report_md_path)
    if not report_markdown:
        raise HTTPException(status_code=400, detail="Markdown report is empty.")

    output_path = ARTIFACTS_DIR / f"{job.ticker}_{report_slug(job.report_type)}_Report.pptx"
    company_name = job.company_name or job.ticker
    key_points = job.key_points if job.key_points else ["Summary unavailable."]
    agent = AnalystIQ()
    visual_deck_spec = asyncio.run(
        agent.generate_visual_deck_spec(
            company_name=company_name,
            ticker=job.ticker,
            report_markdown=report_markdown,
            executive_summary=job.executive_summary_preview or "",
            key_points=key_points,
        )
    )
    pptx_path = build_professional_pptx(
        report_markdown=report_markdown,
        output_path=str(output_path),
        company_name=company_name,
        ticker=job.ticker,
        key_points=key_points,
        executive_summary=job.executive_summary_preview or "",
        style_profile=job.presentation_style,
        visual_deck_spec=visual_deck_spec,
    )
    job.ppt_path = pptx_path
    _append_event(job, "artifact", {"type": "pptx", "path": pptx_path})
    return {"path": pptx_path, "ready": True}


@router.get("/reports/jobs/{job_id}/artifacts/{artifact_type}")
def download_artifact(job_id: str, artifact_type: str) -> FileResponse:
    job = store.get(job_id)
    path_lookup = {
        "md": job.report_md_path,
        "pdf": job.pdf_path,
        "pptx": job.ppt_path,
    }
    if artifact_type not in path_lookup:
        raise HTTPException(status_code=404, detail="Unsupported artifact type.")
    file_path = path_lookup[artifact_type]
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Artifact not found.")
    media_types = {
        "md": "text/markdown",
        "pdf": "application/pdf",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    return FileResponse(file_path, media_type=media_types[artifact_type], filename=os.path.basename(file_path))


@router.get("/reports/jobs/{job_id}/viewer", response_class=HTMLResponse)
def report_viewer(job_id: str) -> HTMLResponse:
    job = store.get(job_id)
    if not job.report_md_path or not os.path.exists(job.report_md_path):
        raise HTTPException(status_code=404, detail="Markdown report not found.")
    markdown_text = load_report_markdown(job.report_md_path)
    title = f"{job.ticker} - {job.report_type.title()} Report"
    return HTMLResponse(build_report_viewer_html(markdown_text, title))


app.include_router(router, prefix="/api")


def _mount_frontend(application: FastAPI) -> None:
    """Serve the Vite production build from the same origin as the API."""
    if not FRONTEND_DIST_DIR.exists():
        return

    index_path = FRONTEND_DIST_DIR / "index.html"
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        application.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @application.get("/")
    def serve_frontend_root() -> FileResponse:
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="Frontend build not found.")
        return FileResponse(index_path)

    @application.get("/{full_path:path}")
    def serve_frontend_path(full_path: str) -> FileResponse:
        if full_path.startswith("api") or full_path == "health":
            raise HTTPException(status_code=404, detail="Not found.")
        candidate = FRONTEND_DIST_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="Frontend build not found.")
        return FileResponse(index_path)


_mount_frontend(app)
