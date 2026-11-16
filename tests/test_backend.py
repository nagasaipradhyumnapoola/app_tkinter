from datetime import date, datetime, timedelta
from pathlib import Path
import csv
import sqlite3
import tempfile
import unittest

from backend import Countdown, Repository, daily_plan, seed_demo


class StudyPilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.repo = Repository(self.path)
        self.today = date(2026, 11, 16)

    def tearDown(self):
        self.repo.close()
        self.temp.cleanup()

    def add(self, name="Joins", days=3, confidence=2, minutes=60):
        return self.repo.save_topic("Databases", name, (self.today + timedelta(days=days)).isoformat(), minutes, confidence)

    def test_validation_duplicates_and_parameterized_names(self):
        for values in [("", "Topic", "2026-11-20", 60, 3), ("S", "T", "2026-02-30", 60, 3),
                       ("S", "T", "2026-11-20", "oops", 3), ("S", "T", "2026-11-20", 2, 3)]:
            with self.assertRaises(ValueError):
                self.repo.save_topic(*values)
        topic_id = self.add("O'Brien's joins")
        with self.assertRaises(ValueError):
            self.add("O'Brien's joins")
        self.assertEqual(self.repo.topics()[0]["id"], topic_id)

    def test_plan_prioritizes_urgent_weak_topics_and_respects_budget(self):
        urgent = self.add("Joins", 1, 1, 60)
        self.add("Indexes", 15, 5, 60)
        plan = daily_plan(self.repo.topics(), 45, self.today)
        self.assertEqual(plan[0].topic_id, urgent)
        self.assertEqual(sum(p.minutes for p in plan), 45)
        self.assertTrue(all(0 < p.minutes <= 25 for p in plan))
        with self.assertRaises(ValueError):
            daily_plan(self.repo.topics(), -5, self.today)

    def test_planner_never_overallocates_and_excludes_completed_topics(self):
        first = self.add(minutes=10)
        second = self.add("Indexes", minutes=5)
        self.repo.set_completed(second, True)
        plan = daily_plan(self.repo.topics(), 90, self.today)
        self.assertEqual(sum(p.minutes for p in plan), 10)
        self.assertEqual({p.topic_id for p in plan}, {first})

    def test_saved_session_changes_confidence_and_schedules_revision(self):
        topic_id = self.add(minutes=5)
        self.repo.log_session(topic_id, 300, 1, at=datetime(2026, 11, 16, 15))
        topic = self.repo.topics()[0]
        self.assertEqual(topic["confidence"], 1)
        self.assertEqual(topic["review_on"], "2026-11-17")
        self.assertEqual(daily_plan(self.repo.topics(), 30, self.today), [])
        plan = daily_plan(self.repo.topics(), 30, self.today + timedelta(days=1))
        self.assertEqual(sum(p.minutes for p in plan), 15)
        self.assertIn("Revision due", plan[0].reason)

    def test_invalid_session_is_not_saved(self):
        topic_id = self.add()
        with self.assertRaises(ValueError):
            self.repo.log_session(topic_id, 0, 3)
        self.assertEqual(self.repo.sessions(), [])
        self.assertEqual(self.repo.topics()[0]["studied_seconds"], 0)

    def test_delete_preserves_history_and_reopen_preserves_data(self):
        topic_id = self.add()
        self.repo.log_session(topic_id, 90, 4)
        self.repo.set_budget(120)
        self.repo.delete_topic(topic_id)
        self.repo.close()
        self.repo = Repository(self.path)
        self.assertEqual(self.repo.topics(), [])
        self.assertEqual(self.repo.sessions()[0]["topic_title"], "Joins")
        self.assertIsNone(self.repo.sessions()[0]["topic_id"])
        self.assertEqual(self.repo.budget(), 120)

    def test_edit_changes_only_selected_topic(self):
        first, second = self.add(), self.add("Indexes")
        self.repo.save_topic("Python", "Classes", "2026-12-01", 30, 4, topic_id=first)
        topics = {t["id"]: t for t in self.repo.topics()}
        self.assertEqual(topics[first]["title"], "Classes")
        self.assertEqual(topics[second]["title"], "Indexes")

    def test_export_and_backup(self):
        topic_id = self.add("=malicious formula")
        self.repo.log_session(topic_id, 73, 4)
        output = Path(self.temp.name) / "sessions.csv"
        self.repo.export_csv(output)
        with output.open(encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(rows[0]["seconds"], "73")
        self.assertTrue(rows[0]["topic_title"].startswith("'="))
        backup = Path(self.temp.name) / "backup.sqlite3"
        self.repo.backup(backup)
        other = Repository(backup)
        self.assertEqual(len(other.sessions()), 1)
        other.close()
        with self.assertRaises(ValueError):
            self.repo.backup(self.path)

    def test_demo_seeds_once_and_normal_database_starts_empty(self):
        self.assertEqual(self.repo.topics(), [])
        seed_demo(self.repo)
        seed_demo(self.repo)
        self.assertEqual(len(self.repo.topics()), 5)
        self.assertEqual(len(self.repo.sessions()), 6)

    def test_countdown_pauses_without_drift(self):
        now = [0.0]
        timer = Countdown(lambda: now[0])
        timer.start(60)
        now[0] = 12.3
        timer.pause()
        now[0] = 100
        self.assertAlmostEqual(timer.elapsed, 12.3)
        timer.resume()
        now[0] = 105.7
        self.assertAlmostEqual(timer.elapsed, 18)
        now[0] = 200
        self.assertEqual(timer.remaining, 0)
        self.assertEqual(timer.elapsed, 60)
        timer.reset()
        self.assertEqual(timer.elapsed, 0)


if __name__ == "__main__":
    unittest.main()
