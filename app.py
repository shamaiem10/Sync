from flask import Flask, render_template, session, url_for, request, redirect, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'syn-secret'  # Needed for session

# --- DB Helper ---
def get_db_connection():
    conn = sqlite3.connect('data.db')
    conn.row_factory = sqlite3.Row
    return conn

# --- Signup Route ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if email already exists
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            return "Email already registered."

        # Insert new user
        cursor.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)',
                       (name, email, hashed_password))
        conn.commit()
        conn.close()

        return redirect('/login')

    return render_template('signup.html')

# --- Login Route ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            return redirect('/dashboard')
        else:
            return "Invalid email or password."

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    user_name = session['user_name']

    conn = get_db_connection()
    c = conn.cursor()

    # Get count of pending invitations
    c.execute("""
        SELECT COUNT(*) FROM invitations
        WHERE invited_user_id = ? AND status = 'pending'
    """, (user_id,))
    invite_count = c.fetchone()[0]

    # 💡 NEW: Get full invitation info
    c.execute("""
        SELECT invitations.id, projects.title AS project_title, users.name AS inviter_name
        FROM invitations
        JOIN projects ON invitations.project_id = projects.id
        JOIN users ON invitations.invited_by = users.id
        WHERE invitations.invited_user_id = ? AND invitations.status = 'pending'
    """, (user_id,))
    invitations = c.fetchall()

    conn.close()

    return render_template(
        'dashboard.html',
        name=user_name,
        invite_count=invite_count,
        invitations=invitations
    )


    

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/create', methods=['GET', 'POST'])
def create_project():
    if 'user_id' not in session:
        return redirect('/login')

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        deadline = request.form['deadline']
        member_emails = request.form['members'].split(',')

        user_id = session['user_id']

        conn = sqlite3.connect("data.db")
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # 1. Create project
        c.execute("""
            INSERT INTO projects (title, description, deadline, created_by)
            VALUES (?, ?, ?, ?)
        """, (title, description, deadline, user_id))
        project_id = c.lastrowid

        # 2. Add creator as leader
        c.execute("""
            INSERT INTO project_members (project_id, user_id, role)
            VALUES (?, ?, ?)
        """, (project_id, user_id, 'leader'))

        # 3. Invite members
        for email in member_emails:
            email = email.strip().lower()
            if email:
                # Check if user exists
                c.execute("SELECT id FROM users WHERE email = ?", (email,))
                invited = c.fetchone()
                if invited:
                    invited_user_id = invited['id']
                    # Add to invitations
                    c.execute("""
                        INSERT INTO invitations (project_id, invited_by, invited_user_id)
                        VALUES (?, ?, ?)
                    """, (project_id, user_id, invited_user_id))

        conn.commit()
        conn.close()
        return redirect('/dashboard')

    return render_template('create_project.html')

# --- Run App ---
if __name__ == '__main__':
    app.run(debug=True)
