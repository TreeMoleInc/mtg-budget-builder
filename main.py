# main.py — Entry point for MTG Budget Builder
# Run with: .venv/Scripts/python main.py

import sys
if sys.platform == "win32":
    # Tell Windows this is a standalone app, not just another python.exe —
    # this makes the taskbar use the window's icon instead of Python's.
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("mtg.budgetbuilder.1")

from ui.app import BudgetBuilderApp

if __name__ == "__main__":
    app = BudgetBuilderApp()
    app.mainloop()
