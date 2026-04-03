from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import json
import PyPDF2
from datetime import datetime
import random

from database import db, User, ResumeAnalysis, InterviewQuestion, AnswerEvaluation, WeakArea, Roadmap, UserProgress, ResumeData
from resume_parser import ResumeParser
from ai_engine import AIEngine

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///placement_assistant.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def extract_text_from_pdf(file_path):
    text = ""
    try:
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text()
    except Exception as e:
        print(f"PDF error: {e}")
    return text

# ---------- Authentication ----------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        pwd = request.form.get('password')
        confirm = request.form.get('confirm_password')
        if pwd != confirm:
            flash('Passwords do not match!', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered!', 'danger')
            return redirect(url_for('register'))
        user = User(name=name, email=email, password=generate_password_hash(pwd))
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        pwd = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, pwd):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid email or password!', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', 'info')
    return redirect(url_for('index'))

# ---------- Dashboard & Resume Processing ----------
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

@app.route('/process_resume', methods=['POST'])
@login_required
def process_resume():
    company = request.form.get('company')
    role = request.form.get('role')
    if not company or not role:
        flash('Please provide both company and job role!', 'danger')
        return redirect(url_for('dashboard'))
    if 'resume' not in request.files:
        flash('Please upload a resume file!', 'danger')
        return redirect(url_for('dashboard'))
    file = request.files['resume']
    if file.filename == '':
        flash('Select a file!', 'danger')
        return redirect(url_for('dashboard'))
    if not (file.filename.endswith('.pdf') or file.filename.endswith('.txt')):
        flash('Only PDF or TXT files allowed!', 'danger')
        return redirect(url_for('dashboard'))
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{current_user.id}_{filename}")
    file.save(filepath)
    if filename.endswith('.pdf'):
        resume_text = extract_text_from_pdf(filepath)
    else:
        with open(filepath, 'r', encoding='utf-8') as f:
            resume_text = f.read()
    os.remove(filepath)
    if not resume_text.strip():
        flash('Could not extract text from resume.', 'danger')
        return redirect(url_for('dashboard'))
    
    skills = ResumeParser.extract_skills(resume_text)
    projects = ResumeParser.extract_projects(resume_text)
    education = ResumeParser.extract_education(resume_text)
    strengths = ResumeParser.analyze_strengths(skills, role)
    weak_resume = ResumeParser.identify_weak_areas(skills, role)
    missing = ResumeParser.get_missing_skills(skills, role)
    
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if analysis:
        analysis.resume_text = resume_text
        analysis.target_company = company
        analysis.job_role = role
        analysis.skills = json.dumps(skills)
        analysis.projects = json.dumps(projects)
        analysis.education = education
        analysis.strengths = json.dumps(strengths)
        analysis.weak_areas_resume = json.dumps(weak_resume)
        analysis.missing_skills = json.dumps(missing)
    else:
        analysis = ResumeAnalysis(user_id=current_user.id, resume_text=resume_text, target_company=company, job_role=role,
                                  skills=json.dumps(skills), projects=json.dumps(projects), education=education,
                                  strengths=json.dumps(strengths), weak_areas_resume=json.dumps(weak_resume), missing_skills=json.dumps(missing))
        db.session.add(analysis)
    
    WeakArea.query.filter_by(user_id=current_user.id).delete()
    for w in weak_resume:
        db.session.add(WeakArea(user_id=current_user.id, topic=w, source='resume', severity=7))
    
    InterviewQuestion.query.filter_by(user_id=current_user.id).delete()
    questions = AIEngine.generate_questions(company, role, missing, weak_resume)
    for q in questions:
        db.session.add(InterviewQuestion(user_id=current_user.id, question_text=q['text'], question_type=q['type']))
    db.session.commit()
    session['company'] = company
    session['role'] = role
    flash('Resume analyzed successfully!', 'success')
    return redirect(url_for('preparation'))

# ---------- Preparation (Text Q&A) ----------
@app.route('/preparation')
@login_required
def preparation():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis:
        flash('Please upload resume first!', 'warning')
        return redirect(url_for('dashboard'))
    questions = InterviewQuestion.query.filter_by(user_id=current_user.id).all()
    answers = AnswerEvaluation.query.filter_by(user_id=current_user.id).all()
    weak = WeakArea.query.filter_by(user_id=current_user.id).all()
    strengths = json.loads(analysis.strengths) if analysis.strengths else []
    missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
    return render_template('preparation.html', analysis=analysis, questions=questions, answers=answers, weak_areas=weak, strengths=strengths, missing_skills=missing)

@app.route('/evaluate_answer', methods=['POST'])
@login_required
def evaluate_answer():
    data = request.get_json()
    qid = data.get('question_id')
    answer = data.get('answer')
    question = InterviewQuestion.query.get(qid)
    if not question or question.user_id != current_user.id:
        return jsonify({'error': 'Invalid question'}), 400
    eval_res = AIEngine.evaluate_answer(question.question_text, answer, question.question_type)
    existing = AnswerEvaluation.query.filter_by(user_id=current_user.id, question_id=qid).first()
    if existing:
        existing.user_answer = answer
        existing.score = eval_res['score']
        existing.feedback = eval_res['feedback']
        existing.improved_answer = eval_res['improved_answer']
        existing.clarity_score = eval_res['clarity_score']
        existing.confidence_score = eval_res['confidence_score']
    else:
        db.session.add(AnswerEvaluation(user_id=current_user.id, question_id=qid, user_answer=answer, score=eval_res['score'],
                                        feedback=eval_res['feedback'], improved_answer=eval_res['improved_answer'],
                                        clarity_score=eval_res['clarity_score'], confidence_score=eval_res['confidence_score']))
    if eval_res['score'] < 5:
        topic = f"Answering {question.question_type} question: {question.question_text[:50]}"
        if not WeakArea.query.filter_by(user_id=current_user.id, topic=topic).first():
            db.session.add(WeakArea(user_id=current_user.id, topic=topic, source='answer', severity=8))
    progress = UserProgress.query.filter_by(user_id=current_user.id).first()
    if not progress:
        progress = UserProgress(user_id=current_user.id)
        db.session.add(progress)
    total = AnswerEvaluation.query.filter_by(user_id=current_user.id).count()
    avg = db.session.query(db.func.avg(AnswerEvaluation.score)).filter_by(user_id=current_user.id).scalar() or 0
    progress.total_questions_answered = total
    progress.average_score = avg
    progress.last_active = datetime.utcnow()
    db.session.commit()
    return jsonify(eval_res)

# ---------- Text Mock Interview ----------
@app.route('/mock_interview')
@login_required
def mock_interview():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis:
        flash('Please upload resume first', 'warning')
        return redirect(url_for('dashboard'))
    questions = InterviewQuestion.query.filter_by(user_id=current_user.id).all()
    if not questions:
        missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
        weak = [w.topic for w in WeakArea.query.filter_by(user_id=current_user.id).all()]
        qs = AIEngine.generate_questions(analysis.target_company, analysis.job_role, missing, weak)
        for q in qs:
            db.session.add(InterviewQuestion(user_id=current_user.id, question_text=q['text'], question_type=q['type']))
        db.session.commit()
        questions = InterviewQuestion.query.filter_by(user_id=current_user.id).all()
    q_list = [{'id': q.id, 'text': q.question_text, 'type': q.question_type} for q in questions]
    return render_template('mock_interview.html', questions=q_list)

@app.route('/evaluate_mock', methods=['POST'])
@login_required
def evaluate_mock():
    data = request.get_json()
    qid = data.get('question_id')
    answer = data.get('answer')
    question = InterviewQuestion.query.get(qid)
    if not question or question.user_id != current_user.id:
        return jsonify({'error': 'Invalid question'}), 400
    eval_res = AIEngine.evaluate_answer(question.question_text, answer, question.question_type)
    existing = AnswerEvaluation.query.filter_by(user_id=current_user.id, question_id=qid).first()
    if existing:
        existing.user_answer = answer
        existing.score = eval_res['score']
        existing.feedback = eval_res['feedback']
        existing.improved_answer = eval_res['improved_answer']
    else:
        db.session.add(AnswerEvaluation(user_id=current_user.id, question_id=qid, user_answer=answer, score=eval_res['score'],
                                        feedback=eval_res['feedback'], improved_answer=eval_res['improved_answer'],
                                        clarity_score=eval_res['clarity_score'], confidence_score=eval_res['confidence_score']))
    if eval_res['score'] < 5:
        topic = f"Mock Q: {question.question_text[:50]}"
        if not WeakArea.query.filter_by(user_id=current_user.id, topic=topic).first():
            db.session.add(WeakArea(user_id=current_user.id, topic=topic, source='mock', severity=8))
    progress = UserProgress.query.filter_by(user_id=current_user.id).first()
    if not progress:
        progress = UserProgress(user_id=current_user.id)
        db.session.add(progress)
    total = AnswerEvaluation.query.filter_by(user_id=current_user.id).count()
    avg = db.session.query(db.func.avg(AnswerEvaluation.score)).filter_by(user_id=current_user.id).scalar() or 0
    progress.total_questions_answered = total
    progress.average_score = avg
    progress.last_active = datetime.utcnow()
    db.session.commit()
    return jsonify({'score': eval_res['score'], 'feedback': eval_res['feedback'], 'improved_answer': eval_res['improved_answer']})

# ---------- Interview Chatbot (Text-based) ----------
@app.route('/interview_chatbot')
@login_required
def interview_chatbot():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis:
        flash('Please upload your resume first!', 'warning')
        return redirect(url_for('dashboard'))
    if 'chatbot_questions' not in session:
        missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
        weak = [w.topic for w in WeakArea.query.filter_by(user_id=current_user.id).all()]
        questions_data = AIEngine.generate_questions(analysis.target_company, analysis.job_role, missing, weak)
        session['chatbot_questions'] = questions_data
        session['chatbot_index'] = 0
        session['chatbot_history'] = []
    return render_template('interview_chatbot.html', company=analysis.target_company, role=analysis.job_role, total_questions=len(session.get('chatbot_questions', [])))

@app.route('/chatbot_get_question', methods=['GET'])
@login_required
def chatbot_get_question():
    questions = session.get('chatbot_questions', [])
    index = session.get('chatbot_index', 0)
    if index >= len(questions):
        return jsonify({'finished': True})
    q = questions[index]
    return jsonify({'finished': False, 'question': q['text'], 'type': q['type'], 'index': index+1, 'total': len(questions)})

@app.route('/chatbot_submit_answer', methods=['POST'])
@login_required
def chatbot_submit_answer():
    data = request.get_json()
    user_answer = data.get('answer', '')
    index = session.get('chatbot_index', 0)
    questions = session.get('chatbot_questions', [])
    if index >= len(questions):
        return jsonify({'finished': True})
    current_q = questions[index]
    eval_res = AIEngine.evaluate_answer(current_q['text'], user_answer, current_q['type'])
    history = session.get('chatbot_history', [])
    history.append({'question': current_q['text'], 'type': current_q['type'], 'answer': user_answer, 'score': eval_res['score'], 'feedback': eval_res['feedback']})
    session['chatbot_history'] = history
    if eval_res['score'] < 5:
        topic = f"Chatbot Q: {current_q['text'][:50]}"
        if not WeakArea.query.filter_by(user_id=current_user.id, topic=topic).first():
            db.session.add(WeakArea(user_id=current_user.id, topic=topic, source='chatbot', severity=7))
            db.session.commit()
    progress = UserProgress.query.filter_by(user_id=current_user.id).first()
    if not progress:
        progress = UserProgress(user_id=current_user.id)
        db.session.add(progress)
    total_answers = AnswerEvaluation.query.filter_by(user_id=current_user.id).count() + 1
    new_avg = (progress.average_score * progress.total_questions_answered + eval_res['score']) / total_answers if total_answers > 0 else eval_res['score']
    progress.total_questions_answered = total_answers
    progress.average_score = new_avg
    progress.last_active = datetime.utcnow()
    db.session.commit()
    session['chatbot_index'] = index + 1
    return jsonify({'score': eval_res['score'], 'feedback': eval_res['feedback'], 'improved_answer': eval_res['improved_answer'], 'next_index': index+1, 'finished': index+1 >= len(questions)})

@app.route('/chatbot_reset', methods=['POST'])
@login_required
def chatbot_reset():
    session.pop('chatbot_questions', None)
    session.pop('chatbot_index', None)
    session.pop('chatbot_history', None)
    return jsonify({'status': 'reset'})

# ---------- Voice Interview (with rounds & speech) ----------
@app.route('/voice_interview')
@login_required
def voice_interview():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis:
        flash('Please upload your resume first!', 'warning')
        return redirect(url_for('dashboard'))
    
    skills = json.loads(analysis.skills) if analysis.skills else []
    missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
    weak = [w.topic for w in WeakArea.query.filter_by(user_id=current_user.id).all()]
    interview_rounds = AIEngine.generate_round_questions(analysis.target_company, analysis.job_role, skills, missing, weak)
    
    session['voice_rounds'] = interview_rounds
    session['voice_current_round'] = 'introduction'
    session['voice_q_index'] = 0
    session['voice_history'] = []
    
    return render_template('voice_interview.html', 
                         company=analysis.target_company,
                         role=analysis.job_role)

@app.route('/voice_interview_next', methods=['GET'])
@login_required
def voice_interview_next():
    rounds = session.get('voice_rounds', {})
    current_round = session.get('voice_current_round')
    q_index = session.get('voice_q_index', 0)
    
    round_order = ['introduction', 'hr', 'technical', 'non_technical']
    if not current_round:
        current_round = round_order[0]
        session['voice_current_round'] = current_round
    
    round_data = rounds.get(current_round, {})
    questions = round_data.get('questions', [])
    
    if q_index >= len(questions):
        next_idx = round_order.index(current_round) + 1
        if next_idx < len(round_order):
            session['voice_current_round'] = round_order[next_idx]
            session['voice_q_index'] = 0
            current_round = round_order[next_idx]
            round_data = rounds.get(current_round, {})
            questions = round_data.get('questions', [])
            if questions:
                return jsonify({
                    'type': 'round_transition',
                    'round_name': round_data.get('name', current_round.capitalize()),
                    'question': questions[0],
                    'question_index': 1,
                    'total_in_round': len(questions),
                    'rounds_completed': next_idx
                })
            else:
                return jsonify({'finished': True})
        else:
            return jsonify({'finished': True})
    
    return jsonify({
        'type': 'question',
        'round_name': round_data.get('name', current_round.capitalize()),
        'question': questions[q_index],
        'question_index': q_index + 1,
        'total_in_round': len(questions),
        'rounds_completed': round_order.index(current_round)
    })

@app.route('/voice_interview_submit', methods=['POST'])
@login_required
def voice_interview_submit():
    data = request.get_json()
    user_answer = data.get('answer', '')
    
    current_round = session.get('voice_current_round')
    q_index = session.get('voice_q_index', 0)
    rounds = session.get('voice_rounds', {})
    round_data = rounds.get(current_round, {})
    questions = round_data.get('questions', [])
    current_question = questions[q_index] if q_index < len(questions) else ""
    
    score, feedback = AIEngine.evaluate_conversational(user_answer)
    
    history = session.get('voice_history', [])
    history.append({
        'round': current_round,
        'question': current_question,
        'answer': user_answer,
        'score': score
    })
    session['voice_history'] = history
    
    if score < 5:
        topic = f"Voice Interview - {current_round}: {current_question[:50]}"
        if not WeakArea.query.filter_by(user_id=current_user.id, topic=topic).first():
            db.session.add(WeakArea(user_id=current_user.id, topic=topic, source='voice_interview', severity=8))
            db.session.commit()
    
    progress = UserProgress.query.filter_by(user_id=current_user.id).first()
    if not progress:
        progress = UserProgress(user_id=current_user.id)
        db.session.add(progress)
    total_answers = AnswerEvaluation.query.filter_by(user_id=current_user.id).count() + 1
    new_avg = (progress.average_score * progress.total_questions_answered + score) / total_answers if total_answers > 0 else score
    progress.total_questions_answered = total_answers
    progress.average_score = new_avg
    progress.last_active = datetime.utcnow()
    db.session.commit()
    
    session['voice_q_index'] = q_index + 1
    
    return jsonify({
        'score': score,
        'feedback': feedback,
        'next_index': q_index + 1
    })

@app.route('/voice_interview_reset', methods=['POST'])
@login_required
def voice_interview_reset():
    session.pop('voice_rounds', None)
    session.pop('voice_current_round', None)
    session.pop('voice_q_index', None)
    session.pop('voice_history', None)
    return jsonify({'status': 'reset'})

# ---------- Detailed Analysis ----------
@app.route('/analysis')
@login_required
def analysis():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis:
        flash('No resume found.', 'warning')
        return redirect(url_for('dashboard'))
    skills = json.loads(analysis.skills) if analysis.skills else []
    projects = json.loads(analysis.projects) if analysis.projects else []
    strengths = json.loads(analysis.strengths) if analysis.strengths else []
    weak_resume = json.loads(analysis.weak_areas_resume) if analysis.weak_areas_resume else []
    missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
    return render_template('analysis.html', skills=skills, projects=projects, strengths=strengths, weak_resume=weak_resume, missing=missing, education=analysis.education, company=analysis.target_company, role=analysis.job_role)

# ---------- Mentor Chat ----------
@app.route('/mentor')
@login_required
def mentor():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    company = analysis.target_company if analysis else "your target company"
    role = analysis.job_role if analysis else "the role"
    return render_template('mentor.html', company=company, role=role)

@app.route('/ask_mentor', methods=['POST'])
@login_required
def ask_mentor():
    data = request.get_json()
    user_question = data.get('question', '').lower()
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    company = analysis.target_company if analysis else "the company"
    role = analysis.job_role if analysis else "the role"
    
    if 'resume' in user_question:
        reply = f"Based on your resume, to improve for {company} {role}, tailor your resume with action verbs and quantify achievements."
    elif 'prepare' in user_question or 'preparation' in user_question:
        reply = f"For {company} {role}, focus on DSA, system design, and company values. Practice mock interviews daily."
    elif 'company' in user_question:
        reply = f"{company} looks for problem-solving skills and cultural fit. Research their leadership principles (Amazon), Googleyness (Google), or growth mindset (Microsoft)."
    elif 'technical' in user_question:
        reply = "Practice coding on LeetCode (easy-medium), review OS, DBMS, networks, and build projects."
    elif 'hr' in user_question or 'behavioral' in user_question:
        reply = "Use STAR method (Situation, Task, Action, Result) for behavioral questions."
    elif 'weakness' in user_question or 'weak area' in user_question:
        weak = WeakArea.query.filter_by(user_id=current_user.id).all()
        if weak:
            topics = [w.topic for w in weak[:3]]
            reply = f"Your weak areas: {', '.join(topics)}. Focus on improving these."
        else:
            reply = "No major weak areas detected yet. Keep practicing!"
    else:
        reply = f"I'm your AI mentor for {company} {role}. Ask me about resume, interview questions, company culture, or weak areas."
    return jsonify({'reply': reply})

# ---------- Aptitude ----------
aptitude_questions = [
    {"q": "If a train travels 60 km in 1 hour, how far in 45 minutes?", "options": ["40 km","45 km","50 km","55 km"], "ans": "40 km"},
    {"q": "What is 15% of 200?", "options": ["20","25","30","35"], "ans": "30"},
    {"q": "Solve: 8 + 4 × 2 - 6 ÷ 3", "options": ["14","12","10","16"], "ans": "14"},
    {"q": "Average of 5 numbers is 20. Remove one, average becomes 18. Removed number?", "options": ["28","30","26","24"], "ans": "28"},
    {"q": "Buy cycle for ₹1200, sell at 10% loss. Selling price?", "options": ["₹1080","₹1100","₹1120","₹1000"], "ans": "₹1080"}
]
@app.route('/aptitude')
@login_required
def aptitude():
    q = random.choice(aptitude_questions)
    session['aptitude_answer'] = q['ans']
    return render_template('aptitude.html', question=q['q'], options=q['options'])

@app.route('/check_aptitude', methods=['POST'])
@login_required
def check_aptitude():
    user_ans = request.form.get('answer')
    correct = session.get('aptitude_answer')
    if user_ans == correct:
        flash('✅ Correct! Great job!', 'success')
    else:
        flash(f'❌ Wrong! Correct: {correct}', 'danger')
    return redirect(url_for('aptitude'))

# ---------- Leaderboard ----------
@app.route('/leaderboard')
@login_required
def leaderboard():
    users_data = []
    for u in User.query.all():
        prog = UserProgress.query.filter_by(user_id=u.id).first()
        avg = prog.average_score if prog else 0
        total = prog.total_questions_answered if prog else 0
        users_data.append({'name': u.name, 'email': u.email, 'avg_score': round(avg,1), 'total_answers': total})
    users_data.sort(key=lambda x: x['avg_score'], reverse=True)
    return render_template('leaderboard.html', users=users_data)

# ---------- Resume Builder & Templates ----------
@app.route('/resume_templates')
@login_required
def resume_templates():
    return render_template('resume_templates.html')

@app.route('/resume_builder')
@login_required
def resume_builder():
    rd = ResumeData.query.filter_by(user_id=current_user.id).first()
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    parsed_skills = json.loads(analysis.skills) if analysis and analysis.skills else []
    parsed_projects = json.loads(analysis.projects) if analysis and analysis.projects else []
    parsed_education = analysis.education if analysis else ""
    if rd:
        full_name = rd.full_name or current_user.name
        email = rd.email or current_user.email
        phone = rd.phone or ""
        address = rd.address or ""
        summary = rd.summary or ""
        skills_list = json.loads(rd.skills) if rd.skills else parsed_skills
        projects_list = json.loads(rd.projects) if rd.projects else [{"title": p, "description": ""} for p in parsed_projects]
        education_list = json.loads(rd.education) if rd.education else [{"degree": parsed_education, "institution": "", "year": ""}]
        experience_list = json.loads(rd.experience) if rd.experience else [{"title": "", "company": "", "duration": "", "description": ""}]
        template_choice = rd.template_choice
    else:
        full_name = current_user.name
        email = current_user.email
        phone = ""
        address = ""
        summary = ""
        skills_list = parsed_skills
        projects_list = [{"title": p, "description": ""} for p in parsed_projects]
        education_list = [{"degree": parsed_education, "institution": "", "year": ""}]
        experience_list = [{"title": "", "company": "", "duration": "", "description": ""}]
        template_choice = "professional"
    return render_template('resume_builder.html', full_name=full_name, email=email, phone=phone, address=address,
                          summary=summary, skills_list=skills_list, projects_list=projects_list,
                          education_list=education_list, experience_list=experience_list, template_choice=template_choice)

@app.route('/save_resume_data', methods=['POST'])
@login_required
def save_resume_data():
    data = request.get_json()
    rd = ResumeData.query.filter_by(user_id=current_user.id).first()
    if not rd:
        rd = ResumeData(user_id=current_user.id)
        db.session.add(rd)
    rd.full_name = data.get('full_name')
    rd.email = data.get('email')
    rd.phone = data.get('phone')
    rd.address = data.get('address')
    rd.summary = data.get('summary')
    rd.skills = json.dumps(data.get('skills', []))
    rd.projects = json.dumps(data.get('projects', []))
    rd.education = json.dumps(data.get('education', []))
    rd.experience = json.dumps(data.get('experience', []))
    rd.template_choice = data.get('template_choice', 'professional')
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/preview_resume')
@login_required
def preview_resume():
    rd = ResumeData.query.filter_by(user_id=current_user.id).first()
    if not rd:
        flash('Please build your resume first.', 'warning')
        return redirect(url_for('resume_builder'))
    skills = json.loads(rd.skills) if rd.skills else []
    projects = json.loads(rd.projects) if rd.projects else []
    education = json.loads(rd.education) if rd.education else []
    experience = json.loads(rd.experience) if rd.experience else []
    return render_template('resume_preview.html', full_name=rd.full_name, email=rd.email, phone=rd.phone, address=rd.address,
                          summary=rd.summary, skills=skills, projects=projects, education=education, experience=experience,
                          template=rd.template_choice)

# ---------- Code Practice ----------
@app.route('/code_practice')
@login_required
def code_practice():
    return render_template('code_practice.html')

# ---------- Roadmap & Tips APIs ----------
@app.route('/get_roadmap')
@login_required
def get_roadmap():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis:
        return jsonify({'error': 'No resume'}), 400
    weak_topics = [w.topic for w in WeakArea.query.filter_by(user_id=current_user.id).all()]
    missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
    progress = UserProgress.query.filter_by(user_id=current_user.id).first()
    avg = progress.average_score if progress else 0
    roadmap, platforms = AIEngine.generate_roadmap(weak_topics, missing, analysis.target_company, analysis.job_role, avg)
    existing = Roadmap.query.filter_by(user_id=current_user.id).first()
    if existing:
        existing.plan_data = json.dumps(roadmap)
        existing.updated_at = datetime.utcnow()
    else:
        db.session.add(Roadmap(user_id=current_user.id, plan_data=json.dumps(roadmap)))
    db.session.commit()
    return jsonify({'roadmap': roadmap, 'platforms': platforms, 'weak_areas': weak_topics[:5], 'avg_score': avg})

@app.route('/resume_suggestions')
@login_required
def resume_suggestions():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis:
        return jsonify({'error': 'No resume'}), 400
    skills = json.loads(analysis.skills) if analysis.skills else []
    missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
    sug = []
    if len(skills) < 5:
        sug.append("Add more relevant technical skills.")
    if missing:
        sug.append(f"Include projects demonstrating: {', '.join(missing[:3])}")
    sug.extend(["Use action verbs and quantify achievements.", "Tailor summary to job description.", "Add GitHub/LinkedIn links."])
    return jsonify({'suggestions': sug})

@app.route('/motivation_tip')
@login_required
def motivation_tip():
    tips = ["💪 Consistency beats intensity. Study 2 hours daily!", "🎯 Set small daily goals.", "📝 Review mistakes daily.",
            "🧠 Practice mock interviews.", "⏰ Use Pomodoro technique.", "🌟 Visualize success.", "🤝 Join study groups."]
    return jsonify({'tip': random.choice(tips)})

# ---------- Run ----------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5500)