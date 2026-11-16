"""Exercises real Tk widgets, callbacks and SQLite persistence on a desktop display."""
from datetime import date, timedelta
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import StudyPilot
from backend import Repository


def switch_tab(app, name):
    app.notebook.select(app.pages[name])
    app.update()


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "workflow.sqlite3"
        repo = Repository(path)
        app = StudyPilot(repo)
        app.update()
        assert app.plan == []
        assert str(app.start_button["state"]) == "disabled"
        assert "0" in app.metrics[0]["text"]

        # Add through the actual dialog. Invalid data must stay in the dialog.
        switch_tab(app, "Topics")
        win = app.topic_dialog()
        win.save_button.invoke()
        app.update()
        assert win.winfo_exists() and win.error_label["text"]
        for key, value in dict(subject="Python", title="Testing Tkinter", minutes="5", confidence="2",
                               exam_date=(date.today() + timedelta(days=2)).isoformat()).items():
            win.fields[key].set(value)
        win.save_button.invoke()
        app.update()
        assert len(repo.topics()) == 1
        assert len(app.plan) == 1 and app.plan[0].minutes == 5
        topic_id = repo.topics()[0]["id"]

        # Search and edit the same topic, not a duplicate.
        app.search_var.set("no matching topic")
        app.update()
        assert not app.topic_tree.get_children()
        app.search_var.set("tkinter")
        app.update()
        win = app.edit_selected()
        win.fields["title"].set("Tkinter events")
        win.save_button.invoke()
        app.update()
        assert repo.topics()[0]["title"] == "Tkinter events"
        app.search_var.set("")

        # Real countdown callbacks use a controlled clock so this test never waits minutes.
        clock = [100.0]
        app.timer.clock = lambda: clock[0]
        switch_tab(app, "Today")
        app.start_button.invoke()
        clock[0] += 12
        app.start_button.invoke()
        assert app.timer.elapsed == 12 and not app.timer.running
        clock[0] += 500
        assert app.timer.elapsed == 12
        app.start_button.invoke()
        clock[0] += 3
        win = app.finish_dialog()
        win.rating.set("4")
        win.save_button.invoke()
        app.update()
        assert len(repo.sessions()) == 1 and repo.sessions()[0]["seconds"] == 15
        assert repo.topics()[0]["confidence"] == 4
        assert app.metrics[1]["text"] == "1"
        assert not app.active_item

        # A timer reaching zero opens the save dialog without blocking the event loop.
        app.start_button.invoke()
        clock[0] += app.timer.duration + 1
        app.after_cancel(app.tick_job)
        app.tick()
        dialogs = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
        assert len(dialogs) == 1
        dialogs[0].rating.set("5")
        dialogs[0].done.set(True)
        dialogs[0].save_button.invoke()
        app.update()
        assert len(repo.sessions()) == 2 and repo.topics()[0]["completed"]
        assert not app.plan

        switch_tab(app, "Topics")
        app.complete_button.invoke()
        app.update()
        assert not repo.topics()[0]["completed"]
        # Essential controls remain visible at the supported minimum window size.
        app.geometry("900x650")
        app.update()
        for page_name, controls in [("Today", [app.today_add_button, app.plan_summary, app.reset_button]),
                                    ("Topics", [app.edit_button, app.complete_button, app.delete_button])]:
            app.show_page(page_name)
            app.update()
            page = app.pages[page_name]
            for control in controls:
                assert control.winfo_rooty() + control.winfo_height() <= page.winfo_rooty() + page.winfo_height(), control
        switch_tab(app, "Progress")
        app.update()
        assert len(app.history_tree.get_children()) == 2
        csv_path = Path(directory) / "history.csv"
        with patch("app.filedialog.asksaveasfilename", return_value=str(csv_path)):
            app.export_csv()
        assert csv_path.exists()
        backup_path = Path(directory) / "backup.sqlite3"
        with patch("app.filedialog.asksaveasfilename", return_value=str(backup_path)):
            app.backup()
        assert backup_path.exists()

        # Delete through its button, confirm, and keep the historical sessions.
        switch_tab(app, "Topics")
        with patch("app.messagebox.askyesno", return_value=True):
            app.delete_button.invoke()
        app.update()
        assert repo.topics() == [] and len(repo.sessions()) == 2
        app.close_app()

        # Reopen the full application against the same file.
        repo = Repository(path)
        app = StudyPilot(repo)
        app.update()
        assert len(repo.sessions()) == 2
        assert len(app.history_tree.get_children()) == 2
        assert not repo.topics()
        app.close_app()
    print("PASS: add, validation, search, edit, plan, pause/resume, early finish, timer completion,")
    print("rating, complete/reopen, history, CSV, backup, delete, and persistence after restart.")


if __name__ == "__main__":
    main()
