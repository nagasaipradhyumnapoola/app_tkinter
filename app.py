"""StudyPilot: a complete, offline Tkinter mini-project."""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import logging
from pathlib import Path
import sqlite3
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from backend import Countdown, Repository, daily_plan, seed_demo

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def label(parent, text="", bold=False, **kwargs):
    if bold:
        kwargs["font"] = "TkHeadingFont"
    return tk.Label(parent, text=text, anchor="w", **kwargs)


def frame(parent, **kwargs):
    return tk.Frame(parent, **kwargs)


class StudyPilot(tk.Tk):
    def __init__(self, repository, demo=False):
        super().__init__()
        self.repo, self.demo = repository, demo
        self.timer = Countdown()
        self.active_item = None
        self.plan = []
        self.page = "Today"
        self.tick_job = None
        self.title("StudyPilot" + (" - Demo" if demo else ""))
        self.geometry("1080x720+40+42")
        self.minsize(900, 650)
        # Keep Tk's platform-default fonts, colours, scaling and ttk theme.
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self.bind("<Control-n>", lambda event: self.topic_dialog())
        self.build_shell()
        self.build_today()
        self.build_topics()
        self.build_progress()
        self.refresh()
        self.show_page("Today")
        self.tick()


    def build_shell(self):
        heading = frame(self)
        heading.pack(fill="x", padx=10, pady=8)
        label(heading, "StudyPilot", bold=True).pack(side="left")
        label(heading, "Sample data (demo)" if self.demo else "Personal study planner").pack(side="right")
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.pages = {}
        for name in ("Today", "Topics", "Progress"):
            page = frame(self.notebook, padx=10, pady=10)
            self.pages[name] = page
            self.notebook.add(page, text=name)
        self.notebook.bind("<<NotebookTabChanged>>", self.tab_changed)
        self.status_var = tk.StringVar(value="Ready. Your changes are saved automatically.")
        tk.Label(self, textvariable=self.status_var, anchor="w", relief="sunken", bd=1).pack(fill="x", side="bottom")

    def tab_changed(self, event=None):
        selected = self.notebook.select()
        if selected:
            self.page = self.notebook.tab(selected, "text")
            if self.page == "Topics" and hasattr(self, "topic_tree"):
                self.refresh_topics()
            elif self.page == "Progress" and hasattr(self, "history_tree"):
                self.refresh_progress()

    def page_header(self, page, title, subtitle=""):
        top = frame(page)
        top.pack(fill="x", pady=(0, 10))
        label(top, title, bold=True).pack(side="left")
        return top


    def make_tree(self, parent, columns, height=6):
        wrap = frame(parent)
        wrap.pack(fill="both", expand=True)
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        tree = ttk.Treeview(wrap, columns=[c[0] for c in columns], show="headings", height=height,
                            selectmode="browse")
        for key, name, width, anchor in columns:
            tree.heading(key, text=name, anchor=anchor)
            tree.column(key, width=width, minwidth=55, anchor=anchor,
                        stretch=key in ("topic", "why", "title"))
        vertical = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        return tree

    def build_today(self):
        page = self.pages["Today"]
        top = self.page_header(page, "Today's study plan")
        label(top, date.today().strftime("%A, %d %B %Y")).pack(side="right")
        self.finding = label(page, wraplength=820, justify="left")
        self.finding.pack(fill="x", pady=(0, 8))
        summary = tk.LabelFrame(page, text="Today", padx=10, pady=8)
        summary.pack(fill="x", pady=(0, 10))
        self.metrics = []
        for title in ("Focused today", "Sessions today", "Topics to work on"):
            cell = frame(summary)
            cell.pack(side="left", fill="x", expand=True)
            label(cell, title).pack(side="left", padx=(0, 8))
            value = label(cell, bold=True)
            value.pack(side="left")
            self.metrics.append(value)
        area = frame(page)
        area.pack(fill="both", expand=True)
        area.columnconfigure(0, weight=1)
        area.columnconfigure(1, minsize=225)
        area.rowconfigure(0, weight=1)
        left = tk.LabelFrame(area, text="Study plan", padx=8, pady=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        controls = frame(left)
        controls.pack(fill="x", pady=(0, 8))
        label(controls, "Time available:").pack(side="left")
        self.budget_var = tk.StringVar(value=str(self.repo.budget()))
        self.budget_entry = tk.Spinbox(controls, from_=5, to=480, increment=5, width=5,
                                        textvariable=self.budget_var)
        self.budget_entry.pack(side="left", padx=(6, 4))
        label(controls, "minutes").pack(side="left")
        self.replan_button = tk.Button(controls, text="Build plan", command=self.rebuild_plan)
        self.replan_button.pack(side="right")
        self.plan_tree = self.make_tree(left, [("topic", "Topic", 145, "w"),
            ("subject", "Subject", 100, "w"), ("time", "Time", 65, "e"),
            ("why", "Reason", 235, "w")], height=5)
        self.plan_tree.bind("<<TreeviewSelect>>", lambda event: self.update_focus())
        self.plan_empty = label(left, wraplength=500, justify="left")
        self.plan_empty.pack(fill="x", pady=6)
        self.plan_summary = label(left)
        self.plan_summary.pack(fill="x", pady=8)
        self.today_add_button = tk.Button(left, text="Add topic", command=self.topic_dialog)
        self.today_add_button.pack(anchor="w")
        focus = tk.LabelFrame(area, text="Focus session", padx=10, pady=10)
        focus.grid(row=0, column=1, sticky="new")
        self.focus_topic = label(focus, bold=True, wraplength=205, justify="left")
        self.focus_topic.pack(fill="x", pady=(0, 5))
        self.focus_subject = label(focus, wraplength=205)
        self.focus_subject.pack(fill="x")
        self.timer_label = tk.Label(focus, text="25:00", font="TkFixedFont", relief="sunken", bd=2, padx=12, pady=10)
        self.timer_label.pack(fill="x", pady=12)
        self.timer_progress = ttk.Progressbar(focus, mode="determinate")
        self.timer_progress.pack(fill="x", pady=(0, 8))
        self.timer_state = label(focus, "Ready when you are", wraplength=205)
        self.timer_state.pack(fill="x", pady=(0, 10))
        self.start_button = tk.Button(focus, text="Start focus", command=self.toggle_timer)
        self.start_button.pack(fill="x")
        self.finish_button = tk.Button(focus, text="Finish and rate", command=self.finish_dialog)
        self.finish_button.pack(fill="x", pady=6)
        self.reset_button = tk.Button(focus, text="Reset", command=self.reset_timer)
        self.reset_button.pack(fill="x")

    def build_topics(self):
        page = self.pages["Topics"]
        header = self.page_header(page, "Topics")
        self.add_topic_button = tk.Button(header, text="Add topic", command=self.topic_dialog)
        self.add_topic_button.pack(side="right")
        controls = frame(page)
        controls.pack(fill="x", pady=(0, 8))
        label(controls, "Search:").pack(side="left", padx=(0, 6))
        self.search_var = tk.StringVar()
        tk.Entry(controls, textvariable=self.search_var, width=30).pack(side="left")
        self.search_var.trace_add("write", lambda *args: self.refresh_topics())
        self.topic_count = label(controls)
        self.topic_count.pack(side="right")
        self.topic_tree = self.make_tree(page, [("title", "Topic", 180, "w"),
            ("subject", "Subject", 130, "w"), ("exam", "Exam date", 110, "e"),
            ("effort", "Time left", 90, "e"), ("confidence", "Confidence", 90, "e"),
            ("status", "Status", 110, "w")], height=8)
        self.topic_tree.bind("<Double-1>", lambda event: self.edit_selected())
        self.topic_empty = label(page)
        self.topic_empty.pack(fill="x", pady=6)
        actions = frame(page)
        actions.pack(fill="x", pady=8)
        self.edit_button = tk.Button(actions, text="Edit topic", command=self.edit_selected)
        self.edit_button.pack(side="left")
        self.complete_button = tk.Button(actions, text="Complete / reopen", command=self.toggle_completed)
        self.complete_button.pack(side="left", padx=6)
        self.delete_button = tk.Button(actions, text="Delete", command=self.delete_selected)
        self.delete_button.pack(side="right")
        label(page, "Confidence: 1 = needs practice, 5 = comfortable. Completed topics are excluded from the plan.").pack(fill="x")

    def build_progress(self):
        page = self.pages["Progress"]
        header = self.page_header(page, "Progress")
        tk.Button(header, text="Export CSV", command=self.export_csv).pack(side="right")
        self.progress_summary = label(page)
        self.progress_summary.pack(fill="x", pady=(0, 8))
        chart_frame = tk.LabelFrame(page, text="Focus time - last 7 days (minutes)", padx=6, pady=6)
        chart_frame.pack(fill="x", pady=(0, 10))
        self.chart = tk.Canvas(chart_frame, height=185)
        self.chart.pack(fill="x")
        self.chart.bind("<Configure>", lambda event: self.draw_chart())
        history = tk.LabelFrame(page, text="Session history", padx=6, pady=6)
        history.pack(fill="both", expand=True)
        self.history_tree = self.make_tree(history, [("topic", "Topic", 180, "w"),
            ("subject", "Subject", 130, "w"), ("date", "Date and time", 150, "e"),
            ("duration", "Focused", 110, "e"), ("rating", "Confidence", 90, "e")], height=4)
        self.history_empty = label(history)
        self.history_empty.pack(fill="x", pady=6)
        bottom = frame(page)
        bottom.pack(fill="x", pady=(8, 0))
        tk.Button(bottom, text="Back up data", command=self.backup).pack(side="left")
        label(bottom, "Only saved focus time appears here.").pack(side="right")

    def show_page(self, name):
        self.page = name
        self.notebook.select(self.pages[name])
        if name == "Progress":
            self.refresh_progress()
        elif name == "Topics":
            self.refresh_topics()

    def refresh(self):
        self.refresh_plan()
        self.refresh_topics()
        self.refresh_progress()

    def rebuild_plan(self):
        try:
            self.repo.set_budget(self.budget_var.get())
        except ValueError as error:
            messagebox.showerror("Check your study time", str(error), parent=self)
            return
        self.refresh_plan()
        self.status_var.set("Plan updated. Time available means study time you still have today; breaks are separate.")

    def refresh_plan(self):
        topics = self.repo.topics()
        self.plan = daily_plan(topics, self.repo.budget())
        self.plan_tree.delete(*self.plan_tree.get_children())
        for index, item in enumerate(self.plan):
            self.plan_tree.insert("", "end", iid=str(index), values=(item.title, item.subject, f"{item.minutes} min", item.reason.replace("\n", "; ")))
        if self.plan:
            self.plan_tree.selection_set("0")
            self.finding.configure(text=f"Start with {self.plan[0].title} — {self.plan[0].reason.replace(chr(10), ' · ').lower()}.")
            self.plan_empty.configure(text="")
            self.plan_empty.pack_forget()
        else:
            self.finding.configure(text="Make space for your next learning goal.")
            self.plan_empty.configure(text="You’re up to date. Add a topic, reopen one, or return when a revision is due."
                                      if topics else "Add your first topic to get a personalised study plan.")
            self.plan_empty.pack(fill="x", pady=(12, 0), before=self.plan_summary)
        allocated = sum(item.minutes for item in self.plan)
        self.plan_summary.configure(text=f"{len(self.plan)} focus blocks · {allocated} of {self.repo.budget()} min available planned")
        today = [s for s in self.repo.sessions() if s["completed_at"][:10] == date.today().isoformat()]
        values = (self.duration(sum(s["seconds"] for s in today)), str(len(today)),
                  str(sum(not t["completed"] for t in topics)))
        for widget, value in zip(self.metrics, values):
            widget.configure(text=value)
        self.update_focus()

    @staticmethod
    def duration(seconds):
        minutes, seconds = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours} h {minutes:02d} min" + (f" {seconds:02d} s" if seconds else "")
        return f"{minutes} min {seconds:02d} s" if seconds else f"{minutes} min"

    def selected_plan(self):
        selected = self.plan_tree.selection()
        return self.plan[int(selected[0])] if selected and int(selected[0]) < len(self.plan) else None

    def update_focus(self):
        item = self.active_item or self.selected_plan()
        self.focus_topic.configure(text=item.title if item else "Choose your first topic")
        self.focus_subject.configure(text=item.subject if item else "A focused session starts with a plan.")
        seconds = self.timer.remaining if self.active_item else item.minutes * 60 if item else 0
        minutes, seconds = divmod(seconds, 60)
        self.timer_label.configure(text=f"{minutes:02d}:{seconds:02d}")
        self.start_button.configure(text="Pause" if self.timer.running else "Resume" if self.active_item else "Start focus",
                                    state="normal" if item and (not self.active_item or self.timer.remaining) else "disabled")
        self.finish_button.configure(state="normal" if self.active_item and self.timer.elapsed >= 1 else "disabled")
        self.reset_button.configure(state="normal" if self.active_item else "disabled")
        self.timer_state.configure(text="Focusing — one topic at a time" if self.timer.running else
            "Session complete — save your rating" if self.active_item and not self.timer.remaining else
            "Paused — your time is kept" if self.active_item else "Ready when you are")
        self.timer_progress.configure(maximum=self.timer.duration or 1, value=self.timer.elapsed)

    def toggle_timer(self):
        if self.timer.running:
            self.timer.pause()
        elif self.active_item:
            self.timer.resume()
        else:
            self.active_item = self.selected_plan()
            if self.active_item:
                self.timer.start(self.active_item.minutes * 60)
        self.update_focus()

    def tick(self):
        if self.timer.running and self.timer.remaining == 0:
            self.timer.pause()
            self.bell()
            self.update_focus()
            self.finish_dialog()
        else:
            self.update_focus()
        self.tick_job = self.after(250, self.tick)

    def reset_timer(self):
        if self.active_item and messagebox.askyesno("Reset this session?", "Unsaved focus time will be discarded.", parent=self):
            self.timer.reset()
            self.active_item = None
            self.update_focus()

    def modal(self, title, width=420, height=460):
        win = tk.Toplevel(self)
        win.title(title)
        win.resizable(False, False)
        win.geometry(f"{width}x{height}+{self.winfo_rootx() + (self.winfo_width() - width)//2}+{self.winfo_rooty() + 60}")
        win.transient(self)
        win.grab_set()
        content = frame(win)
        content.pack(fill="both", expand=True, padx=12, pady=12)
        return win, content

    def topic_dialog(self, topic=None):
        win, content = self.modal("Edit topic" if topic else "Add a topic", height=460)
        label(content, "Edit topic" if topic else "A new learning goal", bold=True).pack(anchor="w")
        fields = {}
        defaults = dict(subject="", title="", exam_date=(date.today() + timedelta(days=7)).isoformat(), minutes="60", confidence="3")
        if topic:
            defaults.update(topic)
        for key, caption in [("subject", "Subject"), ("title", "Topic"), ("exam_date", "Exam date · YYYY-MM-DD"),
                             ("minutes", "Estimated study time · minutes"), ("confidence", "Confidence · 1 needs practice / 5 comfortable")]:
            label(content, caption).pack(anchor="w", pady=(10, 4))
            var = tk.StringVar(value=str(defaults[key]))
            fields[key] = var
            entry = ttk.Combobox(content, textvariable=var, values=("1", "2", "3", "4", "5"), state="readonly") if key == "confidence" else tk.Entry(content, textvariable=var)
            entry.pack(fill="x")
            if key == "subject":
                entry.focus_set()
        error = label(content, "", fg="red", wraplength=380, justify="left")
        error.pack(fill="x", pady=(12, 8))
        def save():
            try:
                self.repo.save_topic(**{key: var.get() for key, var in fields.items()}, topic_id=topic["id"] if topic else None)
            except (ValueError, sqlite3.Error) as exc:
                error.configure(text=str(exc))
                return
            win.destroy()
            self.refresh()
            self.status_var.set("Topic saved. Your study plan has been updated.")
        actions = frame(content)
        actions.pack(side="bottom", fill="x")
        tk.Button(actions, text="Cancel", command=win.destroy).pack(side="left")
        save_button = tk.Button(actions, text="Save topic", command=save)
        save_button.pack(side="right")
        win.bind("<Return>", lambda event: save())
        win.bind("<Escape>", lambda event: win.destroy())
        # Expose real controls for repeatable desktop integration checks.
        win.fields, win.save_button, win.error_label = fields, save_button, error
        return win

    def selected_topic(self):
        selected = self.topic_tree.selection()
        if not selected:
            self.status_var.set("Select a topic first.")
            return None
        return next((t for t in self.repo.topics() if t["id"] == int(selected[0])), None)

    def edit_selected(self):
        topic = self.selected_topic()
        if topic:
            return self.topic_dialog(topic)

    def toggle_completed(self):
        topic = self.selected_topic()
        if topic:
            if self.active_item and self.active_item.topic_id == topic["id"]:
                self.status_var.set("Finish or reset the active focus session before changing this topic.")
                return
            self.repo.set_completed(topic["id"], not topic["completed"])
            self.refresh()
            self.status_var.set("Topic reopened." if topic["completed"] else "Topic completed. It will stay out of your plan.")

    def delete_selected(self):
        topic = self.selected_topic()
        if not topic:
            return
        if self.active_item and self.active_item.topic_id == topic["id"]:
            self.status_var.set("Finish or reset the active focus session before deleting this topic.")
            return
        if messagebox.askyesno("Delete topic?", f"Delete “{topic['title']}”? Your saved session history will be kept.", parent=self):
            self.repo.delete_topic(topic["id"])
            self.refresh()
            self.status_var.set("Topic deleted. Session history has been kept.")

    def refresh_topics(self):
        if not hasattr(self, "topic_tree"):
            return
        selected = self.topic_tree.selection()
        query = self.search_var.get().casefold().strip()
        all_topics = self.repo.topics()
        topics = [t for t in all_topics if query in (t["subject"] + " " + t["title"]).casefold()]
        self.topic_tree.delete(*self.topic_tree.get_children())
        for topic in topics:
            left = max(0, (topic["minutes"] * 60 - topic["studied_seconds"] + 59) // 60)
            status = "Completed" if topic["completed"] else "Revision due" if topic["review_on"] and topic["review_on"] <= date.today().isoformat() else "In progress" if topic["studied_seconds"] else "Not started"
            self.topic_tree.insert("", "end", iid=str(topic["id"]), values=(topic["title"], topic["subject"],
                topic["exam_date"], f"{left} min", f"{topic['confidence']} / 5", status))
        if selected and self.topic_tree.exists(selected[0]):
            self.topic_tree.selection_set(selected[0])
        elif topics:
            self.topic_tree.selection_set(str(topics[0]["id"]))
        self.topic_count.configure(text=f"{len(topics)} of {len(all_topics)} topics")
        self.topic_empty.configure(text="" if topics else "No topics match your search." if all_topics else "Your first topic starts here. Choose Add topic to begin.")
        if topics:
            self.topic_empty.pack_forget()
        else:
            self.topic_empty.pack(fill="x", pady=12, after=self.topic_tree.master)
        for button in (self.edit_button, self.complete_button, self.delete_button):
            button.configure(state="normal" if topics else "disabled")

    def finish_dialog(self, close_after=False):
        if not self.active_item or self.timer.elapsed < 1:
            return
        self.timer.pause()
        self.update_focus()
        seconds = max(1, int(self.timer.elapsed))
        item = self.active_item
        win, content = self.modal("Save your focus session", height=330)
        label(content, "One session forward", bold=True).pack(anchor="w")
        label(content, item.title, bold=True, wraplength=380).pack(anchor="w", pady=(10, 4))
        label(content, f"{self.duration(seconds)} focused · {item.subject}").pack(anchor="w")
        label(content, "How well do you understand it now?").pack(anchor="w", pady=(12, 5))
        rating = tk.StringVar(value="3")
        ttk.Combobox(content, textvariable=rating, values=("1", "2", "3", "4", "5"), state="readonly").pack(fill="x")
        label(content, "1 = needs practice · 5 = comfortable").pack(anchor="w", pady=8)
        done = tk.BooleanVar(value=False)
        tk.Checkbutton(content, text="Mark this topic complete", variable=done).pack(anchor="w", pady=8)
        error = label(content, "", fg="red", wraplength=380)
        error.pack(fill="x")
        def save():
            try:
                self.repo.log_session(item.topic_id, seconds, int(rating.get()), done.get())
            except (ValueError, sqlite3.Error) as exc:
                error.configure(text=str(exc))
                return
            self.timer.reset()
            self.active_item = None
            win.destroy()
            self.refresh()
            self.status_var.set("Session saved. Your confidence and next revision date have been updated.")
            if close_after:
                self.close_app()
        actions = frame(content)
        actions.pack(side="bottom", fill="x")
        tk.Button(actions, text="Back to session", command=win.destroy).pack(side="left")
        save_button = tk.Button(actions, text="Save session", command=save)
        save_button.pack(side="right")
        win.rating, win.done, win.save_button = rating, done, save_button
        return win

    def refresh_progress(self):
        sessions = self.repo.sessions()
        self.progress_summary.configure(text=f"{self.duration(sum(s['seconds'] for s in sessions))} focused across {len(sessions)} saved sessions")
        self.history_tree.delete(*self.history_tree.get_children())
        for session in sessions:
            when = session["completed_at"][:16].replace("T", "  ")
            self.history_tree.insert("", "end", values=(session["topic_title"], session["subject"], when,
                self.duration(session["seconds"]), f"{session['confidence']} / 5"))
        self.history_empty.configure(text="" if sessions else "Finish a focus session to see your progress here.")
        if sessions:
            self.history_empty.pack_forget()
        else:
            self.history_empty.pack(fill="x", pady=12, after=self.history_tree.master)
        self.draw_chart()

    def draw_chart(self):
        if not hasattr(self, "chart"):
            return
        chart = self.chart
        chart.delete("all")
        width = max(400, chart.winfo_width())
        days = [date.today() - timedelta(days=ago) for ago in range(6, -1, -1)]
        totals = {day.isoformat(): 0 for day in days}
        for session in self.repo.sessions():
            key = session["completed_at"][:10]
            if key in totals:
                totals[key] += session["seconds"] / 60
        maximum = max(30, ((max(totals.values()) // 15) + 1) * 15)
        left, right, top, baseline = 46, width - 22, 22, 145
        for i in range(4):
            value = maximum * i / 3
            y = baseline - (baseline - top) * i / 3
            chart.create_line(left, y, right, y, fill="gray75")
            chart.create_text(left - 10, y, text=f"{value:g}", anchor="e", fill="black", font="TkDefaultFont")
        chart.create_text(left - 10, 8, text="min", anchor="e", fill="black", font="TkDefaultFont")
        slot = (right - left) / 7
        for index, day in enumerate(days):
            value = totals[day.isoformat()]
            x = left + slot * (index + 0.5)
            if value:
                height = (baseline - top) * value / maximum
                chart.create_rectangle(x - min(21, slot/3), baseline - height, x + min(21, slot/3), baseline,
                                       fill="black", outline="")
                chart.create_text(x, baseline - height - 9, text=f"{value:.1f}".removesuffix(".0"),
                                  font="TkDefaultFont", fill="black")
            chart.create_text(x, 167, text="Today" if day == date.today() else day.strftime("%a %d"),
                              fill="black", font="TkDefaultFont")

    def export_csv(self):
        path = filedialog.asksaveasfilename(parent=self, title="Export session history", defaultextension=".csv",
                                          filetypes=[("CSV spreadsheet", "*.csv")], initialfile="studypilot-sessions.csv")
        if path:
            try:
                self.repo.export_csv(path)
                self.status_var.set(f"Session history exported to {Path(path).name}.")
            except (OSError, sqlite3.Error) as error:
                messagebox.showerror("Export failed", str(error), parent=self)

    def backup(self):
        path = filedialog.asksaveasfilename(parent=self, title="Back up your data", defaultextension=".sqlite3",
                                          filetypes=[("SQLite database", "*.sqlite3")], initialfile="studypilot-backup.sqlite3")
        if path:
            try:
                self.repo.backup(path)
                self.status_var.set(f"Backup saved to {Path(path).name}.")
            except (OSError, sqlite3.Error, ValueError) as error:
                messagebox.showerror("Backup failed", str(error), parent=self)

    def report_callback_exception(self, exc_type, exc_value, traceback):
        logging.error("Application callback failed", exc_info=(exc_type, exc_value, traceback))
        messagebox.showerror("Something went wrong", str(exc_value), parent=self)

    def close_app(self):
        if self.active_item and self.timer.elapsed >= 1:
            choice = messagebox.askyesnocancel("Save your session before closing?",
                "Choose Yes to rate and save, No to discard, or Cancel to keep studying.", parent=self)
            if choice is None:
                return
            if choice:
                self.finish_dialog(close_after=True)
                return
        if self.tick_job:
            self.after_cancel(self.tick_job)
        self.repo.close()
        self.destroy()


def main():
    parser = argparse.ArgumentParser(description="StudyPilot offline Tkinter study planner")
    parser.add_argument("--demo", action="store_true", help="Use a separate database with clearly labelled sample data")
    parser.add_argument("--db", type=Path, help="Optional custom SQLite database path")
    args = parser.parse_args()
    path = args.db or ROOT / "data" / ("demo.sqlite3" if args.demo else "studypilot.sqlite3")
    try:
        repo = Repository(path)
        if args.demo:
            seed_demo(repo)
        app = StudyPilot(repo, args.demo)
        app.mainloop()
    except (sqlite3.Error, OSError, tk.TclError) as error:
        print(f"Could not start StudyPilot: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
