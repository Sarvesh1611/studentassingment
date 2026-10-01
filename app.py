import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super_secret_key_change_this_in_production'

# --- DATABASE SETUP ---
def init_db():
    """Creates the database tables if they don't exist."""
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                subject TEXT NOT NULL,
                description TEXT NOT NULL,
                due_date TEXT NOT NULL,
                max_marks INTEGER NOT NULL,
                created_by INTEGER NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assignment_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                student_name TEXT NOT NULL,
                project_link TEXT NOT NULL,
                work_notes TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                status TEXT DEFAULT 'submitted',
                marks INTEGER,
                remarks TEXT
            )
        ''')
        conn.commit()

# Initialize database on startup
init_db()

# --- HELPER FUNCTION ---
def login_required(role=None):
    if 'user_id' not in session:
        flash('Please log in first!', 'danger')
        return redirect(url_for('login'))
    if role and session.get('role') != role:
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))
    return None

# --- AUTHENTICATION ROUTES ---
@app.route('/')
def home():
    if 'user_id' in session:
        if session['role'] == 'faculty':
            return redirect(url_for('faculty_dashboard'))
        return redirect(url_for('student_portal'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        
        with sqlite3.connect('database.db') as conn:
            conn.row_factory = sqlite3.Row # Allows accessing columns by name
            cursor = conn.cursor()
            
            # Check if user exists
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            if cursor.fetchone():
                flash('Username already exists!', 'danger')
                return redirect(url_for('register'))
                
            # Save user
            hashed_pw = generate_password_hash(password)
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                           (username, hashed_pw, role))
            conn.commit()
            
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        with sqlite3.connect('database.db') as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                
                if user['role'] == 'faculty':
                    return redirect(url_for('faculty_dashboard'))
                return redirect(url_for('student_portal'))
            else:
                flash('Invalid username or password!', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- FACULTY ROUTES ---
@app.route('/faculty')
def faculty_dashboard():
    if err := login_required('faculty'): return err
    
    with sqlite3.connect('database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM assignments WHERE created_by = ?", (session['user_id'],))
        assignments = cursor.fetchall()
        
    return render_template('faculty.html', assignments=assignments)

@app.route('/faculty/assignment/new', methods=['POST'])
def create_assignment():
    if err := login_required('faculty'): return err
    
    title = request.form['title']
    subject = request.form['subject']
    description = request.form['description']
    due_date = request.form['due_date'] # Stored as ISO string
    max_marks = int(request.form['max_marks'])
    
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO assignments (title, subject, description, due_date, max_marks, created_by) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (title, subject, description, due_date, max_marks, session['user_id']))
        conn.commit()
        
    flash('Assignment created successfully!', 'success')
    return redirect(url_for('faculty_dashboard'))

@app.route('/faculty/assignment/<int:assignment_id>')
def view_submissions(assignment_id):
    if err := login_required('faculty'): return err
    
    with sqlite3.connect('database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,))
        assignment = cursor.fetchone()
        
        cursor.execute("SELECT * FROM submissions WHERE assignment_id = ?", (assignment_id,))
        submissions = cursor.fetchall()
        
    return render_template('faculty_submissions.html', assignment=assignment, submissions=submissions)

@app.route('/faculty/submission/<int:submission_id>/grade', methods=['POST'])
def grade_submission(submission_id):
    if err := login_required('faculty'): return err
    
    marks = int(request.form['marks'])
    remarks = request.form['remarks']
    
    with sqlite3.connect('database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get assignment details to check max marks
        cursor.execute("SELECT assignment_id FROM submissions WHERE id = ?", (submission_id,))
        sub = cursor.fetchone()
        
        cursor.execute("SELECT max_marks FROM assignments WHERE id = ?", (sub['assignment_id'],))
        assignment = cursor.fetchone()
        max_marks = assignment['max_marks']
        
        # Business Logic: Validate marks
        if marks < 0 or marks > max_marks:
            flash(f'Error: Marks must be between 0 and {max_marks}.', 'danger')
            return redirect(url_for('view_submissions', assignment_id=sub['assignment_id']))
            
        # Update submission
        cursor.execute("""
            UPDATE submissions SET marks = ?, remarks = ?, status = 'graded' WHERE id = ?
        """, (marks, remarks, submission_id))
        conn.commit()
        
    flash('Submission graded successfully!', 'success')
    return redirect(url_for('view_submissions', assignment_id=sub['assignment_id']))

# --- STUDENT ROUTES ---
@app.route('/student')
def student_portal():
    if err := login_required('student'): return err
    
    with sqlite3.connect('database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM assignments")
        assignments = cursor.fetchall()
        
        # Enrich assignments with student-specific data
        for i, a in enumerate(assignments):
            cursor.execute("SELECT * FROM submissions WHERE assignment_id = ? AND student_id = ?",
                           (a['id'], session['user_id']))
            sub = cursor.fetchone()
            
            # Convert to dictionary so we can add new keys
            a_dict = dict(a)
            a_dict['submission'] = dict(sub) if sub else None
            # Check if overdue
            a_dict['is_overdue'] = datetime.fromisoformat(a['due_date']) < datetime.now()
            assignments[i] = a_dict
            
    return render_template('student.html', assignments=assignments)

@app.route('/student/assignment/<int:assignment_id>/submit', methods=['POST'])
def submit_assignment(assignment_id):
    if err := login_required('student'): return err
    
    with sqlite3.connect('database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,))
        assignment = cursor.fetchone()
        
        # Business Logic: Block submissions after deadline
        if datetime.fromisoformat(assignment['due_date']) < datetime.now():
            flash('Submission rejected: The deadline has passed.', 'danger')
            return redirect(url_for('student_portal'))
            
        # Business Logic: Prevent multiple submissions
        cursor.execute("SELECT id FROM submissions WHERE assignment_id = ? AND student_id = ?",
                       (assignment_id, session['user_id']))
        if cursor.fetchone():
            flash('You have already submitted this assignment.', 'warning')
            return redirect(url_for('student_portal'))
            
        project_link = request.form['project_link']
        work_notes = request.form['work_notes']
        
        cursor.execute("""
            INSERT INTO submissions (assignment_id, student_id, student_name, project_link, work_notes, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (assignment_id, session['user_id'], session['username'], project_link, work_notes, datetime.now().isoformat()))
        conn.commit()
        
    flash('Assignment submitted successfully!', 'success')
    return redirect(url_for('student_portal'))

if __name__ == '__main__':
    app.run(debug=True)