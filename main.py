from fastapi import FastAPI, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from models import get_db, Exam, Question, QuestionType, ExamSession, Answer
import uuid
import json
import os

app = FastAPI(title="Exam Conducting Platform")

# Calculate the absolute path for the templates directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# We'll create these directories later
# app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Instructor Dashboard: List of exams and option to create new ones."""
    exams = db.query(Exam).order_by(Exam.created_at.desc()).all()
    return templates.TemplateResponse("dashboard.html", {"request": request, "exams": exams})

@app.post("/exam/create")
async def create_exam(
    title: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db)
):
    """Create a new exam and generate a unique link."""
    uid = str(uuid.uuid4())
    new_exam = Exam(title=title, description=description, uid=uid)
    db.add(new_exam)
    db.commit()
    db.refresh(new_exam)
    return RedirectResponse(url=f"/exam/{new_exam.id}/edit", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/exam/{exam_id}/edit", response_class=HTMLResponse)
async def edit_exam(request: Request, exam_id: int, db: Session = Depends(get_db)):
    """Edit exam details and add/remove questions."""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    
    questions = db.query(Question).filter(Question.exam_id == exam_id).all()
    
    return templates.TemplateResponse("edit_exam.html", {
        "request": request, 
        "exam": exam,
        "questions": questions,
        "QuestionType": QuestionType
    })

@app.post("/exam/{exam_id}/question/add")
async def add_question(
    exam_id: int,
    question_text: str = Form(...),
    question_type: str = Form(...),
    options: str = Form(""), # JSON string for MCQ
    correct_answer: str = Form(""),
    db: Session = Depends(get_db)
):
    """Add a question to an exam."""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
        
    try:
        q_type = QuestionType(question_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid question type")

    formatted_options = options if q_type == QuestionType.MCQ else None
    
    question = Question(
        exam_id=exam_id,
        question_text=question_text,
        question_type=q_type,
        options=formatted_options,
        correct_answer=correct_answer
    )
    db.add(question)
    db.commit()
    
    return RedirectResponse(url=f"/exam/{exam_id}/edit", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/exam/{exam_id}/question/{question_id}/delete")
async def delete_question(exam_id: int, question_id: int, db: Session = Depends(get_db)):
    """Remove a question from an exam."""
    question = db.query(Question).filter(Question.id == question_id, Question.exam_id == exam_id).first()
    if question:
        db.delete(question)
        db.commit()
    return RedirectResponse(url=f"/exam/{exam_id}/edit", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/exam/{exam_id}/review", response_class=HTMLResponse)
async def review_exam(request: Request, exam_id: int, db: Session = Depends(get_db)):
    """Instructor view to review student submissions for an exam."""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
        
    sessions = db.query(ExamSession).filter(ExamSession.exam_id == exam_id).order_by(ExamSession.started_at.desc()).all()
    
    return templates.TemplateResponse("review_exam.html", {
        "request": request,
        "exam": exam,
        "sessions": sessions
    })

@app.get("/review/session/{session_id}", response_class=HTMLResponse)
async def review_session(request: Request, session_id: int, db: Session = Depends(get_db)):
    """Review a specific student's answers."""
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    exam = db.query(Exam).filter(Exam.id == session.exam_id).first()
    answers = db.query(Answer).filter(Answer.session_id == session_id).all()
    
    # Map answers by question_id for easy lookup in template
    answer_map = {a.question_id: a for a in answers}
    
    return templates.TemplateResponse("review_session.html", {
        "request": request,
        "session": session,
        "exam": exam,
        "answer_map": answer_map,
        "QuestionType": QuestionType
    })

# --- Student Routes ---

@app.get("/take/{uid}", response_class=HTMLResponse)
async def start_exam(request: Request, uid: str, db: Session = Depends(get_db)):
    """Landing page for student to enter details before starting exam."""
    exam = db.query(Exam).filter(Exam.uid == uid).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
        
    return templates.TemplateResponse("student_start.html", {"request": request, "exam": exam})

@app.post("/take/{uid}/start")
async def register_student(
    uid: str,
    student_name: str = Form(...),
    student_id: str = Form(...),
    db: Session = Depends(get_db)
):
    """Register student and start the exam session."""
    exam = db.query(Exam).filter(Exam.uid == uid).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
        
    session = ExamSession(exam_id=exam.id, student_name=student_name, student_id=student_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    
    return RedirectResponse(url=f"/take/session/{session.id}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/take/session/{session_id}", response_class=HTMLResponse)
async def take_exam(request: Request, session_id: int, db: Session = Depends(get_db)):
    """The actual exam interface for the student."""
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if session.completed_at:
        return templates.TemplateResponse("exam_completed.html", {"request": request})
        
    exam = db.query(Exam).filter(Exam.id == session.exam_id).first()
    questions = db.query(Question).filter(Question.exam_id == exam.id).all()
    
    # Parse JSON options for MCQ
    for q in questions:
        if q.question_type == QuestionType.MCQ and q.options:
            try:
                q.parsed_options = json.loads(q.options)
            except:
                q.parsed_options = []
        else:
            q.parsed_options = []
            
    return templates.TemplateResponse("take_exam.html", {
        "request": request,
        "session": session,
        "exam": exam,
        "questions": questions,
        "QuestionType": QuestionType
    })

@app.post("/take/session/{session_id}/submit")
async def submit_exam(request: Request, session_id: int, db: Session = Depends(get_db)):
    """Handle student answer submission."""
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session or session.completed_at:
        raise HTTPException(status_code=400, detail="Invalid or already completed session")
        
    form_data = await request.form()
    
    # Loop through submitted form data. Key is like 'question_123'
    for key, value in form_data.items():
        if key.startswith("question_"):
            try:
                question_id = int(key.split("_")[1])
                # Save answer
                answer = Answer(
                    session_id=session.id,
                    question_id=question_id,
                    answer_text=str(value)
                )
                db.add(answer)
            except ValueError:
                pass # ignore poorly formatted keys
                
    from datetime import datetime
    session.completed_at = datetime.utcnow()
    db.commit()
    
    return templates.TemplateResponse("exam_completed.html", {"request": request})

