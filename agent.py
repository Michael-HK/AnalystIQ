
"""
This module contains the AgentInvest class, which is responsible for generating a financial report for a given company.
"""
import os
import asyncio
import json
import ast
from typing import List, Dict, Any, Optional
from datetime import datetime
from tenacity import retry, wait_exponential, stop_after_attempt
import html
from dotenv import load_dotenv

from prompts import (
    GENERATE_REPORT_STRUCTURE_PROMPT,
    GENERATE_WEB_QUERIES_PROMPT,
    GENERATE_FINANCIAL_QUERIES_PROMPT,
    GENERATE_OPENING_SECTION_PROMPT,
    GENERATE_EXECUTIVE_SUMMARY_PROMPT,
    CONTENT_GENERATION_SYSTEM_PROMPT_v2,
    CONTENT_GENERATION_USER_PROMPT,
    POLISH_REPORT_SYSTEM_PROMPT,
    POLISH_REPORT_USER_PROMPT,
)
from llama_index.core.chat_engine.types import AgentChatResponse
from tools.web_search import WebSearchTool, parallel_search
from tools.financial_tools import FinancialToolSpec, FinancialAgent, run_financial_queries_parallel
from utils import convert_report_to_pdf, ProgressCallback
from cache_manager import RedisCacheManager
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.llms.openrouter import OpenRouter


load_dotenv()

class AgentInvest:
    def __init__(self, verbose_agent: bool = False):
        self.current_date = datetime.now().strftime("%Y-%m-%d")


        self.llm = OpenRouter(
            model="google/gemini-2.0-flash-001",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            context_window=100000,
            temperature=1,
            max_tokens=8000
        )

        self.llm2 = OpenRouter(
            model="google/gemini-2.5-flash",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            context_window=100000,
            temperature=1,
            max_tokens=8000
        )

        self.financial_tools = FinancialToolSpec()
        self.web_search_tool = WebSearchTool()
        self.financial_agent = FinancialAgent(llm=self.llm, verbose=verbose_agent)
        self.source_map = {}
        self.cache_manager = RedisCacheManager(ttl_seconds=3600)

    def _parse_llm_python_output(self, output: str) -> Any:
        """Parse LLM output that should be in JSON or Python literal format."""
        try:
            # First, try to parse as JSON
            output_clean = output.strip()
            
            # Handle markdown code blocks
            if output_clean.startswith("```json"):
                output_clean = output_clean[7:-3].strip()
            elif output_clean.startswith("```python"):
                output_clean = output_clean[9:-3].strip()
            elif output_clean.startswith("```"):
                # Generic code block
                lines = output_clean.split('\n')
                if len(lines) > 2:
                    output_clean = '\n'.join(lines[1:-1])
            
            # Try JSON first
            try:
                return json.loads(output_clean)
            except json.JSONDecodeError:
                # Fall back to Python literal evaluation
                return ast.literal_eval(output_clean)
                
        except (ValueError, SyntaxError, json.JSONDecodeError) as e:
            print(f"Error parsing LLM output: {e}")
            print(f"Raw output was: {repr(output)}")
            print(f"Cleaned output was: {repr(output_clean)}")
            return None

    def _parse_llm_json_output(self, output: str) -> Any:
        try:
            # Handle markdown code blocks
            if output.strip().startswith("```json"):
                output = output.strip()[7:-4]
            return json.loads(output.strip())
        except json.JSONDecodeError as e:
            print(f"Error parsing LLM json output: {e}\nOutput was: {output}")
            return None

    @retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(3))
    async def generate_report_structure(self, company_name: str) -> List[str]:
        prompt = GENERATE_REPORT_STRUCTURE_PROMPT.format(
            company_name=company_name, current_date=self.current_date
        )
        response = await self.llm.acomplete(prompt)
        return self._parse_llm_python_output(response.text)

    @retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(3))
    async def generate_web_queries(self, company_name: str, report_structure: List[str]) -> List[str]:
        prompt = GENERATE_WEB_QUERIES_PROMPT.format(
            company_name=company_name,
            report_structure=str(report_structure),
            current_date=self.current_date,
        )
        response = await self.llm.acomplete(prompt)
        return self._parse_llm_python_output(response.text)

    @retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(3))
    async def generate_financial_queries(
        self, company_name: str, ticker: str, report_structure: List[str]
    ) -> List[Dict[str, str]]:
        prompt = GENERATE_FINANCIAL_QUERIES_PROMPT.format(
            company_name=company_name,
            ticker=ticker,
            report_structure=str(report_structure),
            current_date=self.current_date,
        )
        response = await self.llm.acomplete(prompt)

        # The prompt asks for a python list of dicts, so we use the python parser
        return self._parse_llm_python_output(response.text)

    def _format_context(self, web_results: List[Dict], financial_results: List[Any], financial_queries: List[Dict]) -> str:
        formatted_context = ""
        source_idx = 1
        seen_titles = set()  
        
        # Clear source map at the beginning to ensure clean state
        self.source_map.clear()
        print(f"DEBUG: Starting context formatting with {len(web_results)} web results and {len(financial_results)} financial results")
        
        # Process web results - handle nested lists and deduplicate by title
        for res in web_results:
            # If res is a list, flatten it
            if isinstance(res, list):
                for item in res:
                    if isinstance(item, dict) and item.get('url') and item.get('content'):
                        title = item.get('title', '').strip()
                        # Skip if we've already seen this title (case-insensitive comparison)
                        if title and title.lower() in seen_titles:
                            continue
                        
                        self.source_map[source_idx] = {"url": item['url'], "title": title}
                        formatted_context += f"Source [{source_idx}]:\n{item['content']}\n\n"
                        if title:
                            seen_titles.add(title.lower())
                        source_idx += 1
            # If res is a dict, process it directly
            elif isinstance(res, dict) and res.get('url') and res.get('content'):
                title = res.get('title', '').strip()
                # Skip if we've already seen this title (case-insensitive comparison)
                if title and title.lower() in seen_titles:
                    continue
                
                self.source_map[source_idx] = {"url": res['url'], "title": title}
                formatted_context += f"Source [{source_idx}]:\n{res['content']}\n\n"
                if title:
                    seen_titles.add(title.lower())
                source_idx += 1

        # Process financial results
        for i, res in enumerate(financial_results):
            if isinstance(res, Exception):
                print(f"Error in financial query {i}: {res}")
                continue

            query = financial_queries[i]['query']
            ticker = financial_queries[i]['ticker']
            url = f"https://finance.yahoo.com/quote/{ticker}"
            
            content = ""
            if isinstance(res, AgentChatResponse):
                content = str(res)
            elif isinstance(res, list) and all(isinstance(item, dict) for item in res): # It's from get_stock_news
                 content = "\n".join([f"Title: {n.get('title', '')}\nContent: {n.get('content', '')}" for n in res])
            elif isinstance(res, str):
                content = res

            if content:
                financial_title = f"Financial data for {ticker} ({query})"
                self.source_map[source_idx] = {"url": url, "title": financial_title}
                formatted_context += f"Source [{source_idx}]:\n{content}\n\n"
        #        print(f"DEBUG: Added financial source [{source_idx}]: {financial_title}")
                source_idx += 1

        print(f"DEBUG: Context formatting complete. Total sources mapped: {len(self.source_map)}")
        return formatted_context.strip()

    @retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(3))
    async def generate_section(self, section_title: str, company_name: str, context: str) -> str:
        system_prompt = CONTENT_GENERATION_SYSTEM_PROMPT_v2.format(current_date=self.current_date)
        user_prompt = CONTENT_GENERATION_USER_PROMPT.format(
            section_title=section_title,
            company_name=company_name,
            context=context
        )
        
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]
        
        response = await self.llm.achat(messages)
        return response.message.content

    @retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(3))
    async def generate_section_v3(self, section_title: str, company_name: str, context: str, previous_content: str = "") -> str:
        """
        NEW VERSION: Content-aware section generation with enhanced formatting and chart variety.
        This version considers previous sections for better flow and chart type diversity.
        """
        from prompts import CONTENT_GENERATION_SYSTEM_PROMPT_v4, CONTENT_GENERATION_USER_PROMPT_v3
        
        system_prompt = CONTENT_GENERATION_SYSTEM_PROMPT_v4.format(current_date=self.current_date)
        user_prompt = CONTENT_GENERATION_USER_PROMPT_v3.format(
            section_title=section_title,
            company_name=company_name,
            context=context,
            previous_content=previous_content
        )
        
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]
        
        response = await self.llm.achat(messages)
        return response.message.content

    @retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(3))
    async def polish_report(self, report_content: str, company_name: str) -> str:

        system_prompt = POLISH_REPORT_SYSTEM_PROMPT.format(current_date=self.current_date)
        
        user_prompt = POLISH_REPORT_USER_PROMPT.format(
            report_content=report_content,
            company_name=company_name
        )
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]
        response = await self.llm2.achat(messages)
        return response.message.content

    def _extract_cited_numbers(self, report_content: str) -> List[int]:
        import re
        # Regex to find numbers inside square brackets
        pattern = r'\[(\d+)\]'
        # Find all matches, convert them to int, and return a sorted list of unique numbers
        return sorted(list(set(map(int, re.findall(pattern, report_content)))))
    
    def _generate_references_section_v1(self, cited_numbers: List[int]) -> str:
        if not cited_numbers:
            return ""
        
        references_content = "\n\n---\n\n## References\n\n"
        for num in cited_numbers:
            source_info = self.source_map.get(num)
            if source_info:
                title_part = f" ({source_info['title']})" if source_info.get('title') else ""
                # Use proper markdown formatting for better PDF rendering
                references_content += f"[{num}] {title_part} url: {source_info['url']}\n"
        
        return references_content

    def _generate_references_section(self, cited_numbers: List[int]) -> str:
        """
        Build a well-formatted References section for Markdown -> HTML -> PDF.

        - Renders as a dedicated H2 with id="references" so CSS in utils.py can style it.
        - Uses a bullet list for reliable wrapping and spacing in PDF generation.
        - Displays the reference number in bold brackets, followed by the URL and optional title.
        """
        if not cited_numbers:
            print("DEBUG: No cited numbers found, skipping references section")
            return ""

        # Ensure deterministic ordering (optional but recommended)
        unique_sorted = sorted(set(cited_numbers), key=int)

        # Header with proper HTML anchor for CSS targeting
        # Note: one blank line after header for reliable Markdown parsing.
        references_md = []
        references_md.append("\n\n---\n")
        references_md.append('\n<a id="references"></a>\n\n## References\n\n')

        valid_references_count = 0
        for num in unique_sorted:
            source_info = self.source_map.get(num)
            if not source_info:
                print(f"DEBUG: Warning - Citation [{num}] found in text but no source info available")
                # Still add a placeholder reference to maintain numbering
                references_md.append(f"**[{num}]** Source information unavailable\n\n")
                continue

            url = str(source_info.get("url", "")).strip()
            title = str(source_info.get("title", "")).strip()
            title_part = f" ({title})" if title else ""

            # Use markdown format for better compatibility
            references_md.append(f"**[{num}]** {title_part} [link]({url})\n\n")
            valid_references_count += 1

        print(f"DEBUG: Generated references section with {valid_references_count} valid references out of {len(unique_sorted)} cited")

        return "\n".join(references_md)

    def _generate_references_section_v3(self, cited_numbers: List[int]) -> str:
        """
        Build a well-formatted References section for Markdown -> HTML -> PDF.

        Behavior:
        - With title: [N] (Title) link
        - Without title: [N] https://example.com (clickable, URL is visible as the anchor text)
        """
        if not cited_numbers:
            return ""

        unique_sorted = sorted(set(cited_numbers), key=int)

        parts = []
        parts.append("\n\n---\n")
        parts.append('## References {#references}\n\n')
        parts.append('<ul id="references-list">')

        for num in unique_sorted:
            source_info = self.source_map.get(num)
            if not source_info:
                continue

            url = (source_info.get("url") or "").strip()
            if not url:
                continue

            title = (source_info.get("title") or "").strip()

            href_escaped = html.escape(url, quote=True)
            title_escaped = html.escape(title)

            if title_escaped:
                # Show short label "link" when title exists
                link_html = f'<a href="{href_escaped}">link</a>'
                title_part = f" ({title_escaped})"
                item_html = f'<li><b>[{num}]</b>{title_part} {link_html}</li>'
            else:
                # No title: make the URL itself the clickable text
                url_text = html.escape(url)
                link_html = f'<a href="{href_escaped}">{url_text}</a>'
                item_html = f'<li><b>[{num}]</b> {link_html}</li>'

            parts.append(item_html)

        parts.append("</ul>\n")

        return "".join(parts)

    def _generate_title_page(self, company_name: str) -> str:
        """
        Generate a professional title page for the investment report.
        NOTE: This method is deprecated - using LLM-generated opening section as title page instead.
        """
        title_page = f"""# Investment Report for {company_name}

**Prepared by AgentInvest**  
**Date: {self.current_date}**

---

*This report provides a comprehensive analysis of {company_name} for investment decision-making purposes. The analysis includes business fundamentals, financial performance, market positioning, growth prospects, valuation assessment, and risk factors to support informed investment decisions.*

---"""
        return title_page

    def _generate_table_of_contents(self, report_structure: List[str]) -> str:
        """
        Generate a well-formatted table of contents based on the report structure with proper spacing.
        Executive Summary is excluded at the structure generation level.
        """
        # Use HTML anchor for proper ID targeting
        toc_content = '<a id="table-of-contents"></a>\n\n## Table of Contents\n\n'
        
        # Use markdown list structure for better compatibility
        for section in report_structure:
            section_clean = section.strip()
            toc_content += f"{section_clean}\n"
        
        # Add References section to TOC
        toc_content += "- References\n\n"
        
        # Add page break after TOC to start main report on fresh page
        toc_content += "<div style='page-break-after: always;'></div>\n\n"
        toc_content += "---\n\n"  # Additional separator for better visual break
        
        return toc_content

    @retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(3))
    async def generate_opening_section(self, company_name: str, ticker: str, context: str) -> str:
        """
        Generate the opening section with company info, thesis, and recommended steps using LLM.
        This creates a data-driven opening based on the retrieved context and serves as the title page.
        """
        prompt = GENERATE_OPENING_SECTION_PROMPT.format(
            company_name=company_name,
            ticker=ticker,
            current_date=self.current_date
        )
        
        # Add context to the prompt
        full_prompt = f"{prompt}\n\nAvailable Research Context (Cite using [1], [2], etc.):\n---\n{context}\n---\n\nONLY output the content for the opening section, no other text or explanation. Generate the opening section now:"
        
        response = await self.llm.acomplete(full_prompt)
        
        # Add the company/date info after the title
        opening_content = response.text.strip()
        
        # Find the first line (title) and add the company info after it with proper styling
        lines = opening_content.split('\n')
        if lines:
            # Insert the company info after the first line (title) with CSS class
            title_line = lines[0]
            rest_content = '\n'.join(lines[1:]) if len(lines) > 1 else ""
            
            # Center the title using a CSS class for reliable centering
            # Remove markdown header syntax if present
            clean_title = title_line.replace('## ', '').replace('# ', '')
            centered_title = f'<div class="title-page-title">\n{clean_title}\n</div>'
            
            # Use CSS class for proper title page formatting
            company_info = f'\n\n<div class="title-page-info">\n<strong>Prepared by AgentInvest</strong><br>\n<strong>Date: {self.current_date}</strong>\n</div>\n'
            
            # Add page break after opening section
            page_break = "\n\n<div style='page-break-after: always;'></div>\n\n---\n"
            
            return centered_title + company_info + rest_content + page_break
        else:
            # Fallback if no content - center the entire opening content
            # Remove markdown header syntax if present
            clean_opening = opening_content.replace('## ', '').replace('# ', '')
            centered_opening = f'<div class="title-page-title">\n{clean_opening}\n</div>'
            company_info = f'\n\n<div class="title-page-info">\n<strong>Prepared by AgentInvest</strong><br>\n<strong>Date: {self.current_date}</strong>\n</div>\n'
            page_break = "\n\n<div style='page-break-after: always;'></div>\n\n---\n"
            return centered_opening + company_info + page_break

    @retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(3))
    async def generate_executive_summary(self, company_name: str, ticker: str, raw_report: str) -> str:
        """
        Generate a comprehensive executive summary based on the complete report content.
        This will be placed on a separate page after the opening section.
        """
        prompt = GENERATE_EXECUTIVE_SUMMARY_PROMPT.format(
            company_name=company_name,
            ticker=ticker,
            current_date=self.current_date
        )
        
        # Add the complete report content for analysis
        full_prompt = f"{prompt}\n\nComplete Report Content for Analysis:\n---\n{raw_report}\n---\n\nONLY output the content for the executive summary, no other text or explanation. Generate the executive summary now:"
        
        response = await self.llm.acomplete(full_prompt)
        
        # Add page break after executive summary with proper HTML anchor for CSS targeting
        executive_summary = f'<a id="executive-summary"></a>\n\n## Executive Summary\n\n{response.text.strip()}\n\n<div style="page-break-after: always;"></div>\n\n---\n'
        
        return executive_summary

    async def run(self, ticker: str, progress_callback: Optional[ProgressCallback] = None):
        
        def update_progress(message: str, data: Optional[Any] = None):
            payload = {"message": message, "data": data}
            if progress_callback:
                progress_callback(payload)
            print(f"{message}{(': ' + str(data)) if data else ''}")

        update_progress(f"🚀 Starting analysis for {ticker}")

        # --- Check Cache ---
        cached_data = self.cache_manager.get_cached_data(ticker)
        
        if cached_data:
            update_progress("✅ Found cached data. Skipping data gathering and using cached content.")
            company_name = cached_data['company_name']
            report_structure = cached_data['structure']

            
            # Use cached raw results if available
            web_results = cached_data.get('web_results', [])
            financial_results = cached_data.get('financial_results', [])
            web_queries = cached_data.get('web_queries', [])
            financial_queries = cached_data.get('financial_queries', [])
            
            update_progress("🏢 Using cached company name", company_name)
            update_progress("📊 Using cached web and financial results")

            context = self._format_context(web_results, financial_results, financial_queries)
        else:
            # 1. Get company name
            company_name = self.financial_tools.get_company_name(ticker)
            update_progress("🏢 Identified company", company_name)

            # 2. Generate report structure
            update_progress("🏗️ Generating report structure...")
            report_structure = await self.generate_report_structure(company_name)
            if not report_structure:
                update_progress("❌ Failed to generate report structure. Aborting.")
                return
            update_progress("✅ Report structure generated", report_structure)

            # 3. & 4. Generate sub-queries in parallel
            update_progress("🔍💹 Generating research queries for web and financial data...")
            web_queries_task = asyncio.create_task(self.generate_web_queries(company_name, report_structure))
            financial_queries_task = asyncio.create_task(self.generate_financial_queries(company_name, ticker, report_structure))
            web_queries, financial_queries = await asyncio.gather(web_queries_task, financial_queries_task)

            if web_queries:
                update_progress("🌐 Generated web search queries", web_queries)
            if financial_queries:
                update_progress("💹 Generated financial data queries", financial_queries)

            # 5. & 6. Run searches in parallel
            update_progress("🔄 Gathering data from web and financial sources...")
            web_results_task = asyncio.create_task(parallel_search(self.web_search_tool, web_queries or []))
            financial_results_task = asyncio.create_task(run_financial_queries_parallel(self.financial_agent, financial_queries or []))
            web_results, financial_results = await asyncio.gather(web_results_task, financial_results_task)
            update_progress("📥 Data gathering complete.")

            # 7. Format context
            update_progress("📝 Formatting and consolidating research data...")
            context = self._format_context(web_results, financial_results, financial_queries or [])
            
            # --- Store in Cache ---
            self.cache_manager.set_cached_data(
                ticker, company_name, report_structure, context,
                web_results, financial_results, web_queries, financial_queries
            )

        # 8. Generate content for each section
        update_progress("✍️ Generating content for each report section...")
        #generate content for each section using for batch of 3 sections at a time
        generated_contents = []
        for i in range(0, len(report_structure), 3):
            batch = report_structure[i:i+3]
            section_generation_tasks = [
                self.generate_section(section, company_name, context)
                for section in batch
            ]
            generated_contents.extend(await asyncio.gather(*section_generation_tasks))
            # wait for 3 seconds
            await asyncio.sleep(3)

        report_sections_content = []
        for i, section_title in enumerate(report_structure):
          
            section_clean = section_title.strip()
            anchor = section_clean.lower().replace('.', '').replace(' ', '-').replace('(', '').replace(')', '').replace('&', 'and')
            import re
            anchor = re.sub(r'^\d+\.?\s*', '', anchor)
            
            # Add section with HTML anchor
            report_sections_content.append(f'<a id="{anchor}"></a>\n\n## {section_title}\n\n{generated_contents[i]}')
        
        raw_report = "\n\n".join(report_sections_content)
        update_progress("📑 All report sections generated.")

        # 9. Polish the report
    #    update_progress("✨ Polishing final report for readability and flow...")
    #    polished_report = await self.polish_report(raw_report, company_name)

        # 10. Generate opening section (serves as title page)
        update_progress("📋 Generating opening section as title page...")
        opening_section = await self.generate_opening_section(company_name, ticker, context)

        # 11. Generate executive summary (separate page)
        update_progress("📝 Generating executive summary...")
        executive_summary = await self.generate_executive_summary(company_name, ticker, raw_report)

        # 12. Generate table of contents (separate page, excludes executive summary)
        update_progress("📋 Generating table of contents...")
        table_of_contents = self._generate_table_of_contents(report_structure)

        # 13. Generate references
        update_progress("📚 Generating references section...")
        cited_numbers = self._extract_cited_numbers(raw_report)
        print(f"DEBUG: Found {len(cited_numbers)} cited numbers: {cited_numbers}")
        print(f"DEBUG: Source map has {len(self.source_map)} entries: {list(self.source_map.keys())}")
        references_section = self._generate_references_section(cited_numbers)

        # New structure: Opening (title) -> Executive Summary -> TOC -> Main Report -> References
        final_report = opening_section + "\n\n" + executive_summary + "\n\n" + table_of_contents + "\n\n" + raw_report + "\n\n" + references_section

        update_progress("🏁 Final report assembly complete.")
        
        # Ensure the generated_reports directory exists with correct permissions
        reports_dir = "./generated_reports"
        os.makedirs(reports_dir, exist_ok=True)
        
        # Save to markdown file in the mounted volume (ensure overwrite)
        output_md_filename = os.path.join(reports_dir, f"{ticker}_AgentInvest_Report.md")
        
        # Explicitly remove existing markdown file if it exists
        if os.path.exists(output_md_filename):
            try:
                os.remove(output_md_filename)
                update_progress(f"🗑️ Removed existing markdown file: {output_md_filename}")
            except OSError as e:
                update_progress(f"⚠️ Warning: Could not remove existing markdown file: {e}")
        
        # Write new markdown file
        try:
            with open(output_md_filename, "w", encoding='utf-8') as f:
                f.write(final_report)
            update_progress(f"✅ Markdown report saved: {output_md_filename}")
        except IOError as e:
            update_progress(f"❌ Failed to save markdown report: {e}")
            return final_report

        # Convert to PDF in the mounted volume (ensure overwrite)
        update_progress("📄 Converting report to PDF...")
        output_pdf_filename = os.path.join(reports_dir, f"{ticker}_AgentInvest_Report.pdf")

        # Explicitly remove existing PDF file if it exists
        if os.path.exists(output_pdf_filename):
            try:
                os.remove(output_pdf_filename)
                update_progress(f"🗑️ Removed existing PDF file: {output_pdf_filename}")
            except OSError as e:
                update_progress(f"⚠️ Warning: Could not remove existing PDF file: {e}")

        chartjs_src = os.getenv("CHARTJS_SRC", None)
        pdf_success = await convert_report_to_pdf(
            final_report, 
            output_pdf_filename, 
            company_name=company_name,
            chartjs_src=chartjs_src
        )

        if pdf_success:
            # Validate that the PDF file was actually created and has content
            if os.path.exists(output_pdf_filename) and os.path.getsize(output_pdf_filename) > 0:
                update_progress("✅ PDF report saved", output_pdf_filename)
            else:
                update_progress("❌ PDF file was not created properly or is empty.")
        else:
            update_progress("❌ Failed to generate PDF report.")
        
        return final_report

    def regenerate_context_from_cache(self, ticker: str) -> Optional[str]:
        """
        Regenerate the formatted context from cached raw results.
        Useful when you want to change formatting logic without re-fetching data.
        
        Args:
            ticker (str): The stock ticker symbol.
            
        Returns:
            Optional[str]: The regenerated context, or None if no cached data exists.
        """
        cached_data = self.cache_manager.get_cached_data(ticker)
        if not cached_data:
            return None
            
        web_results = cached_data.get('web_results', [])
        financial_results = cached_data.get('financial_results', [])
        financial_queries = cached_data.get('financial_queries', [])
        
        if not web_results and not financial_results:
            return None
            
        # Regenerate context with current formatting logic
        new_context = self._format_context(web_results, financial_results, financial_queries)
        
        # Update cache with new context while keeping raw results
        self.cache_manager.set_cached_data(
            ticker, 
            cached_data['company_name'], 
            cached_data['structure'], 
            new_context,
            web_results, 
            financial_results, 
            cached_data.get('web_queries', []), 
            financial_queries
        )
        
        return new_context

    def get_cached_raw_results(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get the raw cached web and financial results for a ticker.
        
        Args:
            ticker (str): The stock ticker symbol.
            
        Returns:
            Optional[Dict[str, Any]]: Dictionary containing raw results, or None if no cached data exists.
        """
        cached_data = self.cache_manager.get_cached_data(ticker)
        if not cached_data:
            return None
            
        return {
            'web_results': cached_data.get('web_results', []),
            'financial_results': cached_data.get('financial_results', []),
            'web_queries': cached_data.get('web_queries', []),
            'financial_queries': cached_data.get('financial_queries', []),
            'company_name': cached_data.get('company_name'),
            'report_structure': cached_data.get('structure', [])
        }

    async def run_v3(self, ticker: str, progress_callback: Optional[ProgressCallback] = None):
        """
        NEW VERSION: Content-aware report generation with enhanced formatting and chart variety.
        Each section receives previous sections for better flow and context awareness.
        """
        
        def update_progress(message: str, data: Optional[Any] = None):
            payload = {"message": message, "data": data}
            if progress_callback:
                progress_callback(payload)
            print(f"{message}{(': ' + str(data)) if data else ''}")

        update_progress(f"🚀 Starting enhanced analysis for {ticker}")

        # --- Check Cache ---
        cached_data = self.cache_manager.get_cached_data(ticker)
        
        if cached_data:
            update_progress("✅ Found cached data. Skipping data gathering and using cached content.")
            company_name = cached_data['company_name']
            report_structure = cached_data['structure']
            context = cached_data['context']
            
            # Use cached raw results if available
            web_results = cached_data.get('web_results', [])
            financial_results = cached_data.get('financial_results', [])
            web_queries = cached_data.get('web_queries', [])
            financial_queries = cached_data.get('financial_queries', [])
            
            update_progress("🏢 Using cached company name", company_name)
            update_progress("📊 Using cached web and financial results")
        else:
            # 1. Get company name
            company_name = self.financial_tools.get_company_name(ticker)
            update_progress("🏢 Identified company", company_name)

            # 2. Generate report structure
            update_progress("🏗️ Generating comprehensive report structure...")
            report_structure = await self.generate_report_structure(company_name)
            if not report_structure:
                update_progress("❌ Failed to generate report structure. Aborting.")
                return
            update_progress("✅ Report structure generated", report_structure)

            # 3. & 4. Generate sub-queries in parallel
            update_progress("🔍💹 Generating research queries for web and financial data...")
            web_queries_task = asyncio.create_task(self.generate_web_queries(company_name, report_structure))
            financial_queries_task = asyncio.create_task(self.generate_financial_queries(company_name, ticker, report_structure))
            web_queries, financial_queries = await asyncio.gather(web_queries_task, financial_queries_task)

            if web_queries:
                update_progress("🌐 Generated web search queries", web_queries)
            if financial_queries:
                update_progress("💹 Generated financial data queries", financial_queries)

            # 5. & 6. Run searches in parallel
            update_progress("🔄 Gathering comprehensive data from web and financial sources...")
            web_results_task = asyncio.create_task(parallel_search(self.web_search_tool, web_queries or []))
            financial_results_task = asyncio.create_task(run_financial_queries_parallel(self.financial_agent, financial_queries or []))
            web_results, financial_results = await asyncio.gather(web_results_task, financial_results_task)
            update_progress("📥 Data gathering complete.")

            # 7. Format context
            update_progress("📝 Formatting and consolidating research data...")
            context = self._format_context(web_results, financial_results, financial_queries or [])
            
            # --- Store in Cache ---
            self.cache_manager.set_cached_data(
                ticker, company_name, report_structure, context,
                web_results, financial_results, web_queries, financial_queries
            )

        # 8. Generate content for each section with content-awareness
        update_progress("✍️ Generating content-aware sections with enhanced formatting...")
        generated_contents = []
        previous_sections_content = ""
        
        # Process sections sequentially to build context awareness
        for i, section_title in enumerate(report_structure):
            update_progress(f"📝 Generating section {i+1}/{len(report_structure)}: {section_title}")
            
            section_content = await self.generate_section_v3(
                section_title, 
                company_name, 
                context, 
                previous_sections_content
            )
            
            generated_contents.append(section_content)
            
            # Build cumulative previous content for next section
            formatted_section = f"## {section_title}\n\n{section_content}"
            if previous_sections_content:
                previous_sections_content += "\n\n" + formatted_section
            else:
                previous_sections_content = formatted_section
            
            # Small delay to prevent rate limiting
            await asyncio.sleep(2)
            
            # Create sections with anchor IDs for clickable TOC
        report_sections_content = []
        for i, section_title in enumerate(report_structure):
            # Create matching anchor ID for clickable TOC
            section_clean = section_title.strip()
            anchor = section_clean.lower().replace('.', '').replace(' ', '-').replace('(', '').replace(')', '').replace('&', 'and')
            import re
            anchor = re.sub(r'^\d+\.?\s*', '', anchor)
            
            # Add section with HTML anchor 
            report_sections_content.append(f'<a id="{anchor}"></a>\n\n## {section_title}\n\n{generated_contents[i]}')
        
        raw_report = "\n\n".join(report_sections_content)
        update_progress("📑 All enhanced report sections generated.")

        # 9. Generate opening section (serves as title page)
        update_progress("📋 Generating professional opening section as title page...")
        opening_section = await self.generate_opening_section(company_name, ticker, context)

        # 10. Generate executive summary (separate page)
        update_progress("📝 Generating comprehensive executive summary...")
        executive_summary = await self.generate_executive_summary(company_name, ticker, raw_report)

        # 11. Generate table of contents (separate page, excludes executive summary)
        update_progress("📋 Generating table of contents...")
        table_of_contents = self._generate_table_of_contents(report_structure)

        # 12. Generate references
        update_progress("📚 Generating comprehensive references section...")
        cited_numbers = self._extract_cited_numbers(raw_report)
        print(f"DEBUG: Found {len(cited_numbers)} cited numbers: {cited_numbers}")
        print(f"DEBUG: Source map has {len(self.source_map)} entries: {list(self.source_map.keys())}")
        references_section = self._generate_references_section(cited_numbers)

        # New structure: Opening (title) -> Executive Summary -> TOC -> Main Report -> References
        final_report = opening_section + "\n\n" + executive_summary + "\n\n" + table_of_contents + "\n\n" + raw_report + "\n\n" + references_section

        update_progress("🏁 Enhanced final report assembly complete.")
        
        # Ensure the generated_reports directory exists with correct permissions
        reports_dir = "generated_reports"
        os.makedirs(reports_dir, exist_ok=True)
        
        # Ensure we have write permissions (additional safety check)
        try:
            os.chmod(reports_dir, 0o755)
        except PermissionError:
            
            pass
        
        # Save to markdown file in the mounted volume (ensure overwrite)
        output_md_filename = os.path.join(reports_dir, f"{ticker}_AgentInvest_Report_v3.md")
        
        # Explicitly remove existing markdown file if it exists
        if os.path.exists(output_md_filename):
            try:
                os.remove(output_md_filename)
                update_progress(f"🗑️ Removed existing markdown file: {output_md_filename}")
            except OSError as e:
                update_progress(f"⚠️ Warning: Could not remove existing markdown file: {e}")
        
        # Write new markdown file
        try:
            with open(output_md_filename, "w", encoding='utf-8') as f:
                f.write(final_report)
            update_progress(f"✅ Markdown report saved: {output_md_filename}")
        except IOError as e:
            update_progress(f"❌ Failed to save markdown report: {e}")
            return final_report

        # Convert to PDF in the mounted volume (ensure overwrite)
        update_progress("📄 Converting enhanced report to PDF...")
        output_pdf_filename = os.path.join(reports_dir, f"{ticker}_AgentInvest_Report_v3.pdf")
        
        # Explicitly remove existing PDF file if it exists
        if os.path.exists(output_pdf_filename):
            try:
                os.remove(output_pdf_filename)
                update_progress(f"🗑️ Removed existing PDF file: {output_pdf_filename}")
            except OSError as e:
                update_progress(f"⚠️ Warning: Could not remove existing PDF file: {e}")

        chartjs_src = os.getenv("CHARTJS_SRC", None)
        pdf_success = await convert_report_to_pdf(
            final_report, 
            output_pdf_filename, 
            company_name=company_name,
            chartjs_src=chartjs_src
        )

        if pdf_success:
            # Validate that the PDF file was actually created and has content
            if os.path.exists(output_pdf_filename) and os.path.getsize(output_pdf_filename) > 0:
                update_progress("✅ Enhanced PDF report saved", output_pdf_filename)
            else:
                update_progress("❌ Enhanced PDF file was not created properly or is empty.")
        else:
            update_progress("❌ Failed to generate enhanced PDF report.")
        
        return final_report
