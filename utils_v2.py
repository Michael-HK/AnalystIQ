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
import subprocess
import tempfile
from typing import Protocol, Any, Optional
from datetime import datetime

import pdfkit
import markdown2
import logging
from typing import Match
from plot_utils import execute_matplotlib_code_safely

logger = logging.getLogger(__name__)

class ProgressCallback(Protocol):
    def __call__(self, update: Any) -> None: ...


# =========================
# Authoring/Build Helpers
# =========================

def extract_live_chart_blocks(md: str) -> str:
    """
    Unwrap fenced ```html ... ``` code blocks that actually contain Chart.js visualizations
    into live HTML so that markdown2 does NOT escape them as <pre><code>.

    Rules:
    - Only unwrap blocks that contain '<canvas' or 'new Chart(' (heuristic).
    - Strip any <script src="...chart(.min).js"> inside the block; wrapper injects Chart.js once.
    - Return other fenced blocks as-is (they will remain code blocks).
    """
    fenced_html_pattern = r'```html\s*(.*?)\s*```'

    def looks_like_chart_block(text: str) -> bool:
        t = text.lower()
        return ('<canvas' in t) or ('new chart(' in t)

    def repl(m: re.Match) -> str:
        inner = m.group(1)
        if not looks_like_chart_block(inner):
            return m.group(0)  # keep non-chart fenced HTML as code
        # Remove any Chart.js CDN/local script includes; wrapper will add one global include.
        inner = re.sub(
            r'<script[^>]+src=["\'][^"\']*chart(\.min)?\.js[^"\']*["\'][^>]*>\s*</script>',
            '',
            inner,
            flags=re.IGNORECASE | re.DOTALL
        )
        # Remove surrounding triple backticks that some LLMs may echo inside the block body
        inner = inner.replace('```', '')
        return inner  # live HTML+inline script

    return re.sub(fenced_html_pattern, repl, md, flags=re.IGNORECASE | re.DOTALL)


def sanitize_html_content(html_content: str, keep_inline_scripts: bool = True) -> str:
    """
    Minimal sanitization that:
    - Removes inline event handlers (onload, onerror, onclick, etc.).
    - Preserves the Chart.js external script tag (in the wrapper, not inside body).
    - Preserves inline scripts (needed to instantiate charts) unless disabled.
    NOTE: For untrusted input, use a robust allowlist sanitizer instead.
    """
    # Strip common event handler attributes
    for attr in [
        'onload','onerror','onclick','onmouseover','onfocus',
        'onmouseenter','onmouseleave','onmousemove','onmousedown',
        'onmouseup','onkeypress','onkeydown','onkeyup'
    ]:
        html_content = re.sub(
            rf'\s{attr}\s*=\s*(".*?"|\'.*?\'|[^\s>]+)',
            '',
            html_content,
            flags=re.IGNORECASE | re.DOTALL
        )

    # Drop external <script src=...> in body except chart.js (which should be injected by wrapper anyway).
    # Keep inline <script> for chart init if requested.
    def script_replacer(m: re.Match) -> str:
        open_tag = m.group(1)
        tag_lower = open_tag.lower()

        # If external script:
        if 'src=' in tag_lower:
            # If someone inlines Chart.js in body, drop it (wrapper loads globally in <head>)
            return ''
        # Inline scripts: keep if allowed (needed for charts)
        return m.group(0) if keep_inline_scripts else ''

    html_content = re.sub(
        r'(<script\b[^>]*>)(.*?)(</script>)',
        script_replacer,
        html_content,
        flags=re.IGNORECASE | re.DOTALL
    )

    return html_content


def _wrap_html_document(body_html: str, chartjs_src: Optional[str] = None) -> str:
    """
    Wraps body HTML into a full document and ensures Chart.js is available.
    If chartjs_src is provided, it will be used (e.g., file:///abs/path/chart.min.js).
    Otherwise uses a CDN.
    """
    if chartjs_src:
        chart_tag = f'<script src="{chartjs_src}"></script>'
    else:
        chart_tag = '<script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>'

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Report</title>
  <base href="."> <!-- Add this -->
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  {chart_tag}
  <style>
    html, body {{ background: #fff; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, "Noto Sans",
                   "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji", sans-serif;
      line-height: 1.6;
      color: #333;
      max-width: 8.5in;
      margin: 0 auto;
      padding: 0.5in;
      font-size: 12pt;
    }}
    h1, h2, h3 {{
      color: #1a2c42;
      border-bottom: 2px solid #e1e4e8;
      padding-bottom: 10px;
      margin-top: 24px;
      page-break-after: avoid;
    }}
    
    /* Page break support */
    div[style*="page-break-after: always"] {{
      page-break-after: always;
    }}
    h1 {{ font-size: 24pt; }}
    h2 {{ font-size: 18pt; }}
    h3 {{ font-size: 14pt; }}

    table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 20px;
      page-break-inside: avoid;
    }}
    th, td {{
      border: 1px solid #dfe2e5;
      padding: 10px;
      text-align: left;
      font-size: 11pt;
      vertical-align: top;
    }}
    th {{ background-color: #f6f8fa; font-weight: bold; }}

    .chart-container {{
      margin: 20px 0;
      page-break-inside: avoid;
      text-align: center;
      min-height: 360px;
      background: #fff;
      border: 1px solid #e1e4e8;
      border-radius: 6px;
      padding: 12px;
    }}
    /* Fixed canvas size for predictable print rendering */
    canvas {{
      width: 560px !important;
      height: 360px !important;
      max-width: 100% !important;
      page-break-inside: avoid;
      display: block;
      margin: 0 auto;
    }}

    pre {{
      background-color: #f6f8fa;
      padding: 16px;
      border-radius: 6px;
      overflow-x: auto;
      page-break-inside: avoid;
    }}
    code {{
      background-color: #f6f8fa;
      padding: 2px 4px;
      border-radius: 3px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }}

    /* References styling */
    h2#references {{
      color: #1a2c42;
      border-bottom: 2px solid #e1e4e8;
      padding-bottom: 10px;
      margin-top: 30px;
    }}
    #references-list {{
      list-style: none;
      padding-left: 0;
      margin: 10px 0 0 0;
    }}
    #references-list li {{
      margin: 6px 0;
      font-size: 10.5pt;
      line-height: 1.4;
      text-indent: -24px;
      padding-left: 24px;
      word-break: break-word;
    }}
    #references-list li b {{
      color: #0366d6;
    }}

    hr {{
      border: none;
      border-top: 2px solid #e1e4e8;
      margin: 30px 0;
    }}

    @media print {{
      body {{
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      .chart-container {{
        break-inside: avoid;
        -webkit-break-inside: avoid;
        page-break-inside: avoid;
      }}
      canvas {{
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
    }}
  </style>
</head>
<body>
  {body_html}
  <script>
    // Make Chart.js render predictably for print
    if (typeof Chart !== 'undefined') {{
      Chart.defaults.responsive = false;       // fixed size canvas for PDF
      Chart.defaults.maintainAspectRatio = false;
      Chart.defaults.animation = false;
      Chart.defaults.interaction = {{ intersect: false }};
      Chart.defaults.plugins.legend.labels.usePointStyle = true;
      Chart.defaults.plugins.legend.labels.boxWidth = 12;
      Chart.defaults.scale.grid.color = '#e1e4e8';
      Chart.defaults.scale.ticks.color = '#586069';
      Chart.defaults.color = '#24292e';
    }}

    // Signal wkhtmltopdf when ready; allow time for inline chart init scripts to run
    (function() {{
      var attempts = 0, maxAttempts = 40;
      function done() {{
        try {{ window.status = 'ready'; }} catch (e) {{}}
      }}
      function check() {{
        attempts++;
        var canvases = document.querySelectorAll('canvas');
        var ok = true;
        canvases.forEach(function(c) {{
          if (!c.width || !c.height) ok = false;
        }});
        if (ok || attempts >= maxAttempts) {{
          setTimeout(done, 100); // slight defer
        }} else {{
          setTimeout(check, 150);
        }}
      }}
      if (document.readyState === 'complete') {{
        setTimeout(check, 400);
      }} else {{
        window.addEventListener('load', function() {{ setTimeout(check, 400); }});
      }}
    }})();
  </script>
</body>
</html>"""


def convert_report_to_pdf(
    markdown_content: str,
    output_filename: str,
    *,
    company_name: str,
    chartjs_src: Optional[str] = None,
    keep_inline_scripts: bool = True
) -> bool:
    """
    Convert Markdown (that may include live HTML blocks with Chart.js) to PDF using wkhtmltopdf 0.12.6.

    - markdown_content: Markdown string (your .md file contents).
    - output_filename: Target PDF path.
    - company_name: The name of the company for the report header.
    - chartjs_src: Optional Chart.js path/URL. For offline use, pass file:///abs/path/chart.min.js.
    - keep_inline_scripts: Keep inline <script> blocks (required for chart init).
    """
    try:
        if not shutil.which('wkhtmltopdf'):
            raise FileNotFoundError("wkhtmltopdf not found in system PATH")

        # 1) Convert any fenced chart code blocks into live HTML before markdown2
        markdown_content = extract_live_chart_blocks(markdown_content)

        # 2) Convert Markdown to HTML
        body_html = markdown2.markdown(
            markdown_content,
            extras=["tables", "fenced-code-blocks", "strike", "code-friendly"]
        )

        # 3) Minimal sanitization: keep chart init scripts; drop external body scripts
        body_html = sanitize_html_content(body_html, keep_inline_scripts=keep_inline_scripts)

        # 4) Wrap in full HTML with Chart.js in <head>
        html_doc = _wrap_html_document(body_html, chartjs_src=chartjs_src)

        # 5) wkhtmltopdf options suitable for charts
        options = {
            'enable-javascript': None,
            'no-stop-slow-scripts': None,
            'window-status': 'ready',
            'javascript-delay': 4000,  # fallback timeout; charts should signal readiness earlier
            'encoding': 'UTF-8',
            'page-size': 'A4',
            'margin-top': '0.75in',
            'margin-right': '0.75in',
            'margin-bottom': '0.75in',
            'margin-left': '0.75in',
            'dpi': 300,
            'image-dpi': 300,
            'disable-smart-shrinking': None,
            'print-media-type': None,
            'load-error-handling': 'ignore',
            # Professional headers and footers
            'header-left': f'{company_name} - Investment Analysis',
            'header-font-size': '9',
            'header-spacing': '5',
            'footer-left': f'Generated by AgentInvest on {datetime.now().strftime("%Y-%m-%d")}',
            'footer-right': 'Page [page] of [topage]',
            'footer-font-size': '9',
            'footer-spacing': '5',
        }

        # Allow local files when using file:/// chartjs_src or other local assets
        if chartjs_src and chartjs_src.lower().startswith('file://'):
            options['enable-local-file-access'] = None

        # 6) Generate PDF via subprocess for better stderr capture
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_file:
            temp_file.write(html_doc)
            temp_html_path = temp_file.name

        try:
            cmd = ['wkhtmltopdf']
            for key, value in options.items():
                if value is None:
                    cmd.append(f'--{key}')
                else:
                    cmd.extend([f'--{key}', str(value)])
            cmd.extend([temp_html_path, output_filename])

            logger.info(f"Generating PDF report at: {output_filename}")
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=180  # 3 minutes safety
            )

            if result.returncode == 0 and os.path.exists(output_filename) and os.path.getsize(output_filename) > 0:
                logger.info("PDF generation successful.")
                return True

            logger.error("PDF generation failed.")
            logger.error(f"Return code: {result.returncode}")
            logger.error(f"STDOUT: {result.stdout}")
            logger.error(f"STDERR: {result.stderr}")
            return False

        finally:
            try:
                os.unlink(temp_html_path)
            except Exception:
                pass

    except (OSError, FileNotFoundError) as e:
        logger.error("\n" + "=" * 60)
        logger.error("CRITICAL ERROR: `wkhtmltopdf` not found or inaccessible.")
        logger.error("=" * 60)
        logger.error("`pdfkit` requires the `wkhtmltopdf` command-line tool to be installed.")
        logger.error("Please install the stable 0.12.6 version for your OS.")
        logger.error("Downloads page: https://wkhtmltopdf.org/downloads.html")
        logger.error("\nDo NOT use wkhtmltopdf with untrusted HTML/JS.")
        logger.error("=" * 60 + "\n")
        logger.error(f"Specific error: {e}")
        return False
    except Exception as e:
        logger.error("\n--- An unexpected error occurred during PDF conversion ---")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {e}")
        logger.error("\nPossible causes:")
        logger.error("• Chart blocks still wrapped in code fences (ensure extract_live_chart_blocks runs)")
        logger.error("• Network blocked for CDN (use chartjs_src='file:///abs/path/chart.min.js')")
        logger.error("• Invalid or crashing inline Chart.js init code")
        logger.error("• Incompatible wkhtmltopdf build for your OS")
        return False


def convert_markdown_file_to_pdf(
    md_path: str,
    output_filename: str,
    *,
    company_name: str,
    chartjs_src: Optional[str] = None,
    keep_inline_scripts: bool = True
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
        chartjs_src=chartjs_src,
        keep_inline_scripts=keep_inline_scripts
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


def convert_report_to_pdf_v2(
    markdown_content: str,
    output_filename: str,
    *,
    company_name: str,
    headless: bool = True
) -> bool:
    """
    Converts a Markdown string with embedded Python matplotlib blocks to a PDF.
    It executes the Python code to generate charts, converts them to base64 images, 
    embeds them, and then generates the PDF.
    """
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        # 1. Extract and execute Python code blocks, replace with base64 images
        def python_chart_to_image_replacer(m: Match[str]) -> str:
            python_code = m.group(1)
            
            # plot and generate the chart
            img_base64 = execute_matplotlib_code_safely(python_code)
            
            if img_base64:
                data_uri = f"data:image/png;base64,{img_base64}"
                return f'''<div style="text-align:center; page-break-inside: avoid; margin: 20px 0;">
                    <img src="{data_uri}" alt="Chart" style="max-width: 90%; height: auto; border: 1px solid #ddd; border-radius: 4px;">
                </div>'''
            else:
                return '<div style="text-align:center; color: red;">Chart generation failed</div>'

        # Extract Python code blocks and replace with images
        pattern = re.compile(r'```python\n(.*?)\n```', re.DOTALL)
        markdown_with_images = pattern.sub(python_chart_to_image_replacer, markdown_content)

        # 2. Convert the modified markdown (with images) to HTML
        body_html = markdown2.markdown(
            markdown_with_images,
            extras=["tables", "strike", "code-friendly"]
        )

        # 3. Wrap in a full HTML document for PDF generation
        html_doc = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>{company_name} - Investment Analysis Report</title>
            <base href=".">
            <style>
                body {{ 
                    font-family: 'Times New Roman', serif; 
                    line-height: 1.6; 
                    max-width: 8.5in; 
                    margin: 0 auto; 
                    padding: 0.5in;
                    color: #333;
                }}
                h1, h2, h3 {{ 
                    border-bottom: 2px solid #e1e4e8; 
                    padding-bottom: 10px; 
                    page-break-after: avoid;
                    color: #2c3e50;
                }}
                h1 {{ font-size: 24px; }}
                h2 {{ font-size: 20px; }}
                h3 {{ font-size: 16px; }}
                table {{ 
                    width: 100%; 
                    border-collapse: collapse; 
                    page-break-inside: avoid;
                    margin: 15px 0;
                }}
                th, td {{ 
                    border: 1px solid #dfe2e5; 
                    padding: 10px; 
                    text-align: left;
                }}
                th {{ 
                    background-color: #f6f8fa;
                    font-weight: bold;
                }}
                img {{ 
                    max-width: 100%; 
                    height: auto;
                    display: block;
                    margin: 0 auto;
                }}
                .chart-container {{
                    page-break-inside: avoid;
                    margin: 20px 0;
                }}
                ul, ol {{
                    margin: 10px 0;
                    padding-left: 30px;
                }}
                li {{
                    margin: 5px 0;
                }}
                p {{
                    margin: 10px 0;
                    text-align: justify;
                }}
                code {{
                    background-color: #f1f3f4;
                    padding: 2px 4px;
                    border-radius: 3px;
                    font-family: 'Courier New', monospace;
                }}
                blockquote {{
                    border-left: 4px solid #dfe2e5;
                    margin: 0;
                    padding-left: 16px;
                    color: #6a737d;
                }}
            </style>
        </head>
        <body>{body_html}</body>
        </html>
        """

        # 4. Generate the PDF with enhanced options
        options = {
            'page-size': 'A4',
            'margin-top': '0.75in',
            'margin-right': '0.75in',
            'margin-bottom': '0.75in',
            'margin-left': '0.75in',
            'encoding': "UTF-8",
            'no-outline': None,
            'enable-local-file-access': None,
            'header-left': f'{company_name} - Investment Analysis',
            'header-font-size': '9',
            'header-spacing': '5',
            'header-font-name': 'Times New Roman',
            'footer-left': f'Generated by AgentInvest on {datetime.now().strftime("%Y-%m-%d")}',
            'footer-right': 'Page [page] of [topage]',
            'footer-font-size': '9',
            'footer-spacing': '5',
            'footer-font-name': 'Times New Roman',
            'print-media-type': None,
            'disable-smart-shrinking': None,
        }
        
        pdfkit.from_string(html_doc, output_filename, options=options)
        logger.info(f"PDF successfully generated: {output_filename}")
        
        return True

    except Exception as e:
        logger.error(f"An error occurred during PDF conversion: {e}", exc_info=True)
        return False
    finally:
        # 5. Clean up
        shutil.rmtree(temp_dir, ignore_errors=True)