# -------- All Your Original Imports --------
from flask import Flask, render_template, request, redirect, flash, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Schedule
from datetime import datetime, timedelta
from flask_mail import Mail, Message
from flask_apscheduler import APScheduler
import os

# -------- Flask Configuration --------
app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback_secret')

basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, "users.db")

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# -------- Mail Configuration --------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Fallback .env loading
env_file = os.path.join(basedir, '.env')
if os.path.exists(env_file):
    with open(env_file, 'r', encoding='utf-8') as f_env:
        for line in f_env:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                val = v.strip().strip("'\"")
                os.environ.setdefault(k.strip(), val)

app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() in ['true', '1', 't']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'yash.glsbca21@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'sowfupoevcfvytpu')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', os.environ.get('MAIL_USERNAME', 'yash.glsbca21@gmail.com'))

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

# -------- Helper to Schedule Reminder 1 Day Before --------
def schedule_reminder_job(schedule_id, user_id, date, time):
    """Schedules an automated email reminder 1 day before the event date and time."""
    event_datetime = datetime.combine(date, time)
    reminder_datetime = event_datetime - timedelta(days=1)
    now = datetime.now()

    # If the event is scheduled for less than 1 day from now,
    # trigger in 10 seconds so the user/tester receives the reminder promptly!
    if reminder_datetime <= now:
        run_date = now + timedelta(seconds=10)
        print(f"[REMINDER] Event {schedule_id} is within 24 hours ({event_datetime}). Reminder set to trigger shortly at {run_date}")
    else:
        run_date = reminder_datetime
        print(f"[REMINDER] Reminder job {schedule_id} scheduled 1 day before event at {run_date}")

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


# -------- Reminder Email Function (1-Day Advance Notice) --------
def send_reminder_email(user_id, schedule_id):
    with app.app_context():
        user = User.query.get(user_id)
        schedule = Schedule.query.get(schedule_id)

        if not user or not schedule:
            print("❌ User or Schedule not found.")
            return

        subject = f"⏰ 1-Day Reminder: '{schedule.title}' is scheduled for tomorrow!"

        # Plain text version
        plain_body = f"""Hi {user.name},

This is an automated 1-day advance reminder for your upcoming schedule tomorrow:

📌 Title: {schedule.title}
📅 Date: {schedule.date.strftime('%d %B %Y')}
🕒 Time: {schedule.time.strftime('%I:%M %p')}
📝 Description: {schedule.description or 'No description provided.'}

-----
This is an automated reminder from Schedule Manager Web App.
Please do not reply to this email."""

        # Modern HTML Email Template
        html_body = f"""
        <!DOCTYPE html>
        <html>
            <head>
                <meta charset="UTF-8">
            </head>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #1e293b;">
                <div style="max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
                    <div style="background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%); padding: 24px; color: #ffffff;">
                        <h2 style="margin: 0 0 6px 0; font-size: 20px; font-weight: 700;">⏰ 1-Day Advance Reminder</h2>
                        <p style="margin: 0; opacity: 0.9; font-size: 14px;">Your scheduled event is coming up tomorrow!</p>
                    </div>
                    <div style="padding: 24px;">
                        <p style="font-size: 15px; margin-top: 0;">Hi <strong>{user.name}</strong>,</p>
                        <p style="font-size: 14px; color: #475569;">This is a friendly notification from Schedule Manager to help you prepare for tomorrow's schedule:</p>
                        
                        <div style="background: #f1f5f9; border-left: 4px solid #4f46e5; border-radius: 8px; padding: 16px; margin: 20px 0;">
                            <h3 style="margin: 0 0 10px 0; color: #1e293b; font-size: 17px;">📌 {schedule.title}</h3>
                            <p style="margin: 6px 0; font-size: 14px;"><strong>📅 Date:</strong> {schedule.date.strftime('%d %B %Y')}</p>
                            <p style="margin: 6px 0; font-size: 14px;"><strong>🕒 Time:</strong> {schedule.time.strftime('%I:%M %p')}</p>
                            <p style="margin: 6px 0; font-size: 14px;"><strong>📝 Description:</strong> {schedule.description or 'No description provided.'}</p>
                        </div>

                        <p style="font-size: 13px; color: #64748b; margin-bottom: 0;">Stay organized and have a productive day ahead!</p>
                    </div>
                    <div style="background: #f8fafc; padding: 14px 24px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center;">
                        Automated reminder sent by <strong>Schedule Manager Web App</strong>.
                    </div>
                </div>
            </body>
        </html>
        """

        try:
            msg = Message(subject,
                          sender=("Schedule Manager App", app.config['MAIL_USERNAME']),
                          recipients=[user.email],
                          body=plain_body,
                          html=html_body,
                          reply_to=app.config['MAIL_USERNAME'])

            mail.send(msg)
            print(f"[SUCCESS] 1-Day Reminder email sent successfully to {user.email} for '{schedule.title}'")
        except Exception as e:
            print(f"[ERROR] Failed to send reminder email: {e}")

# -------- Routes (Unchanged Except add_schedule) --------
@app.route('/')
def home():
    if current_user.is_authenticated:
        schedules = Schedule.query.filter_by(user_id=current_user.id).order_by(Schedule.date, Schedule.time).limit(3).all()
        return render_template('home.html', schedules=schedules)
    return render_template('home.html')

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('✅ Logged in successfully!', 'success')
            return redirect('/')
        flash('❌ Invalid email or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')

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

# -------- ✅ Corrected add_schedule() --------
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_schedule():
    if request.method == "POST":
        title = request.form['title']
        description = request.form['description']
        date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        time = datetime.strptime(request.form['time'], '%H:%M').time()
        reminder = 'reminder' in request.form

        schedule = Schedule(
            title=title,
            description=description,
            date=date,
            time=time,
            reminder=reminder,
            user_id=current_user.id
        )
        db.session.add(schedule)
        db.session.commit()

        if reminder:
            schedule_reminder_job(schedule.id, current_user.id, date, time)

        flash("✅ Schedule added successfully!", "success")
        return redirect(url_for('view_schedules'))
    return render_template('add_schedule.html')

@app.route('/schedules')
@login_required
def view_schedules():
    schedules = Schedule.query.filter_by(user_id=current_user.id).order_by(Schedule.date, Schedule.time).all()
    return render_template('view_schedules.html', schedules=schedules)

@app.route('/schedule/update/<int:schedule_id>', methods=['GET', 'POST'])
@login_required
def update_schedule(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)

    if schedule.user_id != current_user.id:
        flash("You are not authorized to edit this schedule.", "danger")
        return redirect(url_for('view_schedules'))

    if request.method == 'POST':
        schedule.title = request.form['title']
        schedule.description = request.form['description']
        schedule.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        schedule.time = datetime.strptime(request.form['time'], '%H:%M').time()
        schedule.reminder = 'reminder' in request.form

        db.session.commit()

        # Update or cancel reminder job
        job_id = f"reminder_{schedule.id}"
        if schedule.reminder:
            schedule_reminder_job(schedule.id, current_user.id, schedule.date, schedule.time)
        else:
            try:
                scheduler.remove_job(job_id)
                print(f"🗑️ Removed reminder job for schedule {schedule.id}")
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
        # Cancel any scheduled reminder job
        try:
            scheduler.remove_job(f"reminder_{schedule.id}")
        except Exception:
            pass
        db.session.delete(schedule)
        db.session.commit()
        flash("🗑️ Schedule deleted.", "success")
    else:
        flash("❌ Unauthorized or not found.", "danger")
    return redirect(url_for('view_schedules'))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

# -------- Test Email Route (Unchanged) --------
# @app.route('/test_email')
# def test_email():
#     msg = Message('Test Email from Your App',
#                  recipients=['bandayash11@gmail.com'],
#                  body='This is a test email from your Flask application.')
#     try:
#         mail.send(msg)
#         return "✅ Email sent successfully! Check your inbox (and spam folder)"
#     except Exception as e:
#         return f"❌ Email failed: {str(e)} - Verify Gmail settings at https://myaccount.google.com/security"


@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.id != user_id:
        flash("❌ You are not authorized to delete this user.", "danger")
        return redirect(url_for('profile_view'))

    user = User.query.get_or_404(user_id)

    # Delete user's schedules first (if you want to avoid orphaned schedules)
    Schedule.query.filter_by(user_id=user.id).delete()

    # Then delete the user
    db.session.delete(user)
    db.session.commit()

    flash("🗑️ Your account and schedules have been deleted.", "success")
    logout_user()
    return redirect(url_for('signup'))


# -------- Run --------


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
