from flask import Flask, render_template, request, redirect, flash, url_for, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Schedule, check_and_upgrade_db
from datetime import datetime, timedelta, time, date
from flask_mail import Mail, Message
from flask_apscheduler import APScheduler
import os
import urllib.parse
import ai_engine

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

basedir = os.path.abspath(os.path.dirname(__file__))
env_file = os.path.join(basedir, '.env')
if os.path.exists(env_file):
    with open(env_file, 'r', encoding='utf-8') as f_env:
        for line in f_env:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                val = v.strip().strip("'\"")
                os.environ.setdefault(k.strip(), val)

# -------- Flask Configuration --------
app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'schedule_manager_secret_2026')
db_path = os.path.join(basedir, "users.db")

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# -------- Mail Configuration --------
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() in ['true', '1', 't']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', os.environ.get('MAIL_USERNAME'))

# -------- Initialization --------
db.init_app(app)
mail = Mail(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# -------- User Loader --------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# -------- Helper: Schedule Reminder Job with Custom Offset --------
def schedule_reminder_job(schedule_id, user_id, schedule_date, schedule_time, offset_type='1_day'):
    """Schedules an automated email reminder according to selected offset (10m, 1h, 1d, 1w)."""
    event_datetime = datetime.combine(schedule_date, schedule_time)
    
    offset_map = {
        '10_min': timedelta(minutes=10),
        '1_hour': timedelta(hours=1),
        '1_day': timedelta(days=1),
        '1_week': timedelta(weeks=1)
    }
    delta = offset_map.get(offset_type, timedelta(days=1))
    reminder_datetime = event_datetime - delta
    now = datetime.now()

    if reminder_datetime <= now:
        run_date = now + timedelta(seconds=10)
        print(f"[REMINDER] Event {schedule_id} is within offset window ({event_datetime}). Reminder set to trigger shortly at {run_date}")
    else:
        run_date = reminder_datetime
        print(f"[REMINDER] Reminder job {schedule_id} scheduled ({offset_type} before event) at {run_date}")

    job_id = f"reminder_{schedule_id}"
    scheduler.add_job(
        func=send_reminder_email,
        trigger='date',
        run_date=run_date,
        args=[user_id, schedule_id],
        id=job_id,
        replace_existing=True
    )
    return run_date


# -------- Reminder Email Function with Rich Layout --------
def send_reminder_email(user_id, schedule_id):
    with app.app_context():
        user = User.query.get(user_id)
        schedule = Schedule.query.get(schedule_id)

        if not user or not schedule:
            print("[REMINDER ERROR] User or Schedule not found.")
            return

        priority_labels = {
            'high': '🔴 High Priority',
            'medium': '🟡 Medium Priority',
            'low': '🟢 Low Priority'
        }
        category_labels = {
            'work': '💼 Work',
            'personal': '👤 Personal',
            'study': '📚 Study',
            'health': '🏃 Health',
            'finance': '💰 Finance',
            'general': '📌 General'
        }
        p_text = priority_labels.get(schedule.priority, '🟡 Medium Priority')
        c_text = category_labels.get(schedule.category, '📌 General')

        subject = f"⏰ PlanPulse AI Alert: '{schedule.title}' [{p_text.split()[0]}]"

        plain_body = f"""Hi {user.name},

This is an automated reminder from PlanPulse AI:

📌 Title: {schedule.title}
📅 Date: {schedule.date.strftime('%d %B %Y')}
🕒 Time: {schedule.time.strftime('%I:%M %p')}
🎯 Priority: {p_text}
📁 Category: {c_text}
📝 Description: {schedule.description or 'No description provided.'}

-----
PlanPulse AI — Intelligent Schedule & Productivity Platform.
Please do not reply to this email."""

        html_body = f"""
        <!DOCTYPE html>
        <html>
            <head><meta charset="UTF-8"></head>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0a0e1a; margin: 0; padding: 24px; color: #f1f5f9;">
                <div style="max-width: 580px; margin: 0 auto; background: #121829; border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.1); overflow: hidden; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);">
                    <div style="background: linear-gradient(135deg, #4f46e5 0%, #6366f1 50%, #06b6d4 100%); padding: 24px; color: #ffffff;">
                        <h2 style="margin: 0 0 6px 0; font-size: 20px; font-weight: 800;">⚡ PlanPulse AI Schedule Alert</h2>
                        <p style="margin: 0; opacity: 0.9; font-size: 14px;">Your upcoming event is approaching!</p>
                    </div>
                    <div style="padding: 24px;">
                        <p style="font-size: 15px; margin-top: 0; color: #f1f5f9;">Hi <strong>{user.name}</strong>,</p>
                        <p style="font-size: 14px; color: #94a3b8;">PlanPulse AI has flagged the following commitment for you:</p>
                        
                        <div style="background: #172138; border-left: 4px solid #6366f1; border-radius: 10px; padding: 18px; margin: 20px 0; border: 1px solid rgba(255, 255, 255, 0.06);">
                            <h3 style="margin: 0 0 12px 0; color: #38bdf8; font-size: 18px;">📌 {schedule.title}</h3>
                            <p style="margin: 6px 0; font-size: 14px; color: #e2e8f0;"><strong>📅 Date:</strong> {schedule.date.strftime('%d %B %Y')}</p>
                            <p style="margin: 6px 0; font-size: 14px; color: #e2e8f0;"><strong>🕒 Time:</strong> {schedule.time.strftime('%I:%M %p')}</p>
                            <p style="margin: 6px 0; font-size: 14px; color: #e2e8f0;"><strong>🎯 Priority:</strong> {p_text}</p>
                            <p style="margin: 6px 0; font-size: 14px; color: #e2e8f0;"><strong>📁 Category:</strong> {c_text}</p>
                            <p style="margin: 6px 0; font-size: 14px; color: #94a3b8;"><strong>📝 Notes:</strong> {schedule.description or 'No description provided.'}</p>
                        </div>

                        <p style="font-size: 13px; color: #94a3b8; margin-bottom: 0;">Stay focused, productive, and conquer your day!</p>
                    </div>
                    <div style="background: #0d1222; padding: 14px 24px; border-top: 1px solid rgba(255, 255, 255, 0.08); font-size: 12px; color: #64748b; text-align: center;">
                        Automated smart alert delivered by <strong>PlanPulse AI</strong>.
                    </div>
                </div>
            </body>
        </html>
        """

        try:
            msg = Message(subject,
                          sender=("PlanPulse AI", app.config['MAIL_USERNAME']),
                          recipients=[user.email],
                          body=plain_body,
                          html=html_body,
                          reply_to=app.config['MAIL_USERNAME'])

            mail.send(msg)
            print(f"[SUCCESS] Reminder email sent to {user.email} for '{schedule.title}'")
        except Exception as e:
            print(f"[ERROR] Failed to send reminder email: {e}")


# -------- Dashboard & Home Route --------
@app.route('/')
def home():
    if current_user.is_authenticated:
        schedules = Schedule.query.filter_by(user_id=current_user.id).order_by(Schedule.date, Schedule.time).all()
        total_count = len(schedules)
        pending_count = sum(1 for s in schedules if s.status != 'completed')
        completed_count = total_count - pending_count
        upcoming = [s for s in schedules if s.status != 'completed'][:4]
        
        # AI Engine Daily Briefing & Conflict Detection
        briefing = ai_engine.generate_daily_briefing(schedules, user_name=current_user.name)
        conflicts = ai_engine.detect_schedule_conflicts(schedules)

        return render_template(
            'home.html',
            schedules=upcoming,
            total_count=total_count,
            pending_count=pending_count,
            completed_count=completed_count,
            briefing=briefing,
            conflicts=conflicts
        )
    return render_template('home.html')


# -------- Auth Routes --------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        if User.query.filter_by(email=email).first():
            flash('⚠️ Email already exists.', 'warning')
            return redirect('/signup')
        db.session.add(User(name=name, email=email, password=password))
        db.session.commit()
        flash('✅ Account created! Please login.', 'success')
        return redirect('/login')
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('✅ Logged in successfully!', 'success')
            next_page = request.args.get('next') or '/'
            return redirect(next_page)
        flash('❌ Invalid email or password.', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('👋 Logged out successfully.', 'info')
    return redirect('/login')


# -------- Profile Routes --------
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.mobile = request.form.get('mobile')
        current_user.country = request.form.get('country')
        current_user.state = request.form.get('state')
        dob_input = request.form.get('dob')
        if dob_input:
            try:
                current_user.dob = datetime.strptime(dob_input, '%Y-%m-%d').date()
            except ValueError:
                flash("Invalid date format for DOB.", "danger")
        db.session.commit()
        flash("✅ Profile updated successfully!", "success")
        return redirect(url_for('profile_view'))
    return render_template('profile.html', user=current_user)


@app.route('/profile/view')
@login_required
def profile_view():
    return render_template('profile_view.html', user=current_user)


@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.id != user_id:
        flash("❌ Unauthorized.", "danger")
        return redirect(url_for('profile_view'))

    user = User.query.get_or_404(user_id)
    Schedule.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    logout_user()
    flash("🗑️ Account and all schedules have been deleted.", "success")
    return redirect(url_for('signup'))


# -------- Schedule CRUD & Advanced Features --------
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_schedule():
    if request.method == "POST":
        title = request.form['title']
        description = request.form.get('description', '')
        date_val = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        time_val = datetime.strptime(request.form['time'], '%H:%M').time()
        reminder = 'reminder' in request.form
        
        priority = request.form.get('priority', 'medium')
        category = request.form.get('category', 'general')
        reminder_offset = request.form.get('reminder_offset', '1_day')
        is_recurring = request.form.get('is_recurring', 'none')

        schedule = Schedule(
            title=title,
            description=description,
            date=date_val,
            time=time_val,
            reminder=reminder,
            priority=priority,
            category=category,
            reminder_offset=reminder_offset,
            is_recurring=is_recurring,
            status='pending',
            user_id=current_user.id
        )
        db.session.add(schedule)
        db.session.commit()

        if reminder:
            schedule_reminder_job(schedule.id, current_user.id, date_val, time_val, reminder_offset)

        flash("✅ Schedule added successfully!", "success")
        return redirect(url_for('view_schedules'))
    return render_template('add_schedule.html')


@app.route('/schedules')
@login_required
def view_schedules():
    query = Schedule.query.filter_by(user_id=current_user.id)
    
    # Filter by category
    selected_category = request.args.get('category')
    if selected_category and selected_category != 'all':
        query = query.filter_by(category=selected_category)
        
    # Filter by priority
    selected_priority = request.args.get('priority')
    if selected_priority and selected_priority != 'all':
        query = query.filter_by(priority=selected_priority)
        
    # Filter by status
    selected_status = request.args.get('status')
    if selected_status and selected_status != 'all':
        query = query.filter_by(status=selected_status)
        
    # Search keyword
    search_q = request.args.get('q', '').strip()
    if search_q:
        query = query.filter(
            (Schedule.title.ilike(f'%{search_q}%')) | 
            (Schedule.description.ilike(f'%{search_q}%'))
        )
        
    schedules = query.order_by(Schedule.status.desc(), Schedule.date.asc(), Schedule.time.asc()).all()
    return render_template(
        'view_schedules.html',
        schedules=schedules,
        selected_category=selected_category,
        selected_priority=selected_priority,
        selected_status=selected_status,
        search_q=search_q
    )


@app.route('/schedule/update/<int:schedule_id>', methods=['GET', 'POST'])
@login_required
def update_schedule(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    if schedule.user_id != current_user.id:
        flash("You are not authorized to edit this schedule.", "danger")
        return redirect(url_for('view_schedules'))

    if request.method == 'POST':
        schedule.title = request.form['title']
        schedule.description = request.form.get('description', '')
        schedule.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        schedule.time = datetime.strptime(request.form['time'], '%H:%M').time()
        schedule.reminder = 'reminder' in request.form
        schedule.priority = request.form.get('priority', schedule.priority or 'medium')
        schedule.category = request.form.get('category', schedule.category or 'general')
        schedule.reminder_offset = request.form.get('reminder_offset', schedule.reminder_offset or '1_day')
        schedule.is_recurring = request.form.get('is_recurring', schedule.is_recurring or 'none')

        db.session.commit()

        job_id = f"reminder_{schedule.id}"
        if schedule.reminder:
            schedule_reminder_job(schedule.id, current_user.id, schedule.date, schedule.time, schedule.reminder_offset)
        else:
            try:
                scheduler.remove_job(job_id)
                print(f"[REMINDER] Removed reminder job for schedule {schedule.id}")
            except Exception:
                pass

        flash("✅ Schedule updated successfully!", "success")
        return redirect(url_for('view_schedules'))

    return render_template('edit_schedule.html', schedule=schedule)


@app.route('/schedule/delete/<int:schedule_id>', methods=['POST'])
@login_required
def delete_schedule(schedule_id):
    schedule = Schedule.query.filter_by(id=schedule_id, user_id=current_user.id).first()
    if schedule:
        try:
            scheduler.remove_job(f"reminder_{schedule.id}")
        except Exception:
            pass
        db.session.delete(schedule)
        db.session.commit()
        flash("🗑️ Schedule deleted.", "success")
    else:
        flash("❌ Unauthorized or not found.", "danger")
    return redirect(request.referrer or url_for('view_schedules'))


# -------- 1-Click Status Toggle & Recurrence Generator --------
@app.route('/schedule/<int:schedule_id>/toggle-status', methods=['POST'])
@login_required
def toggle_schedule_status(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    if schedule.user_id != current_user.id:
        flash("Unauthorized action.", "danger")
        return redirect(url_for('view_schedules'))

    if schedule.status == 'completed':
        schedule.status = 'pending'
        schedule.completed_at = None
        flash("↩️ Schedule marked as Pending.", "info")
    else:
        schedule.status = 'completed'
        schedule.completed_at = datetime.utcnow()
        flash("🎉 Great job! Schedule marked as Completed.", "success")

        # Spawn next recurrence if recurring schedule
        if schedule.is_recurring and schedule.is_recurring != 'none':
            next_date = schedule.date
            if schedule.is_recurring == 'daily':
                next_date += timedelta(days=1)
            elif schedule.is_recurring == 'weekly':
                next_date += timedelta(weeks=1)
            elif schedule.is_recurring == 'monthly':
                next_date += timedelta(days=30)

            next_sched = Schedule(
                title=schedule.title,
                description=schedule.description,
                date=next_date,
                time=schedule.time,
                reminder=schedule.reminder,
                priority=schedule.priority,
                category=schedule.category,
                reminder_offset=schedule.reminder_offset,
                is_recurring=schedule.is_recurring,
                status='pending',
                user_id=current_user.id
            )
            db.session.add(next_sched)
            db.session.commit()

            if next_sched.reminder:
                schedule_reminder_job(next_sched.id, current_user.id, next_sched.date, next_sched.time, next_sched.reminder_offset)
            flash(f"🔄 Next recurring schedule created for {next_date.strftime('%d %B %Y')}!", "success")

    db.session.commit()
    return redirect(request.referrer or url_for('view_schedules'))


# -------- iCalendar (.ics) Export Route --------
@app.route('/schedule/<int:schedule_id>/export-ics')
@login_required
def export_ics(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    if schedule.user_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for('view_schedules'))

    start_dt = datetime.combine(schedule.date, schedule.time)
    end_dt = start_dt + timedelta(hours=1)

    start_str = start_dt.strftime('%Y%m%dT%H%M%S')
    end_str = end_dt.strftime('%Y%m%dT%H%M%S')
    now_str = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')

    clean_desc = (schedule.description or '').replace('\n', '\\n').replace(',', '\\,')
    clean_title = schedule.title.replace(',', '\\,')
    status_str = 'COMPLETED' if schedule.status == 'completed' else 'CONFIRMED'
    prio_num = 1 if schedule.priority == 'high' else (5 if schedule.priority == 'medium' else 9)

    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Schedule Manager Web App//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
UID:schedule-{schedule.id}@schedulemanager.app
DTSTAMP:{now_str}
DTSTART:{start_str}
DTEND:{end_str}
SUMMARY:{clean_title}
DESCRIPTION:{clean_desc}
PRIORITY:{prio_num}
STATUS:{status_str}
END:VEVENT
END:VCALENDAR"""

    filename = f"schedule_{schedule.id}.ics"
    return Response(
        ics_content,
        mimetype="text/calendar",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# -------- FullCalendar Interactive Calendar View & API --------
@app.route('/calendar')
@login_required
def calendar_view():
    return render_template('calendar.html')


@app.route('/api/schedules')
@login_required
def api_schedules():
    schedules = Schedule.query.filter_by(user_id=current_user.id).all()
    
    category_colors = {
        'work': '#3b82f6',      # Blue
        'personal': '#8b5cf6',  # Purple
        'study': '#10b981',     # Emerald
        'health': '#ef4444',    # Rose
        'finance': '#f59e0b',   # Amber
        'general': '#6366f1'    # Indigo
    }
    
    events = []
    for s in schedules:
        start_str = f"{s.date.strftime('%Y-%m-%d')}T{s.time.strftime('%H:%M:%S')}"
        color = category_colors.get(s.category, '#6366f1')
        if s.status == 'completed':
            color = '#94a3b8'  # Muted Gray for completed tasks

        # Build Google Calendar link
        start_dt = datetime.combine(s.date, s.time)
        end_dt = start_dt + timedelta(hours=1)
        gcal_dates = f"{start_dt.strftime('%Y%m%dT%H%M%S')}/{end_dt.strftime('%Y%m%dT%H%M%S')}"
        gcal_url = (
            f"https://calendar.google.com/calendar/render?action=TEMPLATE"
            f"&text={urllib.parse.quote(s.title)}"
            f"&dates={gcal_dates}"
            f"&details={urllib.parse.quote(s.description or '')}"
        )

        events.append({
            'id': s.id,
            'title': s.title,
            'start': start_str,
            'color': color,
            'extendedProps': {
                'description': s.description or 'No description provided.',
                'category': s.category or 'general',
                'priority': s.priority or 'medium',
                'status': s.status or 'pending',
                'reminder': s.reminder,
                'time_formatted': s.time.strftime('%I:%M %p'),
                'date_formatted': s.date.strftime('%d %b %Y'),
                'edit_url': url_for('update_schedule', schedule_id=s.id),
                'export_url': url_for('export_ics', schedule_id=s.id),
                'gcal_url': gcal_url
            }
        })
    return jsonify(events)


# -------- Productivity Analytics Dashboard Route --------
@app.route('/analytics')
@login_required
def analytics_view():
    schedules = Schedule.query.filter_by(user_id=current_user.id).all()
    total = len(schedules)
    completed = sum(1 for s in schedules if s.status == 'completed')
    pending = total - completed
    rate = int((completed / total * 100)) if total > 0 else 0

    cat_counts = {'work': 0, 'personal': 0, 'study': 0, 'health': 0, 'finance': 0, 'general': 0}
    for s in schedules:
        c = s.category or 'general'
        cat_counts[c] = cat_counts.get(c, 0) + 1

    prio_counts = {'high': 0, 'medium': 0, 'low': 0}
    for s in schedules:
        p = s.priority or 'medium'
        prio_counts[p] = prio_counts.get(p, 0) + 1

    urgent_count = sum(1 for s in schedules if s.priority == 'high' and s.status == 'pending')

    # Calculate streak (consecutive days with completed events)
    completed_dates = sorted(list(set(s.completed_at.date() for s in schedules if s.completed_at)), reverse=True)
    streak = 0
    curr = datetime.utcnow().date()
    for d in completed_dates:
        if d == curr or d == curr - timedelta(days=1):
            streak += 1
            curr = d
        else:
            break

    return render_template(
        'analytics.html',
        total=total,
        completed=completed,
        pending=pending,
        rate=rate,
        urgent_count=urgent_count,
        streak=streak,
        cat_counts=cat_counts,
        prio_counts=prio_counts
    )


# -------- PlanPulse AI Studio & Endpoints --------
@app.route('/ai/studio')
@login_required
def ai_studio():
    schedules = Schedule.query.filter_by(user_id=current_user.id).order_by(Schedule.date, Schedule.time).all()
    briefing = ai_engine.generate_daily_briefing(schedules, user_name=current_user.name)
    conflicts = ai_engine.detect_schedule_conflicts(schedules)
    return render_template('ai_studio.html', briefing=briefing, conflicts=conflicts, total_schedules=len(schedules))


@app.route('/api/ai/parse-task', methods=['POST'])
@login_required
def api_ai_parse_task():
    data = request.get_json() or {}
    prompt = data.get('prompt', '')
    if not prompt or not prompt.strip():
        return jsonify({'error': 'Please provide a task description'}), 400
    parsed = ai_engine.parse_natural_language_schedule(prompt)
    if not parsed:
        return jsonify({'error': 'Unable to parse schedule from text'}), 400
    return jsonify({'success': True, 'task': parsed})


@app.route('/api/ai/save-task', methods=['POST'])
@login_required
def api_ai_save_task():
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    if not title:
        return jsonify({'error': 'Task title is required'}), 400
    
    try:
        t_date = datetime.strptime(data.get('date'), '%Y-%m-%d').date()
        t_time = datetime.strptime(data.get('time'), '%H:%M').time()
    except Exception as e:
        return jsonify({'error': f'Invalid date or time format: {e}'}), 400
        
    category = data.get('category', 'general')
    priority = data.get('priority', 'medium')
    reminder_offset = data.get('reminder_offset', '1_day')
    description = data.get('description', '')

    new_schedule = Schedule(
        title=title,
        description=description,
        date=t_date,
        time=t_time,
        reminder=True,
        priority=priority,
        category=category,
        reminder_offset=reminder_offset,
        status='pending',
        user_id=current_user.id
    )
    db.session.add(new_schedule)
    db.session.commit()

    schedule_reminder_job(new_schedule.id, current_user.id, t_date, t_time, reminder_offset)
    return jsonify({'success': True, 'schedule_id': new_schedule.id, 'message': f"Task '{title}' scheduled successfully!"})


@app.route('/api/ai/breakdown-goal', methods=['POST'])
@login_required
def api_ai_breakdown_goal():
    data = request.get_json() or {}
    goal = data.get('goal', '').strip()
    deadline = data.get('deadline')
    category = data.get('category', 'work')
    if not goal:
        return jsonify({'error': 'Goal title is required'}), 400
    
    milestones = ai_engine.breakdown_goal_into_schedules(goal, target_deadline=deadline, category=category)
    return jsonify({'success': True, 'milestones': milestones})


@app.route('/api/ai/save-milestones', methods=['POST'])
@login_required
def api_ai_save_milestones():
    data = request.get_json() or {}
    milestones = data.get('milestones', [])
    if not milestones:
        return jsonify({'error': 'No milestones provided'}), 400
    
    created_count = 0
    for m in milestones:
        try:
            m_date = datetime.strptime(m.get('date'), '%Y-%m-%d').date()
            m_time = datetime.strptime(m.get('time'), '%H:%M').time()
            new_s = Schedule(
                title=m.get('title'),
                description=m.get('description', ''),
                date=m_date,
                time=m_time,
                reminder=True,
                priority=m.get('priority', 'medium'),
                category=m.get('category', 'work'),
                reminder_offset=m.get('reminder_offset', '1_day'),
                status='pending',
                user_id=current_user.id
            )
            db.session.add(new_s)
            db.session.commit()
            schedule_reminder_job(new_s.id, current_user.id, m_date, m_time, m.get('reminder_offset', '1_day'))
            created_count += 1
        except Exception as e:
            print(f"[AI ERROR] Failed to save milestone: {e}")
            continue

    return jsonify({'success': True, 'count': created_count, 'message': f"Successfully created {created_count} milestones in your schedule!"})


@app.route('/api/ai/coach-chat', methods=['POST'])
@login_required
def api_ai_coach_chat():
    data = request.get_json() or {}
    question = data.get('question', '').strip()
    if not question:
        return jsonify({'error': 'Question cannot be empty'}), 400
    schedules = Schedule.query.filter_by(user_id=current_user.id).all()
    answer = ai_engine.ask_productivity_coach(question, schedules, user_name=current_user.name)
    return jsonify({'success': True, 'answer': answer})


# -------- Info Pages --------
@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/contact')
def contact():
    return render_template('contact.html')


# -------- Main Execution --------
if __name__ == '__main__':
    check_and_upgrade_db(app)
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Schedule Manager on http://127.0.0.1:{port} ...")
    app.run(host="0.0.0.0", port=port, debug=False)
