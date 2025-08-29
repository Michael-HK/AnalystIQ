
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import io
import base64
from contextlib import redirect_stdout, redirect_stderr
from typing import Optional
import logging

logger = logging.getLogger(__name__)
    

def execute_matplotlib_code_safely(code: str) -> Optional[str]:
    """
    Helper function to safely execute matplotlib code and return base64 image.
    Can be used independently for testing chart generation.
    """
    # VALIDATE CODE FIRST
    if not validate_python_chart_code(code):
        logger.error("Python code failed security validation")
        return None
    
    matplotlib.use('Agg')  # Non-interactive backend
    
    try:
        # Configure matplotlib for high-quality output
        plt.rcParams.update({
            'figure.dpi': 300,
            'savefig.dpi': 300,
            'savefig.bbox': 'tight',
            'font.family': 'serif',
            'font.serif': ['Times New Roman', 'DejaVu Serif'],
            'font.size': 11,
            'axes.titlesize': 14,
            'axes.labelsize': 12,
            'xtick.labelsize': 10,
            'ytick.labelsize': 10,
        })
        
        # Safe execution environment
        safe_globals = {
            '__builtins__': {
                # Basic Python functions
                'len': len, 'range': range, 'enumerate': enumerate,
                'zip': zip, 'list': list, 'dict': dict, 'str': str,
                'int': int, 'float': float, 'sum': sum, 'max': max, 
                'min': min, 'round': round, 'abs': abs, 'sorted': sorted,
                # Add these for matplotlib to work properly
                '__import__': __import__,
                'hasattr': hasattr,
                'getattr': getattr,
                'setattr': setattr,
                'isinstance': isinstance,
                'type': type,
                'bool': bool,
                'tuple': tuple,
                'set': set,
                # Math functions that might be needed
                'pow': pow,
            },
            # Pre-imported modules
            'plt': plt,
            'matplotlib': matplotlib,  # Add this
            'numpy': np,
            'np': np,
            'pandas': pd,
            'pd': pd
        }
        
        buffer = io.BytesIO()
        plt.clf()
        plt.close('all')
        
        # Execute code silently
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            exec(code, safe_globals)
            
            current_fig = plt.gcf()
            if current_fig.get_axes():
                current_fig.savefig(
                    buffer, 
                    format='png', 
                    dpi=300, 
                    bbox_inches='tight',
                    facecolor='white',
                    edgecolor='none'
                )
                buffer.seek(0)
                
                img_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
                plt.close(current_fig)
                buffer.close()
                
                return img_data
                
    except Exception as e:
        logger.error(f"Error executing matplotlib code: {e}")
        return None
    finally:
        plt.close('all')
        if 'buffer' in locals():
            buffer.close()
    
    return None


def validate_python_chart_code(code: str) -> bool:
    """
    Validates Python chart code for safety before execution.
    Returns True if code appears safe to execute.
    """
    dangerous_patterns = [
        'import os', 'import sys', 'import subprocess', 'import shutil',
        'open(', 'file(', 'exec(', 'eval(', '__import__',
        'globals()', 'locals()', 'input(', 'raw_input(',
        'exit()', 'quit()', 'reload(', 'delattr(', 'setattr(',
        'hasattr(', 'getattr(', '__'
    ]
    
    code_lower = code.lower()
    for pattern in dangerous_patterns:
        if pattern.lower() in code_lower:
            logger.warning(f"Potentially dangerous code pattern detected: {pattern}")
            return False
    
    return True