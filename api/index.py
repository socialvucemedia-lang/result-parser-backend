"""
FastAPI MU Result Parser - Vercel Deployment Entry Point
"""

import tempfile
import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Import the parser
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
from mu_parser import MUResultParser

app = FastAPI(
    title="MU Result Parser API",
    description="Parse Mumbai University result PDFs into structured JSON",
    version="2.0.0",
)

# Allow CORS from your Next.js domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with your actual domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "MU Result Parser API", "version": "2.0.0", "status": "active"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "mu-result-parser", "version": "2.0.0"}


@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...)):
    """
    Parse a PDF file and return student records.
    
    Accepts: multipart/form-data with a PDF file
    Returns: JSON with students, metadata, and analysis
    """
    # Validate file type
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Validate file size (max 50MB)
    contents = await file.read()
    if len(contents) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size must be less than 50MB")
    
    # Save to temp file for pdfplumber
    tmp_path = None
    
    try:
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
        
        # Parse
        parser = MUResultParser(tmp_path)
        students_dict = parser.parse()
        
        # Convert to list format matching frontend expectations
        students_list = list(students_dict.values())
        
        # Generate analysis
        analysis = generate_analysis(students_list)
        
        return JSONResponse(content={
            "students": students_list,
            "metadata": {
                "sourceFile": file.filename,
                "totalPages": 0,
                "parsedAt": "",
                "parseTimeMs": 0,
                "examSession": "December 2025",
                "university": "University of Mumbai",
                "totalStudents": len(students_list),
            },
            "analysis": analysis,
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")
    
    finally:
        # Clean up temp file
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def generate_analysis(students: list) -> dict:
    """Generate analysis summary"""
    if not students:
        return {
            "totalStudents": 0,
            "passedCount": 0,
            "failedCount": 0,
            "passPercentage": 0,
            "studentsWithKT": 0,
            "averageKTPerStudent": 0,
            "highestMarks": 0,
            "lowestMarks": 0,
            "averageMarks": 0,
            "averageSGPA": 0,
            "marksDistribution": {"distinction": 0, "firstClass": 0, "secondClass": 0, "passClass": 0, "fail": 0},
            "ktDistribution": {"noKT": 0, "oneKT": 0, "twoKT": 0, "threeOrMoreKT": 0},
        }
    
    total = len(students)
    passed = [s for s in students if s.get('result') == 'PASS']
    failed = [s for s in students if s.get('result') == 'FAILED']
    with_kt = [s for s in students if s.get('kt', {}).get('hasKT')]
    
    marks = [s.get('totalMarks', 0) for s in students if s.get('totalMarks', 0) > 0]
    sgpas = [s.get('sgpa', 0) for s in students if (s.get('sgpa') or 0) > 0]
    
    highest = max(marks) if marks else 0
    lowest = min(marks) if marks else 0
    avg_marks = round(sum(marks) / len(marks)) if marks else 0
    avg_sgpa = round(sum(sgpas) / len(sgpas) * 100) / 100 if sgpas else 0
    
    total_kts = sum(s.get('kt', {}).get('totalKT', 0) for s in students)
    avg_kt = round(total_kts / len(with_kt) * 100) / 100 if with_kt else 0
    
    # Marks distribution
    max_marks = 800
    dist = {"distinction": 0, "firstClass": 0, "secondClass": 0, "passClass": 0, "fail": 0}
    for s in students:
        pct = (s.get('totalMarks', 0) / max_marks) * 100
        if pct >= 75:
            dist["distinction"] += 1
        elif pct >= 60:
            dist["firstClass"] += 1
        elif pct >= 50:
            dist["secondClass"] += 1
        elif pct >= 40 and s.get('result') == 'PASS':
            dist["passClass"] += 1
        else:
            dist["fail"] += 1
    
    # KT distribution
    kt_dist = {"noKT": 0, "oneKT": 0, "twoKT": 0, "threeOrMoreKT": 0}
    for s in students:
        kt_count = s.get('kt', {}).get('totalKT', 0)
        if kt_count == 0:
            kt_dist["noKT"] += 1
        elif kt_count == 1:
            kt_dist["oneKT"] += 1
        elif kt_count == 2:
            kt_dist["twoKT"] += 1
        else:
            kt_dist["threeOrMoreKT"] += 1
    
    return {
        "totalStudents": total,
        "passedCount": len(passed),
        "failedCount": len(failed),
        "passPercentage": round(len(passed) / total * 10000) / 100,
        "studentsWithKT": len(with_kt),
        "averageKTPerStudent": avg_kt,
        "highestMarks": highest,
        "lowestMarks": lowest,
        "averageMarks": avg_marks,
        "averageSGPA": avg_sgpa,
        "marksDistribution": dist,
        "ktDistribution": kt_dist,
    }
