
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
            /* Reset default margins and padding */
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            
            body {{ 
              font-family: 'Georgia', 'Times New Roman', serif; 
              line-height: 1.4; 
              color: #333;
              margin: 0;
              padding: 0;
              font-size: 11pt;
            }}
            
            /* Paragraph spacing optimization */
            p {{ 
              margin: 0.4em 0; 
              text-align: justify;
              orphans: 3;
              widows: 3;
            }}
            
            /* Header styling with reduced spacing */
            h1 {{ 
              font-size: 18pt; 
              font-weight: bold; 
              margin: 0.8em 0 0.4em 0; 
              border-bottom: 2px solid #2c3e50; 
              padding-bottom: 8px;
              page-break-after: avoid;
              color: #2c3e50;
            }}
            
            h2 {{ 
              font-size: 14pt; 
              font-weight: bold; 
              margin: 0.6em 0 0.3em 0; 
              border-bottom: 1px solid #34495e; 
              padding-bottom: 6px;
              page-break-after: avoid;
              color: #34495e;
            }}
            
            h3 {{ 
              font-size: 12pt; 
              font-weight: bold; 
              margin: 0.5em 0 0.2em 0;
              page-break-after: avoid;
              color: #34495e;
            }}
            
            /* Table styling with tighter spacing */
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
              background-color: #ecf0f1; 
              font-weight: bold;
              color: #2c3e50;
            }}
            
            /* List styling with reduced spacing */
            ul, ol {{ 
              margin: 0.3em 0 0.3em 1.5em; 
              padding: 0;
            }}
            
            li {{ 
              margin: 0.2em 0;
              line-height: 1.3;
            }}
            
            /* Image styling */
            img {{ 
              max-width: 100%; 
              height: auto; 
              margin: 0.5em 0;
              display: block;
            }}
            
            /* Strong/Bold text */
            strong, b {{ 
              font-weight: bold; 
              color: #2c3e50;
            }}
            
            /* Emphasis/Italic text */
            em, i {{ 
              font-style: italic; 
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
              margin: 0.5em 0; 
              padding: 0.3em 0.8em; 
              border-left: 3px solid #3498db; 
              background-color: #f8f9fa;
              font-style: italic;
            }}
            
            /* Page break utilities */
            .page-break {{ page-break-before: always; }}
            .no-break {{ page-break-inside: avoid; }}
            
            /* Anchor styling */
            a {{ color: #3498db; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
          </style>
        </head>
        <body>{body_html}</body>
        </html>
        """

        # 4. Generate the PDF with optimized spacing
        options = {
            # Page setup
            'page-size': 'A4',
            'orientation': 'Portrait',
            'encoding': 'UTF-8',
            
            # Optimized margins to reduce white space
            'margin-top': '0.6in',      # Reduced from 0.75in
            'margin-right': '0.6in',    # Reduced from 0.75in  
            'margin-bottom': '0.6in',   # Reduced from 0.75in
            'margin-left': '0.6in',     # Reduced from 0.75in
            
            # Header settings with reduced spacing
            'header-left': f'{company_name} - Investment Analysis',
            'header-font-size': '8',    # Reduced from 9
            'header-spacing': '3',      # Reduced from 5
            'header-font-name': 'Arial',
            
            # Footer settings with reduced spacing
            'footer-left': f'Generated by AgentInvest on {datetime.now().strftime("%Y-%m-%d")}',
            'footer-right': 'Page [page] of [topage]',
            'footer-font-size': '8',    # Reduced from 9
            'footer-spacing': '3',      # Reduced from 5
            'footer-font-name': 'Arial',
            
            # Print optimization
            'print-media-type': None,
            'no-pdf-compression': None,
            'dpi': 300,                 # High DPI for better quality
            
            # Layout optimization
            'disable-smart-shrinking': None,  # Prevent automatic shrinking
            'zoom': 1.0,               # No zoom scaling
            'viewport-size': '1280x1024',
            
            # Content optimization
            'minimum-font-size': 8,     # Prevent fonts from being too small
            'image-quality': 95,        # High image quality
            'image-dpi': 300,          # High DPI for images
            
            # PDF structure
            'outline': None,            # Enable PDF bookmarks
            'outline-depth': 3,         # Include up to H3 in outline
            'title': f'Investment Report - {company_name}',
            
            # Performance optimization
            'lowquality': False,        # High quality output
            'enable-local-file-access': None,
            'keep-relative-links': None,
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