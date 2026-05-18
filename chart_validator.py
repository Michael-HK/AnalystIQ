
import re
import logging
import json
import os
from typing import List, Tuple, Optional
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log
)
from llama_index.llms.openrouter import OpenRouter
logger = logging.getLogger(__name__)

class ChartValidatorAgent:
    """
    Chart Validator Agent - Specialized in checking if chart code will fail rendering.
    Returns YES/NO with reasons for potential rendering failures.
    """
    def __init__(self):
        """Initialize the Chart Validator Agent with OpenRouter."""
        self.llm = OpenRouter(
            model=os.getenv("OPENROUTER_CHART_VALIDATOR_MODEL", "xiaomi/mimo-v2.5"),
            api_key=os.getenv("OPENROUTER_API_KEY"),
            context_window=100000,
            temperature=0.1,
            max_tokens=int(os.getenv("OPENROUTER_CHART_VALIDATOR_MAX_TOKENS", "2500")),
        )
        self.chart_validation_prompt = self._create_validation_prompt()
    
    def _create_validation_prompt(self) -> str:
        """Create the system prompt for chart validation (YES/NO assessment)."""
        return """You are a Chart Validation Specialist focused on evaluating HTML chart visualization code for both rendering viability AND professional quality standards.

Your task is to analyze HTML chart code and determine:
1. Will it fail to render properly in a web browser?
2. Does it meet professional chart specifications and quality standards?

**ANALYSIS AREAS:**

**A. TECHNICAL RENDERING:**
1. **HTML Structure**: Valid HTML syntax, proper DOCTYPE, head, and body tags
2. **Chart.js Integration**: Chart.js CDN loading and canvas element setup
3. **JavaScript Syntax**: Syntax errors, missing brackets, semicolons, etc.
4. **Chart.js Configuration**: Proper chart configuration object structure
5. **Data Format**: Valid data arrays and labels
6. **Canvas Element**: Canvas exists with proper ID and is accessible
7. **Script Execution**: Chart.js constructor and methods called correctly

**B. CHART RENDERING DIMENSIONS & CONTAINER QUALITY:**
8. **Container & Dimension Integrity**: 
   - The container div MUST use `position: relative` for proper Chart.js rendering
   - The container SHOULD have explicit height (e.g., 350px) and max-width (e.g., 560px)
   - The canvas element should NOT have fixed width/height HTML attributes that conflict with the CSS container dimensions
   - `maintainAspectRatio` MUST be set to `false` to prevent Chart.js from shrinking the chart inside the container
   - Layout padding must be minimal (e.g., top: 10, right: 15, bottom: 10, left: 15) — excessive padding (40px+) causes chart shrinkage
9. **Chart Fullness & Professional Fill**:
   - The chart's plotting area (bars, lines, pie segments, data points) MUST visually fill the container without excessive empty whitespace
   - If `maintainAspectRatio` is set to `true` or omitted, the chart may shrink inside its container leaving unprofessional empty space — FLAG this
   - If layout padding values exceed 25px on any side, the chart will appear shrunk — FLAG this
   - If the canvas has fixed width/height HTML attributes AND the container has different CSS dimensions, there may be a conflict — FLAG this
10. **Empty Chart Detection**:
   - Check that datasets contain actual data (non-empty data arrays)
   - Check that labels array is non-empty
   - A chart with empty datasets or no labels will render as a blank canvas — FLAG as CRITICAL

**C. PROFESSIONAL QUALITY & SPECIFICATIONS:**
11. **Color Scheme**: Professional colors (NO gray/monochrome), complementary palette (max 6-7 colors)
12. **CRITICAL LEGEND-TO-COLOR MAPPING RULE** (MOST COMMON VIOLATION):
   - **FUNDAMENTAL PRINCIPLE: Number of legends = Number of colors**
   - **1 LEGEND (or NO LEGEND) = 1 BLUE COLOR FOR ALL BARS** - This is the most frequently violated rule
   - **MULTIPLE LEGENDS = MULTIPLE COLORS** - Each legend entry must correspond to one distinct color
   
   **SPECIFIC RULES:**
   - Single-dataset charts: DISABLE legend entirely (redundant) OR if legend is shown, ALL bars MUST be BLUE (use blue shades like #4A90E2, #3B82F6, #2563EB)
   - Multiple-dataset charts: Each dataset gets unique color matching its legend entry exactly
   
   **EXAMPLES OF VIOLATIONS (MOST COMMON ERRORS):**
   - ❌ WRONG: Chart has 1 legend entry but bars are colored green, purple, orange (different colors per bar)
   - ❌ WRONG: Chart has 1 legend entry but bars are NOT blue
   - ❌ WRONG: Chart shows "Investment" as single legend but bars have different colors for different time periods
   - ❌ WRONG: Chart shows "TSMC" as single legend but bars have cyan, purple, orange colors for different dates
   - ❌ WRONG: Chart shows "Performance Improvement (%)" as single legend but bars are colored differently
   - ❌ WRONG: Chart has 1 legend but uses green, red, or any color other than blue
   
   **CORRECT EXAMPLES:**
   - ✅ CORRECT: Chart has 1 legend "Investment" → ALL bars are BLUE color (e.g., #4A90E2) (x-axis shows different periods)
   - ✅ CORRECT: Chart has no legend → ALL bars are BLUE color (e.g., #3B82F6) (x-axis labels provide context)
   - ✅ CORRECT: Chart has 3 legends "Actual Q3 2025", "Estimated Q3 2025", "Q3 2024" → 3 distinct colors (teal, orange, purple)
   - ✅ CORRECT: Chart has 2 legends "CPU Performance", "GPU Performance" → 2 distinct colors
   
13. **Visual Design**: Appropriate height (300-400px), clear axis labels, professional styling, proper spacing
14. **Data Presentation**: No redundant data tables when chart is present, appropriate chart type for data
15. **Innovation & Style**: Modern, stylish appearance, innovative visual elements where appropriate
16. **Single-Entity Color Consistency**: 
   - When bars represent the SAME metric/entity across different x-axis categories, use ONE color
   - X-axis variation (different dates, companies, categories) does NOT justify different bar colors
   - Different bar colors are ONLY appropriate when you have multiple datasets (multiple legends)
17. **Data Access & Function Parameter Matching**: 
   - CRITICAL: Check function calls match their expected parameter types and data structure access patterns
   - CORRECT: `getBarGradient(chart, gradientColors[index][0], gradientColors[index][1])` when function expects individual parameters
   - WRONG: `getBarGradient(chart, gradientColors[index], gradientColors[index])` when function expects individual values but receives arrays
   - Validate function calls match expected parameter types (individual values vs arrays/objects)
   - Check array/object access patterns match function expectations
   - Detect mismatched data structure access (e.g., accessing array elements when function expects arrays, or vice versa)
   - Validate proper indexing for nested data structures
18. **Accessibility**: Clear labels, readable fonts, appropriate contrast

**COMMON RENDERING FAILURES:**
- Missing/incorrect Chart.js CDN, canvas ID mismatches, JavaScript syntax errors
- Invalid Chart.js configuration, malformed data arrays, undefined variables
- Empty datasets or labels arrays causing blank canvas rendering
- Missing CDN script tag (chart will not render at all)

**COMMON DIMENSION/SHRINKAGE ISSUES:**
- `maintainAspectRatio: true` (or omitted) causing chart to shrink inside its container, leaving large empty whitespace — the outer box meets dimensions but the chart is tiny inside
- Excessive layout padding (40px+ on any side) shrinking the visible chart area
- Canvas element with fixed width/height HTML attributes conflicting with CSS container dimensions
- Missing `position: relative` on the container div causing Chart.js to not properly calculate dimensions
- Container div without explicit height, causing the chart to collapse or render at wrong size

**COMMON QUALITY ISSUES:**
- **MOST CRITICAL**: Single legend but multiple bar colors (e.g., 1 legend "Investment" but bars are blue, green, orange)
- **MOST CRITICAL**: No legend but multiple bar colors for same metric (e.g., revenue bars in different colors per quarter)
- Gray/monochrome colors, unnecessary legends on single-dataset charts
- Poor color schemes, missing axis labels, unprofessional styling, poor spacing/formatting
- CRITICAL: Mismatched function calls (passing wrong data types when function expects specific parameter types)
- Inconsistent entity colors, inappropriate chart heights, redundant data presentation

**OUTPUT FORMAT:**
You MUST respond with a JSON object containing:

```json
{{
  "will_fail": "YES" or "NO",
  "confidence": "HIGH", "MEDIUM", or "LOW", 
  "meets_specifications": "YES" or "NO",
  "professional_quality": "EXCELLENT" | "GOOD" | "FAIR" | "POOR",
  "issues": [
    {{
      "category": "RENDERING" | "QUALITY" | "SPECIFICATIONS",
      "type": "HTML_STRUCTURE" | "CHARTJS_INTEGRATION" | "JAVASCRIPT_SYNTAX" | "DATA_FORMAT" | "CANVAS_ELEMENT" | "SCRIPT_EXECUTION" | "CONTAINER_DIMENSIONS" | "CHART_SHRINKAGE" | "EMPTY_CHART" | "COLOR_SCHEME" | "LEGEND_COLOR_MAPPING" | "VISUAL_DESIGN" | "DATA_PRESENTATION" | "INNOVATION_STYLE" | "ENTITY_CONSISTENCY" | "DATA_ACCESS" | "ACCESSIBILITY",
      "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
      "description": "Detailed description of the issue",
      "fix_suggestion": "Specific suggestion on how to fix this issue",
      "improvement_suggestion": "Optional suggestion to make the chart more professional/innovative"
    }}
  ],
  "style_recommendations": [
    "Specific recommendations to enhance chart professionalism and innovation"
  ],
  "overall_assessment": "Brief summary of the chart's rendering viability and quality"
}}
```

**ANALYSIS INSTRUCTIONS:**
- Set "will_fail" to "YES" if ANY critical rendering issues are found
- Set "meets_specifications" to "NO" if chart violates professional standards or system prompt requirements
- Rate "professional_quality" based on overall visual appeal, innovation, and adherence to best practices
- Provide specific, actionable fix suggestions for each issue
- Include style recommendations to enhance professionalism and innovation
- Focus on both technical functionality AND visual excellence

**PROFESSIONAL CHART SPECIFICATIONS TO ENFORCE:**
- Professional color schemes (NO gray/monochrome)
- Proper legend usage (disable for single-dataset bar charts)
- Appropriate dimensions (300-400px height, max-width 560px)
- Clear axis labels and titles
- Consistent entity colors across charts
- Modern, stylish appearance
- No redundant data presentation
- Container uses `position: relative` with explicit height
- `maintainAspectRatio: false` to prevent chart shrinkage
- Minimal layout padding (no more than 25px on any side)
- Canvas element without fixed width/height HTML attributes conflicting with container
- Non-empty datasets and labels (no blank canvas rendering)

**⚠️ CRITICAL VALIDATION FOCUS (CHECK THESE FIRST):**

**STEP 0: CHECK FOR EMPTY/UNRENDERABLE CHARTS:**
1. Does the chart have non-empty data arrays in all datasets?
2. Does the chart have a non-empty labels array?
3. Is the Chart.js CDN script tag present?
4. If ANY of these are missing → FLAG as CRITICAL "EMPTY_CHART" issue

**STEP 0.5: CHECK FOR CHART SHRINKAGE/DIMENSION ISSUES:**
1. Is `maintainAspectRatio` set to `false`? (If `true` or missing → FLAG as HIGH "CHART_SHRINKAGE")
2. Are layout padding values reasonable (≤25px per side)? (If excessive → FLAG as HIGH "CHART_SHRINKAGE")
3. Does the container div have `position: relative`? (If missing → FLAG as MEDIUM "CONTAINER_DIMENSIONS")
4. Does the canvas have fixed width/height HTML attributes? (If yes and they conflict with container CSS → FLAG as HIGH "CONTAINER_DIMENSIONS")
5. Does the container have explicit height set? (If missing → FLAG as MEDIUM "CONTAINER_DIMENSIONS")

**STEP 1: COUNT THE LEGENDS and CHECK BAR COLORS:**
Before evaluating anything else, COUNT THE LEGENDS and CHECK BAR COLORS:
1. How many legend entries are in this chart? (0, 1, or multiple?)
2. How many different colors are used for bars? (1 color or multiple colors?)
3. If 1 legend (or no legend): Are ALL bars BLUE? (Check for blue shades like #4A90E2, #3B82F6, #2563EB, etc.)
4. DOES: Number of legend entries = Number of bar color schemes?
   - If 1 legend (or no legend) but MULTIPLE bar colors → FLAG as CRITICAL ISSUE with type "LEGEND_COLOR_MAPPING"
   - If 1 legend (or no legend) but bars are NOT BLUE → FLAG as CRITICAL ISSUE with type "LEGEND_COLOR_MAPPING"
   - If multiple legends but colors don't match datasets → FLAG as CRITICAL ISSUE with type "LEGEND_COLOR_MAPPING"

Here is the HTML chart code to analyze:

{chart_code}

Provide your comprehensive analysis:"""
    
    async def validate_chart(self, chart_code: str) -> dict:
        """
        Validate chart code and return validation results.
        
        Args:
            chart_code: The HTML chart code to validate
            
        Returns:
            Dictionary with validation results including will_fail, issues, etc.
        """
        try:
            validation_prompt = self.chart_validation_prompt.format(chart_code=chart_code)
            response = await self.llm.acomplete(validation_prompt)
            
            # Parse JSON response
            response_text = response.text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:-3].strip()
            
            validation_result = json.loads(response_text)
            
            logger.info(f"Chart validation result: {validation_result.get('will_fail', 'UNKNOWN')}")
            return validation_result
            
        except Exception as e:
            logger.error(f"Error validating chart: {str(e)}")
            return {
                "will_fail": "UNKNOWN",
                "confidence": "LOW",
                "issues": [],
                "overall_assessment": f"Validation error: {str(e)}"
            }

class ChartCorrectorAgent:
    """
    Chart Corrector Agent - Specialized in fixing specific chart rendering issues.
    Takes chart code and specific issues to fix, returns corrected code.
    """
    
    def __init__(self):
        """Initialize the Chart Corrector Agent with OpenRouter."""
        self.llm = OpenRouter(
            model=os.getenv("OPENROUTER_CHART_CORRECTOR_MODEL", "xiaomi/mimo-v2.5"),
            api_key=os.getenv("OPENROUTER_API_KEY"),
            context_window=100000,
            temperature=0.1,
            max_tokens=int(os.getenv("OPENROUTER_CHART_CORRECTOR_MAX_TOKENS", "4000")),
        )
        self.chart_correction_prompt = self._create_correction_prompt()
    
    def _create_correction_prompt(self) -> str:
        """Create the system prompt for comprehensive chart correction."""
        return """You are a Chart Correction Specialist focused on fixing rendering issues AND enhancing professional quality in HTML chart visualization code.

Your task is to fix specific issues identified by the Chart Validator while creating professional, innovative, and stylish charts.

**CORRECTION PRINCIPLES:**
1. **Data Integrity**: NEVER modify actual data values or data points
2. **Targeted Fixes**: Address all specific issues mentioned in the validation report
3. **Professional Excellence**: Apply professional styling, colors, and design standards
4. **Innovation & Style**: Create modern, visually appealing, innovative charts
5. **Specification Compliance**: Ensure adherence to system prompt requirements
6. **Dimension & Rendering Quality**: Ensure charts fully fill their container without excessive empty whitespace

**CRITICAL PRESERVATION RULES:**
- Preserve all data arrays and labels exactly as provided
- Preserve chart type and configuration structure
- Preserve responsive settings as originally specified

**PROFESSIONAL ENHANCEMENT REQUIREMENTS:**

**CRITICAL LEGEND-TO-COLOR MAPPING RULE** (HIGHEST PRIORITY FIX):
- **FUNDAMENTAL PRINCIPLE: Number of legends = Number of colors**
- **1 LEGEND (or NO LEGEND) = 1 BLUE COLOR FOR ALL BARS** - This is your PRIMARY correction focus
- **MULTIPLE LEGENDS = MULTIPLE COLORS** - Each legend gets one distinct color

**SPECIFIC CORRECTION RULES:**
1. **Single-dataset charts** (1 or 0 legends):
   - If chart has 1 legend: Make ALL bars BLUE (use blue shades: '#4A90E2', '#3B82F6', '#2563EB', '#1D4ED8', '#1E40AF')
   - If chart has no legend: Make ALL bars BLUE (use blue shades: '#4A90E2', '#3B82F6', '#2563EB', '#1D4ED8', '#1E40AF')
   - X-axis labels provide the differentiation, NOT bar colors
   - NEVER use different colors per bar when there's only one legend
   - MANDATORY: Single-legend or no-legend charts MUST use blue color

2. **Multi-dataset charts** (2+ legends):
   - Each legend entry gets its own unique color
   - All bars for "Actual Q3 2025" → same color (e.g., teal)
   - All bars for "Estimated Q3 2025" → different color (e.g., orange)
   - Colors must be visually distinct and professional

**EXAMPLES TO GUIDE YOUR CORRECTIONS:**
- ❌ BEFORE: 1 legend "Investment" + bars colored [green, red, purple, orange] → ✅ AFTER: 1 legend "Investment" + ALL bars BLUE (#4A90E2)
- ❌ BEFORE: 1 legend "Investment" + ALL bars green → ✅ AFTER: 1 legend "Investment" + ALL bars BLUE (#3B82F6)
- ❌ BEFORE: 1 legend "Performance (%)" + bars colored [cyan, purple, orange] → ✅ AFTER: 1 legend "Performance (%)" + ALL bars BLUE (#2563EB)
- ❌ BEFORE: No legend + bars colored [red, green, orange, yellow] → ✅ AFTER: No legend + ALL bars BLUE (#1D4ED8)
- ❌ BEFORE: No legend + ALL bars green → ✅ AFTER: No legend + ALL bars BLUE (#1E40AF)
- ✅ ALREADY CORRECT: 3 legends + 3 distinct colors (one per legend) → No change needed

**Color Schemes:**
- Use professional, vibrant colors (NO gray/monochrome)
- Single-legend or no-legend charts: MUST use BLUE (use shades like '#4A90E2', '#3B82F6', '#2563EB', '#1D4ED8', '#1E40AF')
- Multi-dataset charts: Use complementary palette (max 6-7 distinct colors, one per dataset)

**Visual Design:**
- Set appropriate height (300-400px)
- Add clear, descriptive axis labels and titles
- Apply modern, stylish appearance with proper spacing and formatting
- Ensure good contrast and readability
- Add subtle animations or hover effects where appropriate
- Professional spacing between elements, proper margins and padding

**CHART DIMENSION & RENDERING QUALITY FIXES (CRITICAL):**
When the validator flags CONTAINER_DIMENSIONS, CHART_SHRINKAGE, or EMPTY_CHART issues, apply these corrections:

1. **Fix Chart Shrinkage (MOST COMMON DIMENSION ISSUE):**
   - Set `maintainAspectRatio: false` in Chart.js options (prevents chart from shrinking to maintain a square ratio)
   - Set `responsive: true` in Chart.js options
   - Use minimal layout padding: set layout.padding.top to 10, layout.padding.right to 15, layout.padding.bottom to 10, layout.padding.left to 15. Do NOT use excessive padding (40px+).

2. **Fix Container Dimensions:**
   - Ensure container div has `position: relative` (required for Chart.js to calculate dimensions correctly)
   - Ensure container div has explicit height (e.g., `height: 350px`)
   - Ensure container div has `max-width: 560px; width: 100%;`
   - Remove fixed width/height HTML attributes from the canvas element (let CSS handle sizing)
   - Use `box-sizing: border-box` on the container

3. **Fix Empty Charts:**
   - If datasets have empty data arrays, this chart CANNOT be fixed — flag as unfixable
   - Ensure the Chart.js CDN script tag is present: `<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>`
   - Ensure the canvas element exists with a valid, unique ID
   - Ensure `document.getElementById()` references the correct canvas ID

**CORRECT CONTAINER TEMPLATE:**
```
<div style="position: relative; max-width: 560px; width: 100%; height: 350px; margin: auto; padding: 10px; box-sizing: border-box;">
  <canvas id="uniqueChartId"></canvas>
</div>
```

**CORRECT CHART.JS OPTIONS TEMPLATE:**
```
options: {{
  responsive: true,
  maintainAspectRatio: false,
  layout: {{ padding: {{ top: 10, right: 15, bottom: 10, left: 15 }} }},
  ...
}}
```

**Data Access & Function Parameter Matching:**
- CRITICAL: Check function calls match their expected parameter types and data structure access patterns
- CORRECT: `getBarGradient(chart, gradientColors[index][0], gradientColors[index][1])` when function expects individual parameters
- WRONG: `getBarGradient(chart, gradientColors[index], gradientColors[index])` when function expects individual values but receives arrays
- Validate function calls match expected parameter types (individual values vs arrays/objects)
- Check array/object access patterns match function expectations
- Detect mismatched data structure access (e.g., accessing array elements when function expects arrays, or vice versa)
- Validate proper indexing for nested data structures
- Ensure data access patterns are consistent with function signatures

**Innovation Elements:**
- Modern gradient colors or professional solid colors
- Smooth animations and transitions
- Clean, minimalist design
- Professional typography
- Subtle shadows or borders for visual appeal

**COMMON CORRECTIONS:**

**Rendering Fixes:**
- Fix JavaScript syntax errors (missing brackets, semicolons, quotes)
- Correct Chart.js CDN URLs or loading issues
- Fix canvas element ID mismatches
- Correct malformed Chart.js configuration objects
- Fix undefined variables or function calls

**Quality Enhancements:**
- **TOP PRIORITY**: Fix legend-to-color mismatch - if 1 legend or no legend, make ALL bars BLUE; if multiple legends, each gets distinct color
- **TOP PRIORITY**: Fix multi-colored single-dataset charts (e.g., Investment chart with bars in different colors → ALL bars BLUE)
- **TOP PRIORITY**: Fix non-blue single-dataset charts (e.g., Single legend with green bars → ALL bars BLUE)
- Replace gray/monochrome with professional colors
- Remove unnecessary legends from single-dataset charts OR ensure BLUE coloring if legend is kept
- CRITICAL: Fix mismatched function calls (ensure function signature matches parameter types and data access patterns)
- Add proper axis labels and titles with professional spacing
- Improve color schemes and visual appeal
- Ensure consistent entity colors across all data points
- Add modern styling and visual elements with proper formatting

**CORRECTION PRIORITY ORDER:**
1. FIRST: Fix empty chart issues (missing data, missing CDN, blank canvas)
2. SECOND: Fix chart shrinkage/dimension issues (maintainAspectRatio, container, padding)
3. THIRD: Fix legend-to-color mapping (1 legend or no legend = BLUE for all bars)
4. FOURTH: Fix technical rendering issues (syntax, CDN, canvas)
5. FIFTH: Enhance visual design and styling
6. SIXTH: Add professional touches and animations

**⚠️ CRITICAL CORRECTION FOCUS (FIX THESE FIRST):**

Before making any other changes:

**STEP 0: Fix empty/unrenderable charts:**
1. Check if datasets have data — if empty, chart cannot render
2. Check if CDN script tag is present — add if missing
3. Check if canvas ID matches getElementById — fix mismatches

**STEP 0.5: Fix chart shrinkage/dimension issues:**
1. Set `maintainAspectRatio: false` in options (MANDATORY)
2. Set layout padding to reasonable values (max 25px per side)
3. Ensure container has `position: relative` and explicit height (350px)
4. Remove fixed width/height from canvas element HTML attributes
5. Ensure container has `max-width: 560px; width: 100%; box-sizing: border-box;`

**STEP 1: Fix legend-to-color mapping:**
Identify and fix the legend-to-color mapping:
1. Count the legend entries in the chart (0, 1, or multiple)
2. Count the different bar colors being used
3. If single-dataset chart (0 or 1 legend):
   - IMMEDIATELY fix by making ALL bars BLUE
   - Choose one BLUE shade from: '#4A90E2', '#3B82F6', '#2563EB', '#1D4ED8', '#1E40AF'
   - Apply this BLUE color to ALL bars in the backgroundColor array
   - This applies even if bars are currently a single non-blue color
4. If multi-dataset chart (2+ legends):
   - Ensure each legend has its own distinct color
5. Only after fixing colors, proceed with other enhancements

**OUTPUT FORMAT:**
Return ONLY the corrected HTML code wrapped in ```html...``` markdown block. 
CRITICAL: Do NOT include any additional ```html...``` wrappers inside your response.

```html
[Professional, innovative, corrected HTML code with issues fixed - NO nested wrappers]
```

**INPUT:**
- Original chart code: {chart_code}
- Issues to fix: {issues}

Transform this chart into a professional, innovative, and error-free visualization:"""
    
    async def correct_chart(self, chart_code: str, issues: list) -> str:
        """
        Correct chart code based on identified issues.
        
        Args:
            chart_code: The HTML chart code to correct
            issues: List of issues to fix
            
        Returns:
            Corrected HTML chart code
        """
        try:
            # Format issues for the prompt
            issues_text = "\n".join([
                f"- [{issue.get('category', 'UNKNOWN')}] {issue.get('type', 'UNKNOWN')} ({issue.get('severity', 'MEDIUM')}): "
                f"{issue.get('description', '')}\n"
                f"  Fix: {issue.get('fix_suggestion', 'No suggestion')}\n" +
                (f"  Enhancement: {issue.get('improvement_suggestion', '')}\n" if issue.get('improvement_suggestion') else "")
                for issue in issues
            ])
            
            correction_prompt = self.chart_correction_prompt.format(
                chart_code=chart_code,
                issues=issues_text
            )
            
            response = await self.llm.acomplete(correction_prompt)
            
            # Extract HTML from response
            corrected_code = self._extract_html_from_response(response.text.strip())
            
            logger.info("Chart correction completed")
            return corrected_code
            
        except Exception as e:
            logger.error(f"Error correcting chart: {str(e)}")
            return chart_code  # Return original if correction fails
    
    def _extract_html_from_response(self, response_text: str) -> str:
        """Extract HTML code from LLM response and ensure no nested wrappers."""
        # Look for ```html...``` blocks
        html_match = re.search(r'```html\s*(.*?)\s*```', response_text, re.DOTALL)
        if html_match:
            extracted_html = html_match.group(1).strip()
        else:
            # If no markdown block found, use the response as is
            extracted_html = response_text.strip()
        
        # Remove any nested ```html...``` wrappers that might be inside
        extracted_html = self._remove_nested_html_wrappers(extracted_html)
        
        return extracted_html
    
    def _remove_nested_html_wrappers(self, html_code: str) -> str:
        """Remove any nested ```html...``` wrappers from the HTML code."""
        # Remove any ```html at the beginning
        html_code = re.sub(r'^```html\s*', '', html_code, flags=re.MULTILINE)
        
        # Remove any ``` at the end
        html_code = re.sub(r'\s*```$', '', html_code, flags=re.MULTILINE)
        
        # Remove any internal ```html...``` blocks (keep only the content)
        while True:
            nested_match = re.search(r'```html\s*(.*?)\s*```', html_code, re.DOTALL)
            if nested_match:
                # Replace the nested block with just its content
                html_code = html_code[:nested_match.start()] + nested_match.group(1).strip() + html_code[nested_match.end():]
            else:
                break
        
        return html_code.strip()

class ChartValidationSystem:
    """
    Complete Chart Validation System combining Validator and Corrector agents
    with iterative validation loop (max 3 iterations) and retry mechanism using tenacity.
    """
    
    def __init__(self, max_retries: int = 3, retry_min_wait: int = 1, retry_max_wait: int = 10):
        """
        Initialize the complete chart validation system with tenacity-based retry.
        
        Args:
            max_retries: Maximum number of retries for failed operations (default: 3)
            retry_min_wait: Minimum wait time between retries in seconds (default: 1)
            retry_max_wait: Maximum wait time between retries in seconds (default: 10)
        """
        self.validator = ChartValidatorAgent()
        self.corrector = ChartCorrectorAgent()
        self.max_iterations = 3
        self.max_retries = max_retries
        self.retry_min_wait = retry_min_wait
        self.retry_max_wait = retry_max_wait
    
    def _create_retry_decorator(self, operation_name: str):
        """
        Create a tenacity retry decorator with configured parameters.
        
        Args:
            operation_name: Name of the operation for logging
            
        Returns:
            Configured retry decorator
        """
        return retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(
                multiplier=1,
                min=self.retry_min_wait,
                max=self.retry_max_wait
            ),
            retry=retry_if_exception_type(Exception),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            after=after_log(logger, logging.INFO),
            reraise=True
        )
    
    async def _validate_with_retry(self, chart_code: str, iteration: int) -> Optional[dict]:
        """
        Validate chart with tenacity retry mechanism.
        
        Args:
            chart_code: The HTML chart code to validate
            iteration: Current iteration number for logging
            
        Returns:
            Validation result dict or None if failed after retries
        """
        @self._create_retry_decorator(f"chart validation (iteration {iteration})")
        async def _do_validate():
            return await self.validator.validate_chart(chart_code)
        
        try:
            return await _do_validate()
        except Exception as e:
            logger.error(f"Chart validation failed after {self.max_retries} retries on iteration {iteration}: {str(e)}")
            return None
    
    async def _correct_with_retry(self, chart_code: str, issues: list, iteration: int) -> Optional[str]:
        """
        Correct chart with tenacity retry mechanism.
        
        Args:
            chart_code: The HTML chart code to correct
            issues: List of issues to fix
            iteration: Current iteration number for logging
            
        Returns:
            Corrected chart code or None if failed after retries
        """
        @self._create_retry_decorator(f"chart correction (iteration {iteration})")
        async def _do_correct():
            return await self.corrector.correct_chart(chart_code, issues)
        
        try:
            return await _do_correct()
        except Exception as e:
            logger.error(f"Chart correction failed after {self.max_retries} retries on iteration {iteration}: {str(e)}")
            return None
    
    async def validate_and_correct_chart(self, chart_code: str) -> str:
        """
        Main method to validate and correct a single chart with iterative loop and tenacity retry.
        
        Args:
            chart_code: The HTML chart code to validate and correct
            
        Returns:
            Validated and corrected HTML chart code
        """
        current_code = chart_code
        iteration = 0
        
        logger.info("Starting chart validation and correction process")
        
        while iteration < self.max_iterations:
            iteration += 1
            logger.info(f"Validation iteration {iteration}/{self.max_iterations}")
            
            # Step 1: Validate current code with tenacity retry
            validation_result = await self._validate_with_retry(current_code, iteration)
            
            # If validation failed after all retries, return current code
            if validation_result is None:
                logger.error(f"Chart validation failed after retries on iteration {iteration}, returning current code")
                return current_code
            
            # Check if validation failed or succeeded
            will_fail = validation_result.get('will_fail', 'UNKNOWN')
            meets_specifications = validation_result.get('meets_specifications', 'NO')
            professional_quality = validation_result.get('professional_quality', 'POOR')
            
            # Chart needs correction if it will fail to render OR doesn't meet specifications OR has poor quality
            needs_correction = (
                will_fail == 'YES' or 
                meets_specifications == 'NO' or 
                professional_quality in ['POOR', 'FAIR']
            )
            
            if not needs_correction:
                logger.info(f"Chart validation passed on iteration {iteration} - will_fail: {will_fail}, meets_specs: {meets_specifications}, quality: {professional_quality}")
                break
            elif will_fail == 'UNKNOWN':
                logger.warning(f"Chart validation result unknown on iteration {iteration}, stopping")
                break
            
            # Step 2: If validation failed, get issues and correct
            issues = validation_result.get('issues', [])
            if not issues:
                logger.warning(f"No specific issues identified on iteration {iteration}, stopping")
                break
            
            logger.info(f"Chart needs correction on iteration {iteration} - will_fail: {will_fail}, meets_specs: {meets_specifications}, quality: {professional_quality}")
            logger.info(f"Found {len(issues)} issues to fix on iteration {iteration}")
            
            # Step 3: Correct the chart with tenacity retry
            corrected_code = await self._correct_with_retry(current_code, issues, iteration)
            
            # If correction failed after all retries, return current code
            if corrected_code is None:
                logger.error(f"Chart correction failed after retries on iteration {iteration}, returning current code")
                return current_code
            
            # Check if correction made any changes
            if corrected_code == current_code:
                logger.warning(f"No changes made by corrector on iteration {iteration}, stopping")
                break
            
            current_code = corrected_code
            logger.info(f"Chart correction completed for iteration {iteration}")
        
        if iteration >= self.max_iterations:
            logger.warning(f"Reached maximum iterations ({self.max_iterations}) for chart validation")
        
        return current_code
    
    async def _process_chart_with_retry(self, chart_code: str, chart_number: int) -> Optional[str]:
        """
        Process a single chart with tenacity retry mechanism.
        
        Args:
            chart_code: The HTML chart code to process
            chart_number: Chart number for logging
            
        Returns:
            Corrected chart code or None if failed after retries
        """
        @self._create_retry_decorator(f"chart {chart_number} validation and correction")
        async def _do_process():
            return await self.validate_and_correct_chart(chart_code)
        
        try:
            return await _do_process()
        except Exception as e:
            logger.error(f"Chart {chart_number} processing failed after {self.max_retries} retries: {str(e)}")
            return None
    
    async def validate_and_replace_charts(self, response_text: str, max_retries: Optional[int] = None) -> str:
        """
        Extract, validate, and correct all charts in the response text with tenacity retry.
        
        Args:
            response_text: The full LLM response containing chart blocks
            max_retries: Override default max_retries for this operation (optional)
            
        Returns:
            Response text with validated and corrected charts
        """
        # Use custom retry count if provided, otherwise use instance default
        retry_count = max_retries if max_retries is not None else self.max_retries
        original_max_retries = self.max_retries
        
        try:
            # Temporarily override max_retries if custom value provided
            if max_retries is not None:
                self.max_retries = max_retries
            
            updated_response = response_text
            charts = self.extract_html_charts(response_text)
            
            if not charts:
                logger.info("No HTML charts found in response")
                return response_text
            
            logger.info(f"Found {len(charts)} HTML charts to validate and correct (max retries: {retry_count})")
            
            # Track successful and failed chart corrections
            successful_corrections = 0
            failed_corrections = 0
            
            # Process charts in reverse order to maintain correct indices
            for chart_index, (chart_code, start_index, end_index) in enumerate(reversed(charts), 1):
                chart_number = len(charts) - chart_index + 1
                logger.info(f"Processing chart {chart_number}/{len(charts)}")
                
                try:
                    # Validate and correct the chart with tenacity retry
                    corrected_chart = await self._process_chart_with_retry(chart_code, chart_number)
                    
                    # If correction failed after retries, use original chart
                    if corrected_chart is None:
                        logger.warning(f"Chart {chart_number} correction failed after retries, keeping original chart")
                        failed_corrections += 1
                        corrected_chart = chart_code
                    else:
                        successful_corrections += 1
                    
                    # Ensure the corrected chart has no wrappers before adding our own
                    clean_chart = self._ensure_no_html_wrappers(corrected_chart)
                    
                    # Replace the chart in the response with exactly one wrapper
                    corrected_block = f"```html\n{clean_chart}\n```"
                    updated_response = (
                        updated_response[:start_index] +
                        corrected_block +
                        updated_response[end_index:]
                    )
                    
                    logger.info(f"Chart {chart_number} processing completed")
                    
                except Exception as e:
                    logger.error(f"Unexpected error processing chart {chart_number}: {str(e)}")
                    failed_corrections += 1
                    # Continue with next chart if one fails
                    continue
            
            # Log summary
            logger.info(f"Chart validation summary: {successful_corrections} successful, {failed_corrections} failed out of {len(charts)} total charts")
            
            return updated_response
            
        finally:
            # Restore original max_retries
            self.max_retries = original_max_retries
    
    def _ensure_no_html_wrappers(self, html_code: str) -> str:
        """Ensure HTML code has no ```html...``` wrappers."""
        # Remove any ```html at the beginning
        html_code = re.sub(r'^```html\s*', '', html_code, flags=re.MULTILINE)
        
        # Remove any ``` at the end  
        html_code = re.sub(r'\s*```$', '', html_code, flags=re.MULTILINE)
        
        # Remove any internal ```html...``` blocks (keep only the content)
        while True:
            nested_match = re.search(r'```html\s*(.*?)\s*```', html_code, re.DOTALL)
            if nested_match:
                # Replace the nested block with just its content
                html_code = html_code[:nested_match.start()] + nested_match.group(1).strip() + html_code[nested_match.end():]
            else:
                break
        
        return html_code.strip()
    
    def extract_html_charts(self, text: str) -> List[Tuple[str, int, int]]:
        """
        Extract all HTML chart blocks from text.
        
        Args:
            text: Text containing HTML chart blocks
            
        Returns:
            List of tuples (chart_code, start_index, end_index)
        """
        charts = []
        pattern = r'```html\s*(.*?)\s*```'
        
        for match in re.finditer(pattern, text, re.DOTALL):
            chart_code = match.group(1).strip()
            start_index = match.start()
            end_index = match.end()
            
            # Only include if it contains Chart.js or canvas elements (likely a chart)
            if ('chart' in chart_code.lower() or 
                'canvas' in chart_code.lower() or 
                'Chart(' in chart_code):
                charts.append((chart_code, start_index, end_index))
                logger.info(f"Extracted chart code block at position {start_index}-{end_index}")
        
        return charts