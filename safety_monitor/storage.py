import hashlib
import hmac
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "monitor.sqlite3"
        with self.connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS users(
              name TEXT PRIMARY KEY, salt TEXT NOT NULL, digest TEXT NOT NULL,
              role TEXT NOT NULL CHECK(role IN ('admin','operator')));
            CREATE TABLE IF NOT EXISTS cameras(
              id INTEGER PRIMARY KEY, name TEXT NOT NULL, location TEXT NOT NULL,
              source TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(
              id TEXT PRIMARY KEY, time TEXT NOT NULL, camera TEXT NOT NULL,
              location TEXT NOT NULL, person TEXT NOT NULL, state TEXT NOT NULL,
              reason TEXT NOT NULL, origin TEXT NOT NULL, actor TEXT NOT NULL,
              screenshot TEXT NOT NULL DEFAULT '', clip TEXT NOT NULL DEFAULT '',
              media_status TEXT NOT NULL DEFAULT '录制中',
              review TEXT NOT NULL DEFAULT '待复核');
            CREATE TABLE IF NOT EXISTS reviews(
              id INTEGER PRIMARY KEY, event_id TEXT NOT NULL, time TEXT NOT NULL,
              actor TEXT NOT NULL, verdict TEXT NOT NULL, note TEXT NOT NULL,
              FOREIGN KEY(event_id) REFERENCES events(id));
            """)
        self.sessions = {}

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.db, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def initialized(self):
        with self.connect() as c:
            return bool(c.execute("SELECT 1 FROM users LIMIT 1").fetchone())

    def require(self, token, admin=False):
        name = self.sessions.get(token)
        with self.connect() as c:
            row = c.execute("SELECT name,role FROM users WHERE name=?", (name,)).fetchone()
        if not row or (admin and row["role"] != "admin"):
            raise PermissionError("没有此操作权限")
        return dict(row)

    def add_user(self, name, password, role, token=None):
        if not name.strip() or len(password) < 10 or role not in ("admin", "operator"):
            raise ValueError("用户名不能为空，密码至少10位，角色必须有效")
        if self.initialized():
            self.require(token, admin=True)
        elif role != "admin":
            raise PermissionError("首次必须创建管理员")
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()
        with self.connect() as c:
            c.execute("INSERT INTO users VALUES(?,?,?,?)", (name.strip(), salt, digest, role))

    def login(self, name, password):
        with self.connect() as c:
            row = c.execute("SELECT * FROM users WHERE name=?", (name,)).fetchone()
        salt = row["salt"] if row else "00" * 16
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()
        if not row or not hmac.compare_digest(candidate, row["digest"]):
            raise PermissionError("用户名或密码错误")
        token = secrets.token_urlsafe(32)
        self.sessions[token] = name
        return token

    def logout(self, token):
        self.sessions.pop(token, None)

    def add_camera(self, token, name, location, source):
        self.require(token, admin=True)
        if not all(x.strip() for x in (name, location, source)):
            raise ValueError("名称、位置、视频源均不能为空")
        with self.connect() as c:
            return c.execute("INSERT INTO cameras(name,location,source) VALUES(?,?,?)",
                             (name, location, source)).lastrowid

    def cameras(self, token):
        self.require(token)
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM cameras ORDER BY id")]

    def add_event(self, token, camera, person, decision, origin="人工登记"):
        actor = self.require(token)["name"]
        eid = secrets.token_hex(12)
        with self.connect() as c:
            c.execute("""INSERT INTO events(id,time,camera,location,person,state,reason,origin,actor)
                         VALUES(?,?,?,?,?,?,?,?,?)""",
                      (eid, now(), camera["name"], camera["location"], person,
                       decision.state, decision.reason, origin, actor))
        return eid

    def media(self, eid, screenshot, clip, status):
        with self.connect() as c:
            c.execute("UPDATE events SET screenshot=?,clip=?,media_status=? WHERE id=?",
                      (screenshot, clip, status, eid))

    def events(self, token, text="", state="", verdict="", start="", end=""):
        self.require(token)
        sql = "SELECT * FROM events WHERE 1=1"
        args = []
        for column, value in (("state", state), ("review", verdict)):
            if value:
                sql += f" AND {column}=?"
                args.append(value)
        if text:
            sql += " AND (camera LIKE ? OR location LIKE ? OR person LIKE ?)"
            args.extend(["%" + text + "%"] * 3)
        for op, value in ((">=", start), ("<=", end)):
            if value:
                sql += f" AND time {op} ?"
                args.append(value)
        with self.connect() as c:
            return [dict(r) for r in c.execute(sql + " ORDER BY time DESC, id", args)]

    def review(self, token, eid, verdict, note):
        actor = self.require(token)["name"]
        if verdict not in ("确认违规", "确认正常", "仍无法判断"):
            raise ValueError("无效复核结论")
        with self.connect() as c:
            c.execute("INSERT INTO reviews(event_id,time,actor,verdict,note) VALUES(?,?,?,?,?)",
                      (eid, now(), actor, verdict, note))
            c.execute("UPDATE events SET review=? WHERE id=?", (verdict, eid))

    def export(self, token, path, **filters):
        self.require(token, admin=True)
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "事件台账"
        keys = ["id","time","camera","location","person","state","reason","origin","actor",
                "review","media_status","screenshot","clip"]
        ws.append(keys)
        rows = self.events(token, **filters)
        def append_text(sheet, values):
            sheet.append([str(x) for x in values])
            # Explicit string type prevents spreadsheet formula injection.
            for cell in sheet[sheet.max_row]:
                cell.data_type = "s"
        for row in rows:
            append_text(ws, [row[k] for k in keys])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        audit = wb.create_sheet("复核轨迹")
        audit.append(["event_id","time","actor","verdict","note"])
        ids = {r["id"] for r in rows}
        with self.connect() as c:
            for r in c.execute("SELECT * FROM reviews ORDER BY id"):
                if r["event_id"] in ids:
                    append_text(audit, [r[k] for k in ("event_id","time","actor","verdict","note")])
        wb.save(path)
