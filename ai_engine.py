"""
ai_engine.py
============
PlanPulse AI — Intelligent Schedule & Productivity Engine.
Provides:
  1. Natural Language Task Parsing (NLP extraction of title, date, time, category, priority, reminder)
  2. Smart Goal Decomposer (breaks large objectives into scheduled actionable milestones)
  3. Daily Briefing & Workload Analyzer
  4. Schedule Conflict Detector & Buffer Gap Advisor
  5. Interactive AI Productivity Coach
"""

import re
from datetime import datetime, date, time, timedelta
import os
import json
import urllib.request
import urllib.error

# Supported categories and priorities
CATEGORIES = ['work', 'personal', 'study', 'health', 'finance', 'general']
PRIORITIES = ['high', 'medium', 'low']
REMINDER_OFFSETS = ['10_min', '1_hour', '1_day', '1_week']

WEEKDAYS = {
    'monday': 0, 'mon': 0,
    'tuesday': 1, 'tue': 1, 'tues': 1,
    'wednesday': 2, 'wed': 2,
    'thursday': 3, 'thu': 3, 'thur': 3, 'thurs': 3,
    'friday': 4, 'fri': 4,
    'saturday': 5, 'sat': 5,
    'sunday': 6, 'sun': 6
}


def _clean_str(text):
    return re.sub(r'\s+', ' ', text).strip()


def parse_natural_language_schedule(prompt, reference_date=None):
    """
    Parses natural language text into a structured schedule dictionary:
    {
       'title': str,
       'date': 'YYYY-MM-DD',
       'time': 'HH:MM',
       'category': 'work'|'personal'|'study'|'health'|'finance'|'general',
       'priority': 'high'|'medium'|'low',
       'reminder_offset': '10_min'|'1_hour'|'1_day'|'1_week',
       'description': str,
       'confidence': float
    }
    """
    if not prompt or not prompt.strip():
        return None

    if reference_date is None:
        ref_dt = datetime.now()
    else:
        ref_dt = datetime.combine(reference_date, datetime.min.time())

    text = prompt.strip()
    lower = text.lower()

    # 1. Detect Category
    category = 'general'
    category_scores = {
        'work': ['work', 'meeting', 'client', 'project', 'presentation', 'deadline', 'boss', 'standup', 'interview', 'review', 'sprint', 'office'],
        'study': ['study', 'exam', 'homework', 'assignment', 'lecture', 'class', 'course', 'quiz', 'test', 'research', 'read', 'math', 'python', 'learn'],
        'health': ['gym', 'workout', 'doctor', 'dentist', 'run', 'walk', 'diet', 'yoga', 'hospital', 'medicine', 'checkup', 'fitness'],
        'finance': ['bill', 'pay', 'tax', 'bank', 'invest', 'budget', 'salary', 'invoice', 'credit card', 'rent', 'expense'],
        'personal': ['birthday', 'party', 'dinner', 'lunch', 'family', 'friend', 'movie', 'shopping', 'haircut', 'vacation', 'trip']
    }
    for cat, keywords in category_scores.items():
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', lower):
                category = cat
                break
        if category != 'general':
            break

    # 2. Detect Priority
    priority = 'medium'
    if re.search(r'\b(urgent|critical|high priority|asap|important|emergency)\b', lower):
        priority = 'high'
    elif re.search(r'\b(low priority|minor|relaxed|whenever|optional|low)\b', lower):
        priority = 'low'
    elif re.search(r'\b(medium priority|moderate|normal)\b', lower):
        priority = 'medium'

    # 3. Detect Reminder Offset
    reminder_offset = '1_day'
    if re.search(r'\b(10 mins?|10 minutes?|10m)\b', lower):
        reminder_offset = '10_min'
    elif re.search(r'\b(1 hour|an hour|1h|60 mins?)\b', lower):
        reminder_offset = '1_hour'
    elif re.search(r'\b(1 day|a day|24 hours?|tomorrow before)\b', lower):
        reminder_offset = '1_day'
    elif re.search(r'\b(1 week|a week|7 days?)\b', lower):
        reminder_offset = '1_week'

    # 4. Detect Date
    target_date = ref_dt.date()
    date_matched_str = ""

    # "today"
    if re.search(r'\btoday\b', lower):
        target_date = ref_dt.date()
        date_matched_str = "today"
    # "tomorrow"
    elif re.search(r'\btomorrow\b', lower):
        target_date = (ref_dt + timedelta(days=1)).date()
        date_matched_str = "tomorrow"
    # "day after tomorrow"
    elif re.search(r'\bday after tomorrow\b', lower):
        target_date = (ref_dt + timedelta(days=2)).date()
        date_matched_str = "day after tomorrow"
    # "in X days"
    elif m := re.search(r'\bin (\d+) days?\b', lower):
        days = int(m.group(1))
        target_date = (ref_dt + timedelta(days=days)).date()
        date_matched_str = m.group(0)
    # "next <weekday>" or "on <weekday>" or just "<weekday>"
    elif m := re.search(r'\b(next\s+|on\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b', lower):
        day_word = m.group(2)
        target_weekday = WEEKDAYS.get(day_word)
        if target_weekday is not None:
            current_weekday = ref_dt.weekday()
            days_ahead = (target_weekday - current_weekday) % 7
            if days_ahead == 0:
                days_ahead = 7  # Next week if same day
            if 'next' in m.group(0) and days_ahead < 7:
                days_ahead += 7
            target_date = (ref_dt + timedelta(days=days_ahead)).date()
            date_matched_str = m.group(0)
    # Specific date e.g. "25th Oct", "15 November", "2026-11-05", "12/10/2026"
    elif m := re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:\s+(\d{4}))?\b', lower):
        day = int(m.group(1))
        month_str = m.group(2)[:3]
        year = int(m.group(3)) if m.group(3) else ref_dt.year
        months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
        month = months.index(month_str) + 1
        try:
            target_date = date(year, month, day)
            date_matched_str = m.group(0)
        except ValueError:
            target_date = ref_dt.date()

    # 5. Detect Time
    target_time = time(9, 0)  # default 9:00 AM
    time_matched_str = ""

    # "at 4:30 pm", "4:30pm", "4pm", "at 14:00"
    if m := re.search(r'\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', lower):
        hr = int(m.group(1))
        mn = int(m.group(2)) if m.group(2) else 0
        ampm = m.group(3)
        if ampm == 'pm' and hr < 12:
            hr += 12
        elif ampm == 'am' and hr == 12:
            hr = 0
        target_time = time(hr, mn)
        time_matched_str = m.group(0)
    elif m := re.search(r'\b(?:at\s+)(\d{1,2}):(\d{2})\b', lower):
        hr = int(m.group(1))
        mn = int(m.group(2))
        if 0 <= hr <= 23 and 0 <= mn <= 59:
            target_time = time(hr, mn)
            time_matched_str = m.group(0)
    elif re.search(r'\b(morning|in the morning)\b', lower):
        target_time = time(9, 0)
        time_matched_str = "morning"
    elif re.search(r'\b(afternoon|in the afternoon)\b', lower):
        target_time = time(14, 0)
        time_matched_str = "afternoon"
    elif re.search(r'\b(evening|in the evening)\b', lower):
        target_time = time(18, 0)
        time_matched_str = "evening"
    elif re.search(r'\b(night|tonight|at night)\b', lower):
        target_time = time(20, 0)
        time_matched_str = "night"

    # 6. Extract Clean Title
    clean_title = text
    # Strip detected patterns from the title string
    remove_patterns = [
        r'\b(?:at|on|for|by|in)\s+' + re.escape(time_matched_str) if time_matched_str else '',
        re.escape(time_matched_str) if time_matched_str else '',
        r'\b(?:at|on|for|by|in)\s+' + re.escape(date_matched_str) if date_matched_str else '',
        re.escape(date_matched_str) if date_matched_str else '',
        r'\b(high|medium|low)\s+priority\b',
        r'\b(urgent|critical|asap|important)\b',
        r'\b(work|personal|study|health|finance|general)\s+category\b',
        r'\breminder\s+(?:in\s+)?(10\s*mins?|1\s*hour|1\s*day|1\s*week|before)\b',
        r'\b(schedule|add|set\s+a\s+reminder\s+for|remind\s+me\s+to|task:?)\b'
    ]
    for pat in remove_patterns:
        if pat:
            clean_title = re.sub(pat, '', clean_title, flags=re.IGNORECASE)

    clean_title = re.sub(r'^[,\-\s:;.]+|[,\-\s:;.]+$', '', clean_title).strip()
    # Strip dangling trailing prepositions like 'with in', 'with', 'in', 'on', 'for', 'at'
    clean_title = re.sub(r'\b(with\s+in|with|in|on|for|at|by|from|and|to)\s*$', '', clean_title, flags=re.IGNORECASE).strip()
    clean_title = re.sub(r'^[,\-\s:;.]+|[,\-\s:;.]+$', '', clean_title).strip()
    clean_title = _clean_str(clean_title)

    if not clean_title or len(clean_title) < 3:
        clean_title = text[:50]  # Fallback

    # Capitalize first letter
    clean_title = clean_title[0].upper() + clean_title[1:] if len(clean_title) > 1 else clean_title.upper()

    return {
        'title': clean_title,
        'date': target_date.strftime('%Y-%m-%d'),
        'time': target_time.strftime('%H:%M'),
        'category': category,
        'priority': priority,
        'reminder_offset': reminder_offset,
        'description': f"Auto-scheduled with PlanPulse AI Assistant from prompt: \"{text}\"",
        'confidence': 0.95
    }


def breakdown_goal_into_schedules(goal_title, target_deadline=None, category='work'):
    """
    Decomposes a major goal/project into 3-4 structured, scheduled milestones.
    """
    now = datetime.now()
    if target_deadline:
        try:
            deadline_date = datetime.strptime(target_deadline, '%Y-%m-%d').date()
        except Exception:
            deadline_date = (now + timedelta(days=14)).date()
    else:
        deadline_date = (now + timedelta(days=14)).date()

    total_days = max((deadline_date - now.date()).days, 4)

    # Goal category mapping templates
    lower = goal_title.lower()
    if any(k in lower for k in ['study', 'exam', 'course', 'learn', 'python', 'book', 'test']):
        milestones = [
            ("Core Theory & Concept Review", 0.15, "high", "study", "09:30", "Deep dive into foundational principles, textbooks, and syllabus mapping."),
            ("Practical Hands-On Exercises & Labs", 0.45, "high", "study", "14:00", "Build prototype exercises, solve practice tests, and code implementation."),
            ("Mock Testing & Knowledge Audit", 0.75, "medium", "study", "11:00", "Simulate timed testing environment, identify weak concepts, and review."),
            ("Final Rehearsal & Exam Readiness", 0.95, "high", "study", "16:00", "Final review of cheat sheets, summary points, and rest before execution.")
        ]
    elif any(k in lower for k in ['launch', 'project', 'website', 'app', 'client', 'release', 'software']):
        milestones = [
            ("Requirements & Architecture Blueprint", 0.15, "high", "work", "10:00", "Define MVP scope, functional specifications, and technical milestones."),
            ("Core Feature Implementation & Integration", 0.45, "high", "work", "14:00", "Code main features, integrate APIs, and run internal sanity checks."),
            ("Quality Assurance & User Testing", 0.75, "medium", "work", "15:30", "Perform end-to-end regression testing, fix UI/UX bugs, and verify responsive design."),
            ("Deployment, Public Launch & Announce", 0.95, "high", "work", "11:00", "Deploy production build, monitor analytics, and share announcement updates.")
        ]
    elif any(k in lower for k in ['gym', 'fitness', 'weight', 'health', 'marathon', 'run', 'diet']):
        milestones = [
            ("Fitness Assessment & Baseline Setup", 0.10, "medium", "health", "07:00", "Record initial metrics, calculate nutrition macros, and outline weekly split."),
            ("Strength & Conditioning Phase 1", 0.40, "high", "health", "07:30", "Execute fundamental compound training sessions with proper recovery."),
            ("Mid-Cycle Endurance & Metric Review", 0.70, "medium", "health", "08:00", "Track body composition progress, adjust intensity, and calibrate nutrition."),
            ("Peak Performance Milestone & Goal Check", 0.95, "high", "health", "07:00", "Evaluate target achievement against baseline metrics.")
        ]
    elif any(k in lower for k in ['tax', 'budget', 'invest', 'saving', 'finance', 'audit', 'money']):
        milestones = [
            ("Financial Records & Document Collection", 0.20, "high", "finance", "11:00", "Gather bank statements, invoices, deductible receipts, and accounts."),
            ("Expense Audit & Budget Allocation", 0.50, "medium", "finance", "14:00", "Categorize outgoing spend, eliminate leaks, and configure emergency reserves."),
            ("Investment & Tax Optimization Review", 0.80, "high", "finance", "15:00", "Review tax-saving instruments, investment diversification, and portfolios."),
            ("Final Reconciliation & Compliance Filing", 0.95, "high", "finance", "10:30", "Submit filings, confirm payments, and archive documentation safely.")
        ]
    else:
        milestones = [
            (f"Phase 1: Research & Planning for {goal_title}", 0.15, "medium", category, "10:00", "Gather initial requirements, outline key steps, and set boundaries."),
            (f"Phase 2: Execution & Core Work on {goal_title}", 0.50, "high", category, "14:00", "Focus deep work sessions on core deliverables and unblock issues."),
            (f"Phase 3: Review, Polish & Refinements", 0.80, "medium", category, "16:00", "Review progress against expectations, polish quality, and verify details."),
            (f"Phase 4: Completion & Final Deliverable", 0.95, "high", category, "11:00", "Finalize all items, celebrate achievement, and document next steps.")
        ]

    results = []
    for title, ratio, prio, cat, time_str, desc in milestones:
        offset_days = int(total_days * ratio)
        m_date = (now + timedelta(days=offset_days)).date()
        results.append({
            'title': title,
            'date': m_date.strftime('%Y-%m-%d'),
            'time': time_str,
            'category': cat,
            'priority': prio,
            'reminder_offset': '1_day',
            'description': desc
        })

    return results


def detect_schedule_conflicts(schedules):
    """
    Scans a list of schedule objects/dicts for overlapping times or tight buffers
    (< 30 minutes apart on the same date).
    Returns a list of conflict notices:
    [
      {
         'date': 'YYYY-MM-DD',
         'schedule_id_1': int,
         'schedule_id_2': int,
         'title_1': str,
         'title_2': str,
         'time_1': str,
         'time_2': str,
         'severity': 'overlap'|'tight_buffer',
         'message': str,
         'recommended_fix': str
      }
    ]
    """
    conflicts = []
    # Group by date
    by_date = {}
    for s in schedules:
        d = s.date.strftime('%Y-%m-%d') if hasattr(s.date, 'strftime') else str(s.date)
        by_date.setdefault(d, []).append(s)

    for d_str, day_items in by_date.items():
        if len(day_items) < 2:
            continue

        # Sort by time
        sorted_items = sorted(day_items, key=lambda x: x.time)
        for i in range(len(sorted_items) - 1):
            s1 = sorted_items[i]
            s2 = sorted_items[i + 1]

            t1_mins = s1.time.hour * 60 + s1.time.minute
            t2_mins = s2.time.hour * 60 + s2.time.minute
            diff = t2_mins - t1_mins

            if diff == 0:
                # Exact overlap
                conflicts.append({
                    'date': d_str,
                    'schedule_id_1': s1.id,
                    'schedule_id_2': s2.id,
                    'title_1': s1.title,
                    'title_2': s2.title,
                    'time_1': s1.time.strftime('%I:%M %p'),
                    'time_2': s2.time.strftime('%I:%M %p'),
                    'severity': 'overlap',
                    'message': f"Double Booking Alert: '{s1.title}' and '{s2.title}' are scheduled for the exact same time ({s1.time.strftime('%I:%M %p')}).",
                    'recommended_fix': f"Reschedule '{s2.title}' to {(s1.time.hour + 1) % 24:02d}:{s1.time.minute:02d} for a clean 60-minute window."
                })
            elif diff < 30:
                # Tight buffer
                conflicts.append({
                    'date': d_str,
                    'schedule_id_1': s1.id,
                    'schedule_id_2': s2.id,
                    'title_1': s1.title,
                    'title_2': s2.title,
                    'time_1': s1.time.strftime('%I:%M %p'),
                    'time_2': s2.time.strftime('%I:%M %p'),
                    'severity': 'tight_buffer',
                    'message': f"Tight Schedule: Only {diff} mins between '{s1.title}' and '{s2.title}'.",
                    'recommended_fix': f"Add a 15-minute buffer to avoid rush and mental fatigue."
                })

    return conflicts


def generate_daily_briefing(schedules, user_name="Productivity Champion"):
    """
    Generates a personalized daily briefing & workload assessment.
    """
    today = date.today()
    today_tasks = [s for s in schedules if (s.date == today if hasattr(s.date, 'year') else str(s.date) == today.strftime('%Y-%m-%d'))]
    pending_today = [s for s in today_tasks if getattr(s, 'status', 'pending') != 'completed']
    high_prio_today = [s for s in pending_today if getattr(s, 'priority', 'medium') == 'high']

    total_all = len(schedules)
    completed_all = sum(1 for s in schedules if getattr(s, 'status', 'pending') == 'completed')

    # Workload summary
    if len(today_tasks) == 0:
        headline = "Clear Runway Ahead 🌤️"
        assessment = "You have no scheduled tasks for today. It's a great opportunity to plan upcoming milestones, tackle deep learning, or relax!"
        energy_level = "Rest & Rejuvenation"
    elif len(today_tasks) <= 2:
        headline = "Light & Focused Pace 🎯"
        assessment = f"You have {len(today_tasks)} commitment(s) today. Easy to manage with plenty of deep-focus buffers."
        energy_level = "Moderate"
    elif len(today_tasks) <= 5:
        headline = "Steady Momentum 🚀"
        assessment = f"Balanced schedule with {len(today_tasks)} tasks ({len(high_prio_today)} high-priority). Prioritize the most critical item first before moving to afternoon tasks."
        energy_level = "High Focus"
    else:
        headline = "High-Intensity Command Day ⚡"
        assessment = f"Heavy schedule with {len(today_tasks)} tasks today! Be sure to take deliberate 5-minute breather breaks between events."
        energy_level = "Maximum Capacity"

    # Actionable tips
    tips = []
    if high_prio_today:
        tips.append(f"Tackle '<strong>{high_prio_today[0].title}</strong>' during your peak morning energy window.")
    else:
        tips.append("No urgent emergencies today—focus on steady task completion.")

    conflicts = detect_schedule_conflicts(schedules)
    if conflicts:
        tips.append(f"⚠️ PlanPulse AI detected <strong>{len(conflicts)} schedule conflict(s)</strong>. Review your calendar to space out events.")
    else:
        tips.append("Calendar spacing looks clean with zero overlapping time slots.")

    tips.append(f"Overall Progress: {completed_all}/{total_all} total tasks completed across all boards.")

    return {
        'headline': headline,
        'assessment': assessment,
        'energy_level': energy_level,
        'today_count': len(today_tasks),
        'pending_today_count': len(pending_today),
        'high_prio_count': len(high_prio_today),
        'tips': tips,
        'conflicts_count': len(conflicts)
    }


def ask_productivity_coach(question, schedules, user_name="User"):
    """
    Intelligent Productivity Coach assistant that answers schedule/productivity questions.
    """
    q_lower = question.lower()
    total = len(schedules)
    pending = sum(1 for s in schedules if getattr(s, 'status', 'pending') != 'completed')
    completed = total - pending

    # Check for Gemini API key
    gemini_key = os.environ.get('GEMINI_API_KEY')
    if gemini_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            headers = {'Content-Type': 'application/json'}
            task_summary = f"Total tasks: {total}, Pending: {pending}, Completed: {completed}. Active tasks: {', '.join([s.title for s in schedules[:5]])}"
            body = {
                "contents": [{
                    "parts": [{
                        "text": f"You are PlanPulse AI, a world-class productivity coach and executive time-management assistant for {user_name}. The user asks: '{question}'. Current workload: {task_summary}. Provide a concise, highly motivating, structured response with bullet points and practical advice (under 120 words)."
                    }]
                }]
            }
            req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'), headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=5) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                ans = res_data['candidates'][0]['content']['parts'][0]['text']
                return ans
        except Exception:
            pass  # Fall back smoothly to built-in reasoning engine

    # Built-in High-Accuracy Reasoning Engine
    if any(k in q_lower for k in ['prioritize', 'priority', 'what should i do', 'start']):
        high_prio = [s for s in schedules if getattr(s, 'status', 'pending') != 'completed' and getattr(s, 'priority', 'medium') == 'high']
        if high_prio:
            return (
                f"🎯 **Priority Blueprint for Today:**\n\n"
                f"1. **Eat the Frog First:** Start immediately with high-priority item **'{high_prio[0].title}'**.\n"
                f"2. **Use the 50/10 Rule:** Work in 50-minute uninterrupted sprints with 10-minute mental resets.\n"
                f"3. **Batch Small Items:** Bundle minor administrative tasks in the late afternoon when willpower dips."
            )
        else:
            return (
                f"✨ **Schedule Clarity:** You have no urgent high-priority fires right now! Pick your most impactful pending task and dedicate 45 minutes of deep focus to build momentum."
            )

    elif any(k in q_lower for k in ['break', 'burnout', 'tired', 'rest', 'exhausted']):
        return (
            f"🧠 **Burnout Prevention & Energy Recovery:**\n\n"
            f"• **The 90-Minute Rhythm:** Human ultradian rhythms cap peak attention at 90 minutes. Take a 15-minute walk without your phone.\n"
            f"• **Eye & Muscle Reset:** Apply the 20-20-20 rule (look 20 feet away for 20 seconds every 20 minutes).\n"
            f"• **Calendar Buffers:** Ensure at least 15-minute buffers between consecutive meetings."
        )

    elif any(k in q_lower for k in ['study', 'learn', 'memorize', 'exam']):
        return (
            f"📚 **Active Recall & Study Architecture:**\n\n"
            f"• **Feynman Technique:** Teach the concept out loud in simple terms as if explaining to a 10-year-old.\n"
            f"• **Interleaved Practice:** Alternate between two distinct subjects rather than cramming one for 4 hours.\n"
            f"• **Pomodoro Intervals:** 25 mins active retrieval, 5 mins break, repeat 4 times."
        )

    elif any(k in q_lower for k in ['motivation', 'procrastinat', 'lazy', 'stuck']):
        return (
            f"⚡ **Overcoming Inertia:**\n\n"
            f"• **The 2-Minute Rule:** Commit to working on your next schedule for just 120 seconds. Starting is 80% of the friction.\n"
            f"• **Friction Reduction:** Remove tabs, close email, and keep only your current task open.\n"
            f"• **Remember Your Record:** You have completed {completed} task(s) so far—keep the streak alive!"
        )

    else:
        return (
            f"🚀 **PlanPulse AI Executive Coaching:**\n\n"
            f"• You currently have **{pending} pending** tasks and **{completed} completed** milestones.\n"
            f"• **Key Advice:** Maintain ruthless focus on one deliverable at a time. Protect your morning calendar for creative work and reserve afternoons for meetings and communication."
        )
