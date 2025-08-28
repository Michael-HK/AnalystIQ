
"""
Utilities to turn a Markdown report (with HTML chart blocks) into a PDF using wkhtmltopdf.

Install wkhtmltopdf 0.12.6 from: https://wkhtmltopdf.org/downloads.html
All downloads are via GitHub releases. Current stable series: 0.12.6 (June 11, 2020).

SECURITY WARNING (from project docs):
Do not use wkhtmltopdf with any untrusted HTML — sanitize user-supplied HTML/JS,
otherwise it can lead to complete server takeover. Only use trusted, sanitized content.
"""

import os
import re
import shutil
import tempfile
import subprocess
import base64
from typing import Protocol, Any, Optional, Match
from datetime import datetime
import html

import pdfkit
import markdown2
from html2image import Html2Image
import logging

logger = logging.getLogger(__name__)

class ProgressCallback(Protocol):
    def __call__(self, update: Any) -> None: ...

def convert_report_to_pdf(
    markdown_content: str,
    output_filename: str,
    *,
    company_name: str,
    chartjs_src: Optional[str] = None
) -> bool:
    """
    Converts a Markdown string with embedded Chart.js blocks to a PDF.
    It renders the charts as images first, embeds them, and then generates the PDF.
    """
    temp_dir = tempfile.mkdtemp()
    hti = Html2Image(
        output_path=temp_dir,
        custom_flags=[
            '--no-sandbox',
            '--disable-gpu', 
            '--disable-dev-shm-usage',
            '--disable-extensions',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--disable-features=TranslateUI',
            '--disable-ipc-flooding-protection',
            '--disable-background-networking',
            '--disable-sync',
            '--disable-default-apps',
            '--disable-web-security',
            '--headless',
            '--virtual-time-budget=5000'
        ]
    )
    image_paths = []
    
    try:
        # 1. Isolate chart blocks and replace them with image placeholders
        def chart_to_image_replacer(m: Match[str]) -> str:
            chart_html = m.group(1)
            
            # Prepare a full HTML document for the chart to be rendered
            chart_doc = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <script src="{chartjs_src or 'https://cdn.jsdelivr.net/npm/chart.js'}"></script>
                <style>
                    body {{ margin: 0; padding: 20px; background: white; }}
                    canvas {{ max-width: 100%; height: auto; }}
                </style>
            </head>
            <body>
                {chart_html}
            </body>
            </html>
            """
            
            image_filename = f"chart_{len(image_paths)}.png"
            output_path = os.path.join(temp_dir, image_filename)
            
            # Render the chart as an image with higher quality
            hti.screenshot(
                html_str=chart_doc,
                save_as=image_filename,
                size=(800, 600)  # Larger size for better quality
            )
            
            # Verify the image was actually created
            if not os.path.exists(output_path):
                logger.error(f"Image file was not created at {output_path}")
                return f'<div style="text-align:center; color: red;">Chart could not be rendered</div>'
            
            image_paths.append(output_path)
            
            # Convert image to base64 and embed as data URI
            try:
                with open(output_path, 'rb') as img_file:
                    img_data = base64.b64encode(img_file.read()).decode('utf-8')
                data_uri = f"data:image/png;base64,{img_data}"
                return f'<div style="text-align:center; page-break-inside: avoid; margin: 20px 0;"><img src="{data_uri}" alt="Chart" style="max-width: 90%; height: auto; border: 1px solid #ddd; border-radius: 4px;"></div>'
            except Exception as e:
                logger.error(f"Failed to encode image as base64: {e}")
                return f'<div style="text-align:center; color: red;">Chart encoding failed</div>'

        pattern = re.compile(r'```html\n(.*?)\n```', re.DOTALL)
        markdown_with_images = pattern.sub(chart_to_image_replacer, markdown_content)

        # 2. Convert the modified markdown (with images) to HTML
        body_html = markdown2.markdown(
            markdown_with_images,
            extras=["tables", "strike", "code-friendly", "header-ids"]
        )

        # 3. Wrap in a full HTML document for PDF generation
        html_doc = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="UTF-8"><title>Report</title>
          <base href=".">
          <style>
            body {{ font-family: sans-serif; line-height: 1.6; max-width: 8.5in; margin: 0 auto; padding: 0.5in; }}
            h1, h2, h3 {{ border-bottom: 2px solid #e1e4e8; padding-bottom: 10px; page-break-after: avoid; }}
            table {{ width: 100%; border-collapse: collapse; page-break-inside: avoid; }}
            th, td {{ border: 1px solid #dfe2e5; padding: 10px; }}
            th {{ background-color: #f6f8fa; }}
            img {{ max-width: 100%; height: auto; }}
            ul, ol {{ margin: 1em 0; padding-left: 2em; }}
            li {{ margin: 0.5em 0; }}
          </style>
        </head>
        <body>{body_html}</body>
        </html>
        """

        # 4. Generate the PDF with built-in TOC
        options = {
            'page-size': 'A4',
            'margin-top': '0.75in', 'margin-right': '0.75in',
            'margin-bottom': '0.75in', 'margin-left': '0.75in',
            'encoding': "UTF-8",
        #    'enable-local-file-access': None,
        #    'outline': None,                 # Enable PDF bookmarks/outline for navigation
            'outline-depth': '3',           # Include up to H3 in outline
            'print-media-type': None,       # Use print CSS media type
            'header-left': f'{company_name} - Investment Analysis',
            'header-font-size': '9', 'header-spacing': '5',
            'footer-left': f'Generated by AgentInvest on {datetime.now().strftime("%Y-%m-%d")}',
            'footer-right': 'Page [page] of [topage]',
            'footer-font-size': '9', 'footer-spacing': '5',
        }
        
        pdfkit.from_string(html_doc, output_filename, options=options)
        
        return True

    except Exception as e:
        logger.error(f"An error occurred during PDF conversion: {e}", exc_info=True)
        return False
    finally:
        # 5. Clean up the temporary image files and directory
        shutil.rmtree(temp_dir)


def convert_markdown_file_to_pdf(
    md_path: str,
    output_filename: str,
    *,
    company_name: str,
    chartjs_src: Optional[str] = None
) -> bool:
    """
    Convenience wrapper to read a .md file and convert to PDF.
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        md = f.read()
    return convert_report_to_pdf(
        md,
        output_filename,
        company_name=company_name,
        chartjs_src=chartjs_src
    )


def verify_wkhtmltopdf_installation() -> bool:
    try:
        result = subprocess.run(['wkhtmltopdf', '--version'],
                                capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logger.info(f"wkhtmltopdf is installed: {result.stdout.strip()}")
            # Current stable series is 0.12.6 (released June 11, 2020).
            return True
        logger.error(f"wkhtmltopdf returned error code {result.returncode}")
        return False
    except Exception as e:
        logger.error(f"Error checking wkhtmltopdf installation: {e}")
        return False