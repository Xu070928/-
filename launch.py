import sys
from safety_monitor.app import main

if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        import tempfile
        import tkinter as tk
        from safety_monitor.app import App
        with tempfile.TemporaryDirectory() as directory:
            root=tk.Tk()
            app=App(root,directory)
            root.after(1500,app.close)
            root.mainloop()
    else:
        main()
