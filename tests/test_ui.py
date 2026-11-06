import os
import tempfile
import unittest
import tkinter as tk
from safety_monitor.app import App

@unittest.skipUnless(os.name=="nt","Windows GUI smoke test")
class UITests(unittest.TestCase):
    def test_login_dashboard(self):
        with tempfile.TemporaryDirectory() as directory:
            root=tk.Tk()
            root.withdraw()
            try:
                app=App(root,directory)
                app.store.add_user("admin","test-password","admin")
                app.token=app.store.login("admin","test-password")
                app.dashboard()
                root.update()
                self.assertEqual(app.table.get_children(),())
                self.assertEqual(app.user["role"],"admin")
            finally: root.destroy()
