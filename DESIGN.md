# Default Tkinter appearance

The user explicitly requested traditional, default Tkinter styling. This preference takes
precedence over custom visual directions in the supplied design skill.

- Use the system-default Tk/ttk theme; do not call theme_use or configure custom widget styles.
- Leave the default fonts, scaling, backgrounds and selection colours intact.
- Use standard Notebook tabs for Today, Topics and Progress.
- Group related controls using ordinary LabelFrames.
- Use default Tk buttons, entries and spinboxes, with native ttk tables and scrollbars.
- Use TkHeadingFont for ordinary bold headings and TkFixedFont for the timer readout.
- Draw the actual study-time chart in monochrome using TkDefaultFont for its annotations.
- Keep the focus indicator as a standard ttk Progressbar.

No custom palette, sidebar, logo, branded buttons, downloaded fonts or custom theme remains.
The window defaults to 1080x720, with a supported minimum of 900x650. Tables have both horizontal
and vertical scrollbars. The backend and saved databases are unchanged by this appearance update.

The full Tk widget workflow passed after the change: topic validation, adding, searching, editing,
planning, timer pause/resume and completion, ratings, complete/reopen, history, CSV, backup,
deletion while preserving history, and reopening the same database. Essential controls were
checked at the minimum size. Native screenshots and the demo recording show this default interface.
