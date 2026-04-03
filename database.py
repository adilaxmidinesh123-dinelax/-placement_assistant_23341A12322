from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    resume_analysis = db.relationship('ResumeAnalysis', backref='user', uselist=False)
    answers = db.relationship('AnswerEvaluation', backref='user', lazy=True)
    weak_areas = db.relationship('WeakArea', backref='user', lazy=True)
    roadmap = db.relationship('Roadmap', backref='user', uselist=False)
    resume_data = db.relationship('ResumeData', backref='user', uselist=False)

class ResumeAnalysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    resume_text = db.Column(db.Text, nullable=False)
    target_company = db.Column(db.String(100), nullable=False)
    job_role = db.Column(db.String(100), nullable=False)
    skills = db.Column(db.Text)
    projects = db.Column(db.Text)
    education = db.Column(db.String(200))
    strengths = db.Column(db.Text)
    weak_areas_resume = db.Column(db.Text)
    missing_skills = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class InterviewQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AnswerEvaluation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('interview_question.id'))
    user_answer = db.Column(db.Text, nullable=False)
    score = db.Column(db.Float)
    feedback = db.Column(db.Text)
    improved_answer = db.Column(db.Text)
    clarity_score = db.Column(db.Float)
    confidence_score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WeakArea(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topic = db.Column(db.String(200), nullable=False)
    source = db.Column(db.String(50))
    severity = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Roadmap(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    plan_data = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_questions_answered = db.Column(db.Integer, default=0)
    average_score = db.Column(db.Float, default=0)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)

class ResumeData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    full_name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    summary = db.Column(db.Text)
    skills = db.Column(db.Text)
    projects = db.Column(db.Text)
    education = db.Column(db.Text)
    experience = db.Column(db.Text)
    template_choice = db.Column(db.String(50), default='professional')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)