#!/usr/bin/env python3
"""
Debug script to extract and display component row parsing for a specific student.
This will help identify where the data misalignment is happening.
"""

import pdfplumber
import re
from pathlib import Path
import sys
sys.path.append('/home/vedantchalke36/pdf-parser/parser-api/api')
from mu_parser import parse_component_line

def parse_component_line_debug(line: str, prefix: str) -> list:
    """Parse component line using the FIXED version from mu_parser and show debug info"""
    content = re.sub(f'^{prefix}\\s+', '', line.strip())
    
    # Remove trailing summary info
    content = re.sub(r'\s+MARKS\s*$', '', content)
    content = re.sub(r'\s+\(\d+\)\s*(PASS|FAILED|FAIL)\s*$', '', content, flags=re.IGNORECASE)
    content = re.sub(r'\s+\.\.\.\s+P\s*$', '', content)
    content = re.sub(r'\s+\.\.\.\s*$', '', content)
    
    print(f"\n{prefix} Line Content: '{content}'")
    tokens = content.split()
    print(f"Tokens: {tokens}")
    
    # Use the FIXED parse_component_line function
    marks = parse_component_line(line, prefix)
    print(f"Final marks array: {marks}")
    return marks

# Find student block for seat 1012005 (Aditya Sanjay Dound)
pdf_path = "/home/vedantchalke36/pdf-parser/camelot-prototype/aids.pdf"

if Path(pdf_path).exists():
    print(f"Reading {pdf_path}...")
    
    with pdfplumber.open(pdf_path) as pdf:
        all_text = ""
        for page in pdf.pages:
            all_text += page.extract_text() + "\n"
        
        lines = all_text.split('\n')
        
        # Find the student block
        found = False
        for i, line in enumerate(lines):
            if '1012005' in line:
                print(f"\n{'='*80}")
                print(f"FOUND STUDENT: {line}")
                print(f"{'='*80}")
                found = True
                
                # Parse next ~10 lines to find component rows
                for j in range(i, min(i + 15, len(lines))):
                    current = lines[j].strip()
                    if current.startswith('T1 '):
                        parse_component_line_debug(current, 'T1')
                    elif current.startswith('O1 '):
                        parse_component_line_debug(current, 'O1')
                    elif current.startswith('E1 '):
                        parse_component_line_debug(current, 'E1')
                    elif current.startswith('I1 '):
                        parse_component_line_debug(current, 'I1')
                    elif current.startswith('TOT '):
                        print(f"\nTOT Line: {current[:100]}...")
                        break
                
                break
        
        if not found:
            print("Student 1012005 not found in PDF")
else:
    print(f"PDF file not found: {pdf_path}")
    print("Please update the pdf_path variable with the correct path")
