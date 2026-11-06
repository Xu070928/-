import sys
import traceback
from pathlib import Path

def launch():
    from safety_monitor.app import main
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

if __name__ == "__main__":
    try:
        launch()
    except Exception:
        detail=traceback.format_exc()
        Path("startup-error.txt").write_text(detail,encoding="utf-8")
        if "--smoke-test" not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,detail,"启动失败",0x10)
        sys.exit(1)
