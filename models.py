from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, Enum, DateTime
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
import enum
import os

# Default to local SQLite if DATABASE_URL is not provided (e.g. on Render)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./exam_platform.db")

# Handle Render/Railway's postgres:// vs postgresql:// quirk if needed
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Supabase requires SSL for external connections
if "supabase" in DATABASE_URL and "sslmode=require" not in DATABASE_URL:
    if "?" in DATABASE_URL:
        DATABASE_URL += "&sslmode=require"
    else:
        DATABASE_URL += "?sslmode=require"

# Only SQLite needs check_same_thread=False
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class QuestionType(enum.Enum):
    MCQ = "mcq"
    BRIEF = "brief"
    PYTHON = "python"

class Exam(Base):
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    uid = Column(String, unique=True, index=True) # Unique link ID

    questions = relationship("Question", back_populates="exam", cascade="all, delete-orphan")
    sessions = relationship("ExamSession", back_populates="exam", cascade="all, delete-orphan")

class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"))
    question_text = Column(Text)
    question_type = Column(Enum(QuestionType))
    options = Column(Text, nullable=True) # JSON string for MCQ options
    correct_answer = Column(Text, nullable=True) # Optional correct answer

    exam = relationship("Exam", back_populates="questions")
    answers = relationship("Answer", back_populates="question", cascade="all, delete-orphan")

class ExamSession(Base):
    __tablename__ = "exam_sessions"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"))
    student_name = Column(String)
    student_id = Column(String)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    exam = relationship("Exam", back_populates="sessions")
    answers = relationship("Answer", back_populates="session", cascade="all, delete-orphan")

class Answer(Base):
    __tablename__ = "answers"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("exam_sessions.id"))
    question_id = Column(Integer, ForeignKey("questions.id"))
    answer_text = Column(Text) # Will contain code, brief answer, or selected option

    session = relationship("ExamSession", back_populates="answers")
    question = relationship("Question", back_populates="answers")

# Create tables
Base.metadata.create_all(bind=engine)

# Dependency to get db session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
