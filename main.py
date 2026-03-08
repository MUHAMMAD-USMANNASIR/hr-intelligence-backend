import io, sqlite3, re
import pytesseract
from PIL import Image
from PyPDF2 import PdfReader
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

# Tell Python exactly where you installed Tesseract on your Windows machine
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

app = FastAPI()

# 1. ALLOW REACT TO CONNECT
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. CREATE THE DATABASE IF IT DOES NOT EXIST
def init_db():
    conn = sqlite3.connect("resumes.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            real_name TEXT,
            email TEXT,
            phone TEXT,
            score INTEGER,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# 3. SEND CANDIDATES TO THE REACT DASHBOARD
@app.get("/candidates")
async def get_all_candidates():
    conn = sqlite3.connect("resumes.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM candidates")
    rows = cursor.fetchall()
    conn.close()
    return [{
        "id": r[0], 
        "filename": r[1], 
        "real_name": r[2], 
        "email": r[3], 
        "phone": r[4], 
        "score": r[5], 
        "status": r[6]
    } for r in rows]

# 4. HANDLE UPLOADS (PDF & IMAGES)
@app.post("/upload-resume")
async def scan_resume(file: UploadFile = File(...)):
    file_content = await file.read()
    extracted_text = ""
    filename_lower = file.filename.lower()
    
    try:
        # Handle PDFs
        if filename_lower.endswith(".pdf"):
            reader = PdfReader(io.BytesIO(file_content))
            for page in reader.pages:
                extracted_text += page.extract_text() or ""
                
        # Handle Images (OCR)
        elif filename_lower.endswith((".png", ".jpg", ".jpeg")):
            image = Image.open(io.BytesIO(file_content))
            extracted_text = pytesseract.image_to_string(image)
            
        else:
            return {"message": "Unsupported file format"}
            
    except Exception as e:
        print(f"Failed to read {file.filename}: {e}")
        return {"message": "Corrupted file safely skipped"}

    text_lower = extracted_text.lower()
    
    # EXTRACT CONTACT INFO
    email_match = re.search(r'[\w\.-]+@[\w\.-]+', extracted_text)
    candidate_email = email_match.group(0) if email_match else "No Email"
    
    phone_match = re.search(r'\+?\d[\d -]{8,14}\d', extracted_text)
    candidate_phone = phone_match.group(0) if phone_match else "No Phone"
    
    candidate_name = "Unknown"
    for line in extracted_text.split('\n'):
        clean_line = line.strip()
        if 2 < len(clean_line) < 40 and re.search(r'[A-Za-z]', clean_line):
            candidate_name = clean_line
            break

    # THE GRADING ALGORITHM
    score = 0.0
    if re.search(r'\b(bs|bachelor|bachelors|master|degree|university|engineering)\b', text_lower): score += 1.0
    if re.search(r'\b(gpa|cgpa|percentile|%|marks|nts|nat)\b', text_lower): score += 1.0
        
    tech_skills = ["python", "react", "javascript", "fastapi", "sql", "java", "c++", "git"]
    found_skills = sum(1 for skill in tech_skills if skill in text_lower)
    if found_skills >= 3: score += 2.0
    elif found_skills > 0: score += 1.0
        
    soft_skills = ["representative", "cr", "lead", "leadership", "volunteer", "manager", "team", "communication"]
    if any(word in soft_skills for word in text_lower): score += 1.0
        
    final_score = int(min(round(score), 5))
    status = "Shortlisted" if final_score >= 4 else "Reviewed"
    
    # SAVE TO DATABASE
    conn = sqlite3.connect("resumes.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO candidates (filename, real_name, email, phone, score, status) VALUES (?, ?, ?, ?, ?, ?)",
        (file.filename, candidate_name, candidate_email, candidate_phone, final_score, status)
    )
    conn.commit()
    conn.close()
    
    return {"message": "Success"}

# 5. DELETE A CANDIDATE
@app.delete("/candidates/{c_id}")
async def delete_candidate(c_id: int):
    conn = sqlite3.connect("resumes.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM candidates WHERE id = ?", (c_id,))
    conn.commit()
    conn.close()
    return {"message": "Deleted"}