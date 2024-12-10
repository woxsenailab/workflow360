from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, session
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Add these session configurations
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=13)  # Session lasts for 7 days
app.config['SESSION_PERMANENT'] = True

# SQL Database setup
def sql_connector():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Create tables if they don't exist
    c.execute("""
        CREATE TABLE IF NOT EXISTS signup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            password TEXT,
            team_name TEXT,
            role TEXT
        );
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mentor_email TEXT,
    team_member_email TEXT,
    project_info TEXT,
    description TEXT,
    start_date TEXT,
    end_date TEXT,
    status TEXT DEFAULT 'active',
    team_name TEXT,
    FOREIGN KEY (mentor_email) REFERENCES signup(email),
    FOREIGN KEY (team_member_email) REFERENCES signup(email)
    );
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        login_times TEXT,
        logout_times TEXT,
        date DATE,
        duration TEXT,  -- Store total duration as HH:MM:SS
        FOREIGN KEY (email) REFERENCES signup(email)
    );
    """)

    conn.commit()
    conn.close()

# Route for signing up a user
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        team_name = request.form['team_name']
        role = request.form['role']  # Get role from the form

        conn = sqlite3.connect('database.db')
        c = conn.cursor()

        # Check if the combination of email, password, team_name, and role already exists
        c.execute("SELECT * FROM signup WHERE email = ? AND password = ? AND team_name = ? AND role = ?", (email, password, team_name, role))
        existing_user = c.fetchone()

        if existing_user:
            flash("This email, password, team_name, and role combination is already used. Please try again.", "error")
            return redirect(url_for('signup'))

        # Insert user into signup table
        c.execute("INSERT INTO signup (name, email, password, team_name, role) VALUES (?, ?, ?, ?, ?)", (name, email, password, team_name, role))

        # Create user-specific tables for tickets and daily updates
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS tickets_{email.replace('@', '_').replace('.', '_')} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_info TEXT,
                module_info TEXT,
                description TEXT,
                start_date TIMESTAMP,
                expected_date TIMESTAMP,
                ticket_creation_time TIMESTAMP,
                closed_date TIMESTAMP,
                duration_days INTEGER,
                member TEXT,
                team_member_email TEXT,
                status TEXT DEFAULT 'active'
            );
        """)

        c.execute(f"""
            CREATE TABLE IF NOT EXISTS daily_updates_{email.replace('@', '_').replace('.', '_')} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER,
                update_date DATE,
                daily_description TEXT,
                stage TEXT,
                state TEXT,
                FOREIGN KEY (ticket_id) REFERENCES tickets_{email.replace('@', '_').replace('.', '_')} (id),
                UNIQUE(ticket_id, update_date)
            );
        """)

        conn.commit()
        conn.close()

        flash("Signup successful! Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('signup.html')

# Route for logging in a user
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT * FROM signup WHERE email = ? AND password = ?", (email, password))
        user = c.fetchone()
        conn.close()
    
        if user:
            print(close_project)
            # Make session permanent
            session.permanent = True
            session['email'] = email
            session['name'] = user[1]
            session['role'] = user[5]

            # Mark attendance
            conn = sqlite3.connect('database.db')
            c = conn.cursor()
            login_time = datetime.now()  # Get current time as a datetime object
            date_today = login_time.date()  # Get today's date

            # Format login time as HH:MM:SS
            login_time_str = login_time.strftime('%H:%M:%S')

            # Check if attendance record for today exists
            c.execute("SELECT * FROM attendance WHERE email = ? AND date = ?", (email, date_today))
            attendance_record = c.fetchone()

            if attendance_record:
                # Append new login time
                existing_login_times = attendance_record[2]  # Assuming login_times is the third column
                if existing_login_times:
                    updated_login_times = f"{existing_login_times},{login_time_str}"
                else:
                    updated_login_times = login_time_str
                c.execute("UPDATE attendance SET login_times = ? WHERE id = ?", (updated_login_times, attendance_record[0]))
            else:
                # Create new attendance record
                c.execute("INSERT INTO attendance (email, login_times, date) VALUES (?, ?, ?)", (email, login_time_str, date_today))

            conn.commit()
            conn.close()

            if user[5] == 'team_member':
                return redirect(url_for('home'))
            elif user[5] == 'mentor':
                return redirect(url_for('mentor'))  
            elif user[5] == 'researchers':
                return redirect(url_for('researchers'))

        else:
            flash("Invalid credentials. Please try again.", "error")
            return redirect(url_for('login'))
    
    return render_template('login.html')  # Ensure you have a login.html template

@app.route('/logout')
def logout():
    email = session.get('email')
    if email:
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        logout_time = datetime.now()  # Get current time as a datetime object
        date_today = logout_time.date()

        # Format logout time as HH:MM:SS
        logout_time_str = logout_time.strftime('%H:%M:%S')

        # Update logout time
        c.execute("SELECT id, login_times, logout_times FROM attendance WHERE email = ? AND date = ?", (email, date_today))
        attendance_record = c.fetchone()
        
        if attendance_record:
            existing_logout_times = attendance_record[2]  # Assuming logout_times is the third column
            if existing_logout_times:
                updated_logout_times = f"{existing_logout_times},{logout_time_str}"
            else:
                updated_logout_times = logout_time_str
            
            # Update the logout times
            c.execute("UPDATE attendance SET logout_times = ? WHERE id = ?", (updated_logout_times, attendance_record[0]))

            # Calculate total duration
            login_times = attendance_record[1].split(',')  # Get all login times
            logout_times = updated_logout_times.split(',')  # Get all logout times
            
            total_duration_seconds = 0
            
            # Ensure we only calculate for pairs of login and logout times
            for login_time_str, logout_time_str in zip(login_times, logout_times):
                login_time_dt = datetime.strptime(login_time_str, '%H:%M:%S')
                logout_time_dt = datetime.strptime(logout_time_str, '%H:%M:%S')
                
                # Calculate duration for this login/logout pair
                duration_seconds = (logout_time_dt - login_time_dt).total_seconds()
                total_duration_seconds += duration_seconds

            # Convert total duration to HH:MM:SS
            hours, remainder = divmod(total_duration_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            duration_formatted = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

            # Update the attendance record with the formatted logout time and duration
            c.execute("UPDATE attendance SET duration = ? WHERE id = ?", (duration_formatted, attendance_record[0]))

        else:
            # If no attendance record exists for today, handle this case
            flash("No login record found for today. Please log in first.", "error")
            return redirect(url_for('login'))

        conn.commit()
        conn.close()

    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

@app.route('/mentor', methods=['GET', 'POST'])
def mentor():
    if 'email' not in session:
        flash("You must be logged in to view the mentor page.", "error")
        return redirect(url_for('login'))

    close_expired_tickets()
    mentor_email = session['email']
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Get selected team from form or session
    c.execute("SELECT DISTINCT team_name FROM signup WHERE email = ?", (mentor_email,))
    mentor_teams = [row[0] for row in c.fetchall()]
    
    selected_team = request.form.get('selected_team', session.get('selected_team', mentor_teams[0] if mentor_teams else None))
    
    if selected_team:
        session['selected_team'] = selected_team

    # Fetch active and closed projects
    def fetch_projects(status):
        c.execute("""
            SELECT DISTINCT p.id, p.mentor_email, p.team_member_email, p.project_info, p.description, p.status, p.team_name
            FROM projects p
            LEFT JOIN signup s ON s.email = p.team_member_email
            WHERE p.mentor_email = ? 
            AND p.team_name = ? 
            AND p.status = ?
            GROUP BY p.project_info
            ORDER BY p.id DESC
        """, (mentor_email, selected_team, status))
        return c.fetchall()

    active_projects = fetch_projects('active')
    closed_projects = fetch_projects('closed')

    # Fetch all projects (active and closed) for the selected team
    c.execute("""
        SELECT DISTINCT p.id, p.mentor_email, p.team_member_email, p.project_info, p.description, p.status, p.team_name
        FROM projects p
        WHERE p.mentor_email = ? 
        AND p.team_name = ?
        GROUP BY p.project_info
        ORDER BY p.id DESC
    """, (mentor_email, selected_team))
    projects_all = c.fetchall()

    # Initialize team members, projects, tickets, etc.
    team_members = []
    projects = {}
    tickets = {}
    projects_dict = {}
    current_admin_tickets = []
    closed_admin_tickets = {}

    if selected_team:
        c.execute("SELECT * FROM signup WHERE team_name = ? AND email != ? AND role = 'team_member'", 
                 (selected_team, mentor_email))
        team_members = c.fetchall()

        # Fetch active projects for team members
        for member in team_members:
            member_email = member[2]  # Assuming email is the third column
            c.execute("""
                SELECT * FROM projects 
                WHERE team_member_email = ? 
                AND status = 'active'
            """, (member_email,))
            member_projects = c.fetchall()
            projects[member_email] = member_projects

            # Fetch all projects for the team member (active and closed)
            c.execute("""
                SELECT * FROM projects 
                WHERE team_member_email = ?
            """, (member_email,))
            member_projects = c.fetchall()
            projects_dict[member_email] = member_projects

            # Fetch tickets for this member
            user_email_table = f'tickets_{member_email.replace("@", "_").replace(".", "_")}'  # Correctly construct the table name
            try:
                c.execute(f"SELECT * FROM {user_email_table} WHERE closed_date IS NULL")  # Fetch only active tickets
                member_tickets = c.fetchall()
                tickets[member_email] = member_tickets  # Store tickets for this member
            except sqlite3.OperationalError:
                # Handle the case where the table does not exist
                tickets[member_email] = []

            # Fetch current and closed admin tickets
            admin_email_table = f'admin_tickets_{member_email.replace("@", "_").replace(".", "_")}'
            try:
                c.execute(f"SELECT * FROM {admin_email_table}")
                admin_tickets = c.fetchall()

                # Process the admin tickets
                for ticket in admin_tickets:
                    closed_date = ticket[7]  # Assuming closed_date is the 8th column
                    if closed_date is None:
                        current_admin_tickets.append(ticket)
                    else:
                        project_info = ticket[1]
                        if project_info not in closed_admin_tickets:
                            closed_admin_tickets[project_info] = []
                        closed_admin_tickets[project_info].append(ticket)
            except sqlite3.OperationalError:
                # Handle the case where the table doesn't exist
                print(f"Table {admin_email_table} does not exist. Skipping admin tickets.")

    conn.close()

    return render_template('mentor.html', 
                           team_members=team_members, 
                           projects=projects, 
                           mentor_teams=mentor_teams,
                           selected_team=selected_team,
                           active_projects=active_projects,
                           closed_projects=closed_projects,
                           tickets=tickets,
                           projects_all=projects_dict,
                           current_admin_tickets=current_admin_tickets,
                           closed_admin_tickets=closed_admin_tickets)

@app.route('/create_project', methods=['POST'])
def create_project():
    if 'email' not in session:
        flash("You must be logged in to create a project.", "error")
        return redirect(url_for('login'))

    mentor_email = session['email']
    project_name = request.form['project_name']  # No longer accessing project_description

    selected_team = session.get('selected_team')

    if not selected_team:
        flash("Please select a team first.", "error")
        return redirect(url_for('mentor'))

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    start_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    c.execute("""
        INSERT INTO projects (mentor_email, project_info, status, team_name, start_date)
        VALUES (?, ?, 'active', ?, ?)
    """, (mentor_email, project_name, selected_team, start_date))

    conn.commit()
    conn.close()

    flash("Project created successfully!", "success")
    return redirect(url_for('mentor'))

@app.route('/project_details/<int:project_id>')
def project_details(project_id):
    if 'email' not in session:
        flash("You must be logged in to view project details.", "error")
        return redirect(url_for('login'))

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Modified query to get project details including closed projects
    c.execute("""
        SELECT 
            p.id,
            p.mentor_email,
            p.project_info,
            p.description,
            p.status,
            p.team_name,
            GROUP_CONCAT(DISTINCT s.name) as member_names,
            GROUP_CONCAT(DISTINCT s.email) as member_emails,
            p.start_date,
            p.end_date
        FROM projects p
        LEFT JOIN signup s ON s.email = p.team_member_email
        WHERE p.project_info = (
            SELECT project_info FROM projects WHERE id = ?
        )
        AND p.mentor_email = ?
        GROUP BY p.project_info
    """, (project_id, session['email']))
    
    project = c.fetchone()

    if not project:
        flash("Project not found.", "error")
        return redirect(url_for('mentor'))

    # Get all tickets and their daily updates for this project from all assigned members
    tickets = []
    daily_updates = {}
    
    # Get all team members who were ever assigned to this project
    c.execute("""
        SELECT DISTINCT team_member_email 
        FROM projects 
        WHERE project_info = ? 
        AND team_member_email IS NOT NULL
    """, (project[2],))  # project[2] contains project_info
    
    member_emails = [member[0] for member in c.fetchall()]
    
    for email in member_emails:
        user_email_table = f'tickets_{email.replace("@", "_").replace(".", "_")}'
        user_updates_table = f'daily_updates_{email.replace("@", "_").replace(".", "_")}'
        
        try:
            # Get all tickets including closed ones
            c.execute(f"""
                SELECT *, ? as member_email 
                FROM {user_email_table}
                WHERE project_info = ?
                ORDER BY ticket_creation_time DESC
            """, (email, project[2]))
            user_tickets = c.fetchall()
            tickets.extend(user_tickets)
            
            # Get daily updates for each ticket
            for ticket in user_tickets:
                c.execute(f"""
                    SELECT * FROM {user_updates_table}
                    WHERE ticket_id = ?
                    ORDER BY update_date DESC
                """, (ticket[0],))
                daily_updates[ticket[0]] = c.fetchall()
                
        except sqlite3.OperationalError:
            continue

    # Get team member names
    c.execute("""
        SELECT DISTINCT s.name 
        FROM projects p
        JOIN signup s ON s.email = p.team_member_email
        WHERE p.project_info = ?
    """, (project[2],))
    member_names = [row[0] for row in c.fetchall()]

    conn.close()

    return render_template('project_details.html',
                         project=project,
                         tickets=tickets,
                         daily_updates=daily_updates,
                         team_member_names=member_names,
                         team_member_emails=member_emails,
                         zip=zip)

@app.route('/close_project/<int:project_id>', methods=['POST'])
def close_project(project_id):
    if 'email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    try:
        # Get project info and team name for closing all related instances
        c.execute("""
            SELECT project_info, team_name 
            FROM projects 
            WHERE id = ? AND mentor_email = ?
        """, (project_id, session['email']))
        project_data = c.fetchone()
        
        if not project_data:
            return jsonify({'success': False, 'message': 'Project not found'})
            
        project_info, team_name = project_data
        end_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Update all related project assignments to closed status
        c.execute("""
            UPDATE projects 
            SET status = 'closed', 
                end_date = ? 
            WHERE project_info = ? 
            AND team_name = ?
        """, (end_date, project_info, team_name))

        # Get all team members who were assigned this project
        c.execute("""
            SELECT DISTINCT team_member_email 
            FROM projects 
            WHERE project_info = ? 
            AND team_name = ? 
            AND team_member_email IS NOT NULL
        """, (project_info, team_name))
        team_members = c.fetchall()

        # Close tickets and updates for each team member
        for member in team_members:
            member_email = member[0]
            if member_email:
                tickets_table = f'tickets_{member_email.replace("@", "_").replace(".", "_")}'
                updates_table = f'daily_updates_{member_email.replace("@", "_").replace(".", "_")}'
                
                try:
                    # Close all open tickets for this project
                    c.execute(f"""
                        UPDATE {tickets_table}
                        SET closed_date = datetime('now'),
                            duration_days = CAST((julianday(datetime('now')) - julianday(start_date)) AS INTEGER)
                        WHERE project_info = ?
                        AND closed_date IS NULL
                    """, (project_info,))

                    # Get all tickets for this project
                    c.execute(f"""
                        SELECT id 
                        FROM {tickets_table} 
                        WHERE project_info = ?
                    """, (project_info,))
                    tickets = c.fetchall()

                    # Close all updates for these tickets
                    for ticket in tickets:
                        c.execute(f"""
                            UPDATE {updates_table}
                            SET state = 'closed'
                            WHERE ticket_id = ?
                        """, (ticket[0],))

                except sqlite3.OperationalError:
                    continue

        conn.commit()
        return jsonify({'success': True})

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()

@app.route('/assign_project', methods=['POST'])
def assign_project():
    if 'email' not in session:
        flash("You must be logged in to assign a project.", "error")
        return redirect(url_for('login'))

    mentor_email = session['email']
    project_id = request.form['project_id']
    team_member_email = request.form['team_member_email']
    description = request.form['description']

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Get project info and team name
    c.execute("""
        SELECT project_info, team_name 
        FROM projects 
        WHERE id = ?
    """, (project_id,))
    project_data = c.fetchone()
    project_info, team_name = project_data

    # Check if member is already assigned
    c.execute("""
        SELECT id FROM projects 
        WHERE project_info = ? 
        AND team_member_email = ? 
        AND team_name = ?
    """, (project_info, team_member_email, team_name))
    
    existing_assignment = c.fetchone()

    if existing_assignment:
        flash("This team member is already assigned to this project.", "error")
    else:
        # Count current assignments for this project
        c.execute("""
            SELECT COUNT(DISTINCT team_member_email) 
            FROM projects 
            WHERE project_info = ? 
            AND team_name = ? 
            AND team_member_email IS NOT NULL
        """, (project_info, team_name))
        
        current_assignments = c.fetchone()[0]

        if current_assignments >= 4:
            flash("This project already has the maximum number of team members (4) assigned.", "error")
        else:
            # Create new assignment
            c.execute("""
                INSERT INTO projects (
                    mentor_email, team_member_email, project_info,
                    description, status, team_name
                ) VALUES (?, ?, ?, ?, 'active', ?)
            """, (mentor_email, team_member_email, project_info, description, team_name))
            
            flash("Project successfully assigned to team member!", "success")

    conn.commit()
    conn.close()

    return redirect(url_for('mentor'))

@app.route('/close_ticket/<int:ticket_id>', methods=['POST'])
def close_ticket(ticket_id):
    if 'email' not in session:
        flash("You must be logged in to close a ticket.", "error")
        return redirect(url_for('login'))

    user_email_table = f'tickets_{session["email"].replace("@", "_").replace(".", "_")}'
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    ticket_closed_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        # Update the ticket with closed date and duration
        c.execute(f"""
            UPDATE {user_email_table}
            SET closed_date = ?, status = 'closed',
                duration_days = CAST((julianday(?) - julianday(start_date)) AS INTEGER)
            WHERE id = ?
        """, (ticket_closed_time, ticket_closed_time, ticket_id))

        conn.commit()
        flash("Ticket closed successfully!", "success")
    except sqlite3.Error as e:
        flash(f"Error closing ticket: {str(e)}", "error")
    finally:
        conn.close()

    return redirect(url_for('home'))

@app.route('/admin_close_ticket/<int:ticket_id>', methods=['POST'])
def admin_close_ticket(ticket_id):
    if 'email' not in session:
        flash("You must be logged in to close a ticket.", "error")
        return redirect(url_for('login'))

    user_email_table = f'admin_tickets_{session["email"].replace("@", "_").replace(".", "_")}'
    ticket_closed_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    try:
        # Update the ticket with closed date and duration
        c.execute(f"""
            UPDATE {user_email_table}
            SET closed_date = ?, status = 'closed',
                duration_days = CAST((julianday(?) - julianday(start_date)) AS INTEGER)
            WHERE id = ?
        """, (ticket_closed_time, ticket_closed_time, ticket_id,))

        conn.commit()
        flash("Ticket closed successfully!", "success")
    except sqlite3.Error as e:
        flash(f"Error closing ticket: {str(e)}", "error")
    finally:
        conn.close()
    
    source = request.args.get('source', 'home')  # Default to 'home' if not provided

    # Redirect based on the source
    if source == 'home':
        return redirect(url_for('home'))
    elif source == 'mentor':
        return redirect(url_for('mentor'))
    elif source == 'researchers':
        return redirect(url_for('researchers'))
    else:
        return redirect(url_for('home'))  # Fallback to home if source is not recognized

ADMIN_EMAIL = 'hemachandran.k@woxsen.edu.in'
ADMIN_PASSWORD = 'Drhema@1234'

# Admin login route
@app.route('/adminlogin', methods=['GET'])
def admin_login_page():
    close_expired_tickets()
    return render_template('adminLogin.html')

# Admin login route
@app.route('/adminlogin', methods=['POST'])
def adminlogin():
    email = request.form['email']
    password = request.form['password']

    if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
        session['admin'] = True  
        flash("Admin login successful!", "success")
        return redirect(url_for('admin'))  # Redirect to the admin page
    else:
        flash("Invalid email or password. Please try again.", "error")
        return redirect(url_for('admin_login_page')) 

# Admin page
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'admin' not in session:
        flash("You must be logged in as an admin to view this page.", "error")
        return redirect(url_for('admin_login_page'))
    close_expired_tickets()
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Fetch all users from the signup table
    c.execute("SELECT * FROM signup")
    users = c.fetchall()

    # Get current month and year
    current_month = datetime.now().month
    current_year = datetime.now().year

    # Get month and year from request args, default to current month/year
    selected_month = request.args.get('month', current_month, type=int)
    selected_year = request.args.get('year', current_year, type=int)

    # Fetch attendance records for the selected month and year
    c.execute("""
        SELECT * FROM attendance 
        WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ?
    """, (str(selected_year), f'{selected_month:02}'))
    attendance_records = c.fetchall()

    # Prepare a dictionary to hold user ticket information grouped by project_info
    user_tickets = {}
    user_updates = {}
    admin_user_tickets = {}
    admin_user_updates = {}

    # Prepare a dictionary to hold team members by team name
    teams = {}

    for user in users:
        user_email = user[2]  # Assuming email is the third column
        user_email_table = f'tickets_{user_email.replace("@", "_").replace(".", "_")}'
        
        # Fetch tickets for each user
        c.execute(f"SELECT * FROM {user_email_table}")
        tickets = c.fetchall()
        
        # Group tickets by project_info
        project_tickets = {}
        for ticket in tickets:
            project_info = ticket[1]  # Assuming project_info is the second column
            if project_info not in project_tickets:
                project_tickets[project_info] = []
            project_tickets[project_info].append(ticket)
        
        # Store the grouped tickets by project under each user
        user_tickets[user_email] = project_tickets

        # Fetch daily updates for each ticket
        user_updates_table = f'daily_updates_{user_email.replace("@", "_").replace(".", "_")}'
        updates = {}
        for ticket in tickets:
            ticket_id = ticket[0]
            c.execute(f"SELECT * FROM {user_updates_table} WHERE ticket_id = ?", (ticket_id,))
            updates[ticket_id] = c.fetchall()
        
        user_updates[user_email] = updates

        # Fetch admin tickets
        admin_email_table = f'admin_tickets_{user_email.replace("@", "_").replace(".", "_")}'
        try:
            c.execute(f"SELECT * FROM {admin_email_table}")
            admin_tickets = c.fetchall()
            admin_project_tickets = {}
            for ticket in admin_tickets:
                project_info = ticket[1]  # Assuming project_info is the second column
                if project_info not in admin_project_tickets:
                    admin_project_tickets[project_info] = []
                admin_project_tickets[project_info].append(ticket)
            
            # Store the grouped tickets by project under each user
            admin_user_tickets[user_email] = admin_project_tickets
            
            # Fetch daily updates for admin tickets
            user_admin_updates_table = f'admin_daily_updates_{user_email.replace("@", "_").replace(".", "_")}'
            admin_updates = {}
            for ticket in admin_tickets:
                ticket_id = ticket[0]
                c.execute(f"SELECT * FROM {user_admin_updates_table} WHERE ticket_id = ?", (ticket_id,))
                admin_updates[ticket_id] = c.fetchall()
            
            admin_user_updates[user_email] = admin_updates
        
        except sqlite3.OperationalError:
            print(f"Table {admin_email_table} does not exist. Skipping admin tickets.")

        team_name = user[4]
        # Group users by team for attendance
        team_name = user[4]  # Assuming team_name is the fifth column
        if team_name not in teams:
            teams[team_name] = {'mentor': [], 'members': []}
        
        if user[5] == 'mentor':
            teams[team_name]['mentor'].append(user)
        else:
            teams[team_name]['members'].append(user)

    # Fetch admin-created tickets for both mentors and team members
    admin_tickets = {}
    c.execute("SELECT email, role FROM signup WHERE role IN ('mentor', 'team_member', 'researchers')")
    users = c.fetchall()

    for user in users:
        user_email, role = user
        admin_email_table = f'admin_tickets_{user_email.replace("@", "_").replace(".", "_")}'
        try:
            c.execute(f"SELECT * FROM {admin_email_table}")
            tickets = c.fetchall()
            admin_tickets[user_email] = {'role': role, 'tickets': tickets}
        except sqlite3.OperationalError:
            print(f"Table {admin_email_table} does not exist. Skipping admin tickets for {user_email}.")

    conn.close()

    return render_template('admin.html', 
                           users=users, 
                           user_tickets=user_tickets, 
                           user_updates=user_updates, 
                           admin_user_tickets=admin_user_tickets, 
                           admin_user_updates=admin_user_updates, 
                           attendance_records=attendance_records, 
                           teams=teams, 
                           selected_month=selected_month, 
                           selected_year=selected_year,
                           admin_tickets=admin_tickets)

@app.route('/admin_ticket_updates_display_new/<int:ticket_id>/<string:user_email>')
def admin_ticket_updates_display_new(ticket_id, user_email):
    if 'admin' not in session:
        return jsonify({'error': 'Unauthorized'}), 403

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Find the correct table for this ticket
    c.execute("SELECT email FROM signup WHERE role IN ('mentor', 'team_member')")
    users = c.fetchall()

    ticket = None
    daily_updates = []

    for user in users:
        admin_email_table = f'admin_tickets_{user_email.replace("@", "_").replace(".", "_")}'
        admin_updates_table = f'admin_daily_updates_{user_email.replace("@", "_").replace(".", "_")}'

        try:
            c.execute(f"SELECT * FROM {admin_email_table} WHERE id = ?", (ticket_id,))
            ticket = c.fetchone()

            if ticket:
                c.execute(f"SELECT * FROM {admin_updates_table} WHERE ticket_id = ? ORDER BY update_date ASC", (ticket_id,))
                daily_updates = c.fetchall()
                break
        except sqlite3.OperationalError:
            continue

    conn.close()

    if not ticket:
        return jsonify({'error': 'Ticket not found'}), 404

    return jsonify({
        'ticket': ticket,
        'daily_updates': daily_updates
    })

@app.route('/get_updates/<int:ticket_id>/<string:user_email>')
def get_updates(ticket_id, user_email):
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        user_updates_table = f'admin_daily_updates_{user_email.replace("@", "_").replace(".", "_")}'
        c.execute(f"""
            SELECT * FROM {user_updates_table}
            WHERE ticket_id = ?
            ORDER BY update_date ASC
        """, (ticket_id,))
        updates = c.fetchall()
        conn.close()
        return jsonify([dict(update) for update in updates])

@app.route('/admin_ticket_updates_display/<int:ticket_id>')
def admin_ticket_updates_display(ticket_id):
    if 'admin' not in session:
        flash("You must be logged in to view ticket updates.", "error")
        return redirect(url_for('admin_login_page'))

    user_updates_table = f'admin_daily_updates_{session["email"].replace("@", "_").replace(".", "_")}'
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Get all updates for this ticket, ordered by date
    c.execute(f"""
        SELECT * FROM {user_updates_table} WHERE ticket_id = ? ORDER BY update_date ASC
    """, (ticket_id,))
    daily_updates = c.fetchall()

    # Get ticket details for display
    user_email_table = f'admin_tickets_{session["email"].replace("@", "_").replace(".", "_")}'
    c.execute(f"SELECT * FROM {user_email_table} WHERE id = ?", (ticket_id,))
    ticket = c.fetchone()

    conn.close()

    if not ticket:
        flash("Ticket not found.", "error")
        return redirect(url_for('admin'))

    return jsonify({
        'ticket': ticket,
        'daily_updates': daily_updates
    })

@app.route('/admin/project_details/<project_info>/<team_name>/<member_email>')
def admin_project_details(project_info, team_name, member_email):
    if 'admin' not in session:
        return "Unauthorized", 403
        
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Fetch the project details
    c.execute("""
        SELECT * FROM projects 
        WHERE project_info = ? 
        AND team_name = ?
    """, (project_info, team_name))
    project = c.fetchone()
    
    # Get the user-specific tables for tickets and daily updates
    user_email_table = f'tickets_{member_email.replace("@", "_").replace(".", "_")}'
    user_updates_table = f'daily_updates_{member_email.replace("@", "_").replace(".", "_")}'
    
    # Fetch all tickets related to the project for all members
    c.execute(f"""
        SELECT * FROM {user_email_table}
        WHERE project_info = ?
        ORDER BY ticket_creation_time DESC
    """, (project_info,))
    tickets = c.fetchall()
    
    # Fetch updates for each ticket
    ticket_updates = {}
    for ticket in tickets:
        c.execute(f"""
            SELECT * FROM {user_updates_table}
            WHERE ticket_id = ?
            ORDER BY update_date DESC
        """, (ticket[0],))
        ticket_updates[ticket[0]] = c.fetchall()
    
    # Fetch assigned members for the project
    c.execute("""
        SELECT DISTINCT s.name, s.email 
        FROM projects p 
        JOIN signup s ON p.team_member_email = s.email 
        WHERE p.project_info = ? AND p.team_name = ?
    """, (project_info, team_name))
    assigned_members = c.fetchall()
    
    conn.close()
    
    # Prepare lists for member names and emails
    member_names = [member[0] for member in assigned_members]
    member_emails = [member[1] for member in assigned_members]

    # Prepare project creation date
    project_creation_date = project[5]  # Assuming start_date is the 6th column

    return render_template('project_details_modal.html',
                         project=project,
                         tickets=tickets,
                         ticket_updates=ticket_updates,
                         member_email=member_email,
                         team_member_names=member_names,
                         team_member_emails=member_emails,
                         project_creation_date=project_creation_date)

@app.route('/admin/attendance', methods=['GET'])
def fetch_attendance():
    # Get month and year from request args
    selected_month = request.args.get('month', type=int)
    selected_year = request.args.get('year', type=int)

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Fetch attendance records for the selected month and year
    c.execute("""
        SELECT * FROM attendance 
        WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ?
    """, (str(selected_year), f'{selected_month:02}'))
    attendance_records = c.fetchall()

    # Convert the records into a list of dictionaries for JSON response
    attendance_list = []
    for record in attendance_records:
        attendance_list.append({
            'email': record[1],
            'date': record[4],
            'login_time': record[2],
            'logout_time': record[3],
            'duration_worked': record[5]
        })

    conn.close()
    return jsonify(attendance_list)

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row  # Optional: allows accessing columns by name
    return conn

# Home page with ticket creation and viewing
@app.route('/home')
def home():
    if 'email' not in session:
        flash("You must be logged in to view the home page.", "error")
        return redirect(url_for('login'))
    # close_expired_tickets()
    user_email = session['email']
    user_email_table = f'tickets_{user_email.replace("@", "_").replace(".", "_")}'
    user_updates_table = f'daily_updates_{user_email.replace("@", "_").replace(".", "_")}'
    admin_email_table = f'admin_tickets_{user_email.replace("@", "_").replace(".", "_")}'

    close_expired_tickets()

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Fetch only active assigned projects for the logged-in user
    c.execute("""
        SELECT * FROM projects 
        WHERE team_member_email = ? 
        AND status = 'active'  
        ORDER BY start_date DESC
    """, (user_email,))
    assigned_projects = c.fetchall()

    # Fetch tickets for the logged-in user from their specific table
    c.execute(f"SELECT * FROM {user_email_table}")
    tickets = c.fetchall()

    # Separate current and closed tickets
    current_tickets = []
    closed_tickets = {}
    today_date = datetime.now()

    for ticket in tickets:
        # ticket_valid_until = datetime.strptime(ticket[7], '%Y-%m-%d %H:%M')
        closed_date = ticket[8]
        if closed_date is None:
            current_tickets.append(ticket)
        elif closed_date is not None:
            project_info = ticket[1]
            if project_info not in closed_tickets:
                closed_tickets[project_info] = []
            closed_tickets[project_info].append(ticket)
        # elif ticket_valid_until is not None:
        #     project_info = ticket[1]
        #     if project_info not in closed_tickets:
        #         closed_tickets[project_info] = []
        #     closed_tickets[project_info].append(ticket)

    # Fetch stages for closed tickets
    stages_for_closed_tickets = {}
    for project, tickets in closed_tickets.items():
        for ticket in tickets:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute(f"SELECT DISTINCT stage FROM {user_updates_table} WHERE ticket_id = ?", (ticket[0],))
                stages = c.fetchall()
                stages_for_closed_tickets[ticket[0]] = [stage[0] for stage in stages]

    # Fetch current and closed admin tickets
    current_admin_tickets = []
    closed_admin_tickets = {}
    
    try:
        c.execute(f"SELECT * FROM {admin_email_table}")
        admin_tickets = c.fetchall()

        for ticket in admin_tickets:
            closed_date = ticket[7]  # Assuming closed_date is the 8th column
            if closed_date is None:
                current_admin_tickets.append(ticket)
            else:
                project_info = ticket[1]
                if project_info not in closed_admin_tickets:
                    closed_admin_tickets[project_info] = []
                closed_admin_tickets[project_info].append(ticket)
    except sqlite3.OperationalError:
        print(f"Table {admin_email_table} does not exist. Skipping admin tickets.")
 
    conn.close()

    return render_template('home.html', 
                         current_tickets=current_tickets, 
                         closed_tickets=closed_tickets, 
                         stages_for_closed_tickets=stages_for_closed_tickets,
                         current_admin_tickets=current_admin_tickets,
                         closed_admin_tickets=closed_admin_tickets,
                         assigned_projects=assigned_projects)

@app.route('/researchers')
def researchers():
    if 'email' not in session:
        flash("You must be logged in to view the home page.", "error")
        return redirect(url_for('login'))
    
    close_expired_tickets()

    user_email = session['email']
    user_email_table = f'tickets_{user_email.replace("@", "_").replace(".", "_")}'
    user_updates_table = f'daily_updates_{user_email.replace("@", "_").replace(".", "_")}'
    admin_email_table = f'admin_tickets_{user_email.replace("@", "_").replace(".", "_")}'

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Fetch only active assigned projects for the logged-in user
    # c.execute("""
    #     SELECT * FROM projects 
    #     WHERE team_member_email = ? 
    #     AND status = 'active'  
    #     ORDER BY start_date DESC
    # """, (user_email,))
    # assigned_projects = c.fetchall()

    # Fetch tickets for the logged-in user from their specific table
    c.execute(f"SELECT * FROM {user_email_table}")
    tickets = c.fetchall()

    # Separate current and closed tickets
    # current_tickets = []
    # closed_tickets = {}
    # today_date = datetime.now()

    # for ticket in tickets:
    #     closed_date = ticket[8]
    #     if closed_date is None:
    #         current_tickets.append(ticket)
    #     elif closed_date is not None:
    #         project_info = ticket[1]
    #         if project_info not in closed_tickets:
    #             closed_tickets[project_info] = []
    #         closed_tickets[project_info].append(ticket)

    # Fetch stages for closed tickets
    # stages_for_closed_tickets = {}
    # for project, tickets in closed_tickets.items():
    #     for ticket in tickets:
    #         with get_db_connection() as conn:
    #             c = conn.cursor()
    #             c.execute(f"SELECT DISTINCT stage FROM {user_updates_table} WHERE ticket_id = ?", (ticket[0],))
    #             stages = c.fetchall()
    #             stages_for_closed_tickets[ticket[0]] = [stage[0] for stage in stages]

    # Fetch current and closed admin tickets
    current_admin_tickets = []
    closed_admin_tickets = {}
    
    try:
        c.execute(f"SELECT * FROM {admin_email_table}")
        admin_tickets = c.fetchall()

        for ticket in admin_tickets:
            closed_date = ticket[7]  # Assuming closed_date is the 8th column
            if closed_date is None:
                current_admin_tickets.append(ticket)
            else:
                project_info = ticket[1]
                if project_info not in closed_admin_tickets:
                    closed_admin_tickets[project_info] = []
                closed_admin_tickets[project_info].append(ticket)
    except sqlite3.OperationalError:
        print(f"Table {admin_email_table} does not exist. Skipping admin tickets.")
 
    conn.close()

    return render_template('researchers.html', 
                         current_admin_tickets=current_admin_tickets,
                         closed_admin_tickets=closed_admin_tickets)

# Create a new ticket
@app.route('/create_ticket', methods=['GET', 'POST'])
def create_ticket():
    if 'email' not in session:
        flash("You must be logged in to create a ticket.", "error")
        return redirect(url_for('login'))

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Fetch assigned projects for dropdown
    c.execute("""
        SELECT DISTINCT project_info 
        FROM projects 
        WHERE team_member_email = ? 
        AND status = 'active'
    """, (session['email'],))
    assigned_projects = [project[0] for project in c.fetchall()]

    # Fetch team members for the dropdown
    c.execute("SELECT name, email FROM signup WHERE team_name = (SELECT team_name FROM signup WHERE email = ?) AND role = 'team_member'", (session['email'],))
    team_members = c.fetchall()

    project_name = request.args.get('project_name')
    member = request.args.get('member')
    member_email = request.args.get('member_email')
    if request.method == 'POST':
        project_info = request.form['project_info']
        module_info = request.form['module_info']
        description = request.form['description']
        start_date = request.form['start_date']
        expected_date = request.form['expected_date']
        assigned_to = request.form['assigned_to']  # Get assigned team member
        memEmail = request.form['memEmail']

        start_time = "09:00:00"  # Fixed start time
        end_time = "23:59:00"     # Fixed end time

        # Combine date and time
        start_datetime = f"{start_date} {start_time}"
        end_datetime = f"{expected_date} {end_time}"

        ticket_creation_time = datetime.now()
        ticket_creation_time_str = ticket_creation_time.strftime('%Y-%m-%d %H:%M')
        ticket_valid_until = ticket_creation_time + timedelta(days=15)
        ticket_valid_until_str = ticket_valid_until.strftime('%Y-%m-%d %H:%M')

        user_email_table = f'tickets_{session["email"].replace("@", "_").replace(".", "_")}'
        member_email_table = f'tickets_{memEmail.replace("@", "_").replace(".", "_")}'
        print(member_email_table)
        # Insert ticket into the database
        # c.execute(f"""
        #     INSERT INTO {user_email_table} (project_info, module_info, description, start_date, expected_date, ticket_creation_time, member, team_member_email)
        #     VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        # """, (project_info, module_info, description, start_date, expected_date, ticket_creation_time_str, assigned_to, member_email))
        
        c.execute(f"""
            INSERT INTO {member_email_table} (project_info, module_info, description, start_date, expected_date, ticket_creation_time, member, team_member_email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_info, module_info, description, start_datetime, end_datetime, ticket_creation_time_str, assigned_to, member_email))

        conn.commit()
        conn.close()

        flash("Ticket created successfully!", "success")
        return redirect(url_for('mentor'))

    conn.close()
    return render_template('create_ticket.html', assigned_projects=assigned_projects, team_members=team_members, project_name=project_name, member=member,member_email=member_email)

@app.route('/get_tickets/<member_email>/<project_info>')
def get_tickets(member_email, project_info):
    if 'email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    user_email_table = f'tickets_{member_email.replace("@", "_").replace(".", "_")}'
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Fetch tickets for the specified member and project
    c.execute(f"""
        SELECT * FROM {user_email_table}
        WHERE project_info = ?
    """, (project_info,))
    tickets = c.fetchall()

    ticket_list = []
    for ticket in tickets:
        ticket_list.append({
            'id': ticket[0],
            'Module': ticket[2],
            'description': ticket[3],
            'started': ticket[4],
            'expected': ticket[5],
            'created': ticket[6],
            'status': ticket[11],
            'closed' : ticket[7]
        })

    conn.close()
    return jsonify(ticket_list)

@app.route('/project_tickets/<int:project_id>')
def project_tickets(project_id):
    if 'email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    c.execute("""
        SELECT * FROM tickets 
        WHERE project_id = ?
    """, (project_id,))
    tickets = c.fetchall()

    ticket_list = []
    for ticket in tickets:
        ticket_list.append({
            'id': ticket[0],
            'description': ticket[3],
            'assigned_to': ticket[2],  # Assuming this is the assigned team member's email
            'status': ticket[8]  # Assuming this is the status
        })

    conn.close()
    return jsonify(ticket_list)

# View ticket details and today's update
@app.route('/ticket_details/<int:ticket_id>', methods=['GET', 'POST'])
def ticket_details(ticket_id):
    if 'email' not in session:
        flash("You must be logged in to view ticket details.", "error")
        return redirect(url_for('login'))

    user_email_table = f'tickets_{session["email"].replace("@", "_").replace(".", "_")}'
    user_updates_table = f'daily_updates_{session["email"].replace("@", "_").replace(".", "_")}'

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Get ticket details
    c.execute(f"SELECT * FROM {user_email_table } WHERE id = ?", (ticket_id,))
    ticket = c.fetchone()

    if not ticket:
        flash("Ticket not found.", "error")
        return redirect(url_for('home'))

    # Get the ticket's valid until date
    ticket_valid_until = datetime.strptime(ticket[6], '%Y-%m-%d %H:%M').date()

    # Get today's date
    today_date = datetime.now().date()
        # Check if ticket[8] (closed_date) is None before calling strptime
    if ticket[8]:
        closed_date = datetime.strptime(ticket[8], '%Y-%m-%d %H:%M').date()
    else:
        closed_date = None

    # Only allow updates if the ticket is still valid and closed_date is not None
        if closed_date is None or today_date <= closed_date:
            if request.method == 'POST':
                c.execute(f""" 
                    SELECT * FROM {user_updates_table} WHERE ticket_id = ? AND update_date = ?
                """, (ticket_id, today_date))
                existing_update = c.fetchone()

                if not existing_update:
                    daily_description = request.form['daily_description']
                    stage = request.form['stage']
                    state = request.form['state']
                    update_date = today_date

                    c.execute(f"""
                        INSERT INTO {user_updates_table} (ticket_id, update_date, daily_description, stage, state)
                        VALUES (?, ?, ?, ?, ?)
                    """, (ticket_id, update_date, daily_description, stage, state))
                    conn.commit()
                    flash(f"Daily update for {update_date} added successfully.", "success")
                else:
                    flash(f"An update for {today_date} already exists.", "error")

    # Retrieve all updates for this ticket, ordered by date
    c.execute(f"""
        SELECT * FROM {user_updates_table} WHERE ticket_id = ? ORDER BY update_date ASC
    """, (ticket_id,))
    daily_updates = c.fetchall()

    conn.close()

    return render_template('ticket_details.html', ticket=ticket, daily_updates=daily_updates, today_date=today_date, closed_date=closed_date)

@app.route('/admin_ticket_details/<int:ticket_id>', methods=['GET', 'POST'])
def admin_ticket_details(ticket_id):
    if 'email' not in session:
        flash("You must be logged in to view ticket details.", "error")
        return redirect(url_for('login'))
    
    user_updates_table = f'admin_daily_updates_{session["email"].replace("@", "_").replace(".", "_")}'
    admin_email_table = f'admin_tickets_{session["email"].replace("@", "_").replace(".", "_")}'

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    c.execute(f"SELECT * FROM {admin_email_table} WHERE id = ?", (ticket_id,))
    ticket = c.fetchone()

    if not ticket:
        flash("Ticket not found.", "error")
        return redirect(url_for('home'))

    # Get the ticket's valid until date
    ticket_valid_until = datetime.strptime(ticket[6], '%Y-%m-%d %H:%M').date()

    # Get today's date
    today_date = datetime.now().date()
        # Check if ticket[8] (closed_date) is None before calling strptime
    if ticket[8]:
        closed_date = datetime.strptime(ticket[8], '%Y-%m-%d %H:%M').date()
    else:
        closed_date = None

    # Only allow updates if the ticket is still valid and closed_date is not None
        if closed_date is None or today_date <= closed_date:
            if request.method == 'POST':
                c.execute(f""" 
                    SELECT * FROM {user_updates_table} WHERE ticket_id = ? AND update_date = ?
                """, (ticket_id, today_date))
                existing_update = c.fetchone()

                if not existing_update:
                    daily_description = request.form['daily_description']
                    stage = request.form['stage']
                    state = request.form['state']
                    update_date = today_date

                    c.execute(f"""
                        INSERT INTO {user_updates_table} (ticket_id, update_date, daily_description, stage, state)
                        VALUES (?, ?, ?, ?, ?)
                    """, (ticket_id, update_date, daily_description, stage, state))
                    conn.commit()
                    flash(f"Daily update for {update_date} added successfully.", "success")
                else:
                    flash(f"An update for {today_date} already exists.", "error")

    # Retrieve all updates for this ticket, ordered by date
    c.execute(f"""
        SELECT * FROM {user_updates_table} WHERE ticket_id = ? ORDER BY update_date ASC
    """, (ticket_id,))
    daily_updates = c.fetchall()

    conn.close()

    source = request.args.get('source', 'home')  # Get the source parameter

    return render_template('admin_ticket_details.html', ticket=ticket, daily_updates=daily_updates, today_date=today_date, closed_date=closed_date, source=source)  

# View daily updates for a specific ticket
@app.route('/ticket_updates/<int:ticket_id>')
def ticket_updates(ticket_id):
    if 'email' not in session:
        flash("You must be logged in to view ticket updates.", "error")
        return redirect(url_for('login'))

    user_updates_table = f'daily_updates_{session["email"].replace("@", "_").replace(".", "_")}'
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Get all updates for this ticket, ordered by date
    c.execute(f"""
        SELECT * FROM {user_updates_table} WHERE ticket_id = ? ORDER BY update_date ASC
    """, (ticket_id,))
    daily_updates = c.fetchall()

    # Get ticket details for display
    user_email_table = f'tickets_{session["email"].replace("@", "_").replace(".", "_")}'
    c.execute(f"SELECT * FROM {user_email_table} WHERE id = ?", (ticket_id,))
    ticket = c.fetchone()

    conn.close()

    if not ticket:
        flash("Ticket not found.", "error")
        return redirect(url_for('home'))

    return render_template('ticket_updates.html', daily_updates=daily_updates, ticket=ticket)

@app.route('/admin_ticket_updates/<int:ticket_id>')
def admin_ticket_updates(ticket_id):
    if 'email' not in session:
        flash("You must be logged in to view ticket updates.", "error")
        return redirect(url_for('login'))

    user_updates_table = f'admin_daily_updates_{session["email"].replace("@", "_").replace(".", "_")}'
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Get all updates for this ticket, ordered by date
    c.execute(f"""
        SELECT * FROM {user_updates_table} WHERE ticket_id = ? ORDER BY update_date ASC
    """, (ticket_id,))
    daily_updates = c.fetchall()

    # Get ticket details for display
    user_email_table = f'admin_tickets_{session["email"].replace("@", "_").replace(".", "_")}'
    c.execute(f"SELECT * FROM {user_email_table} WHERE id = ?", (ticket_id,))
    ticket = c.fetchone()

    conn.close()

    if not ticket:
        flash("Ticket not found.", "error")
        return redirect(url_for('home'))

    source = request.args.get('source', 'home')  # Get the source parameter
    return render_template('admin_ticket_updates.html', daily_updates=daily_updates, ticket=ticket, source=source)

@app.route('/admin/create_ticket', methods=['GET', 'POST'])
def create_ticket_admin():
    if 'admin' not in session:
        flash("You must be logged in as an admin to create a ticket.", "error")
        return redirect(url_for('admin_login_page'))

    if request.method == 'POST':
        team_name = request.form['team_name']
        mentor_name = request.form['mentor_name']
        mentor_email = request.form['mentor_email']
        project_name = request.form['project_name']
        module_info = request.form['module_info']
        description = request.form['description']
        start_date = request.form['start_date']
        end_date = request.form['end_date']

        # Set the fixed times
        start_time = "09:00:00"  # Fixed start time
        end_time = "23:59:00"     # Fixed end time

        # Combine date and time
        start_datetime = f"{start_date} {start_time}"
        end_datetime = f"{end_date} {end_time}"

        # Insert the ticket into the database
        conn = sqlite3.connect('database.db')
        c = conn.cursor()

        # Create user-specific tables for tickets and daily updates
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS admin_tickets_{mentor_email.replace('@', '_').replace('.', '_')} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_info TEXT,
                module_info TEXT,
                description TEXT,
                start_date TIMESTAMP,
                expected_date TIMESTAMP,
                ticket_creation_time TIMESTAMP,
                closed_date TIMESTAMP,
                duration_days INTEGER,
                member TEXT,
                team_member_email TEXT,
                status TEXT DEFAULT 'active'
            );
        """)

        c.execute(f"""
            CREATE TABLE IF NOT EXISTS admin_daily_updates_{mentor_email.replace('@', '_').replace('.', '_')} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER,
                update_date DATE,
                daily_description TEXT,
                stage TEXT,
                state TEXT,
                FOREIGN KEY (ticket_id) REFERENCES tickets_{mentor_email.replace('@', '_').replace('.', '_')} (id),
                UNIQUE(ticket_id, update_date)
            );
        """)

        # try:
        #     start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        #     expected_date_obj = datetime.strptime(end_date, '%Y-%m-%d')

        #     if expected_date_obj == start_date_obj:
        #         expected_date_obj = expected_date_obj.replace(hour=23, minute=59, second=59, microsecond=999999)
        #     elif expected_date_obj < start_date_obj:
        #         flash("Expected Date must be after the Start Date.", "error")
        #         return render_template('admin.html')

        # except ValueError:
        #     flash("Invalid date format. Please use YYYY-MM-DD.", "error")
        #     return render_template('admin.html')
        
        member_email_table = f'admin_tickets_{mentor_email.replace("@", "_").replace(".", "_")}'
        ticket_creation_time = datetime.now()
        ticket_creation_time_str = ticket_creation_time.strftime('%Y-%m-%d %H:%M')

        c.execute(f"""
            INSERT INTO {member_email_table} (project_info, description,module_info, start_date, expected_date, ticket_creation_time, team_member_email)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (project_name, description, module_info, start_datetime, end_datetime, ticket_creation_time_str, mentor_email))

        conn.commit()
        conn.close()

        flash("Ticket created successfully!", "success")
        return redirect(url_for('admin'))

    # Fetch teams and their mentors
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT team_name FROM signup")
    teams = c.fetchall()

    conn.close()

    return render_template('admin.html', teams=teams)

@app.route('/get_mentors_and_members/<team_name>')
def get_mentors_and_members(team_name):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Fetch mentors for the selected team
    c.execute("SELECT name, email FROM signup WHERE team_name = ? AND role = 'mentor'", (team_name,))
    mentors = c.fetchall()

    # Fetch team members for the selected team
    c.execute("SELECT name, email FROM signup WHERE team_name = ? AND role = 'team_member'", (team_name,))
    members = c.fetchall()

    c.execute("SELECT name, email FROM signup WHERE team_name = ? AND role = 'researchers'", (team_name,))
    researchers = c.fetchall()

    conn.close()

    return jsonify({
        'mentors': [{'name': mentor[0], 'email': mentor[1]} for mentor in mentors],
        'members': [{'name': member[0], 'email': member[1]} for member in members],
        'researchers': [{'name': researcher[0], 'email': researcher[1]} for researcher in researchers]
    })

def close_expired_tickets():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Get the current date and time
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Close tickets in user-specific tables
    c.execute("""
        SELECT DISTINCT team_member_email FROM projects WHERE status = 'active'
    """)
    team_members = c.fetchall()
    
    for member in team_members:
        member_email = member[0]  # Get the email from the tuple
        if member_email is None:
            print("Skipping None member_email")
            continue  # Skip if member_email is None

        user_email_table = f'tickets_{member_email.replace("@", "_").replace(".", "_")}'
        c.execute(f"""
            SELECT * FROM {user_email_table} WHERE closed_date IS NULL
        """)
        tickets_detail = c.fetchall()

        # Check if there are any tickets to process
        if not tickets_detail:
            print(f"No open tickets found for {member_email}.")
            continue  # Skip to the next member if no tickets are found

        for ticket in tickets_detail:
            ticket_id = ticket[0]  # Assuming the first column is the ticket ID
            expected_date = ticket[5]  # Assuming the expected_date is in the 6th column (index 5)

            # Close tickets where expected_date is less than or equal to current_time
            if expected_date <= current_time:
                c.execute(f"""
                    UPDATE {user_email_table}
                    SET closed_date = ?, status = 'closed',
                        duration_days = CAST((julianday(?) - julianday(start_date)) AS INTEGER)
                    WHERE id = ?
                """, (expected_date, expected_date, ticket_id))

    # Close tickets in admin-specific tables
    c.execute("SELECT email FROM signup WHERE role IN ('mentor', 'team_member', 'researchers')")
    users = c.fetchall()

    for user in users:
        user_email = user[0]
        admin_email_table = f'admin_tickets_{user_email.replace("@", "_").replace(".", "_")}'

        try:
            c.execute(f"""
                SELECT * FROM {admin_email_table} WHERE closed_date IS NULL
            """)
            admin_tickets_detail = c.fetchall()

            # Check if there are any admin tickets to process
            if not admin_tickets_detail:
                print(f"No open admin tickets found for {user_email}.")
                continue  # Skip to the next user if no tickets are found

            for admin_ticket in admin_tickets_detail:
                admin_ticket_id = admin_ticket[0]  # Assuming the first column is the ticket ID
                admin_expected_date = admin_ticket[5]  # Assuming the expected_date is in the 6th column (index 5)

                # Close admin tickets where expected_date is less than or equal to current_time
                if admin_expected_date <= current_time:
                    try:
                        c.execute(f"""
                            UPDATE {admin_email_table}
                            SET closed_date = ?, status = 'closed',
                                duration_days = CAST((julianday(?) - julianday(start_date)) AS INTEGER)
                            WHERE id = ?
                        """, (admin_expected_date, admin_expected_date, admin_ticket_id))
                    except sqlite3.OperationalError:
                        print(f"Error updating admin ticket {admin_ticket_id} for {user_email}.")
        except sqlite3.OperationalError:
            print("Invalid Email", "error")
        
        
    conn.commit()
    conn.close()

# Main route (home)
@app.route('/')
def index():
    return redirect(url_for('login'))

if __name__ == '__main__':
    sql_connector()  # Ensure the database is initialized
    app.run(debug=True, host='0.0.0.0')
