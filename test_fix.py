#!/usr/bin/env python3
"""
Test script to verify the directory creation fix works correctly.
"""

import os

def test_directory_creation():
    """Test that we can create the generated_reports directory."""
    try:
        # Test the same path logic used in agent.py
        reports_dir = "generated_reports"
        os.makedirs(reports_dir, exist_ok=True)
        
        # Try to create a test file
        test_file = os.path.join(reports_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("Test successful!")
        
        # Clean up
        os.remove(test_file)
        os.rmdir(reports_dir)
        
        print("✅ Directory creation test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Directory creation test failed: {e}")
        return False

if __name__ == "__main__":
    test_directory_creation()
