"""
Standalone PPT generation test utility.

Usage example:
    python test_ppt_generation.py --ticker 0001.HK --style "Institutional Light"
"""
import argparse
import asyncio
import os
import re
from typing import List

from agent import AgentInvest
from ppt_export import build_professional_pptx


def _extract_summary_from_markdown(markdown_text: str) -> str:
    match = re.search(
        r"##\s+Executive Summary\s*(.*?)(?=\n##\s+Table of Contents|\n##\s+[^\n]+|\Z)",
        markdown_text,
        flags=re.DOTALL,
    )
    if not match:
        return ""
    content = match.group(1).strip()
    content = re.sub(r"<[^>]+>", " ", content)
    content = re.sub(r"\s+", " ", content)
    return content.strip()


def run_ppt_generation_test(
    ticker: str = "0001.HK",
    style_profile: str = "Institutional Light",
) -> str:
    """
    Generate a PPT from an existing report markdown without rerunning report generation.
    Returns generated PPT path.
    """
    report_md_path = os.path.join("generated_reports", f"{ticker}_AgentInvest_Report.md")
    if not os.path.exists(report_md_path):
        raise FileNotFoundError(f"Report markdown not found: {report_md_path}")

    with open(report_md_path, "r", encoding="utf-8") as md_file:
        report_markdown = md_file.read()

    output_ppt_path = os.path.join("generated_reports", f"{ticker}_AgentInvest_Presentation_TEST.pptx")
    agent = AgentInvest(verbose_agent=False)
    company_name = ticker
    key_points: List[str] = []
    executive_summary = _extract_summary_from_markdown(report_markdown)
    visual_deck_spec = None

    # Try full agentic workflow first. If unavailable, fallback still generates a deck.
    try:
        company_name = agent.financial_tools.get_company_name(ticker) or ticker
    except Exception:
        company_name = ticker

    try:
        key_points = asyncio.run(
            agent.extract_five_key_points(
                company_name=company_name,
                ticker=ticker,
                report_content=report_markdown,
            )
        )
    except Exception:
        key_points = []

    try:
        visual_deck_spec = asyncio.run(
            agent.generate_visual_deck_spec(
                company_name=company_name,
                ticker=ticker,
                report_markdown=report_markdown,
                executive_summary=executive_summary,
                key_points=key_points,
            )
        )
    except Exception:
        visual_deck_spec = None

    build_professional_pptx(
        report_markdown=report_markdown,
        output_path=output_ppt_path,
        company_name=company_name,
        ticker=ticker,
        key_points=key_points,
        executive_summary=executive_summary,
        chartjs_src=os.getenv("CHARTJS_SRC", None),
        visual_deck_spec=visual_deck_spec,
        style_profile=style_profile,
    )
    return output_ppt_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate PPT from existing AgentInvest markdown report.")
    parser.add_argument("--ticker", default="0001.HK", help="Ticker symbol used in report filename.")
    parser.add_argument(
        "--style",
        default="Institutional Light",
        choices=["Institutional Light", "Executive Dark", "Minimal Clean"],
        help="PPT visual style.",
    )
    args = parser.parse_args()
    ppt_path = run_ppt_generation_test(ticker=args.ticker, style_profile=args.style)
    print(f"PPT test generated: {ppt_path}")
