import os
import queue
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, simpledialog, filedialog

from PIL import Image, ImageTk
from . import __version__
from .storage import Store
from .rules import Evidence, decide, VIOLATIONS
from .video import VideoWorker

class App:
    def __init__(self, root, data_dir=None):
        self.root = root
        self.root.title("高空作业安全监控 · " + __version__)
        self.root.geometry("1200x800")
        self.store = Store(data_dir or Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "HeightSafety")
        self.token = None
        self.workers, self.views = {}, {}
        self.pre, self.post = 10,20
        self.root.report_callback_exception = self.error
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.login_page()

    def error(self, kind, value, traceback):
        messagebox.showerror("操作失败", str(value), parent=self.root)

    def clear(self):
        for child in self.root.winfo_children():
            child.destroy()

    def login_page(self):
        self.clear()
        box = ttk.Frame(self.root, padding=50)
        box.pack(expand=True)
        first = not self.store.initialized()
        ttk.Label(box,text="创建首位管理员" if first else "高空作业安全监控 · 登录",font=("",20)).pack(pady=15)
        ttk.Label(box,text="离线工作流原型 · 自动违规识别尚未验证").pack(pady=10)
        name, password = tk.StringVar(), tk.StringVar()
        for label,var,secret in (("账号",name,False),("密码（至少10位）",password,True)):
            ttk.Label(box,text=label).pack(anchor="w")
            ttk.Entry(box,textvariable=var,show="*" if secret else "",width=32).pack(pady=8)
        def submit():
            if first:
                self.store.add_user(name.get(),password.get(),"admin")
            self.token = self.store.login(name.get().strip(),password.get())
            self.dashboard()
        ttk.Button(box,text="创建并登录" if first else "登录",command=submit).pack(pady=15)

    def dashboard(self):
        self.clear()
        self.user = self.store.require(self.token)
        top = ttk.Frame(self.root,padding=10)
        top.pack(fill="x")
        ttk.Label(top,text="高空作业安全监控",font=("",19,"bold")).pack(side="left")
        ttk.Label(top,text=f"  {self.user['name']} / {self.user['role']}  ").pack(side="right")
        ttk.Button(top,text="退出登录",command=self.logout).pack(side="right")
        ttk.Label(self.root,text="当前为工作流验证版：视频可预览，事件由人工登记；尚不支持自动识别违规。",
                  foreground="#b45309",padding=8).pack(fill="x")
        book = ttk.Notebook(self.root)
        book.pack(fill="both",expand=True,padx=10,pady=10)
        self.live = ttk.Frame(book,padding=10)
        self.history = ttk.Frame(book,padding=10)
        book.add(self.live,text="实时画面")
        book.add(self.history,text="事件与人工复核")
        if self.user["role"] == "admin":
            settings = ttk.Frame(book,padding=20)
            book.add(settings,text="管理")
            self.settings_page(settings)
        tools = ttk.Frame(self.live)
        tools.pack(fill="x")
        ttk.Button(tools,text="刷新摄像头",command=self.reload_cameras).pack(side="left")
        self.camera_choice = ttk.Combobox(tools,state="readonly",width=45)
        self.camera_choice.pack(side="left",padx=8)
        ttk.Button(tools,text="打开视频",command=self.open_video).pack(side="left")
        ttk.Button(tools,text="停止所选视频",command=self.stop_video).pack(side="left")
        self.panels = ttk.Frame(self.live)
        self.panels.pack(fill="both",expand=True)
        self.reload_cameras()
        self.history_page()
        self.root.after(100,self.refresh_video)

    def reload_cameras(self):
        self.cameras = self.store.cameras(self.token)
        self.camera_choice["values"] = [f"{c['id']} · {c['name']} / {c['location']}" for c in self.cameras]
        if self.cameras:
            self.camera_choice.current(0)

    def selected_camera(self):
        idx=self.camera_choice.current()
        if idx < 0:
            raise ValueError("请管理员先添加摄像头或本地视频")
        return self.cameras[idx]

    def open_video(self):
        camera = self.selected_camera()
        key = camera["id"]
        if key in self.workers:
            raise ValueError("该视频已打开；断流后请先停止再打开")
        if len(self.workers) >= 4:
            raise ValueError("首版最多同时预览4路，更多路数需性能验证")
        worker = VideoWorker(camera,self.store,self.pre,self.post)
        self.workers[key] = worker
        panel = ttk.LabelFrame(self.panels,text=camera["name"]+" · "+camera["location"],padding=5)
        panel.pack(side="left",fill="both",expand=True)
        image = ttk.Label(panel)
        image.pack(fill="both",expand=True)
        status = ttk.Label(panel,wraplength=280)
        status.pack()
        ttk.Button(panel,text="框选人员并人工登记事件",command=lambda:self.event_dialog(key)).pack(pady=8)
        self.views[key] = (panel,image,status)
        worker.start()

    def stop_video(self):
        key=self.selected_camera()["id"]
        worker=self.workers.get(key)
        if worker:
            worker.stop()
            # Do not drop worker while it may still be finalizing evidence.
            self.views[key][2].configure(text="正在停止并保存片段")
            def finish():
                if worker.is_alive():
                    self.root.after(100,finish)
                elif key in self.workers:
                    self.workers.pop(key)
                    self.views.pop(key)[0].destroy()
            finish()

    def refresh_video(self):
        if not self.token:
            return
        for key,worker in list(self.workers.items()):
            frame=worker.snapshot()
            panel,label,status=self.views[key]
            if frame is not None:
                image=Image.fromarray(frame[:,:,::-1])
                image.thumbnail((max(240,1100//max(1,len(self.workers))),420))
                photo=ImageTk.PhotoImage(image)
                label.configure(image=photo)
                label.image=photo
            status.configure(text=f"{worker.status}\n采集平均 {worker.fps:.1f} FPS；推理 FPS：未启用")
        self.root.after(33,self.refresh_video)

    def event_dialog(self,key):
        worker=self.workers[key]
        frame=worker.snapshot()
        if frame is None or not worker.is_alive():
            raise ValueError("当前无有效实时画面")
        win=tk.Toplevel(self.root)
        win.title("人工证据登记（不是模型自动结论）")
        win.transient(self.root)
        win.grab_set()
        image=Image.fromarray(frame[:,:,::-1])
        image.thumbnail((760,400))
        photo=ImageTk.PhotoImage(image)
        canvas=tk.Canvas(win,width=image.width,height=image.height)
        canvas.pack()
        canvas.create_image(0,0,anchor="nw",image=photo)
        canvas.image=photo
        roi, start = [], []
        rectangle=[None]
        def down(e):
            start[:]=[max(0,min(image.width,e.x)),max(0,min(image.height,e.y))]
        def up(e):
            if not start:return
            x,y=max(0,min(image.width,e.x)),max(0,min(image.height,e.y))
            x1,x2=sorted([start[0],x]);y1,y2=sorted([start[1],y])
            if x2-x1<5 or y2-y1<5:return
            roi[:]=[x1/image.width,y1/image.height,x2/image.width,y2/image.height]
            if rectangle[0]:canvas.delete(rectangle[0])
            rectangle[0]=canvas.create_rectangle(x1,y1,x2,y2,outline="red",width=3)
        canvas.bind("<ButtonPress-1>",down)
        canvas.bind("<ButtonRelease-1>",up)
        ttk.Label(win,text="请拖框定位人员。首版人员编号为人工输入，不具备自动跟踪。").pack()
        person=tk.StringVar()
        ttk.Entry(win,textvariable=person).pack()
        fields={}
        for name,label in [("workwear","穿高空工作服"),("at_height","确认处于高处"),("wearing","佩戴安全带"),
                           ("hooked","挂钩已挂"),("below_workplane","挂点低于工作面")]:
            row=ttk.Frame(win);row.pack(fill="x",padx=15,pady=2)
            ttk.Label(row,text=label,width=22).pack(side="left")
            var=tk.StringVar(value="未知")
            ttk.Combobox(row,textvariable=var,values=["未知","是","否"],state="readonly",width=12).pack(side="left")
            fields[name]=var
        ttk.Label(win,text="锚点可靠性标准待确认，本版保持未知；已确认未挂仍立即报警。").pack(padx=10,pady=8)
        def submit():
            if not person.get().strip() or not roi:
                raise ValueError("请输入人员编号并框选人员")
            mapping={"是":True,"否":False,"未知":None}
            decision=decide(Evidence(**{k:mapping[v.get()] for k,v in fields.items()}))
            eid=self.store.add_event(self.token,worker.camera,person.get().strip(),decision)
            try:
                worker.record(eid,person.get().strip(),decision.state,list(roi))
            except queue.Full:
                self.store.media(eid,"","","录制队列已满")
                raise ValueError("事件已记录但录像队列已满")
            if decision.state in VIOLATIONS:
                self.root.bell()
                try:
                    import winsound
                    winsound.PlaySound("SystemExclamation",winsound.SND_ALIAS|winsound.SND_ASYNC)
                except ImportError:pass
            win.destroy()
            self.load_events()
            messagebox.showinfo("事件已登记",decision.state+"："+decision.reason)
        ttk.Button(win,text="按证据判定并保存",command=submit).pack(pady=10)

    def settings_page(self, parent):
        ttk.Label(parent,text="摄像头 / 本地视频",font=("",16)).pack(anchor="w")
        fields={}
        for k,label in [("name","名称"),("location","安装位置"),("source","RTSP地址 / USB编号（如0）/ 本地视频完整路径")]:
            ttk.Label(parent,text=label).pack(anchor="w",pady=(8,0))
            fields[k]=tk.StringVar()
            ttk.Entry(parent,textvariable=fields[k],width=80,show="*" if k=="source" else "").pack(anchor="w")
        def browse():
            path=filedialog.askopenfilename(filetypes=[("视频","*.mp4 *.avi *.mkv"),("全部","*.*")])
            if path:fields["source"].set(path)
        ttk.Button(parent,text="选择本地视频",command=browse).pack(anchor="w",pady=5)
        def add_camera():
            self.store.add_camera(self.token,**{k:v.get() for k,v in fields.items()})
            self.reload_cameras()
            messagebox.showinfo("完成","视频源已保存")
        ttk.Button(parent,text="添加视频源",command=add_camera).pack(anchor="w",pady=8)
        ttk.Label(parent,text="片段默认前10秒、后20秒；不足部分标记，不伪造历史帧。").pack(anchor="w",pady=8)
        def timing():
            pre=simpledialog.askinteger("录像设置","报警前秒数（0～30）",initialvalue=self.pre,minvalue=0,maxvalue=30)
            if pre is None:return
            post=simpledialog.askinteger("录像设置","报警后秒数（1～60）",initialvalue=self.post,minvalue=1,maxvalue=60)
            if post is not None:
                self.pre,self.post=pre,post
                messagebox.showinfo("完成","对之后打开的视频生效；当前运行视频参数不变")
        ttk.Button(parent,text="调整本次会话录像时长",command=timing).pack(anchor="w")
        def add_user():
            name=simpledialog.askstring("账号","新用户名")
            if not name:return
            password=simpledialog.askstring("账号","密码（至少10位）",show="*")
            if password is None:return
            admin=messagebox.askyesno("角色","设为管理员？选择否创建值班员。")
            self.store.add_user(name,password,"admin" if admin else "operator",self.token)
            messagebox.showinfo("完成","账号已创建")
        ttk.Button(parent,text="创建账号",command=add_user).pack(anchor="w",pady=15)
        ttk.Label(parent,text="运行数据目录："+str(self.store.root),wraplength=850).pack(anchor="w")

    def history_page(self):
        row=ttk.Frame(self.history);row.pack(fill="x")
        self.query=tk.StringVar()
        ttk.Label(row,text="摄像头/位置/人员").pack(side="left")
        ttk.Entry(row,textvariable=self.query,width=20).pack(side="left")
        self.state=tk.StringVar();self.verdict=tk.StringVar()
        for var,values in [(self.state,["","未佩戴","佩戴不规范","人工复核","规范佩戴","忽略"]),
                           (self.verdict,["","待复核","确认违规","确认正常","仍无法判断"])]:
            ttk.Combobox(row,textvariable=var,values=values,width=12,state="readonly").pack(side="left",padx=4)
        ttk.Button(row,text="查询/刷新",command=self.load_events).pack(side="left")
        dates=ttk.Frame(self.history);dates.pack(fill="x",pady=6)
        self.start,self.end=tk.StringVar(),tk.StringVar()
        ttk.Label(dates,text="UTC 起止日期 YYYY-MM-DD（可空）").pack(side="left")
        ttk.Entry(dates,textvariable=self.start,width=14).pack(side="left")
        ttk.Entry(dates,textvariable=self.end,width=14).pack(side="left")
        cols=("time","camera","person","state","origin","review","media_status")
        self.table=ttk.Treeview(self.history,columns=cols,show="headings",selectmode="browse")
        for k,title in zip(cols,["时间(UTC)","摄像头","人员","判定","来源","复核结果","留证状态"]):
            self.table.heading(k,text=title);self.table.column(k,width=140)
        self.table.pack(fill="both",expand=True)
        self.table.tag_configure("violation",foreground="#c62828")
        self.table.tag_configure("review",foreground="#b45309")
        buttons=ttk.Frame(self.history);buttons.pack(fill="x",pady=10)
        ttk.Button(buttons,text="复核选中事件",command=self.review_event).pack(side="left")
        ttk.Button(buttons,text="查看截图",command=lambda:self.open_media("screenshot")).pack(side="left")
        ttk.Button(buttons,text="播放片段",command=lambda:self.open_media("clip")).pack(side="left")
        if self.user["role"]=="admin":
            ttk.Button(buttons,text="导出筛选结果 Excel",command=self.export).pack(side="right")
        self.load_events()

    def filters(self):
        from datetime import date
        for value in (self.start.get(),self.end.get()):
            if value:date.fromisoformat(value)
        return dict(text=self.query.get(),state=self.state.get(),verdict=self.verdict.get(),
                    start=self.start.get(),end=self.end.get()+"T23:59:59+00:00" if self.end.get() else "")

    def load_events(self):
        rows=self.store.events(self.token,**self.filters())
        self.rows={r["id"]:r for r in rows}
        self.table.delete(*self.table.get_children())
        for r in rows:
            tag="violation" if r["state"] in VIOLATIONS else "review"
            self.table.insert("", "end",iid=r["id"],values=[r[k] for k in self.table["columns"]],tags=(tag,))

    def selected_event(self):
        ids=self.table.selection()
        if not ids:raise ValueError("请先选中事件")
        return self.rows[ids[0]]

    def review_event(self):
        event=self.selected_event()
        win=tk.Toplevel(self.root);win.title("人工复核");win.transient(self.root);win.grab_set()
        ttk.Label(win,text=f"{event['camera']} / {event['person']}\n原判定：{event['state']}\n{event['reason']}",padding=15).pack()
        verdict=tk.StringVar(value="仍无法判断")
        ttk.Combobox(win,textvariable=verdict,values=["确认违规","确认正常","仍无法判断"],state="readonly").pack()
        note=ttk.Entry(win,width=60);note.pack(padx=10,pady=10)
        def submit():
            self.store.review(self.token,event["id"],verdict.get(),note.get())
            win.destroy();self.load_events()
        ttk.Button(win,text="保存复核结论（保留历史）",command=submit).pack(pady=10)

    def open_media(self,key):
        event=self.selected_event()
        path=Path(event[key]) if event[key] else None
        if not path or not path.is_file():raise ValueError("文件尚未保存或不可用，请刷新留证状态")
        if os.name=="nt":os.startfile(str(path))
        else:
            import webbrowser
            webbrowser.open(path.as_uri())

    def export(self):
        path=filedialog.asksaveasfilename(defaultextension=".xlsx",filetypes=[("Excel","*.xlsx")])
        if path:
            self.store.export(self.token,path,**self.filters())
            messagebox.showinfo("完成","已导出事件与复核轨迹")

    def shutdown_workers(self, done):
        for w in self.workers.values():w.stop()
        def poll():
            if any(w.is_alive() for w in self.workers.values()):
                self.root.after(100,poll)
            else:
                self.workers.clear();self.views.clear();done()
        poll()

    def logout(self):
        token=self.token
        def done():
            self.store.logout(token);self.token=None;self.login_page()
        self.shutdown_workers(done)

    def close(self):
        self.shutdown_workers(self.root.destroy)

def main():
    root=tk.Tk()
    ttk.Style(root).theme_use("clam")
    App(root)
    root.mainloop()
