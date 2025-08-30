
"""
Utilities to turn a Markdown report (with HTML chart blocks) into a PDF using Playwright.

Uses Playwright's Chromium browser for high-quality HTML to PDF conversion with 
full support for modern web standards, JavaScript rendering, and CSS styling.
"""

import os
import re
import tempfile
import base64
import shutil
import subprocess
import sys
import markdown2
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Protocol, Any, Optional, Match
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Helper function to run async code in a thread
def run_async_in_thread(coro):
    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_in_thread)
        return future.result()

footer_html = """
<style>
  .footer {
    font-size: 9px;
    color: #666;
    width: 100%;
    padding: 0 12mm;
    display: flex;
    justify-content: flex-end;  /* right-align */
    align-items: center;
  }
  /* Avoid unexpected page scaling artifacts */
  .footer * { font-family: Arial, sans-serif; }
</style>
<div class="footer">
  <span><span class="pageNumber"></span> of <span class="totalPages"></span></span>
</div>
"""

def ensure_playwright_browser():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # Test if chromium is available
            p.chromium.launch()
    except Exception as e:
        print("Installing Playwright Chromium browser...")
        try:
            subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
            print("Chromium browser installed successfully!")
        except subprocess.CalledProcessError as install_error:
            print(f"Failed to install Chromium: {install_error}")
            raise

logger = logging.getLogger(__name__)

#============= uisng playwright to convert html to pdf =============
# 1. create a complete HTML document with CSS styling for PDF generation
def create_pdf_html_document(body_html: str, company_name: str) -> str:
    """
    Create a complete HTML document with CSS styling for PDF generation.
    """
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Investment Report - {company_name}</title>
    <style>
        /* Reset default margins and padding */
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{ 
            font-family: 'Georgia', 'Times New Roman', serif; 
            line-height: 1.4; 
            color: #000000;
            margin: 0;
            padding: 0;
            font-size: 10pt;
        }}
        
        /* Enhanced paragraph spacing with 1.5 line spacing */
        p {{ 
            margin: 0.6em 0; 
            text-align: justify;
            orphans: 3;
            widows: 3;
            line-height: 1.5;
        }}
        
        /* Title page specific styling */
        h1:first-child {{ 
            font-size: 24pt; 
            font-weight: bold; 
            text-align: center !important;
            margin: 2em 0 1.5em 0;
            border-bottom: none;
            padding-bottom: 0;
            page-break-after: avoid;
            color: #000000;
        }}
        
        /* Ensure title page title is centered */
        .title-page-title {{
            text-align: center !important;
            font-size: 24pt;
            font-weight: bold;
            margin: 2em 0 1.5em 0;
            color: #000000;
        }}
        
        /* Regular H1 styling with enhanced spacing */
        h1 {{ 
            font-size: 20pt; 
            font-weight: bold; 
            margin: 2em 0 1em 0;
            border-bottom: 3px solid #000000;
            padding-bottom: 10px;
            page-break-after: avoid;
            color: #000000;
        }}
        
        /* H2 styling with enhanced spacing */
        h2 {{ 
            font-size: 16pt; 
            font-weight: bold; 
            margin: 1.8em 0 1em 0;
            border-bottom: 2px solid #000000;
            padding-bottom: 8px;
            page-break-after: avoid;
            color: #000000;
        }}
        
        /* H3 styling with enhanced spacing */
        h3 {{ 
            font-size: 14pt; 
            font-weight: bold; 
            margin: 1.5em 0 0.8em 0;
            page-break-after: avoid;
            color: #000000;
        }}
        
        /* H4 styling */
        h4 {{ 
            font-size: 12pt; 
            font-weight: bold; 
            margin: 1.2em 0 0.6em 0;
            page-break-after: avoid;
            color: #000000;
        }}
        
        /* Title page company info styling */
        .title-page-info {{ 
            text-align: center !important;
            margin: 2em 0;
            line-height: 2;
            font-size: 12pt;
        }}
        
        /* Ensure title page elements are properly centered */
        .title-page-info strong {{
            display: inline-block;
            margin: 0.2em 0;
        }}
        
        /* Special styling for key sections */
        a#table-of-contents + h2,
        a#executive-summary + h2,
        a#references + h2 {{
            text-align: center;
            font-size: 18pt;
            border-bottom: 3px solid #000000;
            padding-bottom: 10px;
            margin-bottom: 1.5em;
        }}
        
        /* List styling */
        ul {{
            list-style-type: disc;
            margin: 0.8em 0 0.8em 1.5em;
            padding: 0;
            line-height: 1.5;
        }}
        
        ol {{ 
            margin: 0.8em 0 0.8em 1.5em; 
            padding: 0;
            line-height: 1.5;
        }}
        
        li {{
            margin: 0.5em 0;
            line-height: 1.5;
            text-align: justify;
            word-wrap: break-word;
            hyphens: none;
        }}
        
        /* Prevent colon jumping in list items */
        li p {{
            text-align: justify;
            margin: 0.3em 0;
        }}
        
        /* Specific styling for bullet point content */
        li strong {{
            display: inline;
            white-space: nowrap;
        }}
        
        /* Prevent colon orphaning - keep colons with preceding words */
        li strong:after {{
            content: "";
            white-space: nowrap;
        }}
        
        /* General text formatting to prevent colon issues */
        .no-break {{
            white-space: nowrap;
        }}
        
        /* Improved word breaking for better text flow */
        p, li {{
            word-break: normal;
            overflow-wrap: break-word;
            hyphens: auto;
        }}
        
        /* Table styling */
        table {{ 
            width: 100%; 
            border-collapse: collapse; 
            margin: 0.5em 0;
            page-break-inside: avoid;
            font-size: 10pt;
        }}
        
        th, td {{ 
            border: 1px solid #bdc3c7; 
            padding: 6px 8px;
            text-align: left;
            vertical-align: top;
        }}
        
        th {{ 
            background-color: #f8f9fa; 
            font-weight: bold;
            color: #000000;
        }}
        
        /* Image styling */
        img {{ 
            max-width: 100%; 
            height: auto; 
        }}
        
        /* Strong/Bold text */
        strong, b {{ 
            font-weight: bold; 
            color: #000000;
        }}
        
        /* Code blocks */
        code {{ 
            background-color: #f8f9fa; 
            padding: 2px 4px; 
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 9pt;
        }}
        
        /* Horizontal rules */
        hr {{ 
            border: none; 
            border-top: 1px solid #bdc3c7; 
            margin: 0.5em 0;
        }}
        
        /* Blockquotes */
        blockquote {{ 
            margin: 1em 0; 
            padding: 0.8em 1em; 
            border-left: 3px solid #3498db; 
            background-color: #f8f9fa;
            font-style: italic;
            line-height: 1.5;
        }}
        
        /* Anchor styling */
        a {{ color: #0066cc; text-decoration: underline; }}
        
        /* Page settings */
        @page {{ 
            size: A4 portrait;
            margin: 20mm;
        }}
        
        /* Page break utilities */
        .page-break {{ page-break-before: always; }}
        .no-break {{ page-break-inside: avoid; }}
    </style>
</head>
<body>{body_html}</body>
</html>"""

# 2. create a standalone HTML document for chart rendering with maximum color preservation
def create_color_preserving_chart_html(chart_html: str, chartjs_src: Optional[str] = None) -> str:
    """
    Create a standalone HTML document for chart rendering with maximum color preservation.
    This version is optimized for software rendering (no GPU) while preserving colors.
    """
    return f"""<!DOCTYPE html>
<html style="background: white !important;">
<head>
    <meta charset="UTF-8">
    <meta name="color-scheme" content="light only">
    <meta name="supported-color-schemes" content="light">
    <meta name="theme-color" content="#ffffff">
    <script src="{chartjs_src or 'https://cdn.jsdelivr.net/npm/chart.js'}"></script>
    <style>
        /* CRITICAL: Force color rendering at every level */
        * {{
            -webkit-print-color-adjust: exact !important;
            color-adjust: exact !important;
            print-color-adjust: exact !important;
            -webkit-filter: none !important;
            filter: none !important;
            color-scheme: light !important;
            forced-color-adjust: none !important;
        }}
        
        html {{
            background: white !important;
            color-scheme: light !important;
            -webkit-color-scheme: light !important;
        }}
        
        body {{ 
            background: white !important;
            margin: 0 !important;
            padding: 20px !important;
            color-scheme: light !important;
            -webkit-color-scheme: light !important;
        }}
        
        canvas {{
            background: transparent !important;
            max-width: 100% !important;
            height: auto !important;
            image-rendering: -webkit-optimize-contrast !important;
            image-rendering: crisp-edges !important;
        }}
        
        .chartjs-render-monitor {{
            background: transparent !important;
        }}
        
        /* Force specific Chart.js element colors */
        .chartjs-tooltip {{
            background: rgba(0,0,0,0.8) !important;
            color: white !important;
        }}
        
        /* Prevent any grayscale filters */
        @media (prefers-color-scheme: dark) {{
            * {{
                filter: none !important;
                -webkit-filter: none !important;
            }}
        }}
    </style>
</head>
<body style="background: white !important;">
    {chart_html}
    <script>
        // Wait for DOM and Chart.js to load, then force color settings
        document.addEventListener('DOMContentLoaded', function() {{
            // Force Chart.js defaults for color preservation
            if (typeof Chart !== 'undefined') {{
                Chart.defaults.plugins.legend.labels.usePointStyle = true;
                Chart.defaults.color = '#000000';
                Chart.defaults.backgroundColor = 'rgba(255, 255, 255, 1)';
                Chart.defaults.borderColor = 'rgba(0, 0, 0, 0.1)';
                
                // Override any potential theme detection
                Chart.defaults.plugins.legend.labels.color = '#000000';
                Chart.defaults.scales = Chart.defaults.scales || {{}};
                Chart.defaults.scales.x = Chart.defaults.scales.x || {{}};
                Chart.defaults.scales.y = Chart.defaults.scales.y || {{}};
                Chart.defaults.scales.x.ticks = Chart.defaults.scales.x.ticks || {{}};
                Chart.defaults.scales.y.ticks = Chart.defaults.scales.y.ticks || {{}};
                Chart.defaults.scales.x.ticks.color = '#000000';
                Chart.defaults.scales.y.ticks.color = '#000000';
            }}
            
            // Force all canvas elements to use proper color space
            const canvases = document.querySelectorAll('canvas');
            canvases.forEach(canvas => {{
                const ctx = canvas.getContext('2d');
                if (ctx) {{
                    ctx.imageSmoothingEnabled = true;
                    ctx.imageSmoothingQuality = 'high';
                }}
            }});
        }});
    </script>
</body>
</html>"""

class ProgressCallback(Protocol):
    def __call__(self, update: Any) -> None: ...

async def test_chart_color_rendering(chart_html: str, test_output_path: str = "/tmp/test_chart.png") -> bool:
    """
    Test function to check if chart rendering preserves colors using Playwright.
    Returns True if successful, False otherwise.
    """
    try:
        chart_doc = create_color_preserving_chart_html(chart_html)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={'width': 800, 'height': 600})
            
            await page.set_content(chart_doc)
            await page.wait_for_function("typeof Chart !== 'undefined'", timeout=10000)
            await page.wait_for_selector("canvas", timeout=10000)
            await page.wait_for_timeout(2000)
            
            await page.screenshot(path=test_output_path, type='png')
            await browser.close()
            
        if os.path.exists(test_output_path):
            logger.info(f"Test chart saved to: {test_output_path}")
            return True
            
    except Exception as e:
        logger.error(f"Chart color test failed: {e}")
        return False
    
    return False

async def convert_report_to_pdf(
    markdown_content: str,
    output_filename: str,
    *,
    company_name: str,
    chartjs_src: Optional[str] = None
) -> bool:
    """
    Converts a Markdown string with embedded Chart.js blocks to a PDF using Playwright.
    Charts are rendered directly in the browser before PDF conversion.
    """

    temp_dir = tempfile.mkdtemp()
    image_paths = []
    
    try:
        # 1. Process chart blocks and replace with image placeholders
        async def chart_to_image_replacer(m: Match[str]) -> str:
            chart_html = m.group(1)
    
            # Use the specialized color-preserving HTML function
            chart_doc = create_color_preserving_chart_html(chart_html, chartjs_src)
            
            image_filename = f"chart_{len(image_paths)}.png"
            output_path = os.path.join(temp_dir, image_filename)
            
            # Render the chart as an image using Playwright
            logger.info(f"Rendering chart {len(image_paths)} with Playwright")
            
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(
                        headless=True,
                        args=[
                            '--no-sandbox',
                            '--disable-dev-shm-usage',
                            '--force-color-profile=srgb',
                            '--disable-background-timer-throttling',
                        ]
                    )
                    
                    page = await browser.new_page(
                        viewport={'width': 800, 'height': 600},
                        color_scheme='light'
                    )
                    
                    # Set the HTML content
                    await page.set_content(chart_doc)
                    
                    # Wait for Chart.js to be loaded
                    await page.wait_for_function("typeof Chart !== 'undefined'", timeout=10000)
                    logger.info(f"Chart.js loaded for chart {len(image_paths)}")
                    
                    # Wait for any canvas elements to be present
                    await page.wait_for_selector("canvas", timeout=10000)
                    
                    # Additional wait for Chart.js rendering and animations
                    await page.wait_for_timeout(2000)
                    
                    # Take screenshot with specific options for color preservation
                    await page.screenshot(
                        path=output_path,
                        type='png',
                        full_page=False,
                        clip={'x': 0, 'y': 0, 'width': 800, 'height': 600}
                    )
                    
                    await browser.close()
                    logger.info(f"Chart {len(image_paths)} rendered successfully with Playwright")
                    
            except Exception as e:
                logger.error(f"Failed to render chart with Playwright: {e}")
                return '<div style="text-align:center; color: red;">Chart could not be rendered</div>'
            
            # Verify the image was actually created
            if not os.path.exists(output_path):
                logger.error(f"Image file was not created at {output_path}")
                return '<div style="text-align:center; color: red;">Chart could not be rendered</div>'
            
            # Check image file size to ensure it's not empty
            file_size = os.path.getsize(output_path)
            logger.info(f"Generated chart image: {output_path}, size: {file_size} bytes")
            
            if file_size < 1000:  # Very small file might indicate rendering failure
                logger.warning(f"Chart image file size is suspiciously small: {file_size} bytes")
            
            image_paths.append(output_path)
            
            # Convert image to base64 and embed as data URI
            try:
                with open(output_path, 'rb') as img_file:
                    img_data = base64.b64encode(img_file.read()).decode('utf-8')
                data_uri = f"data:image/png;base64,{img_data}"
                logger.info(f"Successfully converted chart to base64, data URI length: {len(data_uri)}")
                return f'<div style="text-align:center; page-break-inside: avoid; margin: 20px 0;"><img src="{data_uri}" alt="Chart" style="max-width: 90%; height: auto; border: 1px solid #ddd; border-radius: 4px;"></div>'
            except Exception as e:
                logger.error(f"Failed to encode image as base64: {e}")
                return '<div style="text-align:center; color: red;">Chart encoding failed</div>'

        def chart_to_image_replacer_playwright_async(m: Match[str]) -> str:
            return run_async_in_thread(chart_to_image_replacer(m))

        pattern = re.compile(r'```html\n(.*?)\n```', re.DOTALL)

        # Ensure Playwright browser is installed
        ensure_playwright_browser()

    #    markdown_with_images = pattern.sub(chart_to_image_replacer_playwright_async, markdown_content)
        markdown_with_images = pattern.sub(chart_to_image_replacer_playwright_async, markdown_content)

        # 2. Convert the modified markdown (with images) to HTML
        body_html = markdown2.markdown(
            markdown_with_images,
            extras=["tables", "strike", "code-friendly", "header-ids"]
        )

        # 3. Create the complete HTML document for PDF generation
        html_doc = create_pdf_html_document(body_html, company_name)

        # 4. Generate PDF using Playwright
        await html_to_pdf_from_string_async(
            html_doc,
            output_filename,
            base_url=None,
            page_format="A4",
            margin_top="20mm",
            margin_right="20mm",
            margin_bottom="20mm",
            margin_left="20mm",
            landscape=False,
            scale=1.0,
            prefer_css_page_size=True,
            wait_for_selector=None,
            footer_html=footer_html,
            wait_time_ms=0,
            timeout_ms=45000,
            emulate_media="print"
        )

        logger.info(f"PDF successfully generated: {output_filename}")
        return True

    except Exception as e:
        logger.error(f"An error occurred during PDF conversion: {e}", exc_info=True)
        return False
    finally:
        # Clean up the temporary image files and directory
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


async def convert_markdown_file_to_pdf(
    md_path: str,
    output_filename: str,
    *,
    company_name: str,
    chartjs_src: Optional[str] = None
) -> bool:
    """
    Convenience wrapper to read a .md file and convert to PDF using Playwright.
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        md = f.read()
    return await convert_report_to_pdf(
        md,
        output_filename,
        company_name=company_name,
        chartjs_src=chartjs_src
    )


def validate_pdf_format(pdf_path: str) -> bool:
    """
    Validate that the generated PDF exists and has content.
    """
    try:
        if not os.path.exists(pdf_path):
            logger.error(f"PDF file does not exist: {pdf_path}")
            return False
        
        file_size = os.path.getsize(pdf_path)
        if file_size == 0:
            logger.error(f"PDF file is empty: {pdf_path}")
            return False
        
        # Basic validation - file exists and has content
        logger.info(f"PDF validation passed: {pdf_path} ({file_size} bytes)")
        return True
        
    except Exception as e:
        logger.error(f"Error validating PDF format: {e}")
        return False

async def html_to_pdf_from_string_async(
    html: str,
    output_pdf: str,
    base_url: Optional[str] = None,
    page_format: str = "A4",
    margin_top: str = "18mm",
    margin_right: str = "12mm",
    margin_bottom: str = "18mm",
    margin_left: str = "12mm",
    landscape: bool = False,
    scale: float = 1.0,
    prefer_css_page_size: bool = True,
    wait_for_selector: Optional[str] = None,
    footer_html: Optional[str] = None,
    wait_time_ms: int = 0,
    timeout_ms: int = 45000,
    emulate_media: str = "print",
) -> None:
    """
    Async: Render a raw HTML string to PDF using Playwright (Chromium).
    Intended for use inside an asyncio event loop (e.g., FastAPI endpoints).
    """


    async with async_playwright() as p:
        browser = await p.chromium.launch()  # headless by default
        context = await browser.new_context()
        page = await context.new_page()

        # Media emulation
        try:
            await page.emulate_media(media=emulate_media)
        except Exception:
            pass

        # Load content
        await page.set_content(html, wait_until="load", timeout=timeout_ms)

        # Wait for charts to render if requested
        if wait_for_selector:
            try:
                await page.wait_for_selector(wait_for_selector, state="visible", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                # Proceed even if selector didn't appear in time
                pass

        if wait_time_ms > 0:
            await page.wait_for_timeout(wait_time_ms)

        # Generate PDF
        await page.pdf(
            path=output_pdf,
            print_background=True,
            format=page_format,
            landscape=landscape,
            footer_template=footer_html,
            scale=scale,
            margin={"top": margin_top, "right": margin_right, "bottom": margin_bottom, "left": margin_left},
            prefer_css_page_size=prefer_css_page_size,
        )

        await browser.close()


