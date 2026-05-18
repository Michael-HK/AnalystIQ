import html
import re
import urllib.parse
from dataclasses import dataclass
from typing import Dict, List

import markdown2


@dataclass
class ReportSection:
    title: str
    body_markdown: str


def load_report_markdown(report_md_path: str) -> str:
    if not report_md_path:
        return ""
    try:
        with open(report_md_path, "r", encoding="utf-8") as report_file:
            return report_file.read()
    except OSError:
        return ""


def _extract_sections(markdown_text: str) -> List[ReportSection]:
    if not markdown_text.strip():
        return []

    sections: List[ReportSection] = []
    matches = list(re.finditer(r"^##\s+(.+)$", markdown_text, flags=re.MULTILINE))
    if not matches:
        return [ReportSection(title="Report Content", body_markdown=markdown_text.strip())]

    preamble = markdown_text[: matches[0].start()].strip()
    if preamble:
        sections.append(ReportSection(title="Opening Section", body_markdown=preamble))

    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        body_start = match.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown_text)
        body = markdown_text[body_start:body_end].strip()
        sections.append(ReportSection(title=title, body_markdown=body))
    return sections


def _extract_reference_links(markdown_text: str) -> Dict[str, Dict[str, str]]:
    links: Dict[str, Dict[str, str]] = {}
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


def _replace_citations(markdown_text: str, reference_links: Dict[str, Dict[str, str]]) -> str:
    if not reference_links:
        return markdown_text

    chunks = re.split(r"(```[\s\S]*?```)", markdown_text)

    def _citation_replacer(match: re.Match[str]) -> str:
        citation_number = match.group(1)
        citation_data = reference_links.get(citation_number)
        if not citation_data:
            return match.group(0)

        title = html.escape(citation_data["title"])
        domain = html.escape(citation_data.get("domain", ""))
        url = html.escape(citation_data["url"], quote=True)
        preview = f"{title} ({domain})" if domain else title
        preview = preview if len(preview) <= 220 else f"{preview[:217]}..."
        preview_attr = html.escape(preview, quote=True)

        return (
            f'<a href="{url}" class="citation-link" data-preview="{preview_attr}" '
            f'target="_blank" rel="noopener noreferrer">[{citation_number}]</a>'
        )

    for i, chunk in enumerate(chunks):
        if i % 2 == 1:
            continue
        chunks[i] = re.sub(r"\[(\d+)\]", _citation_replacer, chunk)
    return "".join(chunks)


def _prepare_embedded_html_block(block_html: str, block_index: int) -> str:
    """
    Prepare embedded html chart blocks for safe multi-chart rendering.

    Why:
    - Multiple chart blocks often redeclare top-level variables like `const ctx`.
    - Some reports may repeat canvas ids across sections.
    - Both cases can break rendering after the first chart in a shared DOM.
    """
    id_map: Dict[str, str] = {}

    def _canvas_id_replacer(match: re.Match[str]) -> str:
        prefix = match.group(1)
        quote = match.group(2)
        old_id = match.group(3)
        new_id = f"{old_id}__viewer_{block_index}"
        id_map[old_id] = new_id
        return f"{prefix}{quote}{new_id}{quote}"

    # Uniquify canvas ids inside this html fence.
    prepared = re.sub(
        r"(<canvas\b[^>]*\bid\s*=\s*)([\"'])([^\"']+)\2",
        _canvas_id_replacer,
        block_html,
        flags=re.IGNORECASE,
    )

    # Update JS string references to renamed ids.
    for old_id, new_id in id_map.items():
        prepared = re.sub(
            rf"([\"']){re.escape(old_id)}\1",
            rf"\1{new_id}\1",
            prepared,
        )

    # Isolate each script in an IIFE to avoid global const/let collisions.
    prepared = re.sub(
        r"<script(\b[^>]*)>([\s\S]*?)</script>",
        lambda m: f"<script{m.group(1)}>(function(){{\n{m.group(2)}\n}})();</script>",
        prepared,
        flags=re.IGNORECASE,
    )

    return prepared


def _replace_html_code_fences(markdown_text: str) -> str:
    block_counter = 0

    def _html_block_replacer(match: re.Match[str]) -> str:
        nonlocal block_counter
        block_counter += 1
        return _prepare_embedded_html_block(match.group(1), block_counter)

    return re.sub(
        r"```html\s*\n([\s\S]*?)\n```",
        _html_block_replacer,
        markdown_text,
        flags=re.DOTALL | re.IGNORECASE,
    )


def _anchor_links_new_tab(html_body: str) -> str:
    return re.sub(r"<a\s+href=\"([^\"]+)\"", r'<a href="\1" target="_blank" rel="noopener noreferrer"', html_body)


def _render_section_html(section: ReportSection, reference_links: Dict[str, Dict[str, str]]) -> str:
    md_with_links = _replace_citations(section.body_markdown, reference_links)
    md_with_chart_html = _replace_html_code_fences(md_with_links)
    section_html = markdown2.markdown(
        md_with_chart_html,
        extras=["tables", "fenced-code-blocks", "strike", "header-ids"],
    )
    return _anchor_links_new_tab(section_html)


def build_report_viewer_html(markdown_text: str, report_label: str) -> str:
    sections = _extract_sections(markdown_text)
    reference_links = _extract_reference_links(markdown_text)

    details_html: List[str] = []
    for idx, section in enumerate(sections):
        body_html = _render_section_html(section, reference_links)
        open_attr = " open" if idx < 2 else ""
        details_html.append(
            f'<details class="section-card"{open_attr}><summary>{section.title}</summary><div class="section-body">{body_html}</div></details>'
        )

    sections_markup = "\n".join(details_html) if details_html else "<p>No report content available.</p>"
    safe_label = html.escape(report_label)
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {{
      --bg: #ffffff;
      --panel: #f8fbff;
      --border: #dbe3ef;
      --text: #0f172a;
      --muted: #64748b;
      --accent: #2563eb;
    }}
    html, body {{
      margin: 0;
      padding: 0;
      background: transparent;
      font-family: "IBM Plex Sans", Arial, sans-serif;
      color: var(--text);
    }}
    .viewer-shell {{
      height: 100%;
      display: flex;
      flex-direction: column;
      border: 1px solid var(--border);
      border-radius: 14px;
      overflow: hidden;
      box-shadow: 0 16px 40px rgba(15, 23, 42, 0.12);
      background: #fff;
    }}
    .viewer-header {{
      position: sticky;
      top: 0;
      z-index: 5;
      background: var(--panel);
      border-bottom: 1px solid var(--border);
      padding: 0.75rem 1rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
    }}
    .viewer-title {{
      margin: 0;
      font-size: 0.98rem;
      font-weight: 700;
    }}
    .viewer-sub {{
      margin: 0.1rem 0 0 0;
      color: var(--muted);
      font-size: 0.82rem;
    }}
    .toolbar {{
      display: flex;
      gap: 0.45rem;
    }}
    .toolbar button {{
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
      color: #1e3a8a;
      font-size: 0.8rem;
      font-weight: 600;
      padding: 0.28rem 0.6rem;
      cursor: pointer;
    }}
    .viewer-body {{
      flex: 1;
      overflow-y: auto;
      padding: 1.05rem 1.15rem 1.25rem 1.15rem;
      background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
    }}
    .section-card {{
      background: #fff;
      border: 1px solid var(--border);
      border-radius: 10px;
      margin-bottom: 0.8rem;
      overflow: hidden;
    }}
    .section-card > summary {{
      list-style: none;
      cursor: pointer;
      padding: 0.72rem 0.9rem;
      font-size: 0.92rem;
      font-weight: 700;
      border-left: 4px solid var(--accent);
      background: #f8fbff;
    }}
    .section-card > summary::-webkit-details-marker {{
      display: none;
    }}
    .section-body {{
      padding: 0.82rem 1rem 1rem 1rem;
      line-height: 1.68;
      font-size: 0.945rem;
    }}
    .section-body h1, .section-body h2, .section-body h3, .section-body h4 {{
      letter-spacing: -0.01em;
      color: #0b1324;
      margin-top: 0.45rem;
      margin-bottom: 0.5rem;
    }}
    .section-body p {{
      margin: 0.52rem 0;
      color: #1f2e45;
    }}
    .section-body a {{
      color: var(--accent);
      text-decoration: underline;
    }}
    .citation-link {{
      position: relative;
      font-weight: 600;
      text-decoration: none;
      border-bottom: 1px dashed rgba(37, 99, 235, 0.5);
      cursor: pointer;
    }}
    .citation-link:hover {{
      border-bottom-color: rgba(37, 99, 235, 0.95);
    }}
    .citation-link::after {{
      content: attr(data-preview);
      position: absolute;
      left: 50%;
      transform: translateX(-50%);
      bottom: calc(100% + 0.3rem);
      min-width: 260px;
      max-width: 440px;
      z-index: 20;
      padding: 0.5rem 0.62rem;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: #0f172a;
      color: #f8fafc;
      font-size: 0.76rem;
      line-height: 1.35;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.35);
      white-space: normal;
      word-break: break-word;
      opacity: 0;
      visibility: hidden;
      transition: opacity 0.16s ease, visibility 0.16s ease;
      pointer-events: none;
    }}
    .citation-link:hover::after {{
      opacity: 1;
      visibility: visible;
    }}
    .section-body table {{
      width: 100%;
      border-collapse: collapse;
      margin: 0.5rem 0;
    }}
    .section-body th, .section-body td {{
      border: 1px solid var(--border);
      padding: 6px 8px;
      font-size: 0.86rem;
    }}
    .section-body pre {{
      overflow-x: auto;
      padding: 0.5rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #f8fafc;
    }}
  </style>
</head>
<body>
  <div class="viewer-shell">
    <div class="viewer-header">
      <div>
        <h3 class="viewer-title">Rendered Report Viewer</h3>
        <p class="viewer-sub">{safe_label}</p>
      </div>
      <div class="toolbar">
        <button onclick="toggleAll(true)">Expand all</button>
        <button onclick="toggleAll(false)">Collapse all</button>
      </div>
    </div>
    <div class="viewer-body">
      {sections_markup}
    </div>
  </div>
  <script>
    function toggleAll(openState) {{
      document.querySelectorAll("details.section-card").forEach((item) => {{
        item.open = openState;
      }});
    }}
  </script>
</body>
</html>
"""
