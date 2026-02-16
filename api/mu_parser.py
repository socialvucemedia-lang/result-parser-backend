#!/usr/bin/env python3
"""
Complete MU Result PDF Parser v2 using pdfplumber.
Extracts student records with high accuracy and outputs JSON
matching the existing format used by the Next.js frontend.

Key features:
- Handles cross-page ERN splits
- Accurate SGPA extraction from TOT line end
- Total marks from I1 line (XXX) pattern
- Robust name parsing excluding "Repeater" status
"""

import pdfplumber
import json
import re
import sys
from pathlib import Path
from typing import Optional


# ─── Subject Mapping ─────────────────────────────────────────────────────────

SUBJECT_NAMES = {
    "10411": "Applied Mathematics-I",
    "10412": "Applied Physics",
    "10413": "Applied Chemistry",
    "10414": "Engineering Mechanics",
    "10415": "Basic Electrical & Electronics Engineering",
    "10416": "Applied Physics Lab",
    "10417": "Applied Chemistry Lab",
    "10418": "Engineering Mechanics Lab",
    "10419": "Basic Electrical & Electronics Lab",
    "10420": "Professional Communication Ethics",
    "10421": "Professional Communication Ethics TW",
    "10422": "Engineering Workshop-I",
    "10423": "C Programming",
    "10424": "Induction cum Universal Human Values",
}

SUBJECT_CODES = list(SUBJECT_NAMES.keys())
NUM_SUBJECTS = len(SUBJECT_CODES)

# Subjects that have oral marks (only these 3 have oral component)
SUBJECTS_WITH_ORAL = {
    "10418",  # Engineering Mechanics Lab
    "10419",  # Basic Electrical & Electronics Lab
    "10423",  # C Programming
}

# Mapping from subject index to O1 line position
# O1 line has only 3 values: position 0 -> subject index 7 (10418),
#                            position 1 -> subject index 8 (10419),
#                            position 2 -> subject index 12 (10423)
ORAL_SUBJECT_INDICES = {
    7: 0,   # 10418 - Engineering Mechanics Lab
    8: 1,   # 10419 - Basic Electrical & Electronics Lab
    12: 2,  # 10423 - C Programming
}

# Mapping from subject index to T1 line position
# T1 line has 8 values for subjects with TERM WORK component:
# Subjects 10412, 10413, 10414, 10415 are THEORY only (no term work)
TERMWORK_SUBJECT_INDICES = {
    0: 0,   # 10411 - Applied Mathematics-I
    5: 1,   # 10416 - Applied Physics Lab
    6: 2,   # 10417 - Applied Chemistry Lab
    7: 3,   # 10418 - Engineering Mechanics Lab
    8: 4,   # 10419 - Basic Electrical & Electronics Lab
    10: 5,  # 10421 - Professional Communication Ethics TW
    11: 6,  # 10422 - Engineering Workshop-I
    12: 7,  # 10423 - C Programming
}

# Mapping from subject index to E1 line position
# E1 line has 6 values for subjects with EXTERNAL exam component
# Lab subjects don't have external exams
EXTERNAL_SUBJECT_INDICES = {
    0: 0,   # 10411 - Applied Mathematics-I
    1: 1,   # 10412 - Applied Physics
    2: 2,   # 10413 - Applied Chemistry
    3: 3,   # 10414 - Engineering Mechanics
    4: 4,   # 10415 - Basic Electrical & Electronics Engineering
    9: 5,   # 10420 - Professional Communication Ethics (theory)
}

# Mapping from subject index to I1 line position
# I1 line has 6-7 values for subjects with INTERNAL exam component
INTERNAL_SUBJECT_INDICES = {
    0: 0,   # 10411 - Applied Mathematics-I
    1: 1,   # 10412 - Applied Physics
    2: 2,   # 10413 - Applied Chemistry
    3: 3,   # 10414 - Engineering Mechanics
    4: 4,   # 10415 - Basic Electrical & Electronics Engineering
    9: 5,   # 10420 - Professional Communication Ethics (theory)
    13: 6,  # 10424 - Induction cum Universal Human Values (if present)
}


# ─── Validation ──────────────────────────────────────────────────────────────

def is_valid_ern(text: str) -> bool:
    if not text:
        return False
    clean = re.sub(r'[^A-Z0-9]', '', text.upper())
    return bool(re.match(r'^MU\d{16}$', clean))


def extract_ern(text: str) -> Optional[str]:
    match = re.search(r'(MU\d{16})', text)
    return match.group(1) if match else None


def is_seat_number_line(text: str) -> bool:
    """Check if a line is a student header starting with 7-digit seat number."""
    stripped = text.strip()
    return bool(re.match(r'^\d{7}\s+[A-Z]', stripped))


# ─── TOT Row Parser ──────────────────────────────────────────────────────────

def parse_tot_line(line: str) -> tuple:
    """
    Parse the TOT line. Returns (subjects_list, sgpa_value).
    
    TOT line ends with: ... credits creditPoints SGPA
    e.g.: ... 23 178.0 7.73913
          ... 23 101.5 0.00000
    The last number (with 5+ decimal places) is SGPA.
    Second to last is total credit points.
    """
    content = re.sub(r'^TOT\s+', '', line.strip())
    
    subjects = []
    tokens = content.split()
    
    # First, extract SGPA from the very end of TOT line
    sgpa = 0.0
    total_credits_sum = 0.0
    total_cp_sum = 0.0
    
    # SGPA is the last token (like 7.73913 or 0.00000)
    if tokens:
        try:
            last_val = float(tokens[-1])
            if 0 <= last_val <= 10:
                sgpa = last_val
                # Remove SGPA from tokens for subject parsing
                tokens = tokens[:-1]
                # Also remove total credit points sum
                if tokens:
                    try:
                        total_cp_sum = float(tokens[-1])
                        tokens = tokens[:-1]
                    except ValueError:
                        pass
                # And total credits sum
                if tokens:
                    try:
                        total_credits_sum = float(tokens[-1])
                        tokens = tokens[:-1]
                    except ValueError:
                        pass
        except ValueError:
            pass
    
    # Now parse subject groups from remaining tokens
    i = 0
    while i < len(tokens):
        # Handle "..." placeholder (subject 10424)
        if tokens[i] == '...':
            i += 1
            continue
        
        # Must start with a number (total marks)
        if not re.match(r'^\d+\+?$', tokens[i]):
            i += 1
            continue
        
        try:
            # Total marks (may have + suffix for grace)
            total_str = tokens[i]
            total = int(total_str.replace('+', ''))
            i += 1
            
            # Handle @grace marks
            if i < len(tokens) and tokens[i].startswith('@'):
                grace = int(tokens[i][1:])
                total += grace
                i += 1
            
            # GP
            if i >= len(tokens) or not re.match(r'^\d+$', tokens[i]):
                continue
            gp = int(tokens[i])
            i += 1
            
            # Grade
            if i >= len(tokens):
                break
            grade = tokens[i]
            i += 1
            
            # Handle "B+" split as "B" "+" 
            # Actually also handle "B+" as a single token
            if i < len(tokens) and tokens[i] == '+':
                grade += '+'
                i += 1
            
            if not re.match(r'^[ABCDFO][+]?$', grade):
                continue
            
            # Credits
            if i >= len(tokens):
                break
            credits = float(tokens[i])
            i += 1
            
            # Credit points
            if i >= len(tokens):
                break
            credit_points = float(tokens[i])
            i += 1
            
            subjects.append({
                'total': total,
                'gp': gp,
                'grade': grade,
                'credits': credits,
                'creditPoints': credit_points,
            })
            
        except (ValueError, IndexError):
            i += 1
            continue
    
    return subjects, sgpa


# ─── Component Row Parser ────────────────────────────────────────────────────

def parse_component_line(line: str, prefix: str) -> list:
    """
    Parse T1, O1, E1, I1 component rows to extract marks.
    
    E1 lines can have: 23 @3 P (grace marks)
    E1/I1 lines have grade info after marks: <mark> <GP> <Grade> <CreditPoints>
      e.g.: "22 0 F 0.0" means mark=22, GP=0, grade=F, credits=0.0
      e.g.: "19 P" means mark=19, passed (no GP/credits shown)
    The GP value (e.g., the 0) must NOT be extracted as a separate mark.
    """
    content = re.sub(f'^{prefix}\\s+', '', line.strip())
    
    # Remove trailing summary info: MARKS, (XXX) PASS/FAILED
    content = re.sub(r'\s+MARKS\s*$', '', content)
    content = re.sub(r'\s+\(\d+\)\s*(PASS|FAILED|FAIL)\s*$', '', content, flags=re.IGNORECASE)
    content = re.sub(r'\s+\.\.\.\s+P\s*$', '', content)
    content = re.sub(r'\s+\.\.\.\s*$', '', content)
    
    marks = []
    tokens = content.split()
    
    i = 0
    while i < len(tokens):
        token = tokens[i]
        
        # Skip standalone P/F (grade indicators NOT following a number)
        if token in ('P', 'F', '...'):
            i += 1
            continue
        
        # Skip decimal values (credit-related from F rows: 0.0, 0.00)
        if re.match(r'^\d+\.\d+$', token):
            i += 1
            continue
        
        # Try to extract numeric mark
        num_match = re.match(r'^(\d+)$', token)
        if num_match:
            mark = int(num_match.group(1))
            i += 1
            
            # Check for @grace after the number
            if i < len(tokens) and tokens[i].startswith('@'):
                try:
                    grace = int(tokens[i][1:])
                    mark += grace
                except ValueError:
                    pass
                i += 1
            
            # Append the actual mark
            marks.append(mark)
            
            # Now skip any trailing grade notation after this mark:
            # Pattern 1: <mark> P  (passed, just skip P)
            # Pattern 2: <mark> <GP> <Grade> [<CreditPoints>]  (e.g., "22 0 F 0.0")
            # We need to check if next token is a GP value (number followed by F/P)
            
            # First, skip direct P/F after the mark (e.g., "19 P")
            if i < len(tokens) and tokens[i] in ('F', 'P'):
                i += 1
                # Skip optional decimal credit points after grade
                if i < len(tokens) and re.match(r'^\d+\.\d+$', tokens[i]):
                    i += 1
            # Check if the next number is a GP value (followed by F/P grade)
            elif (i < len(tokens) and re.match(r'^\d+$', tokens[i]) and
                  i + 1 < len(tokens) and tokens[i + 1] in ('F', 'P')):
                # This is a GP value, not a mark — skip GP, Grade, and optional CreditPoints
                i += 1  # skip GP
                i += 1  # skip Grade (F/P)
                if i < len(tokens) and re.match(r'^\d+\.\d+$', tokens[i]):
                    i += 1  # skip credit points decimal
        else:
            i += 1
    
    return marks


# ─── Header Line Parser ─────────────────────────────────────────────────────

def parse_header_line(line: str, pending_ern: Optional[str] = None) -> Optional[dict]:
    """
    Parse student header line.
    
    Formats:
    1401763 AAYUSH RAMESH KAPADIA Regular MALE (MU0341120250220778) MU-0524: ...
    1401767 ANTARA VINAY KARVIR Regular FEMALE MU-0524: ...    (ERN on separate line)
    1011999 CHAVAN DAKSH JAYENDRA Repeater MALE (MU0341120240205853) MU-0524: ...
    """
    line = line.strip()
    
    seat_match = re.match(r'^(\d{7})\s+', line)
    if not seat_match:
        return None
    
    seat_number = seat_match.group(1)
    rest = line[seat_match.end():]
    
    # Extract status
    status_match = re.search(r'\b(Regular|Repeater|ATKT)\b', rest, re.IGNORECASE)
    status = status_match.group(1) if status_match else 'Regular'
    
    # Extract gender
    gender_match = re.search(r'\b(MALE|FEMALE)\b', rest, re.IGNORECASE)
    gender = gender_match.group(1).upper() if gender_match else None
    
    # Extract ERN from this line
    ern = extract_ern(rest)
    
    # If not found, use pending ERN from previous page
    if not ern and pending_ern and is_valid_ern(pending_ern):
        ern = pending_ern
    
    # Extract college
    college = ''
    college_match = re.search(r'MU-\d+:\s*(.+?)(?:\s*$)', rest)
    if college_match:
        college = college_match.group(1).strip()
    
    # Extract name - between seat number and status keyword
    name = ''
    if status_match:
        name_part = rest[:status_match.start()].strip()
    else:
        name_part = rest.split('(')[0].split('MU-')[0].strip()
        # Remove MALE/FEMALE from name
        name_part = re.sub(r'\b(MALE|FEMALE)\b', '', name_part).strip()
    
    # Clean name: title case, only alphabetic
    name = ' '.join(
        word.capitalize() for word in name_part.split()
        if word.isalpha() and word.upper() not in ('MALE', 'FEMALE')
    )
    
    return {
        'seatNumber': seat_number,
        'name': name,
        'gender': gender,
        'ern': ern,
        'college': college,
        'status': status,
    }


# ─── Summary Parser ──────────────────────────────────────────────────────────

def parse_summary_from_lines(lines: list, sgpa_from_tot: float) -> dict:
    """Extract total marks and result from student block lines."""
    total_marks = 0
    result = 'FAILED'
    
    for line in lines:
        # Look for (XXX) PASS/FAILED in I1 or E1 lines
        marks_match = re.search(r'\((\d+)\)\s*(PASS|FAILED|FAIL)\s*$', line, re.IGNORECASE)
        if marks_match:
            total_marks = int(marks_match.group(1))
            result = 'PASS' if 'PASS' in marks_match.group(2).upper() else 'FAILED'
            break
    
    return {
        'totalMarks': total_marks,
        'result': result,
        'sgpa': sgpa_from_tot,
        'cgpa': None,
    }


# ─── KT Detection ───────────────────────────────────────────────────────────

def detect_subject_kt_type(tot_data: dict, components: dict) -> Optional[str]:
    if tot_data['grade'] != 'F' and tot_data['gp'] > 0:
        return None
    if components.get('external') is not None and components['external'] == 0:
        return 'external'
    if components.get('internal') is not None and components['internal'] == 0:
        return 'internal'
    if components.get('termWork') is not None and components['termWork'] == 0:
        return 'termWork'
    if components.get('oral') is not None and components['oral'] == 0:
        return 'oral'
    return 'overall'


def detect_kt(subjects: list) -> dict:
    failed = [s for s in subjects if s.get('isKT')]
    return {
        'totalKT': len(failed),
        'internalKT': sum(1 for s in subjects if s.get('ktType') == 'internal'),
        'externalKT': sum(1 for s in subjects if s.get('ktType') in ('external', 'overall')),
        'termWorkKT': sum(1 for s in subjects if s.get('ktType') == 'termWork'),
        'oralKT': sum(1 for s in subjects if s.get('ktType') == 'oral'),
        'failedSubjects': [s['name'] for s in subjects if s.get('isKT')],
        'hasKT': len(failed) > 0,
    }


# ─── Main Parser ─────────────────────────────────────────────────────────────

class MUResultParser:
    """Complete Mumbai University Result PDF Parser."""
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.students = {}
        self.errors = []
    
    def parse(self) -> dict:
        """Parse the entire PDF and return student records."""
        print(f"📄 Parsing {self.pdf_path}...")
        
        # Extract ALL text first, then parse - this handles cross-page issues
        all_lines = []
        
        with pdfplumber.open(self.pdf_path) as pdf:
            total_pages = len(pdf.pages)
            print(f"   Total pages: {total_pages}")
            
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if not text:
                    continue
                
                page_lines = text.split('\n')
                all_lines.extend(page_lines)
                
                if page_num % 10 == 0:
                    print(f"   Processed page {page_num}/{total_pages}...")
        
        print(f"   Total lines: {len(all_lines)}")
        
        # Now parse all lines as one continuous stream
        self._parse_all_lines(all_lines)
        
        print(f"\n✅ Parsed {len(self.students)} students")
        if self.errors:
            print(f"⚠️  {len(self.errors)} errors encountered")
            for err in self.errors[:5]:
                print(f"   - {err}")
        
        return self.students
    
    def _parse_all_lines(self, all_lines: list):
        """
        Parse all lines as a continuous stream.
        This handles ERNs that span across page boundaries.
        """
        # Step 1: Find all student block boundaries
        block_starts = []
        for i, line in enumerate(all_lines):
            stripped = line.strip()
            if is_seat_number_line(stripped):
                block_starts.append(i)
        
        print(f"   Found {len(block_starts)} student blocks")
        
        # Step 2: Identify floating ERNs
        # An ERN line is a line containing "(MU..." or "MU..." that is NOT a student header
        floating_erns = {}  # line_index -> ern
        for i, line in enumerate(all_lines):
            stripped = line.strip()
            # Skip if it's a student header
            if is_seat_number_line(stripped):
                continue
            # Check for ERN
            ern = extract_ern(stripped)
            if ern and is_valid_ern(ern):
                floating_erns[i] = ern
        
        # Map floating ERNs to the next student block they belong to
        ern_for_block = {}  # block_start_index -> ern
        for ern_line, ern in floating_erns.items():
            # Find the nearest student block AFTER this floating ERN
            for bs in block_starts:
                if bs > ern_line:
                    # But also check it's within ~5 lines (don't assign far-away ERNs)
                    if bs - ern_line <= 5:
                        ern_for_block[bs] = ern
                    break
        
        # Step 3: Parse each student block
        for idx, start in enumerate(block_starts):
            end = block_starts[idx + 1] if idx + 1 < len(block_starts) else len(all_lines)
            
            # Get block lines
            block_lines = [l.strip() for l in all_lines[start:end] if l.strip()]
            
            # Filter out header repetitions (SEAT NO, subject headers, TOT GP G C G*C, etc.)
            filtered_lines = []
            for line in block_lines:
                # Skip page header repetitions
                if line.startswith('SEAT NO') or line.startswith('10411 :'):
                    break  # Stop collecting - rest is page header repeats
                if line.startswith('WORK)') and 'Engineering' in line:
                    break
                if line.startswith('TOT GP G') and 'C G*C' in line:
                    break
                if line.startswith('TERM WORK') or line.startswith('ORAL ('):
                    break
                if line.startswith('External (') or line.startswith('Internal('):
                    break
                if line.startswith('Mathematics-I'):
                    break
                if line == ')':  # Orphaned closing paren from ERN
                    continue
                filtered_lines.append(line)
            
            if not filtered_lines:
                continue
            
            # Get pending ERN for this block
            pending_ern = ern_for_block.get(start)
            
            # Skip repeater students (not needed)
            header_line = filtered_lines[0] if filtered_lines else ''
            if re.search(r'\bRepeater\b', header_line, re.IGNORECASE):
                continue
            
            try:
                student = self._parse_student_block(filtered_lines, pending_ern)
                if student:
                    key = student['ern'] if student['ern'] else student['seatNumber']
                    self.students[key] = student
            except Exception as e:
                self.errors.append(f"Block at line {start}: {e}")
    
    def _parse_student_block(self, lines: list, pending_ern: Optional[str] = None) -> Optional[dict]:
        """Parse a single student block into a StudentRecord."""
        if len(lines) < 2:
            return None
        
        # Parse header
        header = parse_header_line(lines[0], pending_ern)
        if not header:
            return None
        
        # Parse component rows and TOT
        t1_marks = []
        o1_marks = []
        e1_marks = []
        i1_marks = []
        tot_data = []
        sgpa = 0.0
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('T1 '):
                t1_marks = parse_component_line(stripped, 'T1')
                # T1 should have at most 8 values (subjects with term work)
                t1_marks = t1_marks[:8]
            elif stripped.startswith('O1 '):
                o1_marks = parse_component_line(stripped, 'O1')
                # O1 should have at most 3 values (subjects with oral)
                o1_marks = o1_marks[:3]
            elif stripped.startswith('E1 '):
                e1_marks = parse_component_line(stripped, 'E1')
                # E1 should have at most 6 values (subjects with external exams)
                e1_marks = e1_marks[:6]
            elif stripped.startswith('I1 '):
                i1_marks = parse_component_line(stripped, 'I1')
                # I1 should have at most 7 values (subjects with internal exams)
                i1_marks = i1_marks[:7]
            elif stripped.startswith('TOT '):
                tot_data, sgpa = parse_tot_line(stripped)
        
        if not tot_data:
            return None
        
        # Build subjects
        subjects = []
        for i in range(min(len(tot_data), NUM_SUBJECTS)):
            td = tot_data[i]
            code = SUBJECT_CODES[i]
            
            # Map T1 values using index mapping (only 8 subjects have term work)
            tw_idx = TERMWORK_SUBJECT_INDICES.get(i)
            term_work = t1_marks[tw_idx] if (tw_idx is not None and tw_idx < len(t1_marks)) else None
            # Only assign oral marks to subjects that actually have oral component
            # The O1 line has only 3 values mapped to specific subject indices
            oral_idx = ORAL_SUBJECT_INDICES.get(i)
            oral = o1_marks[oral_idx] if (oral_idx is not None and oral_idx < len(o1_marks)) else None
            # Map E1 values (only 6 subjects have external exams)
            ext_idx = EXTERNAL_SUBJECT_INDICES.get(i)
            external = e1_marks[ext_idx] if (ext_idx is not None and ext_idx < len(e1_marks)) else None
            # Map I1 values (6-7 subjects have internal exams)
            int_idx = INTERNAL_SUBJECT_INDICES.get(i)
            internal = i1_marks[int_idx] if (int_idx is not None and int_idx < len(i1_marks)) else None
            
            is_kt = td['grade'] == 'F' or td['gp'] == 0
            kt_type = detect_subject_kt_type(td, {
                'termWork': term_work,
                'oral': oral,
                'external': external,
                'internal': internal,
            })
            
            subjects.append({
                'code': code,
                'name': SUBJECT_NAMES.get(code, code),
                'marks': {
                    'termWork': term_work,
                    'oral': oral,
                    'external': external,
                    'internal': internal,
                    'total': td['total'],
                    'gradePoint': td['gp'],
                    'grade': td['grade'],
                    'credits': td['credits'],
                    'creditPoints': td['creditPoints'],
                    'status': 'F' if td['grade'] == 'F' else 'P',
                },
                'isKT': is_kt,
                'ktType': kt_type,
            })
        
        # Parse summary (total marks & result from I1 line)
        summary = parse_summary_from_lines(lines, sgpa)
        
        total_marks = summary['totalMarks'] or sum(s['marks']['total'] for s in subjects)
        total_credits = sum(s['marks']['credits'] for s in subjects)
        total_credit_points = sum(s['marks']['creditPoints'] for s in subjects)
        
        return {
            'seatNumber': header['seatNumber'],
            'name': header['name'],
            'gender': header['gender'],
            'ern': header['ern'],
            'college': header['college'],
            'status': header['status'],
            'subjects': subjects,
            'totalMarks': total_marks,
            'maxMarks': 800,
            'result': summary['result'],
            'sgpa': summary['sgpa'],
            'cgpa': summary['cgpa'],
            'totalCredits': total_credits,
            'totalCreditPoints': total_credit_points,
            'kt': detect_kt(subjects),
        }
    
    def save_json(self, output_path: str):
        with open(output_path, 'w') as f:
            json.dump(self.students, f, indent=4, ensure_ascii=False)
        print(f"💾 Saved to {output_path}")
    
    def compare_with(self, existing_path: str):
        with open(existing_path, 'r') as f:
            existing = json.load(f)
        
        print(f"\n{'='*60}")
        print(f"📊 ACCURACY COMPARISON")
        print(f"{'='*60}")
        print(f"  Existing parser: {len(existing)} students")
        print(f"  New parser:      {len(self.students)} students")
        
        existing_erns = set(existing.keys())
        new_erns = set(self.students.keys())
        
        common = existing_erns & new_erns
        missing = existing_erns - new_erns
        extra = new_erns - existing_erns
        
        print(f"\n  Common:  {len(common)}")
        print(f"  Missing: {len(missing)}")
        print(f"  Extra:   {len(extra)}")
        
        if missing:
            print(f"\n  ⚠️  Missing ERNs ({len(missing)}):")
            for ern in sorted(missing)[:5]:
                old = existing[ern]
                print(f"    - {ern}: {old.get('name')} (seat: {old.get('seatNumber')})")
        
        if extra:
            print(f"\n  ➕ Extra entries ({len(extra)}):")
            for ern in sorted(extra)[:5]:
                new = self.students[ern]
                print(f"    + {ern}: {new.get('name')} (seat: {new.get('seatNumber')})")
        
        if common:
            matches = {
                'name': 0, 'seatNumber': 0, 'gender': 0, 
                'totalMarks': 0, 'result': 0, 'sgpa': 0,
                'subjects_count': 0, 'ern': 0,
            }
            total_sub_match = 0
            total_sub_total = 0
            
            for ern in common:
                old = existing[ern]
                new = self.students[ern]
                
                for field in ['seatNumber', 'gender', 'totalMarks', 'result', 'ern']:
                    if str(old.get(field, '')).strip() == str(new.get(field, '')).strip():
                        matches[field] += 1
                
                # Name comparison (case-insensitive)
                old_name = (old.get('name') or '').lower().replace('repeater', '').strip()
                new_name = (new.get('name') or '').lower().strip()
                if old_name == new_name:
                    matches['name'] += 1
                
                # SGPA with tolerance
                old_sgpa = old.get('sgpa', 0) or 0
                new_sgpa = new.get('sgpa', 0) or 0
                if abs(float(old_sgpa) - float(new_sgpa)) < 0.01:
                    matches['sgpa'] += 1
                
                if len(old.get('subjects', [])) == len(new.get('subjects', [])):
                    matches['subjects_count'] += 1
                
                old_subs = old.get('subjects', [])
                new_subs = new.get('subjects', [])
                for j in range(min(len(old_subs), len(new_subs))):
                    total_sub_total += 1
                    if old_subs[j]['marks']['total'] == new_subs[j]['marks']['total']:
                        total_sub_match += 1
            
            print(f"\n  📈 Field-level accuracy ({len(common)} common students):")
            for field, count in matches.items():
                pct = (count / len(common)) * 100
                emoji = '✅' if pct >= 95 else '⚠️' if pct >= 80 else '❌'
                print(f"    {emoji} {field}: {count}/{len(common)} ({pct:.1f}%)")
            
            if total_sub_total > 0:
                pct = (total_sub_match / total_sub_total) * 100
                emoji = '✅' if pct >= 95 else '⚠️' if pct >= 80 else '❌'
                print(f"    {emoji} subject_totals: {total_sub_match}/{total_sub_total} ({pct:.1f}%)")
            
            # Show samples of mismatches
            print(f"\n  📋 Sample mismatches:")
            mismatch_count = 0
            for ern in sorted(common):
                if mismatch_count >= 3:
                    break
                old = existing[ern]
                new = self.students[ern]
                if old.get('totalMarks') != new.get('totalMarks') or abs((old.get('sgpa') or 0) - (new.get('sgpa') or 0)) > 0.01:
                    print(f"    {ern}:")
                    print(f"      Marks: OLD={old.get('totalMarks')} NEW={new.get('totalMarks')}")
                    print(f"      SGPA:  OLD={old.get('sgpa')} NEW={new.get('sgpa')}")
                    print(f"      Name:  OLD={old.get('name')} NEW={new.get('name')}")
                    mismatch_count += 1


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    print("🚀 Mumbai University Result Parser v2.0 (pdfplumber)\n")
    
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "sample.pdf"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "parsed_results.json"
    
    if not Path(pdf_path).exists():
        print(f"❌ Error: {pdf_path} not found!")
        return
    
    parser = MUResultParser(pdf_path)
    parser.parse()
    parser.save_json(output_path)
    
    # Auto-detect comparison file based on PDF name
    # e.g. aids.pdf -> ../public/data/aids.json
    #      sample.pdf -> ../public/data/mechanical.json (default)
    pdf_name = Path(pdf_path).stem.lower()
    
    # Map common variations to the actual JSON filenames
    comparison_map = {
        'aids': 'aids',
        'mechanical': 'mechanical',
        'sample': 'mechanical',  # sample.pdf is mechanical engineering
        'fe sem-i mech result': 'mechanical',
    }
    
    json_name = comparison_map.get(pdf_name, pdf_name)
    existing = Path(f"../public/data/{json_name}.json")
    
    if existing.exists():
        print(f"\n📊 Comparing with existing data: {existing}")
        parser.compare_with(str(existing))
    else:
        print(f"\n⚠️  No comparison file found at {existing}")
        print(f"   Skipping accuracy comparison.")
    
    print(f"\n🏁 Done!")


if __name__ == "__main__":
    main()

