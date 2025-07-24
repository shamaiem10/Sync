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




@app.route('/respond_invite', methods=['POST'])
def respond_invite():
    if 'user_id' not in session:
        return redirect('/login')

    invite_id = request.form['invite_id']
    response = request.form['response']  # should be 'accepted' or 'declined'

    if response not in ['accepted', 'declined']:
        return "Invalid response"

    try:
        with sqlite3.connect("data.db") as conn:
            c = conn.cursor()

            # 1. Get project_id and invited_user_id
            c.execute("SELECT project_id, invited_user_id FROM invitations WHERE id = ?", (invite_id,))
            invite = c.fetchone()

            if not invite:
                return "Invitation not found."

            project_id = invite[0]
            invited_user_id = invite[1]

            # 2. Update invitation status
            c.execute("UPDATE invitations SET status = ? WHERE id = ?", (response, invite_id))

            # 3. If accepted, add to project_members
            if response == 'accepted':
                c.execute("""
                    INSERT INTO project_members (project_id, user_id, role)
                    VALUES (?, ?, ?)
                """, (project_id, invited_user_id, 'member'))

    except sqlite3.OperationalError as e:
        return f"Database error: {e}"

    return redirect('/dashboard')
@app.route('/my-projects')
def my_projects():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT p.id, p.title, p.description, p.deadline, pm.role
        FROM project_members pm
        JOIN projects p ON pm.project_id = p.id
        WHERE pm.user_id = ?
    """, (user_id,))

    projects = cursor.fetchall()
    conn.close()

    return render_template('my_projects.html', projects=projects)


@app.route('/project/<int:project_id>', methods=['GET', 'POST'])
def project_details(project_id):
    if 'user_id' not in session:
        return redirect('/login')

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    user_id = session['user_id']

    # Get project info
    c.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    project = c.fetchone()

    # Check if user is a leader
    c.execute("SELECT role FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, user_id))
    role = c.fetchone()
    is_leader = role and role['role'] == 'leader'

    # Handle task creation if POST and user is a leader
    if request.method == 'POST' and is_leader:
        task_title = request.form['task_title']
        task_description = request.form['task_description']
        assigned_to = request.form['assigned_to']
        
        # Use the correct status allowed by your schema
        status = 'not started'

        c.execute("""
            INSERT INTO tasks (title, description, status, assigned_to, project_id)
            VALUES (?, ?, ?, ?, ?)
        """, (task_title, task_description, status, assigned_to, project_id))
        conn.commit()

    # Get all members of the project
    c.execute("""
        SELECT u.id, u.name, u.email, pm.role
        FROM project_members pm
        JOIN users u ON pm.user_id = u.id
        WHERE pm.project_id = ?
    """, (project_id,))
    members = c.fetchall()

    # Get all tasks for the project
    c.execute("""
    SELECT t.id, t.title, t.description, t.status, t.assigned_to, u.name as assignee_name
    FROM tasks t
    JOIN users u ON t.assigned_to = u.id
    WHERE t.project_id = ?
""", (project_id,))

    tasks = c.fetchall()

    conn.close()

    return render_template('project_details.html',
                           project=project,
                           members=members,
                           tasks=tasks,
                           is_leader=is_leader)


@app.route('/delete_task/<int:task_id>', methods=['POST'])
def delete_task(task_id):
    if 'user_id' not in session:
        return redirect('/login')

    project_id = request.form['project_id']
    conn = get_db_connection()
    c = conn.cursor()

    # Optionally: verify user is project leader here
    c.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

    return redirect(f'/project/{project_id}')



@app.route('/update_task_status/<int:task_id>', methods=['POST'])
def update_task_status(task_id):
    if 'user_id' not in session:
        return redirect('/login')

    new_status = request.form['status']
    user_id = session['user_id']

    conn = get_db_connection()
    c = conn.cursor()

    # Check if the task is assigned to this user (extra security)
    c.execute("SELECT assigned_to FROM tasks WHERE id = ?", (task_id,))
    task = c.fetchone()

    if task and task['assigned_to'] == user_id:
        c.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, task_id))
        conn.commit()

    conn.close()

    # Redirect back to the same project page
    project_id = request.args.get("project_id")
    return redirect(f"/project/{project_id}" if project_id else "/dashboard")



@app.route('/edit_task/<int:task_id>', methods=['GET', 'POST'])
def edit_task(task_id):
    if 'user_id' not in session:
        return redirect('/login')

    project_id = request.args.get('project_id')
    conn = get_db_connection()
    c = conn.cursor()

    # Fetch the task
    c.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = c.fetchone()

    # Fetch project members for dropdown
    c.execute("""
        SELECT u.id, u.name FROM users u
        JOIN project_members pm ON u.id = pm.user_id
        WHERE pm.project_id = ?
    """, (project_id,))
    members = c.fetchall()

    if request.method == 'POST':
        new_title = request.form['title']
        new_description = request.form['description']
        new_assignee = request.form['assigned_to']

        c.execute("""
            UPDATE tasks
            SET title = ?, description = ?, assigned_to = ?
            WHERE id = ?
        """, (new_title, new_description, new_assignee, task_id))

        conn.commit()
        conn.close()
        return redirect(f'/project/{project_id}')

    conn.close()
    return render_template('edit_task.html', task=task, members=members, project_id=project_id)



@app.route('/')
def intro():
    return render_template('intro.html')



@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    conn = get_db_connection()
    c = conn.cursor()

    if request.method == 'POST':
        new_name = request.form['name']
        new_email = request.form['email']
        new_password = request.form['password']

        if new_password:
            hashed_password = generate_password_hash(new_password)
            c.execute("""
                UPDATE users
                SET name = ?, email = ?, password = ?
                WHERE id = ?
            """, (new_name, new_email, hashed_password, user_id))
        else:
            c.execute("""
                UPDATE users
                SET name = ?, email = ?
                WHERE id = ?
            """, (new_name, new_email, user_id))

        conn.commit()
        flash('Profile updated successfully!')
        return redirect('/profile')

    # GET request
    c.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()

    return render_template('profile.html', user=user)


@app.route('/join')
def join_project_page():
   
    return render_template("join.html")


if __name__ == '__main__':
    app.run(debug=True)
