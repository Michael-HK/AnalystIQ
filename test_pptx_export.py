#!/usr/bin/env python3
"""
Quick PPTX export test — no full report run required.

Uses an existing markdown report from generated_reports/ and builds a
Manus-style PowerPoint so you can review layout quality in isolation.

Examples:
  # Recommended: deterministic Manus fallback deck (no LLM, needs project venv)
  python test_pptx_export.py

  # Fastest: test slide renderer only (no agent import; needs python-pptx + playwright)
  python test_pptx_export.py --renderer-only

  # Production path: LLM-generated deck spec (needs OPENROUTER_API_KEY)
  python test_pptx_export.py --with-llm

  # Custom report / style / output
  python test_pptx_export.py --report generated_reports/0050.HK_CreditAnalysis_Report.md --style "Executive Dark"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_REPORT = ROOT / "generated_reports" / "0001.HK_CreditAnalysis_Report.md"
DEFAULT_STYLE = "Institutional Light"


def _load_markdown(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")
    return path.read_text(encoding="utf-8")


def _guess_ticker(report_path: Path, markdown: str) -> str:
    name = report_path.stem
    match = re.search(r"(\d{4}\.HK|[A-Z]{1,5})", name, flags=re.I)
    if match:
        token = match.group(1)
        return token.upper() if "." not in token else token
    body_match = re.search(r"\(([A-Z0-9.]+)\)", markdown[:500])
    return body_match.group(1) if body_match else "TEST"


def _guess_company(markdown: str, ticker: str) -> str:
    match = re.search(r"^#\s+(.+?)\s*[\(\[]?" + re.escape(ticker), markdown, flags=re.M | re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r"([A-Za-z0-9&.,'\-\s]{4,80}?)\s*\(" + re.escape(ticker) + r"\)", markdown[:800])
    if match:
        return match.group(1).strip()
    return ticker


def _extract_executive_summary(markdown: str) -> str:
    pattern = r"##\s+Executive Summary\s*(.*?)(?=\n##\s+|\Z)"
    match = re.search(pattern, markdown, flags=re.DOTALL | re.I)
    if not match:
        return ""
    text = re.sub(r"<[^>]+>", " ", match.group(1))
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1200]


def _extract_key_points(markdown: str, executive_summary: str) -> list[str]:
    source = executive_summary or markdown[:4000]
    bullets = re.findall(r"^\s*[-*]\s+(.+)$", source, flags=re.MULTILINE)
    cleaned = [re.sub(r"\s+", " ", b).strip() for b in bullets if b.strip()]
    if len(cleaned) >= 3:
        return cleaned[:5]
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", source) if len(s.strip()) > 20]
    return sentences[:5] or ["Summary unavailable."]


def _renderer_only_spec(company_name: str, ticker: str, executive_summary: str, key_points: list[str]) -> dict:
    """Built-in Manus-style spec to exercise all major layouts without importing agent."""
    thesis = executive_summary[:150] if executive_summary else (key_points[0] if key_points else "Investment view.")
    return {
        "deck_title": f"{company_name} Investment Committee Deck",
        "subtitle": f"{ticker} | PPTX renderer test",
        "investment_thesis": thesis,
        "recommendation": "Validate thesis, risks, and sizing before committee action.",
        "slides": [
            {
                "layout_type": "thesis",
                "section_label": "Thesis",
                "headline": "Investment thesis and key decision points",
                "takeaway": thesis[:120],
                "bullets": key_points[:3],
                "chart_ref": 0,
            },
            {
                "layout_type": "big_stat",
                "section_label": "Signal",
                "headline": "Most material quantitative signal",
                "stat_number": "13.9%",
                "stat_label": "Example leverage / capital ratio from report",
                "bullets": [],
            },
            {
                "layout_type": "chart",
                "section_label": "Evidence",
                "headline": "Chart-backed evidence slide",
                "subheading": "Visual proof supporting the core argument.",
                "bullets": key_points[1:4] if len(key_points) > 1 else ["Trend supports base case.", "Monitor inflection points."],
                "chart_ref": 0,
            },
            {
                "layout_type": "three_column_cards",
                "section_label": "Drivers",
                "headline": "Three pillars for the investment case",
                "bullets": (key_points + ["Liquidity remains strong.", "Execution risk is manageable."])[:3],
            },
            {
                "layout_type": "text_and_image",
                "section_label": "Context",
                "headline": "Text plus visual composition",
                "bullets": ["Concise left-column narrative.", "Chart or accent panel on the right.", "Designed for IC readability."],
                "chart_ref": 1,
            },
            {
                "layout_type": "risk_matrix",
                "section_label": "Risk",
                "headline": "Key risks and mitigation path",
                "takeaway": "Stress-test downside before sizing the position.",
                "bullets": [
                    "Macro slowdown can reduce demand visibility.",
                    "Execution miss may compress valuation multiples.",
                    "Regulatory shifts can disrupt forecast assumptions.",
                ],
            },
            {
                "layout_type": "closing_recommendation",
                "section_label": "Action",
                "headline": "Committee actions and monitoring plan",
                "takeaway": "Convert analysis into sizing, risk, and catalyst decisions.",
                "bullets": [
                    "Validate assumptions against internal model outputs.",
                    "Pressure-test downside scenarios before position sizing.",
                    "Define buy, hold, trim, or watchlist decision criteria.",
                ],
            },
        ],
    }


def _print_preview(deck_spec: dict) -> None:
    slides = deck_spec.get("slides") or []
    print("\nDeck preview")
    print("-" * 60)
    print(f"Title:    {deck_spec.get('deck_title', '')}")
    print(f"Subtitle: {deck_spec.get('subtitle', '')}")
    print(f"Slides:   {len(slides)} content slides (+ title slide in file)")
    for idx, slide in enumerate(slides, start=1):
        layout = slide.get("layout_type", "?")
        headline = slide.get("headline", "")
        chart_ref = slide.get("chart_ref")
        chart_note = f", chart_ref={chart_ref}" if chart_ref is not None else ""
        print(f"  {idx:02d}. [{layout}] {headline}{chart_note}")
    print("-" * 60)


def _build_deck_spec(
    *,
    with_llm: bool,
    renderer_only: bool,
    company_name: str,
    ticker: str,
    markdown: str,
    executive_summary: str,
    key_points: list[str],
) -> dict:
    if renderer_only:
        return _renderer_only_spec(company_name, ticker, executive_summary, key_points)

    from agent import AnalystIQ

    agent = AnalystIQ()
    if with_llm:
        return asyncio.run(
            agent.generate_visual_deck_spec(
                company_name=company_name,
                ticker=ticker,
                report_markdown=markdown,
                executive_summary=executive_summary,
                key_points=key_points,
            )
        )
    return agent._build_fallback_visual_deck_spec(
        company_name=company_name,
        ticker=ticker,
        report_markdown=markdown,
        executive_summary=executive_summary,
        key_points=key_points,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Test AnalystIQ PPTX export from an existing report.")
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help=f"Path to markdown report (default: {DEFAULT_REPORT.name})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output .pptx path (default: generated_reports/test_pptx_<timestamp>.pptx)",
    )
    parser.add_argument(
        "--style",
        default=DEFAULT_STYLE,
        choices=["Institutional Light", "Executive Dark", "Minimal Clean"],
        help="Presentation style preset",
    )
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help="Generate visual deck spec via LLM (production path; requires OPENROUTER_API_KEY)",
    )
    parser.add_argument(
        "--renderer-only",
        action="store_true",
        help="Use built-in sample deck spec; skips agent import (good for quick layout checks)",
    )
    parser.add_argument(
        "--company",
        default=None,
        help="Override company name shown on slides",
    )
    parser.add_argument(
        "--ticker",
        default=None,
        help="Override ticker shown on slides",
    )
    parser.add_argument(
        "--save-spec",
        action="store_true",
        help="Also write the deck spec JSON next to the pptx",
    )
    args = parser.parse_args()

    if args.with_llm and args.renderer_only:
        print("Choose either --with-llm or --renderer-only, not both.", file=sys.stderr)
        return 2

    report_path = args.report if args.report.is_absolute() else ROOT / args.report
    markdown = _load_markdown(report_path)
    ticker = args.ticker or _guess_ticker(report_path, markdown)
    company_name = args.company or _guess_company(markdown, ticker)
    executive_summary = _extract_executive_summary(markdown)
    key_points = _extract_key_points(markdown, executive_summary)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output
    if output_path is None:
        output_path = ROOT / "generated_reports" / f"test_pptx_{ticker}_{timestamp}.pptx"
    elif not output_path.is_absolute():
        output_path = ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    from ppt_export import build_professional_pptx, extract_chart_specs_from_markdown

    charts = extract_chart_specs_from_markdown(markdown)
    mode = "renderer-only sample spec"
    if args.with_llm:
        mode = "LLM deck spec"
    elif not args.renderer_only:
        mode = "agent fallback deck spec (no LLM)"

    print(f"Report:  {report_path}")
    print(f"Company: {company_name} ({ticker})")
    print(f"Charts:  {len(charts)} extracted from markdown")
    print(f"Mode:    {mode}")

    try:
        deck_spec = _build_deck_spec(
            with_llm=args.with_llm,
            renderer_only=args.renderer_only,
            company_name=company_name,
            ticker=ticker,
            markdown=markdown,
            executive_summary=executive_summary,
            key_points=key_points,
        )
    except ModuleNotFoundError as exc:
        print(f"\nMissing dependency while loading agent: {exc.name}", file=sys.stderr)
        print("Try:", file=sys.stderr)
        print("  pip install -r requirements.txt", file=sys.stderr)
        print("Or run layout-only test:", file=sys.stderr)
        print("  python test_pptx_export.py --renderer-only", file=sys.stderr)
        return 1

    _print_preview(deck_spec)

    if args.save_spec:
        spec_path = output_path.with_suffix(".deck_spec.json")
        spec_path.write_text(json.dumps(deck_spec, indent=2), encoding="utf-8")
        print(f"Spec:    {spec_path}")

    try:
        pptx_path = build_professional_pptx(
            report_markdown=markdown,
            output_path=str(output_path),
            company_name=company_name,
            ticker=ticker,
            key_points=key_points,
            executive_summary=executive_summary,
            style_profile=args.style,
            visual_deck_spec=deck_spec,
        )
    except ModuleNotFoundError as exc:
        print(f"\nMissing dependency: {exc.name}", file=sys.stderr)
        print("Install:", file=sys.stderr)
        print("  pip install python-pptx playwright", file=sys.stderr)
        print("  python -m playwright install chromium", file=sys.stderr)
        return 1

    print(f"\nPPTX ready: {pptx_path}")
    print("Open the file in PowerPoint to review layout, charts, and typography.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
