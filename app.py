from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session # <-- Ensure 'session' is imported!
import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import re
from PyPDF2 import PdfReader
import string
from sqlalchemy import func
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# ✅ NLP/ML imports
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

app = Flask(__name__)
app.secret_key = "secret123"

# ✅ Database setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/smarthire'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# -------------------- DATABASE MODELS --------------------
class User(db.Model):
    __tablename__ = 'User'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False)

def is_hashed(password):
    # Detect if the password is already hashed (scrypt or pbkdf2)
    return password.startswith("scrypt:") or password.startswith("pbkdf2:")

def hash_plaintext_passwords():
    users = User.query.all()
    for user in users:
        if not is_hashed(user.password):
            user.password = generate_password_hash(user.password)
            print(f"Hashed password for user: {user.username}")
    db.session.commit()
    print("All plain-text passwords have been hashed successfully.")

# -----------------------------------------------------
class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    company = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(100), default="N/A")
    job_type = db.Column(db.String(50), default="Full-Time")
    salary = db.Column(db.String(50), default="Negotiable")
    status = db.Column(db.String(20), default='Pending')
    employer_id = db.Column(db.Integer, db.ForeignKey('employer.id'), nullable=False)
    employer = db.relationship('Employer', backref='jobs')

    # ✅ Add this field for date posted
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --- Profile Models (Must come before Application if referenced by it) ---
class Applicant(db.Model):
    __tablename__ = "applicant"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True, nullable=False)
    fullname = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    skills = db.Column(db.String(255), nullable=True)
    experience = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f"<Applicant {self.fullname}>"

class Employer(db.Model):
    __tablename__ = "employer"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True, nullable=False)
    fullname = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    company = db.Column(db.String(100), nullable=True)

    def __repr__(self):
        return f"<Employer {self.fullname}>"

class Resume(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Links to the Applicant profile
    applicant_id = db.Column(db.Integer, db.ForeignKey('applicant.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    owner_name = db.Column(db.String(150)) 
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    applicant = db.relationship('Applicant', backref='resumes')

# --- Application Model ---
class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Links to the Applicant table
    applicant_id = db.Column(db.Integer, db.ForeignKey('applicant.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    status = db.Column(db.String(50), default='Submitted')

    # applicant_profile relationship is set by Applicant.applications backref
    job = db.relationship('Job', backref='applications', lazy=True)

class Screening(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # The ID of the resume that was screened
    resume_id = db.Column(db.Integer, db.ForeignKey('resume.id'), nullable=False)
    # The ID of the job description used for screening
    job_id = db.Column(db.Integer, db.ForeignKey('job.id')) 
   
    owner_name = db.Column(db.String(150))
    job_description_text = db.Column(db.Text, nullable=False)
    matched_skills = db.Column(db.Text) # Storing a comma-separated list of skills
    match_score = db.Column(db.Float)
    screened_at = db.Column(db.DateTime, default=datetime.utcnow)
    resume = db.relationship('Resume', backref='screenings')
    job = db.relationship('Job', backref='screenings')

# -------------------- FILE FOLDERS --------------------
# Define the base directory of the current script (app.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# UPLOAD_FOLDER is now C:/xampp/htdocs/smarthire/myproject/static/uploads
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# SCREENING_FOLDER is C:/xampp/htdocs/smarthire/myproject/static/screenings
SCREENING_FOLDER = os.path.join(BASE_DIR, "static", "screenings")
os.makedirs(SCREENING_FOLDER, exist_ok=True)

# Update Flask configuration (if not already done later in the code)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# -------------------- SKILL KEYWORDS --------------------
SKILL_KEYWORDS = [
    "python", "java", "c++", "flask", "django", "machine learning",
    "deep learning", "data analysis", "sql", "nlp", "react", "aws"
]

# -------------------- AUTH --------------------

@app.route("/")
def login():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def do_login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    user = User.query.filter(func.lower(User.username) == username.lower()).first()

    if user and user.password == password:
        session["user_id"] = user.id
        session["role"] = user.role
        print(f"✅ Logged in as: {user.username} (role={user.role})")

        if user.role == "admin":
            return redirect(url_for("admin_dashboard"))
        elif user.role == "applicant":
            return redirect(url_for("applicant_dashboard"))
        elif user.role == "employer":
            return redirect(url_for("employer_dashboard"))
        else:
            flash("Unknown user role. Contact admin.", "error")
            return redirect(url_for("login"))

    # If we reach here, login failed
    flash("❌ Invalid username or password", "error")
    return redirect(url_for("login"))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"] 
        password = request.form["password"]
        user_role = request.form.get("role", "applicant")  # default 'applicant'

        # Check if username exists
        existing_user = User.query.filter(func.lower(User.username) == username.lower()).first()
        if existing_user:
            flash("Username already exists!", "error")
            return redirect(url_for("signup"))

        try:
            # 1️⃣ Create User (plain-text password)
            new_user = User(
                username=username,
                password=password,
                role=user_role
            )

            db.session.add(new_user)
            db.session.flush()  # to get new_user.id

            # 2️⃣ Create profile
            if user_role == "applicant":
                new_profile = Applicant(
                    user_id=new_user.id,
                    fullname=username,
                    email=email,
                    skills="N/A",
                    experience="0 years"
                )

            elif user_role == "employer":
                new_profile = Employer(
                    user_id=new_user.id,
                    fullname=username,
                    email=email,
                    company="N/A"
                )

            else:
                db.session.rollback()
                flash("Invalid role selected.", "error")
                return redirect(url_for("signup"))

            db.session.add(new_profile)
            db.session.commit()
            flash("Sign up successful! You can now log in.", "success")
            return redirect(url_for("login"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error during signup: {e}", "error")
            return redirect(url_for("signup"))
    return render_template("signup.html")

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"]
        flash(f"Password reset link sent to {email}", "success")
    return render_template("forgot_password.html")

# -------------------- LOGOUT ROUTE --------------------
@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

# -------------------- DASHBOARDS --------------------
from flask import session # Make sure this is imported
@app.route("/dashboard/employer")
def employer_dashboard():
    if 'user_id' not in session or session.get('role') != 'employer':
        flash("Unauthorized access. Please log in as an employer.", "error")
        return redirect(url_for("login"))

    employer = Employer.query.filter_by(user_id=session['user_id']).first()
    if not employer:
        flash("Employer profile not found.", "error")
        return redirect(url_for("login"))

    # Fetches ALL jobs from the database for viewing
    jobs_list = Job.query.order_by(Job.created_at.desc()).all()

    resumes_list = Resume.query.all()
    screenings_list = Screening.query.order_by(Screening.screened_at.desc()).all()

    stats = {
        "uploaded_resumes": len(resumes_list),
        "screened_resumes": len(screenings_list),
        "job_posts": len(jobs_list)
    }

    return render_template(
        "employer_dashboard.html",
        employer=employer,
        jobs=jobs_list,
        resumes=resumes_list,
        screenings=screenings_list,
        stats=stats,
        shortlisted=[],
        interviews=[]
    )

@app.route("/dashboard/applicant")
def applicant_dashboard():
    # ⚠️ Check if user is logged in and is an applicant
    if 'user_id' not in session or session.get('role') != 'applicant':
        flash("Please log in as an applicant.", "error")
        return redirect(url_for("login"))
  
    # Fetch applicant profile linked to session
    applicant = Applicant.query.filter_by(user_id=session['user_id']).first()
    if not applicant:
        flash("Applicant profile not found. Please contact admin.", "error")
        return redirect(url_for("login"))

        # Fetch all active jobs
    jobs = Job.query.filter(Job.status == "Approved").all()

    # Optional: fetch jobs already applied to by this applicant
    applied_job_ids = [app.job_id for app in Application.query.filter_by(applicant_id=applicant.id).all()]

    return render_template(
        "applicant_dashboard.html",
        jobs=jobs,
        applicant=applicant,
        applied_job_ids=applied_job_ids
    )

@app.route("/dashboard/admin")
def admin_dashboard():
    applicants_list = Applicant.query.all()
    employers_list = Employer.query.all()
   
    approved_jobs = Job.query.filter_by(status='approved').all()
    pending_jobs = Job.query.filter_by(status='pending').all()

    # Combine approved + pending for the dashboard detailed records
    all_jobs = approved_jobs + pending_jobs

    return render_template(
        'admin_dashboard.html',
        applicants_list=applicants_list,
        employers_list=employers_list,
        approved_jobs=approved_jobs,
        pending_jobs=pending_jobs,
        all_jobs=all_jobs
    )

# -------------------- RESUMES --------------------
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded resumes from UPLOAD_FOLDER"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    # ✅ Ensure the user is logged in and is an applicant
    if 'user_id' not in session or session.get('role') != 'applicant':
        flash("Please log in as an applicant.", "error")
        return redirect(url_for("login"))

    applicant = Applicant.query.filter_by(user_id=session['user_id']).first()
    if not applicant:
        flash("Applicant profile not found.", "error")
        return redirect(url_for("applicant_dashboard"))
# ✅ Check if a file was uploaded
    if 'resume' not in request.files:
        flash("No file selected!", "error")
        return redirect(url_for("applicant_dashboard"))

    # The file line must be inside the block or correctly indented after it.
    # Assuming this logic is inside a route function (def upload_resume():)
    file = request.files['resume']
    if file.filename == '':
        flash("No file selected!", "error")
        return redirect(url_for("applicant_dashboard"))
    try:
        # ✅ Make filename safe and unique
        filename = secure_filename(f"{applicant.fullname}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # ✅ Ensure the upload folder exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

        # ✅ Save the file
        file.save(filepath)

        # ✅ Save in DB
        new_resume = Resume(
            applicant_id=applicant.id,
            filename=filename,
            owner_name=applicant.fullname
        )

        db.session.add(new_resume)
        db.session.commit()

        flash("✅ Resume uploaded successfully!", "success")
        return redirect(url_for("applicant_dashboard"))

    except Exception as e:
        db.session.rollback()
        flash(f"Error uploading resume: {e}", "error")
        return redirect(url_for("applicant_dashboard"))

@app.route("/download_resume/<filename>")
def download_resume(filename):
    """Download uploaded resumes from UPLOAD_FOLDER"""
    try:
        return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)
    except FileNotFoundError:
        flash("Resume file not found.", "error")
        return redirect(url_for("employer_dashboard"))

# FIX: /delete_resume/<int:resume_id>
@app.route("/delete_resume/<int:resume_id>", methods=["POST"])
def delete_resume(resume_id):
    # ✅ NEW LOGIC: Fetch and delete the Resume object
    resume = Resume.query.get(resume_id)
    if resume:
        # Delete the file from the filesystem first
        filepath = os.path.join(UPLOAD_FOLDER, resume.filename)
        if os.path.exists(filepath):
            os.remove(filepath)            

        # Delete the record from the database
        owner_name = resume.owner_name
        db.session.delete(resume)
        db.session.commit()
      
        flash(f"{owner_name}'s resume deleted successfully.", "success")
    else:
        flash("Resume not found.", "error")
    return redirect(url_for("employer_dashboard"))

# -------------------- JOB ROUTES --------------------
@app.route("/jobs/add_page", methods=["GET"])
def add_job_page():
    if session.get("role") != "employer":
        flash("Unauthorized access.", "error")
        return redirect(url_for("login"))
    return render_template("add_job.html")

@app.route("/jobs/submit", methods=["POST"])
def submit_job():
    if session.get("role") != "employer":
        flash("Unauthorized access.", "error")
        return redirect(url_for("login"))
    employer_user_id = session.get("user_id")
    employer = Employer.query.filter_by(user_id=employer_user_id).first()
    if not employer:
        flash("Employer profile not found. Please complete your profile first.", "error")
        return redirect(url_for("employer_dashboard"))

    # Collect form data
    title = request.form.get("title")
    company = request.form.get("company")
    location = request.form.get("location")
    job_type = request.form.get("job_type")
    salary = request.form.get("salary")
    description = request.form.get("description")

    # Validation
    if not title or not company:
        flash("Title and company name are required.", "error")
        return redirect(url_for("add_job_page"))

    # Save job
    new_job = Job(
        title=title,
        company=company,
        location=location,
        job_type=job_type,
        salary=salary,
        description=description,
        status="Pending",
        employer_id=employer.id
    )

    db.session.add(new_job)
    db.session.commit()
    flash(f"✅ Job '{title}' added successfully!", "success")
    return redirect(url_for("employer_dashboard"))

# FIX: /jobs/edit/<int:job_id>
@app.route("/jobs/edit/<int:job_id>", methods=["GET", "POST"])
def edit_job(job_id):
    # 1. Authentication Check (Recommended, if not done elsewhere)
    if session.get("role") != "employer":
        flash("Unauthorized access.", "error")
        return redirect(url_for("login"))

    # 2. Fetch the Job Object
    job = Job.query.get(job_id) 
    if not job:
        flash("Job not found.", "error")
        return redirect(url_for("employer_dashboard"))

    if request.method == "POST":
        # 3. Handle POST Request (Form Submission/Update)
        job.title = request.form.get("title")
        job.company = request.form.get("company")
        job.location = request.form.get("location")
        job.job_type = request.form.get("job_type")
        job.salary = request.form.get("salary")
        job.description = request.form.get("description")
        
        db.session.commit()
        
        flash(f"✅ Job '{job.title}' updated successfully!", "success")
        return redirect(url_for("employer_dashboard"))

    # 4. Handle GET Request (Display Form)
    # 🎯 FIX: Render the template and pass the 'job' object.
    return render_template("add_job.html", job=job)

# FIX: /jobs/delete/<int:job_id>
@app.route("/jobs/delete/<int:job_id>", methods=["POST"])
def delete_job(job_id):
    # ✅ NEW LOGIC: Query and delete the Job object
    job = Job.query.get(job_id)
    if job:
        db.session.delete(job)
        db.session.commit() # Commit the deletion
        flash(f"Job {job_id} deleted successfully.", "success")
    else:
        flash(f"Job not found.", "error")
       
    return redirect(url_for("employer_dashboard"))

@app.route("/jobs/approve/<int:job_id>", methods=["POST"])
def approve_job(job_id):
    job = Job.query.get_or_404(job_id)
    job.status = "Approved"
    db.session.commit()
    flash(f"✅ Job '{job.title}' approved successfully!", "success")
    return redirect(url_for("admin_dashboard"))

@app.route('/archive_job/<int:job_id>', methods=['POST'])
def archive_job(job_id):
    job = Job.query.get_or_404(job_id)  # Adjust 'Job' to your model name
    db.session.delete(job)  # Or mark as archived if you have a column
    db.session.commit()
    flash(f"Job ID {job_id} archived successfully!", "success")
    return redirect(url_for('admin_dashboard'))

# -------------------- RESUME SCREENING --------------------
import spacy

# Load spaCy English model for optional NLP detection of professions
nlp = spacy.load("en_core_web_sm")

# List of common professions/job titles to detect
PROFESSIONS = [
    "engineer", "developer", "manager", "analyst", "designer",
    "consultant", "technician", "administrator", "specialist",
    "scientist", "coordinator", "assistant", "officer", "intern"
]

def extract_text_from_pdf(filepath):
    """Extract text from PDF file"""
    try:
        reader = PdfReader(filepath)
        text = "".join(page.extract_text() or "" for page in reader.pages)
        return text
    except Exception as e:
        print("PDF read error:", e)
        return ""



def calculate_ai_match_score(resume_text, job_description):
    """Calculate matched skills and TF-IDF similarity score"""
    translator = str.maketrans(string.punctuation, ' ' * len(string.punctuation))
    resume_clean = resume_text.lower().translate(translator)
    job_clean = job_description.lower().translate(translator)

    # Match predefined skills
    matched = [skill for skill in SKILL_KEYWORDS if re.search(r'\b' + re.escape(skill.lower()) + r'\b', resume_clean)]
    try:
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform([resume_clean, job_clean])
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        score = round(similarity * 100, 2)
    except Exception as e:
        print("TF-IDF similarity error:", e)
        score = 0.0
    return matched, score

def extract_contact_info(text):
    """Extract email and phone number from resume"""
    emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    email = emails[0] if emails else "Not detected"
    phones = re.findall(r"(?:\+?\d{1,3}[\s\-\.])?(?:\(?\d{2,4}\)?[\s\-\.])?\d{3,4}[\s\-\.]?\d{3,4}", text)
    phone = phones[0] if phones else "Not detected"
    return email, phone

def extract_professions(resume_text):

    """Detect professions/job titles from resume"""
    resume_text_lower = resume_text.lower()
    matched = set()
    # Method 1: simple keyword matching
    for prof in PROFESSIONS:
        if prof in resume_text_lower:
            matched.add(prof)

    # Method 2: optional NLP entity recognition for future enhancement
    doc = nlp(resume_text_lower)
    for ent in doc.ents:
        if ent.label_ in ["ORG", "WORK_OF_ART", "PRODUCT"]:
            for prof in PROFESSIONS:
                if prof in ent.text.lower():
                    matched.add(prof)

    return list(matched)

@app.route("/upload_screening", methods=["POST"])
def upload_screening():
    # 1. Get data from the form
    resume_id = request.form.get("resume_id") # Assume the form now passes the Resume ID
    job_id = request.form.get("job_id")
    job_description_text = request.form.get("job_description", "").strip()

    if not resume_id:
        flash("Please select a resume to screen.", "error")
        return redirect(url_for("employer_dashboard"))
       
    # 2. Fetch the Resume and Job from the database
    resume = Resume.query.get(resume_id)
    job = Job.query.get(job_id) if job_id else None

    if not resume:
        flash("Resume not found in database.", "error")
        return redirect(url_for("employer_dashboard"))        

    # Determine the actual job description text to use
    if job:
        job_description = job.description
    elif job_description_text:
        job_description = job_description_text
    else:
        flash("Please select a job or provide a job description for screening.", "error")
        return redirect(url_for("employer_dashboard"))

    # 3. Get the file path
    filepath = os.path.join(UPLOAD_FOLDER, resume.filename)
    if not os.path.exists(filepath):
        # Fallback to checking the SCREENING_FOLDER if UPLOAD_FOLDER is empty
        filepath = os.path.join(SCREENING_FOLDER, resume.filename)
        if not os.path.exists(filepath):
            flash(f"Resume file '{resume.filename}' not found on server.", "error")
            return redirect(url_for("employer_dashboard"))

    # 4. Perform Screening Logic
    resume_text = extract_text_from_pdf(filepath)
    email, phone = extract_contact_info(resume_text)
    # Calculate matched skills and AI score
    matched_skills, match_score = calculate_ai_match_score(resume_text, job_description)

    # Extract professions and merge with matched skills
    matched_professions = extract_professions(resume_text)
    final_matched_skills = list(set(matched_skills + matched_professions))
    # 5. Save Screening Record to the Database (NEW LOGIC)
    try:
        new_screening = Screening(
            resume_id=resume.id,
            job_id=job.id if job else None,
            owner_name=resume.owner_name,
            job_description_text=job_description,
            matched_skills=", ".join(final_matched_skills), # Convert list to string for DB
            match_score=match_score
        )

        db.session.add(new_screening)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Error saving screening result: {e}", "error")
        # Continue to display result even if save fails
       
    # 6. Prepare data for the results page
    highlighted_resume = resume_text
    for skill in sorted(set(final_matched_skills), key=len, reverse=True):
        try:
            highlighted_resume = re.sub(
                rf"\b({re.escape(skill)})\b",
                r"<mark style='background:#FFD54F;padding:0.05rem 0.15rem;border-radius:0.15rem;'>\1</mark>",
                highlighted_resume,
                flags=re.IGNORECASE
            )
        except re.error:
            continue        

    # Find all jobs for the matched jobs section (now using DB)
    all_jobs = Job.query.all()
    matched_jobs = []
    for j in all_jobs:
        combined = f"{j.title} {j.company} {j.description}".lower()
        if any(skill.lower() in combined for skill in final_matched_skills):
            matched_jobs.append(j)

    return render_template(
        "ai_resume_result.html",
        email=email,
        phone=phone,
        score=match_score,
        matched_skills=final_matched_skills,
        skills_count=len(SKILL_KEYWORDS) + len(PROFESSIONS),
        highlighted_resume=highlighted_resume,
        matched_jobs=matched_jobs
    )

@app.route("/download_screening/<filename>")
def download_screening(filename):
    try:
        return send_from_directory(SCREENING_FOLDER, filename, as_attachment=True)
    except FileNotFoundError:
        flash("Screening file not found.", "error")
        return redirect(url_for("employer_dashboard"))

# FIX: /delete_screening/<int:screening_id>
@app.route("/delete_screening/<int:screening_id>", methods=["POST"])
def delete_screening(screening_id):
    # ✅ NEW LOGIC: Query and delete the Screening object
    screening_record = Screening.query.get(screening_id)

    if screening_record:
        # Note: You were trying to delete a PDF, but the screening record
        # doesn't store a separate file. Just delete the database record.
        db.session.delete(screening_record)
        db.session.commit()
        flash("✅ Screening record deleted!", "success")
    else:
        flash("Screening record not found.", "error")
    return redirect(url_for("employer_dashboard"))

# -------------------- APPLICANT PROFILE --------------------
@app.route("/applicant/profile", methods=["GET", "POST"])
def applicant_profile():
    if 'user_id' not in session or session.get("role") != 'applicant':
        flash("Please log in as an applicant.", "error")
        return redirect(url_for("login"))

    applicant = Applicant.query.filter_by(user_id=session['user_id']).first()
    if not applicant:
        flash("Applicant profile not found.", "error")
        return redirect(url_for("applicant_dashboard"))

    if request.method == "POST":
        applicant.fullname = request.form.get("fullname")
        applicant.email = request.form.get("email")
        applicant.skills = request.form.get("skills")
        applicant.experience = request.form.get("experience")
        db.session.commit()
    flash('Profile updated successfully!')
    return redirect(url_for('applicant_dashboard'))
    return render_template("applicant_profile.html", applicant=applicant)

# -------------------- USER MANAGEMENT EDIT PAGES (REVISED) --------------------
@app.route("/edit_applicant/<int:applicant_id>", methods=["GET", "POST"])
def edit_applicant(applicant_id):
    applicant = Applicant.query.get_or_404(applicant_id)

    if request.method == "POST":
        applicant.fullname = request.form.get("fullname")
        applicant.email = request.form.get("email")
        applicant.skills = request.form.get("skills")
        applicant.experience = request.form.get("experience")
        db.session.commit()
        flash(f"✅ Applicant '{applicant.fullname}' profile updated!", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("edit_applicant.html", applicant=applicant)

@app.route("/edit_employer/<int:employer_id>", methods=["GET", "POST"])
def edit_employer(employer_id):
    employer = Employer.query.get_or_404(employer_id)

    if request.method == "POST":
        employer.fullname = request.form.get("fullname")
        employer.email = request.form.get("email")
        employer.company = request.form.get("company")
        db.session.commit()
        flash(f"✅ Employer '{employer.fullname}' profile updated!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("edit_employer.html", employer=employer)

@app.route('/edit-profile', methods=['GET', 'POST'])
def edit_profile():
    applicant_id = session.get('user_id')
    if not applicant_id:
        flash("Please log in first.", "warning")
        return redirect(url_for('login'))

    applicant = Applicant.query.filter_by(user_id=applicant_id).first()
    if not applicant:
        flash("Applicant profile not found.", "error")
        return redirect(url_for('applicant_dashboard'))

    if request.method == 'POST':
        applicant.fullname = request.form.get('fullname')
        applicant.skills = request.form.get('skills')
        applicant.experience = request.form.get('experience')
        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for('applicant_dashboard'))
    return render_template('applicant_profile.html', applicant=applicant)

# -------------------- RUN APP --------------------
if __name__ == "__main__":
    with app.app_context():
        # hash_plaintext_passwords()   <-- remove/comment this
        db.create_all()
    app.run(debug=True)