from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import os
import sqlite3

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    email = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))

    mobile = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    dob = db.Column(db.Date, nullable=True)

    # Relation to Schedule
    schedules = db.relationship('Schedule', backref='user', lazy=True, cascade='all, delete-orphan')


class Schedule(db.Model):
    __tablename__ = 'schedule'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    reminder = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Enhanced Fields
    priority = db.Column(db.String(20), default='medium')          # high, medium, low
    category = db.Column(db.String(50), default='general')         # work, personal, study, health, finance, general
    status = db.Column(db.String(20), default='pending')           # pending, completed
    reminder_offset = db.Column(db.String(20), default='1_day')    # 10_min, 1_hour, 1_day, 1_week
    is_recurring = db.Column(db.String(20), default='none')        # none, daily, weekly, monthly
    completed_at = db.Column(db.DateTime, nullable=True)

    # Foreign Key to User
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


def check_and_upgrade_db(app):
    """Ensures all modern schema columns exist in SQLite without data loss."""
    with app.app_context():
        db.create_all()
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        if os.path.exists(db_path):
            con = sqlite3.connect(db_path)
            cur = con.cursor()
            cur.execute("PRAGMA table_info(schedule)")
            existing = [r[1] for r in cur.fetchall()]
            new_cols = [
                ('priority', "TEXT DEFAULT 'medium'"),
                ('category', "TEXT DEFAULT 'general'"),
                ('status', "TEXT DEFAULT 'pending'"),
                ('reminder_offset', "TEXT DEFAULT '1_day'"),
                ('is_recurring', "TEXT DEFAULT 'none'"),
                ('completed_at', "DATETIME")
            ]
            for col, col_def in new_cols:
                if col not in existing:
                    cur.execute(f"ALTER TABLE schedule ADD COLUMN {col} {col_def}")
            con.commit()
            con.close()
