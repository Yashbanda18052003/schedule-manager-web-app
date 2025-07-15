# -------- All Your Original Imports --------
from flask import Flask, render_template, request, redirect, flash, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Schedule
from datetime import datetime, timedelta
from flask_mail import Mail, Message
from flask_apscheduler import APScheduler

# -------- Flask Configuration --------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'yash_super_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# -------- Mail Configuration --------
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'schedulemanager.notify@gmail.com'
app.config['MAIL_PASSWORD'] = 'onnb yvoy bipm hhyh'  # Replace with your App Password
app.config['MAIL_DEFAULT_SENDER'] = 'schedulemanager.notify@gmail.com'

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

# -------- Reminder Email Function --------
def send_reminder_email(user_id, schedule_id):
    with app.app_context():
        user = User.query.get(user_id)
        schedule = Schedule.query.get(schedule_id)

        if not user or not schedule:
            print("❌ User or Schedule not found.")
            return

        subject = "⏰ Schedule Reminder from Schedule Manager"

        # Plain text version
        plain_body = f"""Hi {user.name},

This is a reminder for your schedule:

Title: {schedule.title}
Date: {schedule.date.strftime('%d %B %Y')}
Time: {schedule.time.strftime('%I:%M %p')}
Description: {schedule.description or 'No description provided.'}

-----
This is an automated reminder from Schedule Manager.
Please do not reply to this email."""

        # HTML version
        html_body = f"""
        <html>
            <body>
                <p>Hi {user.name},</p>
                <p>This is a reminder for your schedule:</p>
                <ul>
                    <li><strong>Title:</strong> {schedule.title}</li>
                    <li><strong>Date:</strong> {schedule.date.strftime('%d %B %Y')}</li>
                    <li><strong>Time:</strong> {schedule.time.strftime('%I:%M %p')}</li>
                    <li><strong>Description:</strong> {schedule.description or 'No description provided.'}</li>
                </ul>
                <hr>
                <p style="font-size: small; color: gray;">
                    This is an automated reminder from <strong>Schedule Manager App</strong>.<br>
                    Please do not reply to this email.
                </p>
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
            print(f"✅ Reminder sent to {user.email} for schedule '{schedule.title}'")
        except Exception as e:
            print(f"❌ Failed to send reminder: {e}")

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
            schedule_datetime = datetime.combine(date, time) - timedelta(minutes=1)
            job_id = f"reminder_{schedule.id}"

            scheduler.add_job(
                func=send_reminder_email,
                trigger='date',
                run_date=schedule_datetime,
                args=[current_user.id, schedule.id],
                id=job_id,
                replace_existing=True
            )
            print(f"✅ Reminder job scheduled at {schedule_datetime}")

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
        flash("✅ Schedule updated successfully!", "success")
        return redirect(url_for('view_schedules'))

    return render_template('edit_schedule.html', schedule=schedule)

@app.route('/schedule/delete/<int:schedule_id>', methods=['POST'])
@login_required
def delete_schedule(schedule_id):
    schedule = Schedule.query.filter_by(id=schedule_id, user_id=current_user.id).first()
    if schedule:
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
    app.run(debug=True)
