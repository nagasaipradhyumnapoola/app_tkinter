"""Storage, planning rules, and timer state. Uses only the Python standard library."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import csv
import math
import sqlite3
import time


def validate_topic(subject, title, exam_date, minutes, confidence):
    subject, title = subject.strip(), title.strip()
    if not subject or not title:
        raise ValueError("Enter both a subject and a topic name.")
    if len(subject) > 60 or len(title) > 100:
        raise ValueError("Use up to 60 characters for a subject and 100 for a topic.")
    try:
        parsed = date.fromisoformat(exam_date)
        if parsed.isoformat() != exam_date:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("Enter the exam date as YYYY-MM-DD, for example 2026-12-10.") from None
    try:
        minutes, confidence = int(minutes), int(confidence)
    except (ValueError, TypeError):
        raise ValueError("Study time and confidence must be whole numbers.") from None
    if not 5 <= minutes <= 1200:
        raise ValueError("Estimated study time must be between 5 and 1,200 minutes.")
    if not 1 <= confidence <= 5:
        raise ValueError("Confidence must be between 1 and 5.")
    return subject, title, exam_date, minutes, confidence


class Repository:
    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY, subject TEXT NOT NULL COLLATE NOCASE,
                title TEXT NOT NULL COLLATE NOCASE, exam_date TEXT NOT NULL,
                minutes INTEGER NOT NULL CHECK(minutes BETWEEN 5 AND 1200),
                confidence INTEGER NOT NULL CHECK(confidence BETWEEN 1 AND 5),
                review_on TEXT, completed INTEGER NOT NULL DEFAULT 0,
                UNIQUE(subject, title)
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY,
                topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
                subject TEXT NOT NULL, topic_title TEXT NOT NULL,
                seconds INTEGER NOT NULL CHECK(seconds > 0),
                confidence INTEGER NOT NULL CHECK(confidence BETWEEN 1 AND 5),
                completed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)

    def topics(self):
        return [dict(r) for r in self.db.execute("""
            SELECT t.*, COALESCE(SUM(s.seconds), 0) AS studied_seconds
            FROM topics t LEFT JOIN sessions s ON s.topic_id = t.id
            GROUP BY t.id ORDER BY t.completed, t.exam_date, t.title
        """)]

    def save_topic(self, subject, title, exam_date, minutes, confidence, topic_id=None):
        values = validate_topic(subject, title, exam_date, minutes, confidence)
        try:
            with self.db:
                if topic_id is None:
                    return self.db.execute("""INSERT INTO topics
                        (subject,title,exam_date,minutes,confidence) VALUES (?,?,?,?,?)""", values).lastrowid
                cursor = self.db.execute("""UPDATE topics SET subject=?,title=?,exam_date=?,
                    minutes=?,confidence=? WHERE id=?""", (*values, topic_id))
                if not cursor.rowcount:
                    raise ValueError("This topic no longer exists.")
                return topic_id
        except sqlite3.IntegrityError:
            raise ValueError("That subject already has a topic with this name.") from None

    def delete_topic(self, topic_id):
        with self.db:
            self.db.execute("DELETE FROM topics WHERE id=?", (topic_id,))

    def set_completed(self, topic_id, completed):
        with self.db:
            self.db.execute("UPDATE topics SET completed=? WHERE id=?", (int(completed), topic_id))

    def sessions(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM sessions ORDER BY completed_at DESC, id DESC")]

    def log_session(self, topic_id, seconds, confidence, completed=False, at=None):
        seconds, confidence = int(seconds), int(confidence)
        if seconds < 1 or not 1 <= confidence <= 5:
            raise ValueError("Study for at least one second and choose a confidence rating from 1 to 5.")
        topic = self.db.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()
        if topic is None:
            raise ValueError("This topic no longer exists.")
        at = at or datetime.now().astimezone()
        review = at.date() + timedelta(days=(1, 2, 4, 7, 14)[confidence - 1])
        with self.db:
            self.db.execute("""INSERT INTO sessions
                (topic_id,subject,topic_title,seconds,confidence,completed_at) VALUES (?,?,?,?,?,?)""",
                (topic_id, topic["subject"], topic["title"], seconds, confidence, at.isoformat(timespec="seconds")))
            self.db.execute("UPDATE topics SET confidence=?,review_on=?,completed=? WHERE id=?",
                            (confidence, review.isoformat(), int(completed), topic_id))

    def budget(self):
        row = self.db.execute("SELECT value FROM settings WHERE key='budget'").fetchone()
        return int(row[0]) if row else 90

    def set_budget(self, minutes):
        try:
            minutes = int(minutes)
        except (ValueError, TypeError):
            raise ValueError("Daily study time must be a whole number from 5 to 480.") from None
        if not 5 <= minutes <= 480:
            raise ValueError("Daily study time must be between 5 and 480 minutes.")
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO settings VALUES ('budget',?)", (str(minutes),))

    def export_csv(self, path):
        rows = self.sessions()
        fields = ("completed_at", "subject", "topic_title", "seconds", "confidence")
        with open(path, "w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                safe = dict(row)
                for field in ("subject", "topic_title"):
                    if safe[field].startswith(("=", "+", "-", "@")):
                        safe[field] = "'" + safe[field]
                writer.writerow(safe)

    def backup(self, path):
        if Path(path).resolve() == Path(self.path).resolve():
            raise ValueError("Choose a different file for your backup.")
        target = sqlite3.connect(path)
        try:
            self.db.backup(target)
        finally:
            target.close()

    def close(self):
        self.db.close()


@dataclass(frozen=True)
class PlanItem:
    topic_id: int
    subject: str
    title: str
    minutes: int
    reason: str


def daily_plan(topics, budget, today=None):
    """Rank urgent/weak topics, then allocate <=25-minute blocks in rounds.

    Budget means study time still available today. It excludes breaks.
    Completed topics are excluded. Fully studied topics return only when review is due.
    """
    today = today or date.today()
    budget = int(budget)
    if not 5 <= budget <= 480:
        raise ValueError("Daily study time must be between 5 and 480 minutes.")
    candidates = []
    for topic in topics:
        if topic["completed"]:
            continue
        days = (date.fromisoformat(topic["exam_date"]) - today).days
        due = topic["review_on"] and date.fromisoformat(topic["review_on"]) <= today
        remaining = max(0, math.ceil((topic["minutes"] * 60 - topic["studied_seconds"]) / 60))
        if not remaining and not due:
            continue
        remaining = remaining or 15
        score = 40 / (max(0, days) + 1) + (6 - topic["confidence"]) * 5 + (20 if due else 0)
        deadline = "Exam overdue" if days < 0 else "Exam today" if days == 0 else f"Exam in {days} days"
        reason = f"{'Revision due' if due else deadline}\nConfidence {topic['confidence']}/5"
        candidates.append([score, topic, remaining, reason])
    candidates.sort(key=lambda entry: (-entry[0], entry[1]["exam_date"], entry[1]["id"]))
    result = []
    while budget > 0 and any(c[2] for c in candidates):
        for entry in candidates:
            _, topic, remaining, reason = entry
            if remaining <= 0 or budget <= 0:
                continue
            allocated = min(25, remaining, budget)
            result.append(PlanItem(topic["id"], topic["subject"], topic["title"], allocated, reason))
            entry[2] -= allocated
            budget -= allocated
    return result


class Countdown:
    """Monotonic clock prevents drift and excludes time spent paused."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.duration = 0
        self.accumulated = 0.0
        self.started_at = None

    @property
    def running(self):
        return self.started_at is not None

    @property
    def elapsed(self):
        value = self.accumulated + (self.clock() - self.started_at if self.running else 0)
        return min(self.duration, max(0.0, value))

    @property
    def remaining(self):
        return max(0, math.ceil(self.duration - self.elapsed))

    def start(self, seconds):
        self.duration, self.accumulated = int(seconds), 0.0
        self.started_at = self.clock()

    def pause(self):
        if self.running:
            self.accumulated = self.elapsed
            self.started_at = None

    def resume(self):
        if not self.running and self.remaining:
            self.started_at = self.clock()

    def reset(self):
        self.duration, self.accumulated, self.started_at = 0, 0.0, None


def seed_demo(repo):
    """Explicit demo data only; normal startup is empty."""
    if repo.topics() or repo.sessions():
        return
    today = date.today()
    examples = [
        ("Database systems", "SQL joins", 3, 90, 2),
        ("Python", "Classes & objects", 5, 75, 3),
        ("Data structures", "Trees & traversal", 7, 80, 2),
        ("Mathematics", "Probability", 10, 60, 4),
        ("Python", "Files & exceptions", 5, 45, 4),
    ]
    ids = [repo.save_topic(subject, title, (today + timedelta(days=days)).isoformat(), minutes, confidence)
           for subject, title, days, minutes, confidence in examples]
    for ago, index, minutes, confidence in [(6, 1, 20, 3), (5, 3, 25, 4), (4, 2, 15, 2),
                                           (3, 0, 20, 2), (2, 4, 25, 4), (1, 1, 25, 3)]:
        at = datetime.combine(today - timedelta(days=ago), datetime.min.time()).replace(hour=17).astimezone()
        repo.log_session(ids[index], minutes * 60, confidence, at=at)
    repo.set_budget(90)
