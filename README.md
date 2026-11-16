# StudyPilot

A small, complete desktop study planner built with **Python, Tkinter/ttk and SQLite**.
Uses the default Tkinter appearance: standard tabs, label frames, buttons, inputs and system fonts.
Works offline. No account, server, API key, pip package, or paid service is needed.

## Download the Windows executable

[Download StudyPilot.exe](https://github.com/nagasaipradhyumnapoola/app_tkinter/releases/latest/download/StudyPilot.exe)

Save it as `D:\app\StudyPilot.exe`, then double-click it. No Python installation is needed
for the EXE. Windows 10/11, 64-bit is supported. Personal data is kept beside the executable
in `data/studypilot.sqlite3`.

If there is no release yet, check [Windows build progress](https://github.com/nagasaipradhyumnapoola/app_tkinter/actions/workflows/windows.yml).
The workflow runs tests, builds on Windows and publishes an EXE and ZIP in Releases.

A local Codex chat with access to your PC can download the executable directly into `D:\app`.
A cloud chat cannot write to your local drives.

## Run from source

Install Python 3.10 or newer with Tkinter support. Open a terminal in this folder:

```sh
python app.py
```

Use `python3` if that is your Python command. On Ubuntu/Debian, install the GUI library
with `sudo apt install python3-tk` if it is missing. The standard Python installers
for Windows and macOS usually include it. Check with `python -m tkinter`.

To explore a separate workspace with labelled sample data:

```sh
python app.py --demo
```

## Full workflow

1. In **Topics**, add a subject, topic, exam date, estimated total study time and confidence (1–5).
2. In **Today**, enter the study minutes you still have available and choose **Build plan**.
3. Select a focus block and choose **Start focus**. Pause and resume as needed.
4. Choose **Finish & rate**, or let the timer end. Rate your understanding and save the session.
5. In **Progress**, inspect actual focus time and session history, export CSV, or back up the database.
6. Close and reopen the app. Your topics, history and available-time setting are retained.

Use **Complete / reopen** to exclude or return a topic to the plan. Deleting a topic keeps
its past sessions. Editing a topic keeps its session history, even if the title changes.
Ctrl+N adds a topic. Double-click a topic to edit it.
The application uses Tkinter's platform-default theme and colours; its exact appearance follows your operating system.

## How planning works

Each active topic receives this priority score:

```text
40 / (max(days until exam, 0) + 1) + (6 - confidence) * 5 + 20 if revision is due
```

Topics are sorted by score, then allocated study blocks of at most 25 minutes in rounds.
The total never exceeds the available time or a topic's remaining estimate. Breaks are separate.
Your available-time setting is a remaining-time budget; the app does not subtract today's sessions
from it automatically. Update it before rebuilding when your availability changes.

After a saved session, the next revision is scheduled in 1, 2, 4, 7 or 14 days for
confidence ratings 1 through 5. A fully studied topic returns for a 15-minute review
when that date arrives. A topic explicitly marked complete stays out of the plan.
These are transparent learning rules, not machine learning or a validated memory model.

## Files and data

- `app.py`: native interface and interaction flow.
- `backend.py`: SQLite storage, validation, planning and monotonic timer.
- `tests/`: automated backend and desktop workflow tests.
- `data/studypilot.sqlite3`: personal database, created on first normal launch.
- `data/demo.sqlite3`: separate demo database, created only with `--demo`.

When running from source, both database paths are relative to this project's folder.
When running the EXE, they are relative to the executable's folder. Keep it somewhere writable.
For a custom location: `python app.py --db /path/to/my-studies.sqlite3`.
To restore a backup, close the app and launch it with `--db /path/to/backup.sqlite3`.
CSV stores durations in seconds. The UI shows actual minutes and seconds.

The demo uses five sample topics: SQL joins, Classes & objects, Trees & traversal,
Probability, and Files & exceptions, with six historical sample sessions.
Personal workspaces start empty. Previews show the demo workspace.

## Verify

```sh
python -m unittest discover -s tests -v
```

The desktop workflow test requires a display and can be run separately:

```sh
python tests/gui_workflow.py
```

## Mini-project scope

This app implements the stated Python Tkinter requirement, a graphical interface and functional
Python logic with persistent storage. Its source is original; the linked habit tracker and timer
repositories were studied as references. Check the instructor's team-size and submission rules separately.
